from fastapi.testclient import TestClient

from app import consumo, main
from app.llm import ProvedorGemini


def test_soma_tokens_do_gemini_e_estima_o_custo():
    consumo.iniciar()
    consumo.somar_da_resposta({"usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200, "thoughtsTokenCount": 50}})
    consumo.somar_da_resposta({"usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 100}})
    r = consumo.resumo()
    assert (r["chamadas"], r["entrada"], r["saida"]) == (2, 1500, 350)
    assert r["custo_usd"] == consumo.custo_usd(1500, 350) > 0


def test_pergunta_sem_modelo_nao_tem_consumo_e_resposta_estranha_conta_zero():
    consumo.iniciar()
    consumo.somar_da_resposta({"usageMetadata": "lixo"})
    consumo.somar_da_resposta({})
    assert consumo.resumo()["entrada"] == 0  # chamou o modelo, mas o provedor não informou: conta a chamada com 0
    consumo.iniciar()
    assert consumo.resumo() is None


def test_chat_devolve_versao_e_so_devolve_consumo_quando_usou_o_modelo():
    cliente = TestClient(main.app)
    r = cliente.post("/chat", json={"pergunta": "como criar um orçamento"}).json()
    assert r["versao"] == main.VERSAO and "consumo" not in r


def test_provedor_registra_o_consumo_da_chamada():
    class Resp:
        status_code = 200
        headers: dict = {}
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "oi"}]}}], "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 5}}

    class Cli:
        def post(self, *a, **k):
            return Resp()

    consumo.iniciar()
    assert ProvedorGemini("k", cliente=Cli()).gerar("s", "u") == "oi"
    assert consumo.resumo()["entrada"] == 40 and consumo.resumo()["saida"] == 5
