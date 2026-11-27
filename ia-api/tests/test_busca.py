"""Testes de cada função de app/busca.py e da integridade do FAQ."""
import json
from pathlib import Path

import pytest

from app.busca import BaseConhecimento, Contexto, extrair_termos, normalizar, pede_dados_do_sistema, raiz

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
    "qual número do orçamento que será devolvido hoje?",
    "quais orçamentos foram criados ontem",
    "quais clientes foram cadastrados esta semana?",
])
def test_pede_dados_detecta_pedidos_de_numeros(pergunta):
    assert pede_dados_do_sistema(pergunta) is True


@pytest.mark.parametrize("pergunta", [
    "como aprovar um orçamento",
    "por que não consigo listar os produtos",
    "o que significa pendente",
    "como criar um orçamento hoje?",
    "qual a previsão do tempo para amanhã",
    "o que significa status atrasado hoje",
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


# ---------- busca com contexto da conversa ----------
def ids(resultados):
    return [r.id for r in resultados]


def test_sem_contexto_a_pergunta_solta_acerta_o_assunto_errado(base):
    """O problema que motivou o recurso: sozinha, 'quero excluir' cai em orçamentos."""
    assert base.buscar("mas eu quero excluir")[0].id == "orc-excluir"


def test_contexto_resolve_pergunta_sem_assunto(base):
    ctx = Contexto(["mas e pra excluir produtos?"], "prod-excluir")
    resultados, mudou = base.buscar_com_contexto("mas eu quero excluir", ctx)
    assert resultados[0].id == "prod-excluir"
    assert mudou is True


def test_contexto_resolve_pergunta_sem_acao(base):
    ctx = Contexto(["mas e pra excluir produtos?"], "prod-excluir")
    resultados, _ = base.buscar_com_contexto("e para clientes?", ctx)
    assert resultados[0].id == "cli-excluir"


def test_assunto_citado_na_pergunta_vence_o_assunto_antigo(base):
    ctx = Contexto(["como excluir produto?"], "prod-excluir")
    resultados, _ = base.buscar_com_contexto("e para clientes?", ctx)
    assert "produt" not in {t for r in resultados[:1] for t in extrair_termos(r.pergunta)}


def test_pergunta_completa_nao_e_alterada_pelo_contexto(base):
    ctx = Contexto(["mas e pra excluir produtos?"], "prod-excluir")
    resultados, mudou = base.buscar_com_contexto("como aprovar um orçamento?", ctx)
    assert resultados == base.buscar("como aprovar um orçamento?")
    assert mudou is False


def test_sem_contexto_ou_contexto_vazio_e_igual_a_busca_normal(base):
    simples = base.buscar("quero excluir")
    assert base.buscar_com_contexto("quero excluir", None) == (simples, False)
    assert base.buscar_com_contexto("quero excluir", Contexto()) == (simples, False)


def test_contexto_nao_inventa_resposta_para_pergunta_sem_termos_conhecidos(base):
    ctx = Contexto(["como excluir produto?"], "prod-excluir")
    resultados, mudou = base.buscar_com_contexto("e o prazo?", ctx)
    assert resultados == [] and mudou is False


def test_so_a_ultima_pergunta_anterior_conta(base):
    ctx = Contexto(["como excluir produto?", "e para clientes?"], "cli-excluir")
    resultados, _ = base.buscar_com_contexto("e se eu quiser cancelar?", ctx)
    assert ids(resultados)[0] != "prod-excluir"


def test_ultimo_id_sozinho_da_bonus_ao_mesmo_modulo(base):
    sem, _ = base.buscar_com_contexto("excluir", None, limite=5)
    com, _ = base.buscar_com_contexto("excluir", Contexto(ultimo_id="cli-cadastro"), limite=5)
    score = lambda lista, i: next(r.score for r in lista if r.id == i)
    assert score(com, "cli-excluir") > score(sem, "cli-excluir")
    assert all(r.score <= 1.0 for r in com)


def test_modulo_do_item(base):
    assert base.modulo_do_item("prod-excluir") == "Produtos"
    assert base.modulo_do_item("nao-existe") is None
    assert base.modulo_do_item(None) is None


# ---------- assunto da conversa ----------
def test_faq_tem_como_editar_produto_e_cliente(base):
    assert base.buscar("como editar um produto")[0].id == "prod-editar"
    assert base.buscar("como editar um cliente")[0].id == "cli-editar"


def test_acompanhamento_de_editar_fica_no_assunto_da_conversa(base):
    ctx = Contexto(["como eu excluir produtos?"], "prod-excluir")
    assert base.buscar_com_contexto("e para editar?", ctx)[0][0].id == "prod-editar"
    ctx = Contexto(["como criar um orçamento?"], "orc-criar")
    assert base.buscar_com_contexto("e para editar?", ctx)[0][0].id == "orc-editar"


def test_assunto_da_conversa_so_existe_para_pergunta_incompleta(base):
    ctx = Contexto(["como eu excluir produtos?"], "prod-excluir")
    assert base.assunto_da_conversa("e para editar?", ctx) == "Produtos"
    assert base.assunto_da_conversa("e para clientes?", ctx) == "Clientes"  # o assunto citado vence
    assert base.assunto_da_conversa("como aprovar um orçamento?", ctx) is None
    assert base.assunto_da_conversa("e para editar?", None) is None
    assert base.assunto_da_conversa("e o prazo?", ctx) is None


def test_assunto_da_conversa_ignora_modulos_que_nao_sao_assunto(base):
    assert base.assunto_da_conversa("e para editar?", Contexto(ultimo_id="assist-o-que-faz")) is None
