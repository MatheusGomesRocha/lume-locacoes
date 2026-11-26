"""Coleta as respostas da API para cada caso (a parte que usa rede e o modelo de verdade)."""
import json
import time
from pathlib import Path

import httpx

CASOS = Path(__file__).with_name("casos.json")


def carregar_casos(grupo: str | None = None, sem_modelo: bool = False) -> list[dict]:
    """`sem_modelo` tira os casos que só passam com o Gemini (ferramentas e busca semântica): é o que o CI roda."""
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    return [c for c in casos if (not grupo or c["grupo"] == grupo) and not (sem_modelo and c.get("precisa_modelo"))]


def corpo_do_caso(caso: dict) -> dict:
    corpo = {"pergunta": caso["pergunta"]}
    for campo in ("historico", "ultimo_id", "hoje"):
        if caso.get(campo):
            corpo[campo] = caso[campo]
    return corpo


def coletar(casos: list[dict], enviar, pausa: float = 2.2) -> dict:
    """`enviar(corpo) -> dict` faz a chamada. A pausa respeita o limite de requisições por minuto da API."""
    saida = {}
    for i, caso in enumerate(casos):
        inicio = time.time()
        try:
            saida[caso["id"]] = {"resposta": enviar(corpo_do_caso(caso)), "ms": round((time.time() - inicio) * 1000), "erro": None}
        except Exception as e:  # noqa: BLE001 - qualquer falha vira "sem resposta" no relatório
            saida[caso["id"]] = {"resposta": None, "ms": None, "erro": f"{type(e).__name__}: {e}"[:200]}
        if i < len(casos) - 1:
            time.sleep(pausa)
    return saida


def enviar_por_http(url: str, token: str | None = None):
    cliente = httpx.Client(timeout=60)
    cabecalhos = {"X-API-Token": token} if token else {}

    def enviar(corpo: dict) -> dict:
        r = cliente.post(url.rstrip("/") + "/chat", json=corpo, headers=cabecalhos)
        r.raise_for_status()
        return r.json()

    return enviar


def enviar_em_processo():
    """Usa a aplicação direto (sem servidor). Precisa de GEMINI_API_KEY no ambiente para exercitar o modelo de verdade."""
    from fastapi.testclient import TestClient

    from app.main import app

    cliente = TestClient(app)

    def enviar(corpo: dict) -> dict:
        r = cliente.post("/chat", json=corpo)
        r.raise_for_status()
        return r.json()

    return enviar
