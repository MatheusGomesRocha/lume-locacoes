"""Busca semântica: índice, margem de segurança, falhas e integração com o /chat (com embedder de mentira)."""
import pytest
from fastapi.testclient import TestClient

from app import main, semantica
from app.semantica import ErroEmbedding, IndiceSemantico, cosseno, vencedor_confiavel

ITENS = [
    {"id": "a", "modulo": "Acesso", "pergunta": "Como cadastrar um usuário?", "resposta": "x", "palavras_chave": ["novo usuário"]},
    {"id": "b", "modulo": "Produtos", "pergunta": "Como excluir um produto?", "resposta": "y", "palavras_chave": []},
]


class EmbedderFalso:
    """Vetores de 2 dimensões escolhidos a dedo: 'pessoa' fica perto do item a, 'banana' longe de tudo."""
    def __init__(self):
        self.chamadas = 0

    def documentos(self, textos):
        return [[1.0, 0.0] if "usuário" in t else [0.0, 1.0] for t in textos]

    def consulta(self, texto):
        self.chamadas += 1
        if "pessoa" in texto:
            return [0.98, 0.1]
        if "talvez" in texto:
            return [0.7, 0.7]
        return [0.6, 0.6] if "banana" in texto else [0.0, 0.0]


class EmbedderQueFalha:
    def documentos(self, textos): raise ErroEmbedding("sem rede")
    def consulta(self, texto): raise ErroEmbedding("sem rede")


def test_cosseno():
    assert cosseno([1, 0], [1, 0]) == pytest.approx(1)
    assert cosseno([1, 0], [0, 1]) == pytest.approx(0)
    assert cosseno([0, 0], [1, 1]) == 0.0


def test_indice_acha_o_item_pelo_significado():
    indice = IndiceSemantico(ITENS, EmbedderFalso())
    assert indice.buscar("pessoa nova") == []  # ainda não construiu
    assert indice.construir() and indice.pronto
    item, nota = indice.buscar("adicionar uma pessoa")[0]
    assert item["id"] == "a" and nota > 0.9


def test_consulta_repetida_nao_chama_o_embedder_de_novo():
    emb = EmbedderFalso()
    indice = IndiceSemantico(ITENS, emb)
    indice.construir()
    indice.buscar("pessoa"); indice.buscar("pessoa")
    assert emb.chamadas == 1


def test_teto_diario_impede_a_consulta():
    indice = IndiceSemantico(ITENS, EmbedderFalso(), permitir=lambda: False)
    indice.construir()
    assert indice.buscar("pessoa") == []


def test_falha_do_provedor_nao_quebra():
    indice = IndiceSemantico(ITENS, EmbedderQueFalha())
    assert indice.construir() is False and not indice.pronto and indice.erro == "sem rede"
    assert indice.buscar("pessoa") == []


def test_vencedor_precisa_de_nota_e_de_margem():
    assert vencedor_confiavel([({"id": "a"}, 0.9), ({"id": "b"}, 0.5)])
    assert not vencedor_confiavel([({"id": "a"}, 0.5), ({"id": "b"}, 0.1)])      # nota baixa
    assert not vencedor_confiavel([({"id": "a"}, 0.90), ({"id": "b"}, 0.89)])    # empate
    assert not vencedor_confiavel([])


# ---------- integração com o /chat ----------

class IndiceDeMentira:
    """Finge o índice: 'pessoa' aponta com clareza para acesso-usuario-criar."""
    pronto = True
    erro = None

    def __init__(self):
        self.perguntas = []

    def buscar(self, pergunta, limite=4):
        self.perguntas.append(pergunta)
        itens = {i["id"]: i for i in main.base.itens}
        if "pessoa" in pergunta:
            return [(itens["acesso-usuario-criar"], 0.9), (itens["cli-cadastro"], 0.6)]
        return [(itens["orc-criar"], 0.5), (itens["cli-cadastro"], 0.4)]


@pytest.fixture
def com_semantica(monkeypatch):
    indice = IndiceDeMentira()
    monkeypatch.setattr(main, "indice_semantico", indice)
    return indice


client = TestClient(main.app)


def perguntar(texto):
    r = client.post("/chat", json={"pergunta": texto})
    assert r.status_code == 200
    return r.json()


def test_sem_indice_nada_muda():
    assert main.indice_semantico is None  # os testes rodam sem GEMINI_API_KEY
    r = perguntar("como adicionar uma pessoa no sistema")
    assert r["encontrou"] is False


def test_sinonimo_que_o_tfidf_nao_conhece_e_resolvido_pelo_significado(com_semantica):
    r = perguntar("como adicionar uma pessoa no sistema")
    assert r["encontrou"] and r["fonte"]["id"] == "acesso-usuario-criar" and r["busca"] == "semantica"


def test_pergunta_sem_relacao_continua_sem_resposta(com_semantica):
    r = perguntar("receita de bolo de chocolate")
    assert r["encontrou"] is False  # nota 0.5 < limite


def test_pergunta_que_o_tfidf_resolve_bem_nao_gasta_embedding(com_semantica):
    r = perguntar("como criar um orçamento")
    assert r["fonte"]["id"] == "orc-criar" and r["busca"] == "lexical"
    assert com_semantica.perguntas == []


def test_health_informa_o_estado_da_busca_semantica():
    assert client.get("/health").json()["semantica"] == "desligada"
