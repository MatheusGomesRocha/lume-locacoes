"""Lê o arquivo "Baixar erros do Tester" (tela de Evolução) e mostra o que se repete, para virar correção no código.

  python -m avaliacao.erros_tester erros-do-tester-2026-11-26.json

Cada erro do Tester cai numa de sete famílias (caso falhou, checagem falhou, corrigido ou descartado pelo código, dúvida do Tester,
aviso do revisor, achado). O que se repete em relatórios diferentes é o que merece uma correção por código, e depois um caso na matriz.
"""
import json
import re
import sys
from collections import Counter


def _molde(texto: str) -> str:
    """O texto sem os números e sem o que está entre aspas: "Busca 7 dias" e "Busca 15 dias" são o mesmo erro."""
    t = re.sub(r"“[^”]*”|\"[^\"]*\"|'[^']*'", "“…”", texto)
    return re.sub(r"\d+", "N", t)[:140]


def resumir(dados: dict) -> str:
    itens = dados.get("itens", [])
    por_tipo = Counter(i["tipo"] for i in itens)
    L = [f"# Erros do Tester: {len(itens)} em {len({i['relatorio'] for i in itens})} relatórios", ""]
    L += [f"- {t}: {n}" for t, n in por_tipo.most_common()]
    L += ["", "## O que se repete (mesmo molde em 2 ou mais relatórios)"]
    moldes: dict[tuple, set] = {}
    for i in itens:
        moldes.setdefault((i["tipo"], _molde(i["texto"])), set()).add(i["relatorio"])
    repetidos = sorted(((len(r), k) for k, r in moldes.items() if len(r) > 1), reverse=True)
    L += [f"- {n}x [{t}] {m}" for n, (t, m) in repetidos] or ["- nada repetido ainda"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    print(resumir(json.load(open(sys.argv[1], encoding="utf-8"))))
