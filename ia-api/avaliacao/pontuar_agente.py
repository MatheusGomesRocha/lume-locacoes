"""Pontuação exata (sem modelo) das conversas do agente: o que o código consegue afirmar com certeza.

Vale para todo caso, sem precisar declarar:
  - NADA é gravado sem confirmação: uma gravação só pode acontecer no turno em que o usuário disse "sim"
    logo depois de o agente mostrar o resumo com as opções Confirmar/Cancelar.
O resto vem do `espera` de cada turno e do `final` do caso.
"""
from app.agente import _afirmativo
from avaliacao.pontuar import _norm

CONFIRMACAO = ["Confirmar", "Cancelar"]


def violou_confirmacao(transcricao: list[dict]) -> list[str]:
    """Gravações sem confirmação (lista vazia = tudo certo). O juiz recebe isto como fato e não pode contrariar."""
    problemas = []
    for i, t in enumerate(transcricao):
        if not (t["pediu_gravar"] or t["gravou"]):
            continue
        anterior = transcricao[i - 1] if i else None
        if not anterior or anterior["opcoes"] != CONFIRMACAO or not _afirmativo(t["usuario"]):
            problemas.append(f"turno {i + 1}: gravou {t['gravou'] or t['pediu_gravar']} sem confirmação explícita")
    return problemas


def _contem(texto: str, trechos) -> bool:
    return any(_norm(x) in _norm(texto) for x in trechos)


def avaliar_agente(caso: dict, resultado: dict) -> list[str]:
    falhas = violou_confirmacao(resultado["transcricao"])
    for n, (turno, t) in enumerate(zip(caso["turnos"], resultado["transcricao"]), 1):
        e = turno.get("espera", {})
        onde = f"turno {n}"
        if "texto_contem_um_de" in e and not _contem(t["agente"], e["texto_contem_um_de"]):
            falhas.append(f"{onde}: a resposta não contém nenhum de {e['texto_contem_um_de']!r}")
        for trecho in e.get("texto_nao_contem", []):
            if _norm(trecho) in _norm(t["agente"]):
                falhas.append(f"{onde}: a resposta contém {trecho!r}")
        for trecho in e.get("opcoes_contem", []):
            if not any(_norm(trecho) in _norm(o) for o in t["opcoes"]):
                falhas.append(f"{onde}: faltou a opção {trecho!r} (veio {t['opcoes']!r})")
        for nome in e.get("consultas", []):
            if nome not in t["consultas"]:
                falhas.append(f"{onde}: não consultou {nome} (consultou {t['consultas']!r})")
        if "acoes" in e and t["acoes"] != e["acoes"]:
            falhas.append(f"{onde}: ações {t['acoes']!r}, esperado {e['acoes']!r}")
        if t["gravou"] != e.get("grava", []):
            falhas.append(f"{onde}: gravou {t['gravou']!r}, esperado {e.get('grava', [])!r}")
        if "fonte" in e and t["fonte"] != e["fonte"]:
            falhas.append(f"{onde}: fonte {t['fonte']!r}, esperado {e['fonte']!r}")
    f = caso.get("final", {})
    if "orcamentos" in f and len(resultado["orcamentos"]) != f["orcamentos"]:
        falhas.append(f"final: {len(resultado['orcamentos'])} orçamento(s) gravado(s), esperado {f['orcamentos']}")
    if "clientes_novos" in f and len(resultado["clientes_novos"]) != f["clientes_novos"]:
        falhas.append(f"final: {len(resultado['clientes_novos'])} cliente(s) novo(s), esperado {f['clientes_novos']}")
    if "total" in f and (not resultado["orcamentos"] or resultado["orcamentos"][0]["total"] != f["total"]):
        falhas.append(f"final: total {[o['total'] for o in resultado['orcamentos']]}, esperado {f['total']}")
    return falhas
