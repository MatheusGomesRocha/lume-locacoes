"""Travas por código em volta do modelo: ele pode errar ao interpretar, mas o erro não chega ao usuário como se fosse certo.

1. `seguimento_confere`: a pergunta reescrita (de "e quais os nomes deles?") tem que continuar sobre o assunto da conversa e
   pedir o mesmo tipo de coisa (nomes, quantidade, valor) que a pessoa pediu. Se não, a Lumi pergunta em vez de chutar.
2. `texto_confere_com_dados`: todo número do texto que o modelo redigiu tem que existir nos dados consultados (ou na pergunta).
   Se aparecer número inventado, o texto é descartado e a resposta sai montada por código.
"""
import json
import re

from app.ferramentas import _sem_acento
from evolucao.consulta import palavras, tipo_da_pergunta

_VAZIAS = {"de", "da", "do", "das", "dos", "e", "o", "a", "os", "as", "um", "uma", "que", "foram", "sao", "ser", "eles", "elas", "deles", "delas", "qual", "quais", "quantos", "quantas", "me", "para", "por", "em", "no", "na", "nos", "nas", "com", "voce", "consegue", "ja"}


def _conteudo(t: str) -> set[str]:
    return {p for p in palavras(_sem_acento(t)) if p not in _VAZIAS and len(p) > 2}


def seguimento_confere(original: str, completa: str, historico: list[str]) -> bool:
    if tipo_da_pergunta(original) and tipo_da_pergunta(completa) != tipo_da_pergunta(original):
        return False  # a pessoa pediu "nomes" e a reescrita virou "quantos" (ou o contrário)
    assunto = set().union(*(_conteudo(h) for h in historico[-3:])) if historico else set()
    return bool(_conteudo(completa) & assunto)  # a reescrita traz o assunto da conversa


def _numeros(t: str) -> set[int]:
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", str(t))  # 1.234,56 -> 1234,56
    return {int(g) for g in re.findall(r"\d+", t)}


def texto_confere_com_dados(texto: str, resultados: list[dict], pergunta: str = "", hoje: str | None = None) -> bool:
    permitidos = _numeros(json.dumps(resultados, ensure_ascii=False)) | _numeros(pergunta) | _numeros(hoje or "") | {0, 1}
    for r in resultados:  # "3 primeiros", "15 linhas": contagens de lista são válidas
        res = r.get("resultado") if isinstance(r, dict) else None
        if isinstance(res, dict):
            permitidos |= {len(v) for v in res.values() if isinstance(v, list)}
    return _numeros(texto) <= permitidos


def texto_seguro(resultados: list[dict]) -> str:
    """Resposta mínima, montada só com o que veio dos dados (usada quando o texto do modelo não confere)."""
    partes = []
    for r in resultados:
        res = r.get("resultado") if isinstance(r, dict) else None
        if isinstance(res, dict) and "total" in res:
            partes.append(f"Encontrei {res['total']} resultado(s) na consulta {r.get('nome', '').replace('consultar_', '')}.")
    return " ".join(partes) or "Não consegui montar a resposta com segurança. Tente reformular a pergunta."
