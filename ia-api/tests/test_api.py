"""Testes dos endpoints, do CORS, do token e do limite de requisições."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.llm import ErroLLM, LimitadorDiario
from app.main import app, identificar_visitante, origens_permitidas, registrar_sem_resposta

client = TestClient(app)


def perguntar(texto, **kw):
    r = client.post("/chat", json={"pergunta": texto}, **kw)
    assert r.status_code == 200, r.text
    return r.json()


def perguntar_com_contexto(texto, historico=None, ultimo_id=None):
    corpo = {"pergunta": texto, "historico": historico or [], "ultimo_id": ultimo_id}
    r = client.post("/chat", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def test_raiz_e_health():
    assert client.get("/").json()["docs"] == "/docs"
    saude = client.get("/health").json()
    assert saude["status"] == "ok" and saude["perguntas_na_base"] >= 30


def test_lista_faq():
    itens = client.get("/faq").json()
    assert len(itens) >= 30
    assert set(itens[0]) == {"id", "modulo", "pergunta"}


@pytest.mark.parametrize("pergunta,id_esperado", [
    ("como criar um orçamento", "orc-criar"),
    ("como o número do orçamento é gerado", "orc-numero"),
    ("como é calculado o total do orçamento", "orc-calculo"),
    ("como as diárias são contadas", "orc-diarias"),
    ("quais os status do orçamento", "orc-status"),
    ("posso editar um orçamento aprovado", "orc-editar"),
    ("como aprovar um orçamento", "orc-aprovar"),
    ("por que não consigo aprovar o orçamento", "orc-disponibilidade"),
    ("como finalizar o orçamento", "orc-finalizar"),
    ("como cancelar um orçamento", "orc-cancelar"),
    ("como deletar um orçamento", "orc-excluir"),
    ("se eu mudar o preço do produto os orçamentos mudam", "orc-preco-congelado"),
    ("quando a cobrança é criada", "fin-cobranca"),
    ("como registrar um pagamento recebido", "fin-baixa"),
    ("o que significam os status das cobranças", "fin-status"),
    ("quais dados preencher ao cadastrar um produto", "prod-cadastro"),
    ("como tirar um produto de circulação", "prod-inativar"),
    ("por que não consigo excluir um produto", "prod-excluir"),
    ("como cadastrar um cliente", "cli-cadastro"),
    ("por que não consigo excluir um cliente", "cli-excluir"),
    ("onde ficam os dados na versão de demonstração", "demo-dados"),
    ("como voltar aos dados de exemplo", "demo-restaurar"),
    ("o que o assistente pode fazer", "assist-oque"),
])
def test_chat_encontra_a_pergunta_certa(pergunta, id_esperado):
    r = perguntar(pergunta)
    assert r["encontrou"] is True, r
    assert r["fonte"]["id"] == id_esperado, r
    assert r["resposta"] and 0 < r["confianca"] <= 1.0001


def test_chat_devolve_relacionadas_sem_repetir_a_fonte():
    r = perguntar("como aprovar um orçamento")
    assert r["relacionadas"] and all(x["id"] != r["fonte"]["id"] for x in r["relacionadas"])


@pytest.mark.parametrize("pergunta", ["qual a previsão do tempo para amanhã", "asdfgh qwerty", "receita de bolo de chocolate"])
def test_chat_recusa_o_que_nao_esta_na_base(pergunta, log_sem_resposta):
    r = perguntar(pergunta)
    assert r["encontrou"] is False and r["fonte"] is None
    ultima = json.loads(log_sem_resposta.read_text(encoding="utf-8").splitlines()[-1])
    assert ultima["pergunta"] == pergunta and ultima["tipo"] == "faq"


@pytest.mark.parametrize("pergunta", ["quantos orçamentos aprovados eu tenho?", "liste os clientes", "quantas cobranças atrasadas"])
def test_chat_recusa_pedidos_de_dados(pergunta, log_sem_resposta):
    r = perguntar(pergunta)
    assert r["encontrou"] is False
    assert "consigo consultar" in r["resposta"]
    assert json.loads(log_sem_resposta.read_text(encoding="utf-8").splitlines()[-1])["tipo"] == "dados"


def test_chat_valida_a_pergunta():
    assert client.post("/chat", json={"pergunta": ""}).status_code == 422
    assert client.post("/chat", json={"pergunta": "x" * 501}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422


def test_token_so_e_exigido_quando_configurado(monkeypatch):
    assert client.post("/chat", json={"pergunta": "como aprovar"}).status_code == 200
    monkeypatch.setenv("IA_API_TOKEN", "segredo")
    assert client.post("/chat", json={"pergunta": "como aprovar"}).status_code == 401
    assert client.get("/faq").status_code == 401
    ok = client.post("/chat", json={"pergunta": "como aprovar"}, headers={"X-API-Token": "segredo"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200  # a saúde nunca exige token


def test_cors_libera_o_site_configurado_e_bloqueia_os_outros():
    ok = client.options("/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    ruim = client.options("/chat", headers={"Origin": "https://site-malicioso.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in ruim.headers


def test_origens_permitidas_le_o_ambiente(monkeypatch):
    monkeypatch.setenv("IA_ORIGENS_PERMITIDAS", " https://fulano.github.io/ , https://outro.com ,, ")
    assert origens_permitidas() == ["https://fulano.github.io", "https://outro.com"]
    monkeypatch.delenv("IA_ORIGENS_PERMITIDAS")
    assert "http://localhost:5173" in origens_permitidas()


def test_limite_de_requisicoes_devolve_429():
    main.limitador.maximo = 2
    assert client.post("/chat", json={"pergunta": "como aprovar"}).status_code == 200
    assert client.post("/chat", json={"pergunta": "como aprovar"}).status_code == 200
    r = client.post("/chat", json={"pergunta": "como aprovar"})
    assert r.status_code == 429 and "Aguarde" in r.json()["detail"]


def test_limite_usa_o_ip_encaminhado_pelo_proxy():
    main.limitador.maximo = 1
    a = {"X-Forwarded-For": "203.0.113.1, 10.0.0.1"}
    b = {"X-Forwarded-For": "203.0.113.2"}
    assert client.post("/chat", json={"pergunta": "como aprovar"}, headers=a).status_code == 200
    assert client.post("/chat", json={"pergunta": "como aprovar"}, headers=a).status_code == 429
    assert client.post("/chat", json={"pergunta": "como aprovar"}, headers=b).status_code == 200


def test_identificar_visitante():
    class Req:
        def __init__(self, headers, host):
            self.headers, self.client = headers, type("C", (), {"host": host})() if host else None
    assert identificar_visitante(Req({"x-forwarded-for": "1.1.1.1, 2.2.2.2"}, "9.9.9.9")) == "1.1.1.1"
    assert identificar_visitante(Req({}, "9.9.9.9")) == "9.9.9.9"
    assert identificar_visitante(Req({}, None)) == "desconhecido"


def test_registrar_sem_resposta_grava_uma_linha_json(log_sem_resposta):
    registrar_sem_resposta("pergunta de teste", 0.12)
    registrar_sem_resposta("outra", 0.0, tipo="dados")
    linhas = [json.loads(x) for x in log_sem_resposta.read_text(encoding="utf-8").splitlines()]
    assert [l["pergunta"] for l in linhas] == ["pergunta de teste", "outra"]
    assert linhas[1]["tipo"] == "dados" and linhas[0]["melhor_score"] == 0.12


# ---------- contexto da conversa ----------
def test_chat_entende_o_acompanhamento_da_conversa():
    primeira = perguntar("mas e pra excluir produtos?")
    assert primeira["fonte"]["id"] == "prod-excluir"
    segunda = perguntar_com_contexto("mas eu quero excluir", ["mas e pra excluir produtos?"], primeira["fonte"]["id"])
    assert segunda["fonte"]["id"] == "prod-excluir"
    assert segunda["usou_contexto"] is True


def test_chat_sem_contexto_continua_funcionando():
    r = perguntar("mas eu quero excluir")
    assert r["fonte"]["id"] == "orc-excluir"
    assert r["usou_contexto"] is False


def test_chat_pergunta_completa_ignora_o_historico():
    r = perguntar_com_contexto("Como criar um orçamento?", ["como excluir produto?"], "prod-excluir")
    assert r["fonte"]["id"] == "orc-criar" and r["usou_contexto"] is False


def test_chat_aceita_ultimo_id_desconhecido():
    r = perguntar_com_contexto("Como criar um orçamento?", ["oi"], "id-que-nao-existe")
    assert r["encontrou"] is True


def test_chat_valida_o_tamanho_do_historico():
    assert client.post("/chat", json={"pergunta": "oi tudo", "historico": ["a"] * 7}).status_code == 422
    assert client.post("/chat", json={"pergunta": "oi tudo", "historico": ["a" * 501]}).status_code == 422
    assert client.post("/chat", json={"pergunta": "oi tudo", "ultimo_id": "x" * 81}).status_code == 422


def test_chat_ignora_historico_em_branco():
    r = perguntar_com_contexto("Como criar um orçamento?", ["   ", ""])
    assert r["fonte"]["id"] == "orc-criar"


def test_resposta_de_dados_e_de_nao_encontrado_trazem_usou_contexto_falso():
    assert perguntar("quantos orçamentos eu tenho?")["usou_contexto"] is False
    assert perguntar("receita de bolo de chocolate")["usou_contexto"] is False


# ---------- LLM (sempre com provedor falso) ----------
class ProvedorFalso:
    def __init__(self, texto="Resposta redigida pelo modelo.", erro=None):
        self.texto, self.erro, self.chamadas = texto, erro, []

    def gerar(self, sistema, usuario):
        self.chamadas.append(usuario)
        if self.erro:
            raise self.erro
        return self.texto


@pytest.fixture
def com_llm(monkeypatch):
    def ligar(provedor, limite=100):
        monkeypatch.setattr(main, "provedor_llm", provedor)
        monkeypatch.setattr(main, "limitador_llm", LimitadorDiario(limite))
        return provedor
    return ligar


def test_sem_llm_a_resposta_vem_do_faq(monkeypatch):
    monkeypatch.setattr(main, "provedor_llm", None)
    r = perguntar("Como criar um orçamento?")
    assert r["gerada_por_llm"] is False and r["fonte"]["id"] == "orc-criar"
    assert client.get("/health").json()["llm"] is False


def test_com_llm_a_resposta_e_redigida_pelo_modelo(com_llm):
    p = com_llm(ProvedorFalso())
    r = perguntar("Como criar um orçamento?")
    assert r["resposta"] == "Resposta redigida pelo modelo." and r["gerada_por_llm"] is True
    assert r["fonte"]["id"] == "orc-criar"
    assert "Como criar um orçamento?" in p.chamadas[0]
    assert client.get("/health").json()["llm"] is True


def test_llm_recebe_o_historico_da_conversa(com_llm):
    p = com_llm(ProvedorFalso())
    perguntar_com_contexto("mas eu quero excluir", ["como excluir produto"], "prod-excluir")
    assert "como excluir produto" in p.chamadas[0]
    assert "Por que não consigo excluir um produto?" in p.chamadas[0]


def test_llm_com_erro_cai_no_faq(com_llm):
    com_llm(ProvedorFalso(erro=ErroLLM("fora do ar")))
    r = perguntar("Como criar um orçamento?")
    assert r["gerada_por_llm"] is False and r["encontrou"] is True and "orçamento" in r["resposta"].lower()
    assert r["resposta"] != "Resposta redigida pelo modelo."


def test_teto_diario_do_llm_cai_no_faq(com_llm):
    p = com_llm(ProvedorFalso(), limite=1)
    assert perguntar("Como criar um orçamento?")["gerada_por_llm"] is True
    assert perguntar("Como criar um orçamento?")["gerada_por_llm"] is False
    assert len(p.chamadas) == 1


def test_llm_nao_e_chamado_quando_o_faq_nao_acha_nada(com_llm):
    p = com_llm(ProvedorFalso())
    r = perguntar("receita de bolo de chocolate")
    assert r["encontrou"] is False and r["gerada_por_llm"] is False and p.chamadas == []


def test_llm_nao_e_chamado_para_pedido_de_dados(com_llm):
    p = com_llm(ProvedorFalso())
    r = perguntar("quantos orçamentos eu tenho?")
    assert r["gerada_por_llm"] is False and p.chamadas == []
