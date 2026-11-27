"""Consultas aprovadas pelo Master: o /chat as usa antes de perguntar ao modelo, e o endpoint de evolução não guarda nada."""
import pytest
from fastapi.testclient import TestClient

from app import main

SPEC = {
    "nome": "contar_usuarios_por_perfil", "descricao": "Conta usuários por perfil", "entidade": "usuarios", "operacao": "contar",
    "permissao": "usuarios.ver", "papel_minimo": "admin", "saida": [],
    "exemplos": ["quantos usuários do tipo master eu tenho", "quantos usuários admin existem", "total de usuários do perfil usuario"], "palavras_chave": ["usuarios", "perfil"],
    "parametros": {"papel": {"tipo": "enum", "valores": ["master", "admin", "usuario"], "obrigatorio": True}},
    "filtros": [{"campo": "papel", "op": "igual", "parametro": "papel"}], "sinonimos": {},
}


@pytest.fixture()
def cliente():
    return TestClient(main.app)


def test_pergunta_do_catalogo_pede_a_consulta_ao_front(cliente):
    r = cliente.post("/chat", json={"pergunta": "quantos usuários do tipo master eu tenho?", "catalogo": [SPEC]}).json()
    assert r["consultas"] == [{"nome": "catalogo", "args": {"nome": "contar_usuarios_por_perfil", "params": {"papel": "master"}}}]


def test_sem_o_parametro_obrigatorio_pergunta_em_vez_de_adivinhar(cliente):
    spec = {**SPEC, "exemplos": ["quantos usuários eu tenho", "total de usuários cadastrados", "número de usuários do sistema"]}
    r = cliente.post("/chat", json={"pergunta": "quantos usuários eu tenho?", "catalogo": [spec]}).json()
    assert "consultas" not in r and "papel" in r["resposta"]


def test_volta_com_resultado_vira_texto_sem_modelo(cliente):
    corpo = {"pergunta": "quantos usuários do tipo master eu tenho?", "catalogo": [SPEC],
             "resultados": [{"nome": "catalogo", "args": {"nome": SPEC["nome"], "params": {"papel": "master"}}, "resultado": {"total": 2}}]}
    r = cliente.post("/chat", json=corpo).json()
    assert "2" in r["resposta"] and r["gerada_por_llm"] is False


def test_spec_perigosa_no_catalogo_e_ignorada(cliente):
    ruim = {**SPEC, "operacao": "excluir", "nome": "apagar_tudo"}
    assert main.specs_validas([ruim, SPEC]) == [main.normalizar_spec(SPEC)[0]]


def test_sem_catalogo_o_comportamento_antigo_continua(cliente):
    r = cliente.post("/chat", json={"pergunta": "quantos usuários do tipo master eu tenho?"}).json()
    assert "consultas" not in r or r["consultas"][0]["nome"] != "catalogo"


def test_evolucao_exige_o_modelo(cliente, monkeypatch):
    monkeypatch.setattr(main, "provedor_llm", None)
    r = cliente.post("/evolucao/propor", json={"perguntas": [{"pergunta": "quantos usuários master?"}]})
    assert r.status_code == 503


def test_evolucao_devolve_relatorios_com_ids_a_partir_do_numero(cliente, monkeypatch):
    monkeypatch.setattr(main, "provedor_llm", object())
    visto = {}

    def falso(provedor, limitador, perguntas, catalogo, proximo_id):
        visto["ids"] = [proximo_id(0), proximo_id(1)]
        visto["catalogo"] = catalogo
        return [{"id": proximo_id(0)}]

    monkeypatch.setattr(main, "gerar_relatorios", falso)
    r = cliente.post("/evolucao/propor", json={"perguntas": [{"pergunta": "total de cobranças pagas"}], "catalogo": [SPEC], "proximo_numero": 7}).json()
    assert r == {"relatorios": [{"id": "EV-0007"}], "ignoradas": []} and visto["ids"] == ["EV-0007", "EV-0008"] and len(visto["catalogo"]) == 1


# --- as mesmas respostas que o executor do front (TypeScript) precisa dar: o arquivo mora no front (a demo é outro repositório) ---
import json
from pathlib import Path

from evolucao import consulta

VETORES = json.loads((Path(__file__).resolve().parents[2] / "versao-real" / "frontend" / "src" / "test" / "catalogo_vetores.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", VETORES["casos"], ids=lambda c: c["nome"])
def test_vetores_compartilhados_com_o_front(caso):
    sessao = VETORES["sessoes"][caso["sessao"]]
    if "erro" in caso:
        with pytest.raises(consulta.ErroConsulta) as e:
            consulta.executar(caso["spec"], caso["params"], VETORES["dados"], sessao)
        assert e.value.codigo == caso["erro"]
    else:
        assert consulta.executar(caso["spec"], caso["params"], VETORES["dados"], sessao) == caso["esperado"]


def test_checar_refaz_as_checagens_sem_modelo(cliente):
    ok = cliente.post("/evolucao/checar", json={"spec": SPEC}).json()
    assert ok["bloqueio"] is False
    ruim = cliente.post("/evolucao/checar", json={"spec": {**SPEC, "operacao": "excluir"}}).json()
    assert ruim["bloqueio"] is True


SPEC_RECENTES = {
    "nome": "contar_clientes_recentes", "descricao": "Conta clientes cadastrados nos últimos N dias.", "entidade": "clientes", "operacao": "contar", "permissao": "clientes.ver", "papel_minimo": "usuario",
    "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}}, "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}],
    "exemplos": ["quantos clientes foram cadastrados nos ultimos 7 dias", "clientes novos nos ultimos 30 dias", "quantos clientes cadastrei hoje"],
}


def test_extrai_a_quantidade_de_dias_da_pergunta():
    from evolucao.consulta import extrair_parametros
    assert extrair_parametros("quantos clientes foram cadastrados nos últimos 7 dias?", SPEC_RECENTES) == {"dias": 7}
    assert extrair_parametros("clientes das últimas 2 semanas", SPEC_RECENTES) == {"dias": 14}
    assert extrair_parametros("clientes do último mês", SPEC_RECENTES) == {"dias": 30}
    assert extrair_parametros("quantos clientes cadastrei hoje", SPEC_RECENTES) == {"dias": 0}
    assert extrair_parametros("quantos clientes temos", SPEC_RECENTES) == {}  # sem período: o chat pergunta


def test_filtro_de_ultimos_dias_passa_nas_checagens_e_exige_parametro_numerico():
    from evolucao import checagens
    assert not checagens.tem_bloqueio(checagens.checar_spec(SPEC_RECENTES, None, []))
    ruim = {**SPEC_RECENTES, "parametros": {"dias": {"tipo": "data", "obrigatorio": True}}}
    assert any("pede numero" in a["mensagem"] for a in checagens.checar_spec(ruim, None, []))


def test_executa_com_hoje_e_recusa_sem_ele():
    import pytest
    from evolucao.consulta import ErroConsulta, executar
    from evolucao.esquema import DADOS_TESTE, SESSOES_TESTE
    assert executar(SPEC_RECENTES, {"dias": 7}, DADOS_TESTE, SESSOES_TESTE["vendedor"]) == {"total": 2}  # Maria (25/11) e Padaria (20/11); Mariana (10/11) está fora
    assert executar(SPEC_RECENTES, {"dias": 3}, DADOS_TESTE, SESSOES_TESTE["vendedor"]) == {"total": 1}
    with pytest.raises(ErroConsulta):
        executar(SPEC_RECENTES, {"dias": 7}, DADOS_TESTE, {"papel": "usuario", "permissoes": ["clientes.ver"]})


def test_parametro_de_texto_vai_ao_front_com_a_pergunta_em_vez_de_travar(cliente):
    spec = {"nome": "estoque_por_categoria", "descricao": "Soma o estoque por categoria", "entidade": "produtos", "operacao": "somar", "campo_soma": "quantidade",
            "permissao": "produtos.ver", "saida": [], "exemplos": ["Qual o total de unidades em estoque da categoria Iluminação?", "Qual o total de unidades em estoque da categoria Som?", "Qual o total de unidades em estoque da categoria Buffet?"],
            "palavras_chave": ["estoque", "categoria"], "parametros": {"cat": {"tipo": "texto", "obrigatorio": True}},
            "filtros": [{"campo": "categoria", "op": "igual", "parametro": "cat"}], "sinonimos": {}}
    r = cliente.post("/chat", json={"pergunta": "Qual o total de unidades em estoque da categoria Cadeiras?", "catalogo": [spec]}).json()
    assert r["consultas"][0]["args"]["pergunta"].startswith("Qual o total") and r["consultas"][0]["args"]["params"] == {}


SPEC_RECENTES = {"nome": "clientes_cadastrados_recentemente", "descricao": "Conta clientes cadastrados nos últimos dias", "entidade": "clientes", "operacao": "contar",
                 "permissao": "clientes.ver", "saida": [], "palavras_chave": ["clientes", "cadastrados"], "sinonimos": {},
                 "exemplos": ["Quantos Clientes cadastrados no últimos 7 dias existem no sistema?", "Quantos clientes novos nos últimos 30 dias?", "Clientes cadastrados hoje"],
                 "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}}, "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}]}


def test_mesma_pergunta_com_outro_periodo_usa_a_consulta_aprovada(cliente):
    for pergunta, dias in [("quantos clientes foram cadastrados nos últimos 15 dias?", 15), ("clientes cadastrados nas últimas 2 semanas", 14), ("quantos clientes cadastrei hoje", 0)]:
        r = cliente.post("/chat", json={"pergunta": pergunta, "catalogo": [SPEC_RECENTES], "hoje": "2026-11-26"}).json()
        assert r["consultas"][0]["args"] == {"nome": "clientes_cadastrados_recentemente", "params": {"dias": dias}}, pergunta


def test_agents_nao_recebem_o_que_a_consulta_aprovada_ja_responde(cliente, monkeypatch):
    enviadas = []
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "gerar_relatorios", lambda *a, **k: enviadas.append([p["pergunta"] for p in a[2]]) or [])
    corpo = {"perguntas": [{"pergunta": "quantos clientes foram cadastrados nos últimos 15 dias?"}, {"pergunta": "quantos clientes são de Sobral?"}], "catalogo": [SPEC_RECENTES]}
    r = cliente.post("/evolucao/propor", json=corpo).json()
    assert enviadas == [["quantos clientes são de Sobral?"]]
    assert len(r["ignoradas"]) == 1 and "clientes_cadastrados_recentemente" in r["ignoradas"][0]["motivo"]


def test_proximos_dias_vai_de_hoje_ate_hoje_mais_n():
    from evolucao.consulta import _janela, extrair_parametros
    assert _janela("2026-11-26", 0, "proximos_dias") == ("2026-11-26", "2026-11-26")
    assert _janela("2026-11-26", 7, "proximos_dias") == ("2026-11-26", "2026-12-03")
    assert _janela("2026-11-26", 7) == ("2026-11-19", "2026-11-26")
    spec = {"parametros": {"dias": {"tipo": "numero"}}, "filtros": [{"campo": "data_devolucao", "op": "proximos_dias", "parametro": "dias"}]}
    assert extrair_parametros("quais orçamentos devolvem nos próximos 15 dias?", spec) == {"dias": 15}
    assert extrair_parametros("o que devolve hoje?", spec) == {"dias": 0}
    assert extrair_parametros("devoluções na próxima semana", spec) == {"dias": 7}


def test_tipo_da_pergunta_separa_contar_de_listar():
    from evolucao.consulta import tipo_da_pergunta as t
    assert t("quantos clientes foram cadastrados hoje?") == "contar"
    assert t("você consegue me listar os NOMES dos clientes que foram cadastrados hoje?") == "listar"
    assert t("quais os nomes deles?") == "listar"
    assert t("e quantos são ativos?") == "contar"
    assert t("qual o valor total das cobranças pagas?") == "somar"
    assert t("clientes cadastrados hoje") is None


def test_consulta_de_contar_nao_responde_pedido_de_nomes():
    from evolucao.consulta import buscar_consulta
    contar = {"nome": "c_hoje", "descricao": "d", "entidade": "clientes", "operacao": "contar", "exemplos": ["quantos clientes cadastrados hoje"], "palavras_chave": ["clientes", "cadastrados"]}
    assert buscar_consulta("quantos clientes foram cadastrados hoje?", [contar]) is contar
    assert buscar_consulta("quais os nomes dos clientes cadastrados hoje?", [contar]) is None
    assert buscar_consulta("quais os nomes dos clientes cadastrados hoje?", [contar], por_tipo=False) is contar


def test_seguimento_e_reformulado_com_o_historico(monkeypatch):
    from app import ferramentas, main
    assert ferramentas.parece_seguimento("e qual os nomes deles?")
    assert not ferramentas.parece_seguimento("quantos clientes foram cadastrados hoje?")
    chamadas = []
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "reformular_seguimento", lambda p, l, q, h: chamadas.append((q, h)) or "quais os nomes dos clientes cadastrados hoje?")
    contar = {"nome": "c_hoje", "descricao": "Conta clientes cadastrados hoje", "entidade": "clientes", "operacao": "contar", "permissao": "clientes.ver", "saida": [], "parametros": {},
              "exemplos": ["quantos clientes cadastrados hoje", "total de clientes cadastrados hoje", "numero de clientes cadastrados hoje"], "palavras_chave": ["clientes", "cadastrados"], "sinonimos": {}, "filtros": []}
    completa, duvida = main._completar_seguimento("e qual os nomes deles?", ["quantos clientes foram cadastrados hoje?"])
    assert duvida is None
    assert completa == "quais os nomes dos clientes cadastrados hoje?"
    r = main._agente(completa, ["quantos clientes foram cadastrados hoje?"], main.PerguntaIn(pergunta=completa, catalogo=[contar]))
    assert chamadas and r["encontrou"] is False and "listar" in r["resposta"] and not r.get("consultas")


def test_texto_do_modelo_com_numero_inventado_e_descartado(monkeypatch):
    from app import main
    from app.confianca import texto_confere_com_dados
    dados = [{"nome": "consultar_clientes", "args": {}, "resultado": {"total": 17, "linhas": [{"nome": "Ana"}] * 3}}]
    assert texto_confere_com_dados("Encontrei 17 clientes, mostrando os 3 primeiros.", dados)
    assert texto_confere_com_dados("O total de R$ 1.234,56 em 26/11/2026.", [{"nome": "x", "args": {}, "resultado": {"soma": 1234.56, "dia": "2026-11-26"}}])
    assert not texto_confere_com_dados("Encontrei 19 clientes.", dados)
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "redigir_com_dados", lambda *a, **k: "Você tem 99 clientes.")
    r = main._agente("quantos clientes?", [], main.PerguntaIn(pergunta="quantos clientes?", resultados=dados))
    assert "99" not in r["resposta"] and "17" in r["resposta"] and r["gerada_por_llm"] is False


def test_reescrita_que_muda_o_pedido_ou_perde_o_assunto_vira_pergunta(monkeypatch):
    from app import main
    from app.confianca import seguimento_confere
    h = ["quantos clientes foram cadastrados hoje?"]
    assert seguimento_confere("e quais os nomes deles?", "quais os nomes dos clientes cadastrados hoje?", h)
    assert not seguimento_confere("e quais os nomes deles?", "quantos clientes foram cadastrados hoje?", h)  # virou contagem
    assert not seguimento_confere("e quais os nomes deles?", "quais os nomes dos produtos mais alugados?", h)  # perdeu o assunto
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "reformular_seguimento", lambda *a: "quantos pedidos foram feitos?")
    main.cache.limpar() if hasattr(main.cache, "limpar") else None
    completa, duvida = main._completar_seguimento("e quais os nomes deles?", h)
    assert duvida == "quantos pedidos foram feitos?"
    monkeypatch.setattr(main, "reformular_seguimento", lambda *a: None)
    assert main._completar_seguimento("e quais os nomes dos outros?", h)[1] == ""
