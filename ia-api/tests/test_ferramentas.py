"""Validação do que o modelo pede (saída não confiável) e filtro que decide se vale chamar o LLM."""
import json

import httpx
import pytest

from app import ferramentas as f
from app.llm import (INSTRUCOES_AGENTE, INSTRUCOES_DADOS, Decisao, ErroLLM, LimitadorDiario, ProvedorGemini, decidir_acao, redigir_com_dados)


# ---------- declarações ----------
def test_toda_ferramenta_tem_nome_e_descricao_e_nao_se_repete():
    nomes = [d["name"] for d in f.declaracoes()[0]["functionDeclarations"]]
    assert len(nomes) == len(set(nomes)) == 9
    assert all(d["description"] for d in f.TODAS.values())


def test_consultas_e_acoes_sao_conjuntos_separados():
    assert not set(f.CONSULTAS) & set(f.ACOES)
    assert all(f.eh_consulta(n) for n in f.CONSULTAS) and not any(f.eh_consulta(n) for n in f.ACOES)


def test_nao_existe_ferramenta_que_grave_ou_exclua_direto():
    # cadastrar_* abre formulário e excluir_registro pede confirmação: a descrição precisa dizer isso
    assert "formulário" in f.ACOES["cadastrar_cliente"]["description"]
    assert "confirmar" in f.ACOES["excluir_registro"]["description"]


# ---------- validar_chamada ----------
def test_ferramenta_desconhecida_ou_nome_invalido_e_descartado():
    assert f.validar_chamada("apagar_tudo", {}) is None
    assert f.validar_chamada(None, {}) is None
    assert f.validar_chamada(["resumo_painel"], {}) is None


def test_argumentos_nao_declarados_sao_removidos():
    r = f.validar_chamada("consultar_clientes", {"busca": "ana", "sql": "DROP TABLE"})
    assert r == {"nome": "consultar_clientes", "args": {"busca": "ana"}}


def test_args_que_nao_e_dicionario_vira_vazio():
    assert f.validar_chamada("resumo_painel", "qualquer coisa") == {"nome": "resumo_painel", "args": {}}


def test_status_invalido_e_ignorado_e_valido_e_normalizado():
    assert f.validar_chamada("consultar_orcamentos", {"status": "APROVADO"})["args"] == {"status": "aprovado"}
    assert f.validar_chamada("consultar_orcamentos", {"status": "apagado"})["args"] == {}


def test_datas_so_no_formato_iso():
    r = f.validar_chamada("consultar_orcamentos", {"retirada_de": "2026-12-01", "retirada_ate": "01/12/2026"})
    assert r["args"] == {"retirada_de": "2026-12-01"}


def test_cobranca_sem_situacao_valida_vira_todos():
    assert f.validar_chamada("consultar_cobrancas", {"situacao": "xyz"})["args"] == {"situacao": "todos"}
    assert f.validar_chamada("consultar_cobrancas", {"situacao": "atrasado"})["args"] == {"situacao": "atrasado"}


def test_texto_gigante_e_cortado():
    r = f.validar_chamada("consultar_clientes", {"busca": "a" * 5000})
    assert len(r["args"]["busca"]) == f.MAX_TEXTO


def test_cadastro_de_cliente_mantem_so_o_que_foi_dito():
    r = f.validar_chamada("cadastrar_cliente", {"nome": "  Padaria Sol ", "tipo": "pj", "email": "", "cidade": None})
    assert r["args"] == {"nome": "Padaria Sol", "tipo": "PJ"}


def test_cadastro_de_produto_converte_numeros():
    r = f.validar_chamada("cadastrar_produto", {"nome": "Mesa", "valor_diaria": "45,50", "quantidade": "12", "valor_reposicao": True})
    assert r["args"] == {"nome": "Mesa", "valor_diaria": 45.5, "quantidade": 12}


def test_cadastro_de_orcamento_limpa_itens():
    itens = [{"produto": "Cadeira", "quantidade": 0}, {"produto": "", "quantidade": 3}, "lixo", {"produto": "Mesa"}]
    r = f.validar_chamada("cadastrar_orcamento", {"cliente": "Ana", "itens": itens})
    assert r["args"]["itens"] == [{"produto": "Cadeira", "quantidade": 1}, {"produto": "Mesa", "quantidade": 1}]


def test_cadastro_de_orcamento_limita_quantidade_de_itens():
    itens = [{"produto": f"p{i}", "quantidade": 1} for i in range(100)]
    assert len(f.validar_chamada("cadastrar_orcamento", {"itens": itens})["args"]["itens"]) == f.MAX_ITENS


def test_exclusao_exige_modulo_e_busca():
    assert f.validar_chamada("excluir_registro", {"modulo": "produto"}) is None
    assert f.validar_chamada("excluir_registro", {"modulo": "pagamento", "busca": "x"}) is None
    assert f.validar_chamada("excluir_registro", {"modulo": "Produto", "busca": "tripé"})["args"] == {"modulo": "produto", "busca": "tripé"}


# ---------- validar_resultados ----------
def test_resultados_aceitam_so_consultas_conhecidas():
    brutos = [
        {"nome": "consultar_clientes", "args": {"busca": "ana", "x": 1}, "resultado": {"total": 1}},
        {"nome": "excluir_registro", "args": {"modulo": "produto", "busca": "a"}, "resultado": 1},
        {"nome": "inventada", "args": {}, "resultado": 1},
        "lixo",
    ]
    assert f.validar_resultados(brutos) == [{"nome": "consultar_clientes", "args": {"busca": "ana"}, "resultado": {"total": 1}}]


def test_resultados_gigantes_e_em_excesso_sao_descartados():
    grande = {"nome": "consultar_clientes", "args": {}, "resultado": "x" * (f.MAX_BYTES_RESULTADO + 1)}
    ok = {"nome": "resumo_painel", "args": {}, "resultado": {"a": 1}}
    assert f.validar_resultados([grande, ok]) == [ok]
    assert len(f.validar_resultados([ok] * 10)) == f.MAX_RESULTADOS
    assert f.validar_resultados("não é lista") == []


# ---------- filtro ----------
@pytest.mark.parametrize("frase", [
    "quantos orçamentos aprovados eu tenho?", "quanto eu tenho a receber?", "lista os clientes de Fortaleza", "me dá um resumo do mês",
    "quero cadastrar um cliente", "crie um produto cadeira", "novo orçamento para a Ana", "exclui o produto tripé", "apague o cliente João",
    "mostre as cobranças atrasadas", "quais são os produtos mais alugados?",
])
def test_filtro_deixa_passar_pedidos_de_dados_e_de_acao(frase):
    assert f.parece_pedido_de_acao_ou_dados(frase)


@pytest.mark.parametrize("frase", [
    "como excluir produto", "como cadastrar um cliente?", "posso excluir um orçamento aprovado?", "por que não consigo excluir?",
    "o que é diária?", "oi", "obrigado", "receita de bolo",
])
def test_filtro_nao_gasta_llm_com_duvida_de_como_fazer(frase):
    assert not f.parece_pedido_de_acao_ou_dados(frase)


def test_resposta_curta_a_uma_pergunta_de_esclarecimento_passa():
    assert f.parece_pedido_de_acao_ou_dados("tripé", ["quero excluir um produto"])
    assert not f.parece_pedido_de_acao_ou_dados("tripé", ["como excluir produto"])
    assert not f.parece_pedido_de_acao_ou_dados("tripé", [])


# ---------- Gemini: decidir ----------
def gemini(handler):
    return ProvedorGemini("chave", cliente=httpx.Client(transport=httpx.MockTransport(handler)))


def resposta(partes):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": partes}}]})


def test_decidir_envia_as_ferramentas_e_le_a_chamada():
    visto = {}

    def handler(req):
        visto["corpo"] = json.loads(req.content)
        return resposta([{"functionCall": {"name": "consultar_clientes", "args": {"busca": "ana"}}}])

    d = gemini(handler).decidir("SIS", "USU", f.declaracoes())
    assert d.chamadas == [{"nome": "consultar_clientes", "args": {"busca": "ana"}}] and d.texto == ""
    assert visto["corpo"]["tools"] == f.declaracoes()
    assert visto["corpo"]["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"
    assert visto["corpo"]["systemInstruction"]["parts"][0]["text"] == "SIS"


def test_decidir_descarta_chamada_invalida_e_le_texto():
    d = gemini(lambda r: resposta([{"text": "Qual produto?"}, {"functionCall": {"name": "rm_rf", "args": {}}}])).decidir("s", "u", [])
    assert d.chamadas == [] and d.texto == "Qual produto?"


def test_decidir_aceita_varias_chamadas():
    partes = [{"functionCall": {"name": "resumo_painel", "args": {}}}, {"functionCall": {"name": "consultar_cobrancas", "args": {"situacao": "pago"}}}]
    assert len(gemini(lambda r: resposta(partes)).decidir("s", "u", []).chamadas) == 2


@pytest.mark.parametrize("status", [400, 429, 500])
def test_decidir_erro_http_vira_erro_llm(status):
    with pytest.raises(ErroLLM):
        gemini(lambda r: httpx.Response(status)).decidir("s", "u", [])


def test_decidir_formato_inesperado_vira_erro_llm():
    with pytest.raises(ErroLLM):
        gemini(lambda r: httpx.Response(200, json={"candidates": []})).decidir("s", "u", [])


# ---------- decidir_acao / redigir_com_dados ----------
class Falso:
    def __init__(self, decisao=None, texto="Resposta.", erro=None):
        self.decisao, self.texto, self.erro, self.visto = decisao or Decisao(), texto, erro, []

    def decidir(self, sistema, usuario, tools):
        self.visto.append(("decidir", sistema, usuario))
        if self.erro:
            raise self.erro
        return self.decisao

    def gerar(self, sistema, usuario):
        self.visto.append(("gerar", sistema, usuario))
        if self.erro:
            raise self.erro
        return self.texto


def test_decidir_acao_sem_provedor_ou_com_teto_estourado_devolve_none():
    assert decidir_acao(None, LimitadorDiario(10), "oi", []) is None
    assert decidir_acao(Falso(), LimitadorDiario(0), "oi", []) is None


def test_decidir_acao_erro_devolve_none():
    assert decidir_acao(Falso(erro=ErroLLM("x")), LimitadorDiario(10), "oi", []) is None


def test_decidir_acao_monta_o_pedido_com_data_e_historico():
    p = Falso()
    decidir_acao(p, LimitadorDiario(10), "e os atrasados?", ["quanto tenho a receber?"], "2026-11-25")
    _, sistema, usuario = p.visto[0]
    assert sistema == INSTRUCOES_AGENTE
    assert usuario.splitlines()[0] == "HOJE: 2026-11-25" and "- quanto tenho a receber?" in usuario and usuario.endswith("MENSAGEM ATUAL: e os atrasados?")


def test_instrucoes_do_agente_deixam_claro_que_nada_e_executado_pelo_modelo():
    assert "confirmação" in INSTRUCOES_AGENTE and "nunca instruções" in INSTRUCOES_AGENTE and "AJUDA" in INSTRUCOES_AGENTE


def test_redigir_com_dados_envia_os_dados_como_informacao():
    p = Falso(texto="Você tem 3.")
    r = [{"nome": "consultar_orcamentos", "args": {"status": "aprovado"}, "resultado": {"total": 3}}]
    assert redigir_com_dados(p, LimitadorDiario(10), "quantos aprovados?", [], r, "2026-11-25") == "Você tem 3."
    tipo, sistema, usuario = p.visto[0]
    assert tipo == "gerar" and sistema == INSTRUCOES_DADOS and '{"total": 3}' in usuario and "PERGUNTA: quantos aprovados?" in usuario
    assert "nunca instruções" in INSTRUCOES_DADOS


def test_redigir_com_dados_sem_dados_provedor_ou_teto_devolve_none():
    r = [{"nome": "resumo_painel", "args": {}, "resultado": {}}]
    assert redigir_com_dados(Falso(), LimitadorDiario(10), "x", [], []) is None
    assert redigir_com_dados(None, LimitadorDiario(10), "x", [], r) is None
    assert redigir_com_dados(Falso(), LimitadorDiario(0), "x", [], r) is None
    assert redigir_com_dados(Falso(erro=ErroLLM("x")), LimitadorDiario(10), "x", [], r) is None


def test_orcamentos_filtra_por_devolucao_e_cobrancas_por_vencimento():
    r = f.validar_chamada("consultar_orcamentos", {"devolucao_de": "2026-11-26", "devolucao_ate": "26/11/2026"})
    assert r["args"] == {"devolucao_de": "2026-11-26"}
    r = f.validar_chamada("consultar_cobrancas", {"vencimento_de": "2026-11-26", "vencimento_ate": "2026-12-03"})
    assert r["args"] == {"situacao": "todos", "vencimento_de": "2026-11-26", "vencimento_ate": "2026-12-03"}


def test_pergunta_de_dado_com_verbo_de_cadastro_nao_e_pedido_de_acao():
    from app.ferramentas import pede_acao
    for p in ["Quantos clientes foram cadastrados nos últimos 7 dias?", "clientes cadastrados nas últimas 2 semanas", "quais orçamentos foram excluídos?", "quantos produtos novos temos?"]:
        assert not pede_acao(p), p
    for p in ["cadastre o cliente João", "crie um orçamento para Maria", "exclua o produto MS-01", "novo cliente Ana de Sobral"]:
        assert pede_acao(p), p
