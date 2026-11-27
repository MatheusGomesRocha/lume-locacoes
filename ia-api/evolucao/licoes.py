"""Lições aprendidas: erros que os Agents já cometeram, escritos como "quando pedirem X, faça Y, evite Z".

Entram no prompt do Analista e do Construtor (só as que valem para a pergunta, para o prompt não crescer). O TESTER não recebe
lições: o esperado dele é escrito sem ver a implementação, e lição sobre número esperado vazaria resposta. Lição é reforço, não
garantia: o modelo pode ignorar, então o que dá para impedir por código continua sendo código (checagens e correções).
Toda lição com `pergunta_de_exemplo` tem teste que confere que ela é escolhida para essa pergunta (matriz dos Agents).
"""
import json
import re
import unicodedata
from pathlib import Path

CAMINHO = Path(__file__).with_name("licoes.json")
MAXIMO_POR_PROMPT = 6


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def carregar() -> list[dict]:
    return json.loads(CAMINHO.read_text(encoding="utf-8"))


def selecionar(agente: str, texto: str, licoes: list[dict] | None = None) -> list[dict]:
    """As lições para este agente: as 'sempre' e as cujo gatilho aparece no texto (perguntas ou proposta). No máximo 6."""
    t = _sem_acento(texto)
    escolhidas = []
    for l in (licoes if licoes is not None else carregar()):
        if agente not in l["agentes"]:
            continue
        if l.get("sempre") or any(re.search(g, t) for g in l.get("gatilhos", [])):
            escolhidas.append({k: l[k] for k in ("id", "fazer", "evitar", "exemplo") if k in l})
    return escolhidas[:MAXIMO_POR_PROMPT]
