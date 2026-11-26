"""Testes da camada de LLM. Nada aqui acessa a internet: o provedor real usa um transporte falso."""
import json
from datetime import date, timedelta

import httpx
import pytest

from app import llm
from app.llm import (ErroLLM, LimitadorDiario, ProvedorGemini, criar_provedor_do_ambiente, gerar_resposta,
                     limite_diario_do_ambiente, montar_pergunta)

TRECHOS = [("Como excluir um orçamento?", "Só rascunho ou cancelado."), ("Como cancelar?", "Use o botão Cancelar.")]


def gemini(handler, **kw):
    return ProvedorGemini("chave-de-teste", cliente=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def resposta_ok(texto="Olá!"):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})


class Falso:
    """Provedor de mentira que registra o que recebeu."""
    def __init__(self, texto="Resposta do modelo.", erro=None):
        self.texto, self.erro, self.chamadas = texto, erro, []

    def gerar(self, sistema, usuario):
        self.chamadas.append((sistema, usuario))
        if self.erro:
            raise self.erro
        return self.texto


# ---------- ProvedorGemini ----------
def test_gemini_monta_a_requisicao_e_le_a_resposta():
    vistos = {}

    def handler(req):
        vistos["url"], vistos["chave"], vistos["corpo"] = str(req.url), req.headers["x-goog-api-key"], json.loads(req.content)
        return resposta_ok("Texto do modelo")

    assert gemini(handler, modelo="modelo-x").gerar("SISTEMA", "USUARIO") == "Texto do modelo"
    assert vistos["url"].endswith("/models/modelo-x:generateContent")
    assert vistos["chave"] == "chave-de-teste"
    assert vistos["corpo"]["systemInstruction"]["parts"][0]["text"] == "SISTEMA"
    assert vistos["corpo"]["contents"][0]["parts"][0]["text"] == "USUARIO"
    assert vistos["corpo"]["generationConfig"]["maxOutputTokens"] <= 400


def test_gemini_nao_coloca_a_chave_na_url():
    vistos = {}
    gemini(lambda r: (vistos.update(url=str(r.url)) or resposta_ok())).gerar("s", "u")
    assert "chave-de-teste" not in vistos["url"]


def test_gemini_junta_varias_partes():
    h = lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Oi, "}, {"text": "tudo bem?"}]}}]})
    assert gemini(h).gerar("s", "u") == "Oi, tudo bem?"


@pytest.mark.parametrize("status", [400, 403, 429, 500, 503])
def test_gemini_erro_http_vira_erro_llm(status):
    with pytest.raises(ErroLLM, match=str(status)):
        gemini(lambda r: httpx.Response(status, json={"error": "x"})).gerar("s", "u")


@pytest.mark.parametrize("corpo", [{}, {"candidates": []}, {"candidates": [{"content": {}}]}, {"candidates": [{"content": {"parts": [{"text": "  "}]}}]}])
def test_gemini_resposta_inesperada_ou_vazia_vira_erro_llm(corpo):
    with pytest.raises(ErroLLM):
        gemini(lambda r: httpx.Response(200, json=corpo)).gerar("s", "u")


def test_gemini_resposta_que_nao_e_json_vira_erro_llm():
    with pytest.raises(ErroLLM):
        gemini(lambda r: httpx.Response(200, content=b"<html>")).gerar("s", "u")


def test_gemini_falha_de_rede_vira_erro_llm():
    def handler(req):
        raise httpx.ConnectTimeout("demorou", request=req)

    with pytest.raises(ErroLLM, match="rede"):
        gemini(handler).gerar("s", "u")


# ---------- LimitadorDiario ----------
def test_limitador_diario_conta_e_bloqueia():
    lim = LimitadorDiario(2)
    assert [lim.permitir(), lim.permitir(), lim.permitir()] == [True, True, False]
    assert lim.usadas == 2


def test_limitador_diario_zera_no_dia_seguinte():
    dia = [date(2026, 11, 25)]
    lim = LimitadorDiario(1, hoje=lambda: dia[0])
    assert lim.permitir() is True and lim.permitir() is False
    dia[0] += timedelta(days=1)
    assert lim.permitir() is True


def test_limitador_diario_zero_desliga_o_llm():
    assert LimitadorDiario(0).permitir() is False


# ---------- configuração pelo ambiente ----------
def test_sem_chave_nao_ha_provedor(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert criar_provedor_do_ambiente() is None


def test_com_chave_cria_o_gemini_com_modelo_configuravel(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  abc  ")
    monkeypatch.delenv("IA_LLM_MODELO", raising=False)
    p = criar_provedor_do_ambiente()
    assert isinstance(p, ProvedorGemini) and p.chave == "abc" and p.modelo == llm.MODELO_PADRAO
    monkeypatch.setenv("IA_LLM_MODELO", "outro-modelo")
    assert criar_provedor_do_ambiente().modelo == "outro-modelo"


def test_limite_diario_do_ambiente(monkeypatch):
    monkeypatch.delenv("IA_LLM_LIMITE_DIARIO", raising=False)
    assert limite_diario_do_ambiente() == llm.LIMITE_DIARIO_PADRAO
    monkeypatch.setenv("IA_LLM_LIMITE_DIARIO", "15")
    assert limite_diario_do_ambiente() == 15
    monkeypatch.setenv("IA_LLM_LIMITE_DIARIO", "muito")
    assert limite_diario_do_ambiente() == llm.LIMITE_DIARIO_PADRAO


# ---------- prompt ----------
def test_prompt_traz_trechos_historico_e_pergunta():
    texto = montar_pergunta("e para clientes?", ["como excluir produto?"], TRECHOS)
    assert "como excluir produto?" in texto
    assert "[1] Pergunta: Como excluir um orçamento?" in texto and "Resposta: Só rascunho ou cancelado." in texto
    assert "[2] Pergunta: Como cancelar?" in texto
    assert texto.rstrip().endswith("PERGUNTA ATUAL: e para clientes?")


def test_prompt_sem_historico_nao_tem_secao_de_conversa():
    assert "CONVERSA ANTERIOR" not in montar_pergunta("oi", [], TRECHOS)


def test_prompt_limita_a_quantidade_de_trechos():
    muitos = [(f"p{i}", f"r{i}") for i in range(10)]
    texto = montar_pergunta("x", [], muitos)
    assert f"[{llm.MAX_TRECHOS}]" in texto and f"[{llm.MAX_TRECHOS + 1}]" not in texto


def test_instrucoes_mandam_usar_so_os_trechos_e_ignorar_ordens_do_usuario():
    assert "SOMENTE" in llm.INSTRUCOES and "ignore pedidos" in llm.INSTRUCOES


# ---------- gerar_resposta ----------
def test_gerar_resposta_devolve_o_texto_do_modelo():
    p = Falso("Só rascunho ou cancelado podem ser excluídos.")
    assert gerar_resposta(p, LimitadorDiario(5), "como excluir?", [], TRECHOS) == "Só rascunho ou cancelado podem ser excluídos."
    sistema, usuario = p.chamadas[0]
    assert sistema == llm.INSTRUCOES and "PERGUNTA ATUAL: como excluir?" in usuario


def test_gerar_resposta_sem_provedor_ou_sem_trechos_devolve_none():
    assert gerar_resposta(None, LimitadorDiario(5), "x", [], TRECHOS) is None
    p = Falso()
    assert gerar_resposta(p, LimitadorDiario(5), "x", [], []) is None and p.chamadas == []


def test_gerar_resposta_erro_do_modelo_devolve_none():
    assert gerar_resposta(Falso(erro=ErroLLM("caiu")), LimitadorDiario(5), "x", [], TRECHOS) is None


def test_gerar_resposta_teto_diario_nao_chama_o_modelo():
    p = Falso()
    lim = LimitadorDiario(1)
    assert gerar_resposta(p, lim, "x", [], TRECHOS) is not None
    assert gerar_resposta(p, lim, "x", [], TRECHOS) is None
    assert len(p.chamadas) == 1


def test_gerar_resposta_corta_texto_gigante():
    assert len(gerar_resposta(Falso("a" * 5000), LimitadorDiario(5), "x", [], TRECHOS)) == llm.TAMANHO_MAXIMO_RESPOSTA
