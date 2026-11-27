"""Mede o entendimento de contexto com o modelo REAL: perguntas de seguimento ("e quais os nomes deles?") contra uma API no ar.

Cada caso é uma conversa curta (histórico + última pergunta) e o que a pergunta completa TEM que conter. Resultado de cada caso:
  certo        a Lumi completou a pergunta com o assunto e o tipo certos
  perguntou    a Lumi não teve certeza e pediu a pergunta completa (aceitável, é seguro)
  errado       completou mal e seguiu em frente (o único resultado que falha a avaliação)

  python -m avaliacao.seguimento --url https://lume-ia.onrender.com --token ... [--md saida.md]
"""
import argparse
import json
import sys
import time
import urllib.request

from evolucao.consulta import tipo_da_pergunta

CASOS = [
    (["quantos clientes foram cadastrados hoje?"], "e qual os nomes deles?", ["clientes", "hoje"], "listar"),
    (["quantos clientes foram cadastrados hoje?"], "e quais são eles?", ["clientes", "hoje"], "listar"),
    (["quantos clientes foram cadastrados hoje?"], "me mostra quem são eles", ["clientes", "hoje"], "listar"),
    (["quantos produtos estão ativos?"], "e quais são os nomes deles?", ["produtos", "ativos"], "listar"),
    (["quantos produtos foram cadastrados nos últimos 7 dias?"], "e nos últimos 30?", ["produtos", "30"], "contar"),
    (["quantos orçamentos foram criados esta semana?"], "e quais são eles?", ["orçamentos"], "listar"),
    (["quantos orçamentos aprovados temos?"], "e desses, quais vencem hoje?", ["orçamentos", "aprovad"], "listar"),
    (["quais orçamentos têm devolução hoje?"], "e amanhã?", ["orçamentos", "devolução", "amanhã"], None),
    (["qual o total de cobranças pagas?"], "e as pendentes?", ["cobranças", "pendentes"], None),
    (["quantos clientes temos?"], "e quantos são pessoa jurídica?", ["clientes", "jurídica"], "contar"),
    (["quantos produtos da categoria Iluminação temos?"], "e de Som?", ["produtos", "Som"], "contar"),
    (["quantos usuários temos?"], "e quais os nomes deles?", ["usuários"], "listar"),
    (["quantas cobranças vencem nos próximos 7 dias?"], "e o valor total delas?", ["cobranças", "7"], "somar"),
    (["quantos clientes foram cadastrados hoje?", "Encontrei 2 em clientes."], "e ontem?", ["clientes", "ontem"], "contar"),
    (["quantos produtos temos?", "quais os nomes dos clientes?"], "e quantos são?", ["clientes"], "contar"),
]


def enviar(url: str, token: str | None, corpo: dict) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/chat", json.dumps(corpo).encode(), {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    for tentativa in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as e:  # 429 da cota: espera e tenta de novo
            if tentativa == 3:
                raise
            time.sleep(8 * (tentativa + 1))
    return {}


def avaliar(caso, r: dict) -> str:
    _, _, deve, tipo = caso
    if r.get("esclarecimento"):
        return "perguntou"
    completa = (r.get("pergunta_completa") or "").lower()
    ok = bool(completa) and all(p.lower() in completa for p in deve) and (tipo is None or tipo_da_pergunta(completa) == tipo)
    return "certo" if ok else "errado"


def rodar(url: str, token: str | None, pausa: float = 2.5) -> list[dict]:
    saida = []
    for caso in CASOS:
        hist, perg, _, _ = caso
        r = enviar(url, token, {"pergunta": perg, "historico": [h for h in hist if h.endswith("?")][-3:] or hist, "hoje": "2026-11-26"})
        saida.append({"historico": hist, "pergunta": perg, "completa": r.get("pergunta_completa"), "resultado": avaliar(caso, r)})
        time.sleep(pausa)
    return saida


def resumo(res: list[dict]) -> str:
    n = len(res)
    c = {k: sum(1 for x in res if x["resultado"] == k) for k in ("certo", "perguntou", "errado")}
    linhas = [f"Seguimento: {c['certo']}/{n} certas, {c['perguntou']} pediram esclarecimento, {c['errado']} erradas"]
    linhas += [f"- ERRADO: “{x['pergunta']}” (após {x['historico'][-1]!r}) virou {x['completa']!r}" for x in res if x["resultado"] == "errado"]
    return "\n".join(linhas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--token")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    res = rodar(a.url, a.token)
    texto = resumo(res)
    print(texto)
    if a.md:
        open(a.md, "w", encoding="utf-8").write("# Entendimento de contexto\n\n" + texto + "\n")
    return 1 if any(x["resultado"] == "errado" for x in res) else 0


if __name__ == "__main__":
    sys.exit(main())
