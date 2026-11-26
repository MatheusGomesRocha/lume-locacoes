"""O agente conversacional: cenários da conversa e a regra de ouro (nada é gravado sem o "sim")."""
import pytest
from fastapi.testclient import TestClient

from app import agente as a
from app import main
from app.llm import Decisao

HOJE = "2026-11-25"
JOAO = {"id": 1, "nome": "João Victor", "cidade": "Fortaleza"}
JOAO2 = {"id": 2, "nome": "João Victor Lima", "cidade": "Sobral"}
MESA = {"id": 5, "nome": "Mesa redonda", "valor_diaria": 30}
CADEIRA = {"id": 6, "nome": "Cadeira", "valor_diaria": 5}


def pedido(**extra):
    args = {"cliente": "João Victor", "evento": "Casamento", "data_retirada": "2026-11-26",
            "itens": [{"produto": "mesas", "quantidade": 2}, {"produto": "cadeiras", "quantidade": 20}]}
    return a.iniciar("cadastrar_orcamento", {**args, **extra}, HOJE)


def clientes(*linhas):
    return {"nome": "localizar_clientes", "resultado": {"linhas": list(linhas)}}


def produtos(*grupos):
    return {"nome": "localizar_produtos", "resultado": {"itens": [{"linhas": g} for g in grupos]}}


SEM_FALTAS = {"nome": "verificar_disponibilidade", "resultado": {"faltas": []}}


def ate_confirmar(passo):
    """Conduz um pedido completo com cliente e produtos únicos até a confirmação."""
    passo = a.continuar(passo["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    return a.continuar(passo["agente"], "x", [SEM_FALTAS], HOJE)


# ---------- o pedido do exemplo ----------
def test_primeiro_passo_pede_as_consultas_e_singulariza_os_produtos():
    p = pedido()
    nomes = [c["nome"] for c in p["consultas"]]
    assert nomes == ["localizar_clientes", "localizar_produtos"]
    assert p["consultas"][1]["args"]["buscas"] == ["mesa", "cadeira"]
    assert "executar" not in p


def test_pedido_completo_chega_na_confirmacao_com_total():
    p = ate_confirmar(pedido())
    assert p["agente"]["aguardando"] == "confirmar"
    assert "Total: R$ 160,00" in p["texto"] and "João Victor" in p["texto"]
    assert p["opcoes"] == ["Confirmar", "Cancelar"]
    assert "executar" not in p  # ainda não gravou


def test_uma_data_so_vale_para_retirada_e_devolucao_e_o_resumo_avisa():
    assert "usei a mesma data" in ate_confirmar(pedido())["texto"]


def test_sim_gera_a_gravacao_e_encerra():
    p = ate_confirmar(pedido())
    fim = a.continuar(p["agente"], "sim", None, HOJE)
    assert fim["agente"] is None
    (criar,) = fim["executar"]
    assert criar["nome"] == "criar_orcamento"
    assert criar["args"]["cliente_id"] == 1 and criar["args"]["itens"] == [{"produto_id": 5, "quantidade": 2}, {"produto_id": 6, "quantidade": 20}]


# ---------- cenários do cliente ----------
def test_cliente_inexistente():
    p = a.continuar(pedido()["agente"], "x", [clientes(), produtos([MESA], [CADEIRA])], HOJE)
    assert p["texto"].startswith("Não encontramos esse usuário")
    assert "Cancelar" in p["opcoes"]


def test_mais_de_um_cliente_pergunta_qual():
    p = a.continuar(pedido()["agente"], "x", [clientes(JOAO, JOAO2), produtos([MESA], [CADEIRA])], HOJE)
    assert p["texto"] == "Qual João Victor deseja selecionar?"
    assert p["opcoes"] == ["João Victor — Fortaleza", "João Victor Lima — Sobral"]
    escolhido = a.continuar(p["agente"], "2", None, HOJE)
    assert escolhido["consultas"][0]["nome"] == "verificar_disponibilidade"
    assert escolhido["agente"]["rascunho"]["cliente_id"] == 2


def test_escolher_cliente_pelo_nome_e_resposta_confusa_repete_a_pergunta():
    p = a.continuar(pedido()["agente"], "x", [clientes(JOAO, JOAO2), produtos([MESA], [CADEIRA])], HOJE)
    assert a.continuar(p["agente"], "talvez", None, HOJE)["agente"]["aguardando"] == "escolher_cliente"
    assert a.continuar(p["agente"], "João Victor Lima", None, HOJE)["agente"]["rascunho"]["cliente_id"] == 2


def test_cadastrar_o_cliente_novo_na_conversa_e_gravar_os_dois_so_no_sim():
    p = a.continuar(pedido()["agente"], "x", [clientes(), produtos([MESA], [CADEIRA])], HOJE)
    p = a.continuar(p["agente"], "1", None, HOJE)
    assert "pessoa física ou empresa" in p["texto"]
    p = a.continuar(p["agente"], "pessoa física", None, HOJE)
    assert "telefone" in p["texto"]
    p = a.continuar(p["agente"], "telefone (85) 98888-7777, joao@email.com, Fortaleza", None, HOJE)
    assert p["consultas"][0]["nome"] == "verificar_disponibilidade"
    p = a.continuar(p["agente"], "x", [SEM_FALTAS], HOJE)
    assert "Cliente NOVO: João Victor" in p["texto"] and "executar" not in p
    fim = a.continuar(p["agente"], "sim", None, HOJE)
    assert [x["nome"] for x in fim["executar"]] == ["criar_cliente", "criar_orcamento"]
    novo = fim["executar"][0]["args"]
    assert novo["tipo"] == "PF" and novo["email"] == "joao@email.com" and novo["telefone"].startswith("(85)") and novo["cidade"] == "Fortaleza"
    assert fim["executar"][1]["args"]["cliente_novo"] is True


def test_pular_os_contatos():
    p = a.continuar(pedido()["agente"], "x", [clientes(), produtos([MESA], [CADEIRA])], HOJE)
    p = a.continuar(a.continuar(p["agente"], "1", None, HOJE)["agente"], "empresa", None, HOJE)
    assert a.continuar(p["agente"], "pular", None, HOJE)["consultas"]


# ---------- dados que faltam ----------
def test_sem_data_pergunta_retirada_e_devolucao():
    p = pedido(data_retirada=None)
    p = a.continuar(p["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    assert p["texto"] == "Qual data de retirada e data de devolução?"
    p = a.continuar(p["agente"], "retirada 26/11/2026 e devolução 28/11/2026", None, HOJE)
    assert p["consultas"][0]["args"] == {"retirada": "2026-11-26", "devolucao": "2026-11-28", "itens": [{"produto_id": 5, "quantidade": 2}, {"produto_id": 6, "quantidade": 20}]}
    p = a.continuar(p["agente"], "x", [SEM_FALTAS], HOJE)
    assert "2 diárias" in p["texto"] and "Total: R$ 320,00" in p["texto"]


def test_so_uma_data_na_resposta_pergunta_a_devolucao():
    p = a.continuar(pedido(data_retirada=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    p = a.continuar(p["agente"], "dia 26/11", None, HOJE)
    assert "devolução" in p["texto"] and p["agente"]["aguardando"] == "devolucao"
    assert a.continuar(p["agente"], "mesmo dia", None, HOJE)["consultas"]


def test_devolucao_antes_da_retirada_e_recusada():
    p = a.continuar(pedido(data_retirada=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    p = a.continuar(p["agente"], "28/11/2026 e 26/11/2026", None, HOJE)
    assert "antes da retirada" in p["texto"] and p["agente"]["aguardando"] == "datas"


def test_sem_evento_e_sem_cliente_perguntam():
    p = a.continuar(pedido(evento=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    assert p["agente"]["aguardando"] == "evento"
    assert a.continuar(p["agente"], "Casamento", None, HOJE)["consultas"]
    sem_cliente = a.continuar(pedido(cliente=None)["agente"], "x", [produtos([MESA], [CADEIRA])], HOJE)
    assert sem_cliente["texto"] == "Para qual cliente é o orçamento?"


def test_produto_inexistente_ou_ambiguo():
    p = a.continuar(pedido()["agente"], "x", [clientes(JOAO), produtos([], [CADEIRA])], HOJE)
    assert "Não encontramos o produto “mesas”" in p["texto"]
    sem = a.continuar(p["agente"], "1", None, HOJE)  # remove
    assert sem["consultas"][0]["args"]["itens"] == [{"produto_id": 6, "quantidade": 20}]
    amb = a.continuar(pedido()["agente"], "x", [clientes(JOAO), produtos([MESA, {"id": 7, "nome": "Mesa retangular", "valor_diaria": 25}], [CADEIRA])], HOJE)
    assert amb["texto"] == "Qual “mesas” deseja selecionar?"
    assert a.continuar(amb["agente"], "2", None, HOJE)["agente"]["rascunho"]["itens"][0]["produto_id"] == 7


def test_aviso_de_estoque_aparece_no_resumo_sem_bloquear():
    p = a.continuar(pedido()["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    falta = {"nome": "verificar_disponibilidade", "resultado": {"faltas": [{"produto": "Cadeira", "solicitado": 20, "disponivel": 10}]}}
    texto = a.continuar(p["agente"], "x", [falta], HOJE)["texto"]
    assert "⚠" in texto and "10 de Cadeira" in texto


# ---------- a regra de ouro ----------
@pytest.mark.parametrize("resposta", ["talvez", "não sei", "ok mas antes me diga o valor", "", "   ", "simm", "yes"])
def test_so_o_sim_na_confirmacao_grava(resposta):
    p = ate_confirmar(pedido())
    r = a.continuar(p["agente"], resposta or "?", None, HOJE)
    assert not (r and r.get("executar"))


@pytest.mark.parametrize("negativa", ["não", "cancelar", "cancela", "deixa pra lá"])
def test_negativa_cancela_sem_gravar(negativa):
    r = a.continuar(ate_confirmar(pedido())["agente"], negativa, None, HOJE)
    assert r["agente"] is None and "executar" not in r and "Nada foi criado" in r["texto"]


def test_nenhuma_etapa_anterior_a_confirmacao_gera_gravacao():
    p = pedido()
    for msg in ["sim", "sim", "sim"]:
        r = a.continuar(p["agente"], msg, [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
        assert "executar" not in r
        p = r


def test_estado_forjado_nao_vira_gravacao():
    # quem forja o estado em "confirmar" só consegue o que o próprio usuário já pode fazer; mas um rascunho incompleto não grava
    forjado = {"fluxo": "orcamento", "aguardando": "confirmar", "rascunho": {"cliente_id": 1, "itens": []}}
    r = a.continuar(forjado, "sim", None, HOJE)
    assert "executar" not in r and r["agente"]["aguardando"] != "confirmar"


def test_pergunta_no_meio_da_conversa_sai_do_agente():
    p = pedido(evento=None)
    p = a.continuar(p["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    assert a.continuar(p["agente"], "como faço para cobrar um cliente?", None, HOJE) is None


def test_erro_de_permissao_na_consulta_encerra_sem_criar():
    r = a.continuar(pedido()["agente"], "x", [{"nome": "localizar_clientes", "resultado": {"erro": "o usuário não tem permissão"}}], HOJE)
    assert r["agente"] is None and "Não criei nada" in r["texto"]


def test_estado_malformado_e_ignorado():
    for lixo in [None, "x", {}, {"fluxo": "apagar", "aguardando": "x", "rascunho": {}}, {"fluxo": "orcamento", "aguardando": "x", "rascunho": "y"}, {"fluxo": "orcamento", "aguardando": "x", "rascunho": {"itens": [{"quantidade": "9"}]}, "escolhas": 3}]:
        r = a.continuar(lixo, "oi", None, HOJE)
        assert r is None or isinstance(r, dict)


# ---------- só cliente ----------
def test_cadastro_de_cliente_pela_conversa_com_duplicado():
    p = a.iniciar("cadastrar_cliente", {"nome": "Maria Souza"}, HOJE)
    assert p["consultas"][0]["args"] == {"busca": "Maria Souza"}
    p = a.continuar(p["agente"], "x", [clientes({"id": 9, "nome": "Maria Souza", "cidade": "Crato"})], HOJE)
    assert "Já existe cliente" in p["texto"]
    p = a.continuar(p["agente"], "Cadastrar mesmo assim", None, HOJE)
    p = a.continuar(p["agente"], "empresa", None, HOJE)
    p = a.continuar(p["agente"], "pular", None, HOJE)
    assert "Vou cadastrar este cliente" in p["texto"] and "empresa" in p["texto"]
    fim = a.continuar(p["agente"], "sim", None, HOJE)
    assert [x["nome"] for x in fim["executar"]] == ["criar_cliente"]


def test_sem_dados_nao_inicia_conversa_e_o_formulario_continua():
    assert a.iniciar("cadastrar_orcamento", {}, HOJE) is None
    assert a.iniciar("cadastrar_cliente", {}, HOJE) is None
    assert a.iniciar("cadastrar_produto", {"nome": "x"}, HOJE) is None


# ---------- regras de apoio ----------
def test_datas_e_itens_e_total():
    assert a.extrair_datas("26/11/2026 e 28/11/26 e 2026-12-01 e 31/02", HOJE) == ["2026-11-26", "2026-11-28", "2026-12-01"]
    assert a.extrair_datas("dia 10/01", HOJE) == ["2027-01-10"]
    assert a.extrair_itens("2 mesas e 20 cadeiras, 3x cortina") == [{"produto": "mesas", "quantidade": 2}, {"produto": "cadeiras", "quantidade": 20}, {"produto": "cortina", "quantidade": 3}]
    assert a.diarias("2026-11-26", "2026-11-26") == 1 and a.diarias("2026-11-26", "2026-11-29") == 3
    assert a.calcular_total([{"valor_diaria": 10.1, "quantidade": 3}], 2, 5) == 55.6
    assert a.calcular_total([{"valor_diaria": 1, "quantidade": 1}], 1, 99) == 0


# ---------- pela API (/chat) ----------
@pytest.fixture
def cliente_http(monkeypatch):
    monkeypatch.setattr(main, "provedor_llm", object())  # só para o filtro "há modelo"; decidir_acao é trocado nos testes
    return TestClient(main.app)


@pytest.fixture
def cliente_sem_modelo():
    return TestClient(main.app)


def test_chat_com_dados_inicia_a_conversa_em_vez_do_formulario(cliente_http, monkeypatch):
    monkeypatch.setattr(main, "decidir_acao", lambda *x, **k: Decisao(chamadas=[{"nome": "cadastrar_orcamento", "args": {"cliente": "João Victor", "itens": [{"produto": "mesas", "quantidade": 2}]}}], texto=None))
    r = cliente_http.post("/chat", json={"pergunta": "crie um orçamento para João Victor com 2 mesas", "hoje": HOJE}).json()
    assert r["consultas"][0]["nome"] == "localizar_clientes" and r["agente"]["aguardando"] == "consulta" and "acoes" not in r


def test_chat_sem_dados_continua_abrindo_o_formulario(cliente_http, monkeypatch):
    monkeypatch.setattr(main, "decidir_acao", lambda *x, **k: Decisao(chamadas=[{"nome": "cadastrar_orcamento", "args": {}}], texto=None))
    r = cliente_http.post("/chat", json={"pergunta": "quero criar um orçamento", "hoje": HOJE}).json()
    assert r["acoes"][0]["nome"] == "cadastrar_orcamento" and not r.get("agente")


def test_chat_continua_a_conversa_sem_chamar_o_modelo(cliente_http, monkeypatch):
    def proibido(*x, **k):
        raise AssertionError("o modelo não pode ser chamado no meio da conversa")
    monkeypatch.setattr(main, "decidir_acao", proibido)
    estado = pedido()["agente"]
    r = cliente_http.post("/chat", json={"pergunta": "xx", "hoje": HOJE, "agente": estado, "resultados": [clientes(JOAO), produtos([MESA], [CADEIRA])]}).json()
    assert r["consultas"][0]["nome"] == "verificar_disponibilidade"
    r = cliente_http.post("/chat", json={"pergunta": "xx", "hoje": HOJE, "agente": r["agente"], "resultados": [SEM_FALTAS]}).json()
    assert "Total: R$ 160,00" in r["resposta"] and r["opcoes"] == ["Confirmar", "Cancelar"] and "executar" not in r
    r = cliente_http.post("/chat", json={"pergunta": "sim", "hoje": HOJE, "agente": r["agente"]}).json()
    assert r["executar"][0]["nome"] == "criar_orcamento" and r["agente"] is None


def test_chat_pergunta_no_meio_cai_no_fluxo_normal(cliente_sem_modelo):
    estado = a.continuar(pedido(evento=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)["agente"]
    r = cliente_sem_modelo.post("/chat", json={"pergunta": "como criar um orçamento?", "agente": estado}).json()
    assert r["fonte"]["id"] == "orc-criar" and not r.get("agente")


# ---------- nomes parecidos não são o mesmo nome ----------
@pytest.mark.parametrize("busca,nome,esperado", [
    ("Maria", "Mariana Albuquerque", False), ("Vitor", "Vitória Lima", False), ("Maria", "Maria Souza", True),
    ("joao victor", "João Victor Lima", True), ("victor joao", "João Victor", True), ("Ana", "Joana", False), ("", "Ana", False),
])
def test_busca_casa_palavra_inteira(busca, nome, esperado):
    assert a.casa_nome(busca, nome) is esperado


def test_plural_do_produto_casa_mas_palavra_parecida_nao():
    assert a.casa_nome("mesa", "Mesa redonda", singular=True) and a.casa_nome("cadeira", "Cadeiras brancas", singular=True)
    assert not a.casa_nome("mesa", "Mesada", singular=True)


def test_agente_descarta_cliente_que_o_front_devolveu_por_engano():
    p = pedido(cliente="Maria")
    r = a.continuar(p["agente"], "x", [clientes({"id": 3, "nome": "Mariana Albuquerque", "cidade": "Fortaleza"}), produtos([MESA], [CADEIRA])], HOJE)
    assert r["texto"].startswith("Não encontramos esse usuário") and "Mariana" not in r["texto"]
    assert "cliente_id" not in r["agente"]["rascunho"]


def test_agente_descarta_produto_parecido_mas_aceita_o_codigo():
    r = a.continuar(pedido()["agente"], "x", [clientes(JOAO), produtos([{"id": 9, "nome": "Mesada de mármore", "valor_diaria": 80}], [CADEIRA])], HOJE)
    assert "Não encontramos o produto “mesas”" in r["texto"]
    p = a.iniciar("cadastrar_orcamento", {"cliente": "João Victor", "evento": "X", "data_retirada": "2026-11-26", "itens": [{"produto": "MS-01", "quantidade": 1}]}, HOJE)
    r = a.continuar(p["agente"], "x", [clientes(JOAO), produtos([{"id": 9, "nome": "Mesa de apoio", "codigo": "MS-01", "valor_diaria": 80}])], HOJE)
    assert r["consultas"][0]["nome"] == "verificar_disponibilidade"


# ---------- datas relativas e nome do evento ----------
@pytest.mark.parametrize("fala,depois", [("no dia seguinte", 1), ("mesmo dia", 0), ("3 dias depois", 3), ("2 diárias", 2), ("amanhã", 1), ("sei lá", None)])
def test_dias_depois(fala, depois):
    assert a._dias_depois(fala) == depois


def test_uma_data_mais_dia_seguinte_na_mesma_frase():
    p = a.continuar(pedido(data_retirada=None, evento="Casamento")["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    r = a.continuar(p["agente"], "vai ser dia 26/11/2026, pra devolver no dia seguinte", None, HOJE)
    assert r["consultas"][0]["args"]["retirada"] == "2026-11-26" and r["consultas"][0]["args"]["devolucao"] == "2026-11-27"


def test_so_dia_seguinte_na_pergunta_da_devolucao():
    p = a.continuar(pedido(data_retirada=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    p = a.continuar(p["agente"], "26/11/2026", None, HOJE)
    assert p["agente"]["aguardando"] == "devolucao"
    r = a.continuar(p["agente"], "no dia seguinte", None, HOJE)
    assert r["consultas"][0]["args"]["devolucao"] == "2026-11-27"


@pytest.mark.parametrize("fala,evento", [("é o casamento da Vitória", "Casamento da Vitória"), ("aniversário de 15 anos", "Aniversário de 15 anos"), ("evento de formatura", "Formatura"), ("é um churrasco", "Churrasco"), ("Casamento", "Casamento")])
def test_nome_do_evento_limpo(fala, evento):
    p = a.continuar(pedido(evento=None)["agente"], "x", [clientes(JOAO), produtos([MESA], [CADEIRA])], HOJE)
    assert a.continuar(p["agente"], fala, None, HOJE)["agente"]["rascunho"]["evento"] == evento


@pytest.mark.parametrize("frase", ["faça um orçamento para o cliente Vitor", "faz um orçamento pra Maria", "gere um orçamento para a Ana", "monte um orçamento para João"])
def test_filtro_reconhece_faca_gere_monte(frase):
    from app.ferramentas import parece_pedido_de_acao_ou_dados
    assert parece_pedido_de_acao_ou_dados(frase)
