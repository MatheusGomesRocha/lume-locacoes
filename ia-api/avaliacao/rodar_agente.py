"""Golden set do agente: roda as conversas (casos_agente.json), confere o exato e, se pedido, chama o juiz.

  python -m avaliacao --agente                       # em processo, decisão do modelo SIMULADA (sem chave, é o que o CI roda)
  python -m avaliacao --agente --url https://...     # contra a API publicada, com o Gemini de verdade entendendo o 1º pedido
  python -m avaliacao --agente --juiz                # + LLM-as-judge (precisa de GEMINI_API_KEY)
  python -m avaliacao --calibrar-juiz                # compara o juiz com as notas humanas de avaliacao/calibracao_juiz.json
"""
import json
import time
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import httpx

from avaliacao.juiz import calibrar, julgar, provedor_do_juiz, relatorio_juiz_md
from avaliacao.pontuar_agente import avaliar_agente
from avaliacao.simulador import conversar

CASOS = Path(__file__).with_name("casos_agente.json")
CALIBRACAO = Path(__file__).with_name("calibracao_juiz.json")


def carregar_casos_agente(grupo: str | None = None) -> list[dict]:
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    return [c for c in casos if not grupo or c["id"] == grupo]


@contextmanager
def enviar_em_processo_simulado():
    """A aplicação em processo; só a ENTENDER o pedido inicial é simulado (o que o Gemini devolveria), o resto é o código de verdade."""
    from fastapi.testclient import TestClient

    from app import main
    from app.llm import Decisao, ErroLLM

    class SemModelo:  # qualquer outra chamada ao modelo falha e a API cai na resposta do FAQ, como sem chave
        def gerar(self, *a, **k):
            raise ErroLLM("sem modelo na avaliação")

        decidir = gerar

    atual: dict = {}
    cliente = TestClient(main.app)

    def decidir(provedor, limitador, pergunta, historico, hoje=None):
        return Decisao(chamadas=atual["caso"]["decisao"], texto=None) if atual.get("caso") else None

    with mock.patch.object(main, "provedor_llm", SemModelo()), mock.patch.object(main, "decidir_acao", decidir), mock.patch.object(main, "indice_semantico", None):
        main.limitador.maximo = 10**6
        main.cache.limpar()

        def enviar(corpo: dict, caso: dict | None = None) -> dict:
            if caso is not None:
                atual["caso"] = caso
            r = cliente.post("/chat", json=corpo)
            r.raise_for_status()
            return r.json()

        yield enviar


def enviar_por_http_agente(url: str, token: str | None = None, pausa: float = 2.2):
    cliente = httpx.Client(timeout=60)
    cabecalhos = {"X-API-Token": token} if token else {}

    def enviar(corpo: dict, caso: dict | None = None) -> dict:
        time.sleep(pausa)
        r = cliente.post(url.rstrip("/") + "/chat", json=corpo, headers=cabecalhos)
        r.raise_for_status()
        return r.json()

    return enviar


def rodar(casos: list[dict], enviar) -> dict:
    saida = {}
    for caso in casos:
        try:
            resultado = conversar(caso, enviar)
            saida[caso["id"]] = {"resultado": resultado, "falhas": avaliar_agente(caso, resultado)}
        except Exception as e:  # noqa: BLE001 - uma conversa que quebra é uma falha do caso, não da rodada
            saida[caso["id"]] = {"resultado": None, "falhas": [f"erro ao conversar: {type(e).__name__}: {e}"[:200]]}
    return saida


def relatorio_agente_md(casos: list[dict], rodada: dict, origem: str) -> str:
    ok = sum(not rodada[c["id"]]["falhas"] for c in casos)
    linhas = ["# Golden set do agente", "", f"Rodada contra {origem}.", "", f"**Resultado geral: {ok}/{len(casos)} ({ok / len(casos):.0%})**" if casos else "Nenhum caso.", "", "| Caso | Cenário | Resultado |", "|---|---|---|"]
    for c in casos:
        f = rodada[c["id"]]["falhas"]
        linhas.append(f"| `{c['id']}` | {c['descricao']} | {'✅' if not f else '❌'} |")
    falhas = [(c, rodada[c["id"]]["falhas"]) for c in casos if rodada[c["id"]]["falhas"]]
    if falhas:
        linhas += ["", "## O que falhou", ""] + [f"- `{c['id']}`: " + "; ".join(f) for c, f in falhas]
    return "\n".join(linhas) + "\n"


def principal(a) -> int:
    """a: argparse com agente, url, token, grupo, minimo, md, juiz, calibrar_juiz, salvar."""
    import sys

    if a.calibrar_juiz:
        provedor = provedor_do_juiz()
        if provedor is None:
            print("Sem GEMINI_API_KEY: não há juiz para calibrar.", file=sys.stderr)
            return 2
        r = calibrar(provedor, json.loads(CALIBRACAO.read_text(encoding="utf-8")))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["concordancia"] >= 0.8 else 1

    casos = carregar_casos_agente(a.grupo)
    if a.url:
        rodada, origem = rodar(casos, enviar_por_http_agente(a.url, a.token)), a.url
    else:
        with enviar_em_processo_simulado() as enviar:
            rodada, origem = rodar(casos, enviar), "a aplicação em processo (decisão do modelo simulada)"
    texto = relatorio_agente_md(casos, rodada, origem)

    vereditos = []
    if a.juiz:
        provedor = provedor_do_juiz()
        if provedor is None:
            texto += "\n_Juiz não executado: falta GEMINI_API_KEY._\n"
        else:
            for c in casos:
                if rodada[c["id"]]["resultado"]:
                    vereditos.append(julgar(provedor, c, rodada[c["id"]]["resultado"]))
                    time.sleep(a.pausa)
            texto += "\n" + relatorio_juiz_md(vereditos)
    print(texto)
    if a.md:
        Path(a.md).write_text(texto, encoding="utf-8")
    if a.salvar:
        Path(a.salvar).write_text(json.dumps({"rodada": rodada, "vereditos": vereditos}, ensure_ascii=False, indent=1), encoding="utf-8")

    taxa = sum(not rodada[c["id"]]["falhas"] for c in casos) / len(casos) if casos else 0.0
    if a.minimo is not None and taxa < a.minimo:
        print(f"Abaixo do mínimo de {a.minimo:.0%}.", file=sys.stderr)
        return 1
    if a.juiz and vereditos and a.minimo_juiz is not None and sum(v["aprovado"] for v in vereditos) / len(vereditos) < a.minimo_juiz:
        print(f"O juiz aprovou menos que {a.minimo_juiz:.0%}.", file=sys.stderr)
        return 1
    return 0
