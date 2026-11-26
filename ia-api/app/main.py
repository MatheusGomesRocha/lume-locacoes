"""API do assistente de ajuda do Lume Locações.

Rodar:  uvicorn app.main:app --port 8001 --reload
Docs interativas (grátis no FastAPI): http://127.0.0.1:8001/docs
"""
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated

from app.busca import BaseConhecimento, Contexto, pede_dados_do_sistema
from app.limite import LimitadorDeRequisicoes
from app.llm import LimitadorDiario, criar_provedor_do_ambiente, gerar_resposta, limite_diario_do_ambiente

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
# Trechos abaixo desta nota não entram no prompt do LLM.
NOTA_MINIMA_DO_TRECHO = 0.15


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=2, max_length=500)
    # Contexto opcional: o que o usuário perguntou antes e qual foi a última resposta dada.
    # A API não guarda conversa; quem chama manda isso a cada pergunta.
    historico: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=6)
    ultimo_id: str | None = Field(default=None, max_length=80)


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


def _relacionadas(resultados, inicio: int, fim: int) -> list[dict]:
    return [{"id": r.id, "pergunta": r.pergunta} for r in resultados[inicio:fim]]


@app.get("/")
def raiz():
    return {"servico": "Lume Locações - Assistente", "docs": "/docs", "saude": "/health"}


@app.get("/health")
def health():
    return {"status": "ok", "perguntas_na_base": len(base.itens), "llm": provedor_llm is not None}


@app.get("/faq", dependencies=[Depends(exigir_token)])
def listar_faq():
    """Lista as perguntas da base. A tela usa isso para mostrar sugestões."""
    return [{"id": i["id"], "modulo": i["modulo"], "pergunta": i["pergunta"]} for i in base.itens]


@app.post("/chat", dependencies=[Depends(exigir_token), Depends(limitar)])
def chat(dados: PerguntaIn):
    pergunta = dados.pergunta.strip()
    contexto = Contexto([p.strip() for p in dados.historico if p.strip()][-3:], dados.ultimo_id)
    resultados, usou_contexto = base.buscar_com_contexto(pergunta, contexto, limite=4)
    melhor = resultados[0] if resultados else None

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

    if melhor and melhor.score >= LIMITE_CONFIANCA:
        trechos = [(r.pergunta, r.resposta) for r in resultados if r.score >= NOTA_MINIMA_DO_TRECHO]
        redigida = gerar_resposta(provedor_llm, limitador_llm, pergunta, contexto.perguntas_anteriores, trechos)
        return {
            "encontrou": True,
            "resposta": redigida or melhor.resposta,
            "gerada_por_llm": redigida is not None,
            "fonte": {"id": melhor.id, "modulo": melhor.modulo, "pergunta": melhor.pergunta},
            "confianca": melhor.score,
            "relacionadas": _relacionadas(resultados, 1, 4),
            "usou_contexto": usou_contexto,
        }

    registrar_sem_resposta(pergunta, melhor.score if melhor else 0.0)
    return {
        "encontrou": False,
        "resposta": "Não encontrei isso nas perguntas frequentes. Sua pergunta foi registrada para a equipe incluir na base de ajuda.",
        "fonte": None,
        "confianca": melhor.score if melhor else 0.0,
        "relacionadas": _relacionadas(resultados, 0, 3),
        "usou_contexto": False,
        "gerada_por_llm": False,
    }
