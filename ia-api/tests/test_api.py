"""Testes dos endpoints, do CORS, do token e do limite de requisições."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app, identificar_visitante, origens_permitidas, registrar_sem_resposta

client = TestClient(app)


def perguntar(texto, **kw):
    r = client.post("/chat", json={"pergunta": texto}, **kw)
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
