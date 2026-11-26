"""Pontuação da avaliação: compara a resposta da API com o que cada caso espera. Não usa rede nem modelo."""
import statistics
import unicodedata
from collections import defaultdict


def _norm(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn").strip()


def _lista(v) -> list:
    return v if isinstance(v, list) else [v]


def primeira_chamada(resp: dict) -> dict | None:
    """Ferramenta que o modelo pediu (consulta ou ação), se pediu."""
    chamadas = resp.get("consultas") or resp.get("acoes") or []
    return chamadas[0] if chamadas else None


def _igual(esperado, obtido) -> bool:
    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        try:
            return float(obtido) == float(esperado)
        except (TypeError, ValueError):
            return False
    return _norm(esperado) == _norm(obtido)


def avaliar(caso: dict, resp: dict) -> list[str]:
    """Motivos pelos quais o caso falhou. Lista vazia = passou."""
    e = caso["espera"]
    falhas: list[str] = []
    chamada = primeira_chamada(resp)
    nome = chamada["nome"] if chamada else None
    args = chamada["args"] if chamada else {}
    texto = _norm(resp.get("resposta", ""))

    if "fonte" in e:
        fonte = (resp.get("fonte") or {}).get("id")
        if fonte not in _lista(e["fonte"]):
            falhas.append(f"fonte {fonte!r}, esperado {e['fonte']!r}")
    if "encontrou" in e and bool(resp.get("encontrou")) != e["encontrou"]:
        falhas.append(f"encontrou={resp.get('encontrou')!r}, esperado {e['encontrou']!r}")
    if e.get("sem_ferramenta") and chamada:
        falhas.append(f"pediu a ferramenta {nome}, esperado nenhuma")
    if "ferramenta" in e and nome not in _lista(e["ferramenta"]):
        falhas.append(f"ferramenta {nome!r}, esperado {e['ferramenta']!r}")
    if nome in _lista(e.get("ferramenta_proibida", [])):
        falhas.append(f"pediu a ferramenta proibida {nome}")
    for chave, valor in e.get("args_contem", {}).items():
        if chave not in args or not _igual(valor, args[chave]):
            falhas.append(f"argumento {chave}={args.get(chave)!r}, esperado {valor!r}")
    for chave, trecho in e.get("args_texto", {}).items():
        if _norm(trecho) not in _norm(args.get(chave, "")):
            falhas.append(f"argumento {chave}={args.get(chave)!r} não contém {trecho!r}")
    if "args_texto_em_qualquer" in e:
        if not any(_norm(e["args_texto_em_qualquer"]) in _norm(v) for v in args.values() if isinstance(v, str)):
            falhas.append(f"nenhum argumento contém {e['args_texto_em_qualquer']!r}")
    for chave in e.get("args_presentes", []):
        if chave not in args:
            falhas.append(f"faltou o argumento {chave}")
    for chave in e.get("args_ausentes", []):
        if chave in args:
            falhas.append(f"inventou o argumento {chave}={args[chave]!r}")
    if "deve_conter_um_de" in e and not any(_norm(t) in texto for t in e["deve_conter_um_de"]):
        falhas.append(f"a resposta não contém nenhum de {e['deve_conter_um_de']!r}")
    for t in e.get("nao_deve_conter", []):
        if _norm(t) in texto:
            falhas.append(f"a resposta contém {t!r}")
    return falhas


def pontuar(casos: list[dict], coletado: dict) -> dict:
    """coletado: {id: {"resposta": {...}, "ms": int, "erro": str|None}}. Caso sem resposta conta como falha."""
    por_grupo: dict[str, list[dict]] = defaultdict(list)
    for caso in casos:
        item = coletado.get(caso["id"])
        if item is None or item.get("erro") or not item.get("resposta"):
            falhas = [f"sem resposta ({(item or {}).get('erro') or 'não coletado'})"]
            resp, ms = {}, None
        else:
            resp, ms = item["resposta"], item.get("ms")
            falhas = avaliar(caso, resp)
        por_grupo[caso["grupo"]].append({"id": caso["id"], "pergunta": caso["pergunta"], "ok": not falhas, "falhas": falhas, "ms": ms,
                                         "llm": bool(resp.get("gerada_por_llm")), "ferramenta": (primeira_chamada(resp) or {}).get("nome")})
    grupos = {g: {"total": len(rs), "acertos": sum(r["ok"] for r in rs), "casos": rs} for g, rs in por_grupo.items()}
    todos = [r for rs in por_grupo.values() for r in rs]
    tempos = sorted(r["ms"] for r in todos if r["ms"] is not None)
    return {
        "total": len(todos), "acertos": sum(r["ok"] for r in todos), "grupos": grupos,
        "latencia_media_ms": round(statistics.mean(tempos)) if tempos else None,
        "latencia_p95_ms": tempos[min(len(tempos) - 1, int(len(tempos) * 0.95))] if tempos else None,
        "com_llm": sum(r["llm"] or r["ferramenta"] is not None for r in todos),
    }


def taxa(acertos: int, total: int) -> float:
    return acertos / total if total else 0.0


TITULOS = {"faq": "FAQ (acha a resposta certa)", "contexto": "Contexto da conversa", "consulta": "Consultas de dados (ferramenta e argumentos)",
           "cadastro": "Cadastro (preenche só o que foi dito)", "exclusao": "Exclusão (pede o registro certo)", "fora_de_escopo": "Fora de escopo (admite que não sabe)",
           "conversa": "Conversa (saudação, agradecimento)", "sinonimo": "Sinônimos (busca semântica)", "seguranca": "Segurança (vazamento, troca de papel, ordem embutida)"}


def relatorio_md(r: dict, data: str = "", origem: str = "") -> str:
    linhas = ["# Avaliação do assistente", ""]
    if data or origem:
        linhas += [f"Rodada em {data} contra {origem}.".strip(), ""]
    linhas += [f"**Resultado geral: {r['acertos']}/{r['total']} ({taxa(r['acertos'], r['total']):.0%})**", "",
               "| Grupo | Acertos | Taxa |", "|---|---|---|"]
    for g, d in r["grupos"].items():
        linhas.append(f"| {TITULOS.get(g, g)} | {d['acertos']}/{d['total']} | {taxa(d['acertos'], d['total']):.0%} |")
    if r["latencia_media_ms"] is not None:
        linhas += ["", f"Latência: média {r['latencia_media_ms']} ms, p95 {r['latencia_p95_ms']} ms (inclui a rede e, na 1ª chamada, a partida a frio do servidor).",
                   f"Chamadas ao modelo: {r['com_llm']} dos {r['total']} casos."]
    falhas = [(g, c) for g, d in r["grupos"].items() for c in d["casos"] if not c["ok"]]
    if falhas:
        linhas += ["", "## O que falhou", ""]
        for g, c in falhas:
            linhas.append(f"- `{c['id']}` “{c['pergunta']}”: " + "; ".join(c["falhas"]))
    return "\n".join(linhas) + "\n"
