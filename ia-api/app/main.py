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

from app import agente as conversa_agente
from app import consumo, ferramentas
from app.conversa import resposta_de_conversa
from app.cache import cache_do_ambiente, chave_da_conversa, versao_do_conteudo
from app.impossivel import pergunta_impossivel
from app.busca import BaseConhecimento, Contexto, Resultado, pede_dados_do_sistema
from app.semantica import NOTA_LEXICAL_CONFIANTE, criar_indice_do_ambiente, vencedor_confiavel
from evolucao import checagens
from evolucao.agentes import normalizar_spec
from evolucao.consulta import buscar_consulta, extrair_parametros, tipo_da_pergunta
from evolucao.esquema import ESQUEMA
from evolucao.pipeline import gerar_relatorios
from app.limite import LimitadorDeRequisicoes
import logging

from app.confianca import seguimento_confere, texto_confere_com_dados, texto_seguro
from app.llm import AJUDA, INSTRUCOES, INSTRUCOES_AGENTE, LimitadorDiario, criar_provedor_do_ambiente, decidir_acao, gerar_resposta, limite_diario_do_ambiente, redigir_com_dados, reformular_seguimento

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
    pergunta: str = Field(min_length=1, max_length=500)  # 1 caractere só vale como resposta ao agente ("2" escolhe a opção 2)
    # Contexto opcional: o que o usuário perguntou antes e qual foi a última resposta dada.
    # A API não guarda conversa; quem chama manda isso a cada pergunta.
    historico: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=6)
    ultimo_id: str | None = Field(default=None, max_length=80)
    # Data de hoje no relógio de quem pergunta (AAAA-MM-DD): "este mês", "amanhã" partem dela.
    hoje: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Segunda volta: o que as consultas pedidas na primeira volta devolveram (o front as executa).
    resultados: list[dict[str, Any]] | None = Field(default=None, max_length=3)
    # Conversa do agente em andamento (criar orçamento/cliente falando no chat). O estado volta a cada resposta; ver app/agente.py.
    agente: dict[str, Any] | None = None
    # FAQ extra (o que o master respondeu a partir das perguntas sem resposta). O Laravel/o front manda a lista a cada pergunta.
    faq_extra: list[ItemExtra] = Field(default_factory=list, max_length=MAX_FAQ_EXTRA)
    # Consultas que os Agents criaram e o Master aprovou (specs, nunca código). Vêm a cada pergunta, como o faq_extra.
    catalogo: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


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


def _da_conversa(passo: dict) -> dict:
    """Resposta do agente conversacional: texto, novo estado (None encerra), opções clicáveis, consultas a executar ou gravações JÁ confirmadas."""
    extra = {k: passo[k] for k in ("opcoes", "consultas", "executar") if passo.get(k)}
    return _resposta_agente(passo["texto"], agente=passo["agente"], gerada_por_llm=False, **extra)


TEXTO_DA_ACAO = {
    "cadastrar_cliente": "Abri o cadastro de cliente com o que você informou. Confira os campos e salve.",
    "cadastrar_produto": "Abri o cadastro de produto com o que você informou. Confira os campos e salve.",
    "cadastrar_orcamento": "Abri o novo orçamento com o que você informou. Confira os campos e salve.",
    "excluir_registro": "Encontrei o registro. Confirme abaixo se quer mesmo excluir.",
}


def specs_validas(brutas: list[dict]) -> list[dict]:
    """Só entram as specs que passam de novo pelas checagens fixas: o catálogo vem de fora, então não se confia nele."""
    saida = []
    for b in brutas:
        spec, _ = normalizar_spec(b)
        if not checagens.tem_bloqueio(checagens.checar_spec(spec, None, [])):
            saida.append(spec)
    return saida


def _faltando(spec: dict, params: dict) -> list[str]:
    return [n for n, d in (spec.get("parametros") or {}).items() if d.get("obrigatorio") and n not in params]


def texto_do_catalogo(spec: dict, resultado: Any) -> str:
    """Resposta montada por código (sem modelo): o número é o que a consulta devolveu, nada inventado."""
    if not isinstance(resultado, dict) or "erro" in resultado:
        return str((resultado or {}).get("erro", "Não consegui consultar agora.")).capitalize() + "." if isinstance(resultado, dict) else "Não consegui consultar agora."
    rotulo = ESQUEMA.get(spec.get("entidade"), {}).get("rotulo", "registros").lower()
    partes = [f"Entendi: {spec['descricao']}"] if spec.get("descricao") else []
    partes.append(f"Encontrei {resultado.get('total', 0)} em {rotulo}.")
    if "soma" in resultado:
        partes.append(f"Soma: {str(resultado['soma']).replace('.', ',')}.")
    for linha in resultado.get("linhas", [])[:15]:
        partes.append("• " + " · ".join(str(v) for v in linha.values() if v not in (None, "")))
    return "\n".join(partes)


log = logging.getLogger("lume.chat")


def _completar_seguimento(pergunta: str, historico: list[str]) -> tuple[str, str | None]:
    """"e quais os nomes deles?" vira a pergunta completa, com o modelo e a conversa. Devolve (pergunta, sugestao):
    sugestao é None quando não era seguimento ou a reescrita foi conferida; senão a reescrita duvidosa ("" se nem houve) e a Lumi PERGUNTA."""
    if not (historico and ferramentas.parece_seguimento(pergunta, historico)):
        return pergunta, None
    chave_seg = chave_da_conversa("seguimento", VERSAO_DO_CONTEUDO, pergunta, historico, None)
    nova = cache.obter(chave_seg)
    if nova is None:
        nova = reformular_seguimento(provedor_llm, limitador_llm, pergunta, historico)
        if nova and seguimento_confere(pergunta, nova, historico):
            cache.guardar(chave_seg, nova)
        else:
            return pergunta, nova or ""
    return nova, None


def _agente(pergunta: str, historico: list[str], dados: PerguntaIn) -> dict | None:
    """Consultas, cadastros e exclusões. None = não é com o agente, segue para o FAQ."""
    resultados = ferramentas.validar_resultados(dados.resultados)
    if resultados and all(r["nome"] == ferramentas.CATALOGO for r in resultados):
        por_nome = {s["nome"]: s for s in specs_validas(dados.catalogo)}
        return _resposta_agente("\n\n".join(texto_do_catalogo(por_nome.get(r["args"]["nome"], {}), r["resultado"]) for r in resultados), gerada_por_llm=False)
    if resultados:  # segunda volta: o front já consultou, falta redigir a resposta
        texto = redigir_com_dados(provedor_llm, limitador_llm, pergunta, historico, resultados, dados.hoje)
        if texto and not texto_confere_com_dados(texto, resultados, pergunta, dados.hoje):  # número que não existe nos dados: descarta o texto do modelo
            log.warning("texto do modelo descartado: número fora dos dados")
            return _resposta_agente(texto_seguro(resultados), gerada_por_llm=False)
        return _resposta_agente(texto or "Não consegui montar a resposta agora. Tente de novo em instantes.", encontrou=texto is not None, gerada_por_llm=texto is not None)

    impossivel = None if ferramentas.pede_acao(pergunta) else pergunta_impossivel(pergunta)
    if impossivel:  # o sistema não guarda esse dado: responde já, sem modelo, e NÃO entra na fila dos Agents (não há consulta que resolva)
        return _resposta_agente(impossivel["resposta"], impossivel=True, gerada_por_llm=False)
    if ferramentas.pede_acao(pergunta) and ferramentas.fala_de_usuario_do_sistema(pergunta):
        return _resposta_agente(TEXTO_USUARIO_DO_SISTEMA)  # antes do modelo: não depende dele nem gasta cota
    if dados.catalogo and not ferramentas.pede_acao(pergunta):  # uma consulta aprovada pelo Master tem prioridade sobre perguntar ao modelo
        specs = specs_validas(dados.catalogo)
        spec = buscar_consulta(pergunta, specs)
        if spec:
            params = extrair_parametros(pergunta, spec)
            # Parâmetro de texto (ex.: categoria) o servidor não consegue ler da pergunta: ele não tem os dados. Vai a pergunta junto
            # e o front acha o valor entre os que existem de verdade; se não achar, ele pergunta com as opções reais.
            sem_texto = [n for n in _faltando(spec, params) if spec["parametros"][n].get("tipo") != "texto"]
            falta = sem_texto
            if falta:
                return _resposta_agente(f"Para responder preciso saber: {', '.join(falta)}. Diga na pergunta, por exemplo “{(spec.get('exemplos') or [''])[0]}”.", gerada_por_llm=False)
            args = {"nome": spec["nome"], "params": params}
            if _faltando(spec, params):
                args["pergunta"] = pergunta[:300]
            return _resposta_agente("", consultas=[{"nome": ferramentas.CATALOGO, "args": args}], gerada_por_llm=False)
    if dados.catalogo and not ferramentas.pede_acao(pergunta) and tipo_da_pergunta(pergunta) in ("listar", "somar"):
        parecida = buscar_consulta(pergunta, specs_validas(dados.catalogo), por_tipo=False)
        if parecida:  # existe consulta do mesmo assunto, mas de outro tipo (sabe contar, não sabe listar): diz isso e deixa para os Agents
            quer = "listar" if tipo_da_pergunta(pergunta) == "listar" else "somar"
            return _resposta_agente(f"Ainda não consigo {quer} isso: só sei {'contar' if parecida.get('operacao') == 'contar' else parecida.get('operacao')} ({parecida.get('descricao', '')[:80]}). "
                                    "Não consegui responder como você pediu; registrei a pergunta para o Master analisar.", encontrou=False, gerada_por_llm=False)
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
        if acoes[0]["nome"] in ("cadastrar_cliente", "excluir_registro") and ferramentas.fala_de_usuario_do_sistema(pergunta):
            return _resposta_agente(TEXTO_USUARIO_DO_SISTEMA, em_cache=em_cache)
        # Com dados para trabalhar, o agente conduz a conversa no chat (sem formulário); sem dados, abre o formulário de sempre.
        if acoes[0]["nome"] in ("cadastrar_orcamento", "cadastrar_cliente"):
            passo = conversa_agente.iniciar(acoes[0]["nome"], acoes[0]["args"], dados.hoje)
            if passo:
                return {**_da_conversa(passo), "em_cache": em_cache, "gerada_por_llm": True}
        return _resposta_agente(TEXTO_DA_ACAO[acoes[0]["nome"]], acoes=acoes, em_cache=em_cache)
    if decisao.texto and decisao.texto.strip().strip(".!").upper() != AJUDA:
        return _resposta_agente(decisao.texto[:400])
    return None


class PerguntaSemResposta(BaseModel):
    pergunta: str = Field(min_length=4, max_length=300)
    tipo: str = Field(default="dados", max_length=20)
    vezes: int = Field(default=1, ge=1, le=10_000)


class EvolucaoIn(BaseModel):
    perguntas: list[PerguntaSemResposta] = Field(min_length=1, max_length=20)
    catalogo: list[dict[str, Any]] = Field(default_factory=list, max_length=30)  # o que já foi aprovado (evita nome repetido e consulta repetida)
    proximo_numero: int = Field(default=1, ge=1, le=100_000)


@app.post("/evolucao/propor", dependencies=[Depends(exigir_token), Depends(limitar)])
def evolucao_propor(dados: EvolucaoIn):
    """Agents 1, 2 e 3 sobre as perguntas sem resposta. Não guarda nada: devolve os relatórios para o Laravel/front guardarem e o Master decidir."""
    if provedor_llm is None:
        raise HTTPException(status_code=503, detail="Os Agents precisam do modelo (GEMINI_API_KEY) e ele não está configurado.")
    ignoradas = [{"pergunta": p.pergunta, "motivo": f"o sistema não guarda {i['atributo']}: nenhuma consulta responde"} for p in dados.perguntas if (i := pergunta_impossivel(p.pergunta))]
    specs = specs_validas(dados.catalogo)
    for p in dados.perguntas:  # a consulta aprovada já responde (só muda o valor, ex.: 7 -> 15 dias): não é trabalho novo para os Agents
        if not pergunta_impossivel(p.pergunta) and (ja := buscar_consulta(p.pergunta, specs)):
            ignoradas.append({"pergunta": p.pergunta, "motivo": f"já respondida pela consulta aprovada “{ja['nome']}” (só muda o valor do parâmetro)"})
    descartar = {i["pergunta"] for i in ignoradas}
    validas = [p.model_dump() for p in dados.perguntas if p.pergunta not in descartar]
    if not validas:
        return {"relatorios": [], "ignoradas": ignoradas}
    try:
        relatorios = gerar_relatorios(provedor_llm, limitador_llm, validas, specs,
                                      lambda i: f"EV-{dados.proximo_numero + i:04d}")
    except Exception as e:  # ErroAgente, cota, rede: o Master vê o motivo em vez de um erro mudo
        raise HTTPException(status_code=502, detail=f"Os Agents não conseguiram terminar: {str(e)[:200]}") from None
    return {"relatorios": relatorios, "ignoradas": ignoradas}


class ChecarIn(BaseModel):
    spec: dict[str, Any]
    proposta: dict[str, Any] = Field(default_factory=dict)
    catalogo: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


@app.post("/evolucao/checar", dependencies=[Depends(exigir_token), Depends(limitar)])
def evolucao_checar(dados: ChecarIn):
    """Refaz só as checagens fixas (sem modelo) de uma consulta. Quem guarda as propostas chama isto de novo na hora de aprovar."""
    spec, _ = normalizar_spec(dados.spec)
    achados = checagens.checar_spec(spec, dados.proposta or None, specs_validas(dados.catalogo))
    return {"achados": achados, "bloqueio": checagens.tem_bloqueio(achados)}


TEXTO_USUARIO_DO_SISTEMA = (
    "Usuário do sistema (quem faz login) eu ainda não consigo criar nem excluir por aqui: isso é na tela de Usuários. "
    "Por aqui eu cadastro clientes, produtos e orçamentos. Se você quis dizer cliente, peça assim: “cadastrar cliente Fulano”."
)


# Identifica a versão do assistente nas métricas: no Render, o commit publicado; fora dele, "dev".
VERSAO = (os.getenv("RENDER_GIT_COMMIT") or os.getenv("IA_VERSAO") or "dev")[:7]


@app.post("/chat", dependencies=[Depends(exigir_token), Depends(limitar)])
def chat(dados: PerguntaIn):
    """Responde e acrescenta quanto a pergunta gastou do modelo (`consumo`) e qual versão respondeu (`versao`)."""
    consumo.iniciar()
    resposta = _responder(dados)
    if isinstance(resposta, dict):
        gasto = consumo.resumo()
        resposta = {**resposta, "versao": VERSAO, **({"consumo": gasto} if gasto else {})}
    return resposta


def _responder(dados: PerguntaIn):
    pergunta = dados.pergunta.strip()
    if len(pergunta) < 2 and not dados.agente:
        raise HTTPException(status_code=422, detail="A pergunta precisa de pelo menos 2 caracteres.")
    if not pergunta:
        raise HTTPException(status_code=422, detail="A mensagem está vazia.")
    contexto = Contexto([p.strip() for p in dados.historico if p.strip()][-3:], dados.ultimo_id)

    if dados.agente:  # há uma conversa do agente em andamento: a mensagem é a resposta à pergunta dele
        passo = conversa_agente.continuar(dados.agente, pergunta, dados.resultados, dados.hoje)
        if passo:
            return _da_conversa(passo)

    base_local, versao_extras = base_para(dados.faq_extra)

    papo = resposta_de_conversa(pergunta)
    if papo:
        return {"encontrou": True, "resposta": papo, "fonte": None, "confianca": 1.0, "relacionadas": [], "usou_contexto": False, "gerada_por_llm": False}

    completa, duvida = _completar_seguimento(pergunta, contexto.perguntas_anteriores)
    if duvida is not None:  # não deu para ter certeza do que ele quis dizer: pergunta, não chuta
        quis = f"Você quis dizer: “{duvida}”? Se sim, envie a pergunta completa." if duvida else "Pode escrever a pergunta completa, com o assunto?"
        return _resposta_agente(f"Não tenho certeza do que você quer saber com “{pergunta[:80]}”. {quis}", esclarecimento=True, gerada_por_llm=False)
    da_ferramenta = _agente(completa, contexto.perguntas_anteriores, dados)
    if da_ferramenta is not None:
        if completa == pergunta:
            return da_ferramenta
        texto = f"Entendi: {completa}\n\n{da_ferramenta['resposta']}" if da_ferramenta.get("resposta") else da_ferramenta["resposta"]
        return {**da_ferramenta, "resposta": texto, "pergunta_completa": completa}

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
