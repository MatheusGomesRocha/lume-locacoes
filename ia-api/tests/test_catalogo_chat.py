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

    def falso(provedor, limitador, perguntas, catalogo, proximo_id, ignoradas=None):
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


def test_pedido_longo_de_nomes_acha_a_consulta_do_mesmo_assunto(monkeypatch):
    from app import main
    contar = {"nome": "c_hoje", "descricao": "Conta clientes cadastrados hoje", "entidade": "clientes", "operacao": "contar", "permissao": "clientes.ver", "saida": [], "parametros": {},
              "exemplos": ["quantos clientes cadastrados hoje", "total de clientes cadastrados hoje", "numero de clientes cadastrados hoje"], "palavras_chave": ["clientes", "cadastrados"], "sinonimos": {}, "filtros": []}
    monkeypatch.setattr(main, "provedor_llm", object())
    q = "você consegue me listar os NOMES dos clientes que foram cadastrados hoje?"
    r = main._agente(q, [], main.PerguntaIn(pergunta=q, catalogo=[contar]))
    assert r["encontrou"] is False and "listar" in r["resposta"] and not r.get("consultas")


def _resultados_do_catalogo():
    return [{"nome": __import__("app.ferramentas", fromlist=["x"]).CATALOGO, "args": {"nome": "c_hoje", "params": {}}, "resultado": {"total": 2, "linhas": [{"nome": "Ana"}, {"nome": "Bia"}]}}]


def _spec_c_hoje():
    return {"nome": "c_hoje", "descricao": "Lista clientes cadastrados hoje", "entidade": "clientes", "operacao": "listar", "permissao": "clientes.ver", "saida": ["nome"], "parametros": {},
            "exemplos": ["nomes dos clientes cadastrados hoje", "listar clientes cadastrados hoje", "clientes novos de hoje"], "palavras_chave": ["clientes"], "sinonimos": {}, "filtros": []}


def test_resposta_da_consulta_e_conversada_sem_entendi_e_com_numero_conferido(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "provedor_llm", object())
    dados = main.PerguntaIn(pergunta="quais os nomes?", catalogo=[_spec_c_hoje()], resultados=_resultados_do_catalogo())
    monkeypatch.setattr(main, "redigir_com_dados", lambda *a, **k: "Hoje entraram 2 clientes: Ana e Bia.")
    r = main._agente("quais os nomes?", [], dados)
    assert r["resposta"] == "Hoje entraram 2 clientes: Ana e Bia." and "Entendi" not in r["resposta"]
    monkeypatch.setattr(main, "redigir_com_dados", lambda *a, **k: "Hoje entraram 9 clientes.")  # número inventado
    r = main._agente("quais os nomes?", [], dados)
    assert "9" not in r["resposta"] and "Encontrei 2" in r["resposta"] and "Entendi" not in r["resposta"]
    monkeypatch.setattr(main, "redigir_com_dados", lambda *a, **k: None)  # modelo fora do ar: texto de código
    assert "Encontrei 2" in main._agente("quais os nomes?", [], dados)["resposta"]


def test_tester_refaz_total_esperado_de_listagem_por_janela():
    from evolucao.agentes import refazer_totais_de_janela
    spec = {**_spec_c_hoje(), "entidade": "clientes", "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}}, "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}]}
    caso = {"tipo": "execucao", "origem": "tester_llm", "esperado": {"total": 99}, "sessao": "master", "params": {"dias": 0}, "descricao": "hoje"}
    avisos = refazer_totais_de_janela(spec, [caso])
    assert avisos and caso["esperado"]["total"] != 99


def test_seguimento_com_agradecimento_na_frente():
    from app.ferramentas import parece_seguimento
    h = ["quantos clientes foram cadastrados hoje?"]
    assert parece_seguimento("valeu! e ontem, quantos foram?", h)
    assert parece_seguimento("ok, e quais os nomes deles?", h)
    assert not parece_seguimento("valeu, como criar um orçamento?", h)


def test_periodo_da_pergunta_traduz_hoje_ontem_semana_mes():
    from evolucao.consulta import periodo_da_pergunta as p
    h = "2026-11-26"  # quinta-feira
    assert p("quantos clientes foram cadastrados hoje?", h) == ("2026-11-26", "2026-11-26")
    assert p("quantos clientes foram cadastrados ontem?", h) == ("2026-11-25", "2026-11-25")
    assert p("e anteontem?", h) == ("2026-11-24", "2026-11-24")
    assert p("cadastrados nessa semana", h) == ("2026-11-23", "2026-11-26")
    assert p("cadastrados na semana passada", h) == ("2026-11-16", "2026-11-22")
    assert p("cadastrados neste mês", h) == ("2026-11-01", "2026-11-26")
    assert p("cadastrados no mês passado", h) == ("2026-10-01", "2026-10-31")
    assert p("cadastrados nos últimos 15 dias", h) == ("2026-11-11", "2026-11-26")
    assert p("cadastrados dia 15/11", h) == ("2026-11-15", "2026-11-15")
    assert p("quantos clientes temos?", h) is None
    assert p("hoje", "lixo") is None


def test_consulta_por_periodo_recebe_as_datas_da_pergunta():
    from evolucao.consulta import extrair_parametros
    spec = {"nome": "clientes_cadastrados_periodo", "entidade": "clientes", "operacao": "contar", "parametros": {"de": {"tipo": "data", "obrigatorio": True}, "ate": {"tipo": "data", "obrigatorio": True}},
            "filtros": [{"campo": "criado_em", "op": "maior_igual", "parametro": "de"}, {"campo": "criado_em", "op": "menor_igual", "parametro": "ate"}]}
    assert extrair_parametros("quantos clientes foram cadastrados ontem?", spec, "2026-11-26") == {"de": "2026-11-25", "ate": "2026-11-25"}
    assert extrair_parametros("quantos clientes foram cadastrados esta semana?", spec, "2026-11-26") == {"de": "2026-11-23", "ate": "2026-11-26"}
    assert extrair_parametros("quantos clientes temos?", spec, "2026-11-26") == {}


def test_proposta_que_repete_consulta_aprovada_nao_vira_relatorio():
    from evolucao.pipeline import consulta_equivalente
    aprov = {"nome": "nomes_clientes_hoje", "entidade": "clientes", "operacao": "listar", "saida": ["nome", "cidade"], "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}]}
    prop = {"entidade": "clientes", "operacao": "listar", "saida": ["nome"], "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}]}
    assert consulta_equivalente(prop, [aprov]) is aprov
    assert consulta_equivalente({**prop, "saida": ["nome", "email"]}, [aprov]) is None  # pede um campo que a aprovada não mostra: é trabalho novo
    assert consulta_equivalente({**prop, "operacao": "contar"}, [aprov]) is None


def test_pergunta_sem_parametro_vai_para_a_fila_dos_agents(monkeypatch):
    from app import main
    spec = {"nome": "c_dias", "descricao": "d", "entidade": "clientes", "operacao": "contar", "permissao": "clientes.ver", "saida": [], "sinonimos": {},
            "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}}, "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}],
            "exemplos": ["quantos clientes cadastrados nos últimos 7 dias", "total de clientes cadastrados nos últimos 30 dias", "numero de clientes cadastrados nos últimos 15 dias"], "palavras_chave": ["clientes", "cadastrados"]}
    r = main._agente("quantos clientes foram cadastrados ontem?", [], main.PerguntaIn(pergunta="quantos clientes foram cadastrados ontem?", catalogo=[spec], hoje="2026-11-26"))
    assert r["encontrou"] is False and "preciso saber" in r["resposta"]


def test_tester_conta_periodo_de_ate_por_datas():
    from evolucao.agentes import _total_da_janela
    from evolucao.esquema import DADOS_TESTE, HOJE_TESTE
    spec = {"entidade": "clientes", "operacao": "listar", "parametros": {"de": {"tipo": "data"}, "ate": {"tipo": "data"}},
            "filtros": [{"campo": "criado_em", "op": "maior_igual", "parametro": "de"}, {"campo": "criado_em", "op": "menor_igual", "parametro": "ate"}]}
    todos = _total_da_janela(spec, {"de": "2000-01-01", "ate": HOJE_TESTE})
    assert todos == len([l for l in DADOS_TESTE["clientes"] if l.get("criado_em") and l["criado_em"][:10] <= HOJE_TESTE])
    assert _total_da_janela(spec, {"de": "lixo", "ate": HOJE_TESTE}) is None


def test_pergunta_com_periodo_e_pedido_de_dado_vai_para_a_fila_dos_agents(cliente):
    """EV do dia 27/11: “qual número do orçamento que será devolvido hoje?” caía na ajuda do número do orçamento e nunca virava proposta."""
    r = cliente.post("/chat", json={"pergunta": "qual número do orçamento que será devolvido hoje?"}).json()
    assert r["encontrou"] is False and "Registrei" in r["resposta"]


def test_ajuda_que_admite_nao_saber_nao_conta_como_resposta(monkeypatch, cliente):
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "gerar_resposta", lambda *a, **k: "Não encontrei essa informação na ajuda. O número do orçamento é gerado automaticamente.")
    r = cliente.post("/chat", json={"pergunta": "qual é o número do orçamento"}).json()
    assert r["encontrou"] is False and "Registrei" in r["resposta"]


def test_numero_do_orcamento_e_lista_e_numero_de_orcamentos_e_contagem():
    from evolucao.consulta import tipo_da_pergunta
    assert tipo_da_pergunta("qual número do orçamento que será devolvido hoje?") == "listar"
    assert tipo_da_pergunta("qual o número da cobrança vencida?") == "listar"
    assert tipo_da_pergunta("qual o número de orçamentos criados hoje?") == "contar"
    assert tipo_da_pergunta("qual a quantidade de clientes novos?") == "contar"
    assert tipo_da_pergunta("quantos orçamentos foram criados hoje?") == "contar"


def test_instrucoes_mandam_o_o_que_foi_pago_hoje_para_dados_e_a_data_usada_para_o_texto():
    from app import llm
    assert "o que foi pago" in llm.INSTRUCOES_AGENTE and "NÃO é dúvida" in llm.INSTRUCOES_AGENTE
    assert "qual data foi usada" in llm.INSTRUCOES_DADOS
