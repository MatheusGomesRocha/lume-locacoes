"""Quanto cada pergunta gastou do modelo (tokens e custo estimado).

O provedor é um só para todas as perguntas, então a soma de uma pergunta fica num ContextVar: cada pedido do FastAPI
roda no seu próprio contexto e só enxerga os tokens das chamadas que ele mesmo fez.
O Gemini devolve a contagem em `usageMetadata`; o custo é uma ESTIMATIVA pelo preço do plano pago (o plano gratuito não cobra).
"""
from __future__ import annotations

import os
from contextvars import ContextVar

# US$ por 1 milhão de tokens (ajuste pelo ambiente se o Google mudar a tabela de preços).
PRECO_ENTRADA_USD = float(os.getenv("IA_PRECO_ENTRADA_USD", "0.10"))
PRECO_SAIDA_USD = float(os.getenv("IA_PRECO_SAIDA_USD", "0.40"))

_atual: ContextVar[dict | None] = ContextVar("consumo_da_pergunta", default=None)


def custo_usd(entrada: int, saida: int) -> float:
    return round((entrada * PRECO_ENTRADA_USD + saida * PRECO_SAIDA_USD) / 1_000_000, 6)


def iniciar() -> None:
    _atual.set({"chamadas": 0, "entrada": 0, "saida": 0})


def somar(entrada: int, saida: int) -> None:
    c = _atual.get()
    if c is not None:
        c["chamadas"] += 1
        c["entrada"] += max(0, int(entrada))
        c["saida"] += max(0, int(saida))


def somar_da_resposta(corpo: dict) -> None:
    """Lê o `usageMetadata` de uma resposta do Gemini (formato inesperado conta como zero, nunca quebra a resposta)."""
    try:
        u = corpo.get("usageMetadata") or {}
        entrada = int(u.get("promptTokenCount") or 0)
        saida = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    except (AttributeError, TypeError, ValueError):
        return
    somar(entrada, saida)


def resumo() -> dict | None:
    """O consumo da pergunta atual, ou None se ela não chamou o modelo."""
    c = _atual.get()
    if not c or not c["chamadas"]:
        return None
    return {**c, "custo_usd": custo_usd(c["entrada"], c["saida"])}
