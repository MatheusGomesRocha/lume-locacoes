import pytest

from app.conversa import resposta_de_conversa
from tests.test_api import perguntar


@pytest.mark.parametrize("texto", ["oi", "Oi!", "Olá", "bom dia", "obrigado!", "Obrigada", "valeu", "tchau", "até logo"])
def test_papo_social_recebe_resposta_amigavel(texto):
    assert resposta_de_conversa(texto)


@pytest.mark.parametrize("texto", ["oi, como crio um orçamento?", "obrigado, e para aprovar?", "como criar um orçamento", "", "excluir cliente"])
def test_pergunta_de_verdade_nao_vira_papo(texto):
    assert resposta_de_conversa(texto) is None


def test_chat_responde_oi_sem_dizer_que_nao_encontrou_e_sem_gastar_o_modelo():
    r = perguntar("oi")
    assert r["encontrou"] is True
    assert "não encontrei" not in r["resposta"].lower()
    assert r["gerada_por_llm"] is False
