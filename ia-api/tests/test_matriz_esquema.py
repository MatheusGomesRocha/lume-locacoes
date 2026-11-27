"""A matriz gerada a partir do esquema: perguntas de todos os módulos, com gabarito calculado à parte, passando pelo chat inteiro (sem modelo)."""
import pytest

from avaliacao import matriz_esquema as m
from evolucao.esquema import ESQUEMA, VOCABULARIO

# Valores de enum que ficam fora da matriz de propósito (palavra comum demais: "usuário", "master").
SEM_FRASE = {("usuarios", "papel", "master"), ("usuarios", "papel", "usuario")}


@pytest.fixture(scope="module")
def r():
    return m.rodar()  # uma rodada só para o arquivo inteiro (leva uns 20 s)


def test_nenhuma_pergunta_gerada_falha(r):
    novas = m.novas_falhas(r)
    resumo = "\n".join(f"{k}: {len(v)} falhas, ex.: {v[0]['pergunta']} -> {v[0]['motivo']}" for k, v in novas.items())
    assert not novas, resumo
    assert not r["invalidas"], r["invalidas"]
    assert r["total"] >= 1000  # a matriz não pode encolher em silêncio


def test_todo_modulo_do_esquema_tem_vocabulario_para_a_matriz():
    assert set(ESQUEMA) <= set(VOCABULARIO), f"módulo sem vocabulário: {set(ESQUEMA) - set(VOCABULARIO)}"
    for ent, esq in ESQUEMA.items():
        datas = {c for c, d in esq["campos"].items() if d["tipo"] == "data"}
        assert datas <= set(VOCABULARIO[ent]["datas"]), f"{ent}: data sem vocabulário: {datas - set(VOCABULARIO[ent]['datas'])}"
        faladas = {(c, v) for (c, v) in VOCABULARIO[ent]["valores"]}
        for c, d in esq["campos"].items():
            if d["tipo"] == "enum":
                for v in d["valores"]:
                    assert (c, v) in faladas or (ent, c, v) in SEM_FRASE or (c == "status" and v == "pago" and ent == "pagamentos"), f"{ent}.{c}={v} sem frase no vocabulário"


def test_consulta_que_nao_filtra_algo_do_pedido_nunca_responde_o_total_geral(r):
    assert not [k for k in r["falhas"] if k.endswith("/lacuna") or k.endswith("/ambiguidade")], r["falhas"]
