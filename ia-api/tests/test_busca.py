"""Testes de cada função de app/busca.py e da integridade do FAQ."""
import json
from pathlib import Path

import pytest

from app.busca import BaseConhecimento, extrair_termos, normalizar, pede_dados_do_sistema, raiz

FAQ = Path(__file__).resolve().parent.parent / "data" / "faq.json"


@pytest.fixture(scope="module")
def base():
    return BaseConhecimento(FAQ)


# ---------- normalizar ----------
@pytest.mark.parametrize("entrada,esperado", [
    ("Orçamento!", "orcamento"),
    ("  CANCELAR   o  pedido?? ", "cancelar o pedido"),
    ("e-mail & cia.", "e mail cia"),
    ("Ação — Ñandú", "acao nandu"),
    ("", ""),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


# ---------- raiz ----------
def test_raiz_junta_formas_da_mesma_palavra():
    assert raiz("aprovar") == raiz("aprovado") == raiz("aprovacao") == "aprova"


def test_raiz_remove_plural():
    assert raiz("orcamentos") == raiz("orcamento")


def test_raiz_aplica_sinonimos():
    assert raiz("deletar") == raiz("apagar") == raiz("excluir")
    assert raiz("cobranca") == raiz("pagamento")


def test_raiz_nao_mexe_em_palavra_curta():
    assert raiz("sol") == "sol"


# ---------- extrair_termos ----------
def test_extrair_termos_remove_palavras_sem_valor():
    assert extrair_termos("como faço para aprovar o orçamento?") == [raiz("aprovar"), raiz("orcamento")]


def test_extrair_termos_vazio():
    assert extrair_termos("") == []
    assert extrair_termos("de a o") == []


def test_extrair_termos_reconhece_frases_de_problema():
    problema = raiz("problema")
    assert problema in extrair_termos("não consigo aprovar")
    assert problema in extrair_termos("o botão não funciona")
    assert problema not in extrair_termos("como aprovar")


def test_extrair_termos_mantem_numeros():
    assert "2026" in extrair_termos("orçamento 2026")


# ---------- pede_dados_do_sistema ----------
@pytest.mark.parametrize("pergunta", [
    "quantos orçamentos aprovados eu tenho?",
    "Liste os clientes de Fortaleza",
    "mostre o financeiro",
    "quantas cobranças estão atrasadas",
])
def test_pede_dados_detecta_pedidos_de_numeros(pergunta):
    assert pede_dados_do_sistema(pergunta) is True


@pytest.mark.parametrize("pergunta", [
    "como aprovar um orçamento",
    "por que não consigo listar os produtos",
    "o que significa pendente",
    "",
])
def test_pede_dados_ignora_duvidas_de_uso(pergunta):
    assert pede_dados_do_sistema(pergunta) is False


# ---------- BaseConhecimento ----------
def test_base_carrega_todo_o_faq(base):
    assert len(base.itens) >= 30
    assert len(base.vetores) == len(base.normas) == len(base.itens)


def test_buscar_ordena_por_score_e_respeita_limite(base):
    r = base.buscar("como aprovar um orçamento", limite=3)
    assert len(r) <= 3
    assert [x.score for x in r] == sorted((x.score for x in r), reverse=True)
    assert r[0].id == "orc-aprovar"


def test_buscar_score_fica_entre_zero_e_um(base):
    for x in base.buscar("cancelar orçamento aprovado cobrança", limite=10):
        assert 0 < x.score <= 1.0001


def test_buscar_sem_termos_conhecidos_devolve_vazio(base):
    assert base.buscar("zzzz xxxx qqqq") == []
    assert base.buscar("") == []


def test_buscar_a_propria_pergunta_acha_o_item(base):
    for item in base.itens:
        assert base.buscar(item["pergunta"], limite=1)[0].id == item["id"], item["pergunta"]


# ---------- integridade do FAQ ----------
def test_faq_ids_unicos_e_campos_preenchidos():
    itens = json.loads(FAQ.read_text(encoding="utf-8"))
    ids = [i["id"] for i in itens]
    assert len(ids) == len(set(ids))
    for i in itens:
        assert i["pergunta"].endswith("?")
        assert len(i["resposta"]) > 40
        assert i["modulo"] and i["palavras_chave"]
