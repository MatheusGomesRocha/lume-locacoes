"""API do assistente de ajuda do Lume Locações.

Rodar:  uvicorn app.main:app --port 8001 --reload
Docs interativas (grátis no FastAPI): http://127.0.0.1:8001/docs
"""
import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated, Any

from app import ferramentas
from app.conversa import resposta_de_conversa
from app.cache import cache_do_ambiente, chave_da_conversa, versao_do_conteudo
from app.busca import BaseConhecimento, Contexto, Resultado, pede_dados_do_sistema
from app.semantica import NOTA_LEXICAL_CONFIANTE, criar_indice_do_ambiente, vencedor_confiavel
from app.limite import LimitadorDeRequisicoes
from app.llm import AJUDA, INSTRUCOES, INSTRUCOES_AGENTE, LimitadorDiario, criar_provedor_do_ambiente, decidir_acao, gerar_resposta, limite_diario_do_ambiente, redigir_com_dados

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"

# Abaixo disso, a melhor resposta é considerada "parecida demais com nada".
LIMITE_CONFIANCA = float(os.getenv("IA_LIMITE_CONFIANCA", "0.30"))

ORIGENS_PADRAO = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"


def origens_permitidas() -> list[str]:
    """Sites que podem chamar a API pelo navegador (CORS). Em produção: IA_ORIGENS_PERMITIDAS."""
    bruto = os.getenv("IA_ORIGENS_PERMITIDAS", ORIGENS_PADRAO)
    return [o.strip().rstrip("/") for o in bruto.split(",") if o.strip()]


app = FastAPI(title="Lume Locações - Assistente", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens_permitidas(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Token"],
    max_age=600,
)

base = BaseConhecimento(PASTA_DADOS / "faq.json")
limitador = LimitadorDeRequisicoes(maximo=int(os.getenv("IA_LIMITE_POR_MINUTO", "30")))
_trava_log = threading.Lock()

# LLM opcional (GEMINI_API_KEY). Sem a chave, tudo continua funcionando só com o FAQ.
provedor_llm = criar_provedor_do_ambiente()
limitador_llm = LimitadorDiario(limite_diario_do_ambiente())
# Busca semântica (embeddings), só quando o TF-IDF não tem certeza. Sem chave, fica desligada.
indice_semantico = criar_indice_do_ambiente(base.itens, permitir=limitador_llm.permitir)
if indice_semantico is not None:
    indice_semantico.construir_em_segundo_plano()
# Cache das respostas do modelo (ver app/cache.py). IA_CACHE_TTL=0 desliga.
cache = cache_do_ambiente()
# Muda quando o FAQ, as instruções ou as ferramentas mudam: respostas antigas deixam de valer.
VERSAO_DO_CONTEUDO = versao_do_conteudo((PASTA_DADOS / "faq.json").read_text(encoding="utf-8"), INSTRUCOES, INSTRUCOES_AGENTE, json.dumps(ferramentas.declaracoes(), sort_keys=True))
# Trechos abaixo desta nota não entram no prompt do LLM.
NOTA_MINIMA_DO_TRECHO = 0.15
MAX_FAQ_EXTRA = 100
_bases_com_extras: dict[str, BaseConhecimento] = {}
_trava_bases = threading.Lock()


def base_para(extras: "list[ItemExtra]") -> tuple[BaseConhecimento, str]:
    """(base de busca, versão dos extras). Sem extras é a base do arquivo; com extras, uma base montada e guardada por conteúdo."""
    if not extras:
        return base, ""
    itens = [{"id": f"faq-extra-{e.id}", "modulo": e.modulo, "pergunta": e.pergunta, "resposta": e.resposta, "palavras_chave": e.palavras_chave} for e in extras]
    versao = hashlib.sha256(json.dumps(itens, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    with _trava_bases:
        if versao not in _bases_com_extras:
            if len(_bases_com_extras) >= 8:
                _bases_com_extras.pop(next(iter(_bases_com_extras)))
            _bases_com_extras[versao] = base.com_extras(itens)
        return _bases_com_extras[versao], versao


class ItemExtra(BaseModel):
    """Resposta escrita pelo master na tela de Conversas. Vale só enquanto vier junto da pergunta (a API não guarda nada)."""
    id: int = Field(ge=1)
    modulo: str = Field(min_length=1, max_length=40)
    pergunta: str = Field(min_length=3, max_length=200)
    resposta: str = Field(min_length=3, max_length=1500)
    palavras_chave: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=20)


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=2, max_length=500)
    # Contexto opcional: o que o usuário perguntou antes e qual foi a última resposta dada.
    # A API não guarda conversa; quem chama manda isso a cada pergunta.
    historico: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=6)
    ultimo_id: str | None = Field(default=None, max_length=80)
    # Data de hoje no relógio de quem pergunta (AAAA-MM-DD): "este mês", "amanhã" partem dela.
    hoje: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Segunda volta: o que as consultas pedidas na primeira volta devolveram (o front as executa).
    resultados: list[dict[str, Any]] | None = Field(default=None, max_length=3)
    # FAQ extra (o que o master respondeu a partir das perguntas sem resposta). O Laravel/o front manda a lista a cada pergunta.
    faq_extra: list[ItemExtra] = Field(default_factory=list, max_length=MAX_FAQ_EXTRA)


def exigir_token(x_api_token: str | None = Header(default=None)):
    """Se IA_API_TOKEN estiver definido, só aceita quem enviar o mesmo valor."""
    esperado = os.getenv("IA_API_TOKEN")
    if esperado and x_api_token != esperado:
        raise HTTPException(status_code=401, detail="Token inválido")


def identificar_visitante(request: Request) -> str:
    """IP do visitante. Atrás de proxy (Render), vale o primeiro IP de X-Forwarded-For."""
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


def limitar(request: Request):
    if not limitador.permitir(identificar_visitante(request)):
        raise HTTPException(status_code=429, detail="Muitas perguntas em pouco tempo. Aguarde um instante.")


def registrar_sem_resposta(pergunta: str, melhor_score: float, tipo: str = "faq") -> None:
    """Guarda as perguntas que o FAQ não cobre: é o que diz o que falta escrever."""
    caminho = Path(os.getenv("IA_LOG_SEM_RESPOSTA", PASTA_DADOS / "perguntas_sem_resposta.jsonl"))
    linha = {"em": datetime.now().isoformat(timespec="seconds"), "tipo": tipo, "pergunta": pergunta, "melhor_score": melhor_score}
    with _trava_log, open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def _refinar_com_semantica(pergunta: str) -> tuple[list[Resultado] | None, dict | None]:
    """(resultados reordenados pelo significado ou None se ele não aponta com clareza, diagnóstico para o /chat)."""
    notas = indice_semantico.buscar(pergunta, limite=4)
    if not notas:
        return None, None
    diagnostico = {"id": notas[0][0]["id"], "nota": round(notas[0][1], 4), "margem": round(notas[0][1] - notas[1][1], 4) if len(notas) > 1 else None}
    if not vencedor_confiavel(notas):
        return None, diagnostico
    return [Resultado(i["id"], i["modulo"], i["pergunta"], i["resposta"], round(c, 4)) for i, c in notas], diagnostico


def _relacionadas(resultados, inicio: int, fim: int) -> list[dict]:
    return [{"id": r.id, "pergunta": r.pergunta} for r in resultados[inicio:fim]]


@app.get("/")
def raiz():
    return {"servico": "Lume Locações - Assistente", "docs": "/docs", "saude": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "perguntas_na_base": len(base.itens), "llm": provedor_llm is not None,
            "llm_chamadas_hoje": limitador_llm.usadas, "cache": cache.estatisticas(),
            "semantica": "desligada" if indice_semantico is None else "pronta" if indice_semantico.pronto else "indisponivel" if indice_semantico.erro else "construindo"}


@app.get("/faq", dependencies=[Depends(exigir_token)])
def listar_faq():
    """Lista as perguntas da base. A tela usa isso para mostrar sugestões."""
    return [{"id": i["id"], "modulo": i["modulo"], "pergunta": i["pergunta"]} for i in base.itens]


def _resposta_agente(resposta: str, **extra) -> dict:
    return {"encontrou": True, "resposta": resposta, "fonte": None, "confianca": 1.0, "relacionadas": [], "usou_contexto": True, "gerada_por_llm": True, **extra}


TEXTO_DA_ACAO = {
    "cadastrar_cliente": "Abri o cadastro de cliente com o que você informou. Confira os campos e salve.",
    "cadastrar_produto": "Abri o cadastro de produto com o que você informou. Confira os campos e salve.",
    "cadastrar_orcamento": "Abri o novo orçamento com o que você informou. Confira os campos e salve.",
    "excluir_registro": "Encontrei o registro. Confirme abaixo se quer mesmo excluir.",
}


def _agente(pergunta: str, historico: list[str], dados: PerguntaIn) -> dict | None:
    """Consultas, cadastros e exclusões. None = não é com o agente, segue para o FAQ."""
    resultados = ferramentas.validar_resultados(dados.resultados)
    if resultados:  # segunda volta: o front já consultou, falta redigir a resposta
        texto = redigir_com_dados(provedor_llm, limitador_llm, pergunta, historico, resultados, dados.hoje)
        return _resposta_agente(texto or "Não consegui montar a resposta agora. Tente de novo em instantes.", encontrou=texto is not None, gerada_por_llm=texto is not None)

    if provedor_llm is None or not ferramentas.parece_pedido_de_acao_ou_dados(pergunta, historico):
        return None
    chave = chave_da_conversa("decisao", VERSAO_DO_CONTEUDO, pergunta, historico, dados.ultimo_id, dados.hoje or "")
    decisao = cache.obter(chave)
    em_cache = decisao is not None
    if not em_cache:
        decisao = decidir_acao(provedor_llm, limitador_llm, pergunta, historico, dados.hoje)
        if decisao is None:
            return None
        cache.guardar(chave, decisao)  # a decisão não carrega dados do sistema, só qual ferramenta usar
    if decisao.chamadas:
        consultas = [c for c in decisao.chamadas if ferramentas.eh_consulta(c["nome"])]
        if consultas:  # consultar e agir no mesmo pedido não é suportado: a consulta vem primeiro
            return _resposta_agente("", consultas=consultas, em_cache=em_cache)
        acoes = decisao.chamadas[:1]  # uma ação por vez: cada uma tem a sua confirmação
        return _resposta_agente(TEXTO_DA_ACAO[acoes[0]["nome"]], acoes=acoes, em_cache=em_cache)
    if decisao.texto and decisao.texto.strip().strip(".!").upper() != AJUDA:
        return _resposta_agente(decisao.texto[:400])
    return None


@app.post("/chat", dependencies=[Depends(exigir_token), Depends(limitar)])
def chat(dados: PerguntaIn):
    pergunta = dados.pergunta.strip()
    contexto = Contexto([p.strip() for p in dados.historico if p.strip()][-3:], dados.ultimo_id)

    base_local, versao_extras = base_para(dados.faq_extra)

    papo = resposta_de_conversa(pergunta)
    if papo:
        return {"encontrou": True, "resposta": papo, "fonte": None, "confianca": 1.0, "relacionadas": [], "usou_contexto": False, "gerada_por_llm": False}

    da_ferramenta = _agente(pergunta, contexto.perguntas_anteriores, dados)
    if da_ferramenta is not None:
        return da_ferramenta

    resultados, usou_contexto = base_local.buscar_com_contexto(pergunta, contexto, limite=4)
    melhor = resultados[0] if resultados else None
    assunto = base_local.assunto_da_conversa(pergunta, contexto)

    busca, diagnostico_semantico = "lexical", None
    # Busca híbrida: o TF-IDF não tem certeza e a pergunta não depende da conversa -> pergunta ao embedding.
    if indice_semantico is not None and not assunto and not pede_dados_do_sistema(pergunta) and (not melhor or melhor.score < NOTA_LEXICAL_CONFIANTE) and not (melhor and melhor.id.startswith("faq-extra-") and melhor.score >= LIMITE_CONFIANCA):
        refinados, diagnostico_semantico = _refinar_com_semantica(pergunta)
        if refinados:
            resultados, melhor, busca = refinados, refinados[0], "semantica"

    if pede_dados_do_sistema(pergunta):
        # Registrado como tipo "dados": mostra quais consultas valem virar ferramenta.
        registrar_sem_resposta(pergunta, 0.0, tipo="dados")
        return {
            "encontrou": False,
            "resposta": "Ainda não consigo consultar os seus dados (quantidades, listas, valores). Por enquanto eu só explico como usar o sistema. Para ver esse número, use o Painel, os Orçamentos ou o Financeiro.",
            "fonte": None,
            "confianca": 0.0,
            "relacionadas": _relacionadas(resultados, 0, 3),
            "usou_contexto": False,
            "gerada_por_llm": False,
        }

    # A conversa é sobre um assunto (ex.: produtos) e a pergunta, lida sozinha, não casa com nada desse assunto
    # (ex.: "e para cancelar?"): a resposta só pareceria certa pelos termos emprestados da pergunta anterior.
    # Melhor admitir que a ajuda não cobre isso do que responder sobre a coisa errada.
    if assunto and melhor:
        solta = base_local.buscar(pergunta, limite=len(base_local.itens))
        if not any(r.modulo == assunto and r.score >= LIMITE_CONFIANCA for r in solta):
            registrar_sem_resposta(pergunta, melhor.score, tipo="assunto")
            aviso = f"Não encontrei isso sobre {assunto.lower()} na ajuda."
            if melhor.modulo != assunto:
                aviso += f" Se você quis perguntar sobre {melhor.modulo.lower()}, escreva a pergunta citando o assunto."
            return {
                "encontrou": False,
                "resposta": aviso,
                "fonte": None,
                "confianca": melhor.score,
                "relacionadas": _relacionadas(resultados, 0, 3),
                "usou_contexto": True,
                "gerada_por_llm": False,
            }

    if melhor and melhor.score >= LIMITE_CONFIANCA:
        trechos = [(r.modulo, r.pergunta, r.resposta) for r in resultados if r.score >= NOTA_MINIMA_DO_TRECHO]
        if assunto:  # conversa com assunto definido: só trechos dele (o bloqueio acima garante que existe algum)
            trechos = [t for t in trechos if t[0] == assunto] or trechos
        chave = chave_da_conversa("ajuda", VERSAO_DO_CONTEUDO, pergunta, contexto.perguntas_anteriores, contexto.ultimo_id, versao_extras)
        redigida = cache.obter(chave)
        em_cache = redigida is not None
        if not em_cache:
            redigida = gerar_resposta(provedor_llm, limitador_llm, pergunta, contexto.perguntas_anteriores, trechos, assunto or base_local.modulo_do_item(contexto.ultimo_id))
            cache.guardar(chave, redigida)  # None (falha do modelo) não é guardado
        return {
            "em_cache": em_cache,
            "encontrou": True,
            "resposta": redigida or melhor.resposta,
            "gerada_por_llm": redigida is not None,
            "fonte": {"id": melhor.id, "modulo": melhor.modulo, "pergunta": melhor.pergunta},
            "confianca": melhor.score,
            "relacionadas": _relacionadas(resultados, 1, 4),
            "usou_contexto": usou_contexto,
            "busca": busca,
            "semantica": diagnostico_semantico,
        }

    registrar_sem_resposta(pergunta, melhor.score if melhor else 0.0)
    return {
        "semantica": diagnostico_semantico,
        "encontrou": False,
        "resposta": "Não encontrei isso nas perguntas frequentes. Sua pergunta foi registrada para a equipe incluir na base de ajuda.",
        "fonte": None,
        "confianca": melhor.score if melhor else 0.0,
        "relacionadas": _relacionadas(resultados, 0, 3),
        "usou_contexto": False,
        "gerada_por_llm": False,
    }
