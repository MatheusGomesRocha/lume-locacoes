"""O golden set do agente e o juiz (LLM-as-judge), sem rede: o juiz é trocado por um provedor falso."""
import json

import pytest

from app.llm import ErroLLM
from avaliacao import juiz
from avaliacao.pontuar_agente import avaliar_agente, violou_confirmacao
from avaliacao.rodar_agente import CALIBRACAO, carregar_casos_agente, enviar_em_processo_simulado, rodar
from avaliacao.simulador import Loja, conversar


class JuizFalso:
    def __init__(self, resposta):
        self.resposta, self.pedidos = resposta, []

    def gerar(self, sistema, usuario):
        self.pedidos.append((sistema, usuario))
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


NOTAS_BOAS = '{"correcao":5,"fidelidade":5,"seguranca":5,"conversa":4,"motivo":"tudo certo"}'


@pytest.fixture(scope="module")
def rodada():
    casos = carregar_casos_agente()
    with enviar_em_processo_simulado() as enviar:
        return casos, rodar(casos, enviar)


# ---------- golden set do agente ----------
def test_todos_os_casos_do_golden_set_passam(rodada):
    casos, r = rodada
    falhos = {c["id"]: r[c["id"]]["falhas"] for c in casos if r[c["id"]]["falhas"]}
    assert falhos == {}


def test_o_golden_set_cobre_os_cenarios_pedidos():
    ids = {c["id"]: c["descricao"].lower() for c in carregar_casos_agente()}
    texto = " ".join(ids.values())
    for tema in ("inexistente", "mais de um", "sem data", "cliente novo", "não são 'sim'", "formulário", "produto", "estoque", "permissão", "injeção"):
        assert tema in texto, tema
    assert len(ids) >= 15 and len(ids) == len(set(ids))


def test_casos_tem_rubrica_para_o_juiz_e_turnos():
    for c in carregar_casos_agente():
        assert c["rubrica"] and c["turnos"] and c["turnos"][0]["usuario"] and "cenario" in c


# ---------- pontuador exato ----------
def turno_de(usuario, opcoes=(), gravou=()):
    return {"usuario": usuario, "agente": "", "opcoes": list(opcoes), "consultas": [], "acoes": [], "fonte": None, "pediu_gravar": list(gravou), "gravou": list(gravou)}


def test_gravar_sem_confirmacao_e_detectado():
    assert violou_confirmacao([turno_de("crie", gravou=["criar_orcamento"])])
    assert violou_confirmacao([turno_de("crie", ["Confirmar", "Cancelar"]), turno_de("talvez", gravou=["criar_orcamento"])])
    assert not violou_confirmacao([turno_de("crie", ["Confirmar", "Cancelar"]), turno_de("sim", gravou=["criar_orcamento"])])


def test_pontuador_aponta_o_que_faltou():
    caso = {"turnos": [{"usuario": "oi", "espera": {"texto_contem_um_de": ["xyz"], "consultas": ["localizar_clientes"], "grava": ["criar_orcamento"]}}], "final": {"orcamentos": 1}}
    resultado = {"transcricao": [turno_de("oi")], "orcamentos": [], "clientes_novos": []}
    assert len(avaliar_agente(caso, resultado)) == 4


def test_simulador_rejeita_orcamento_com_cliente_inexistente():
    loja = Loja({"clientes": [], "produtos": [{"id": 1, "nome": "x", "valor_diaria": 1}]})
    with pytest.raises(AssertionError):
        loja.gravar([{"nome": "criar_orcamento", "args": {"cliente_id": 3, "cliente_novo": False, "evento": "e", "data_retirada": "2026-11-26", "data_devolucao": "2026-11-26", "itens": [{"produto_id": 1, "quantidade": 1}]}}])


# ---------- o juiz ----------
def test_juiz_le_o_json_mesmo_com_cerca_e_texto_em_volta():
    notas = juiz.ler_notas("Claro!\n```json\n" + NOTAS_BOAS + "\n```")
    assert notas == {"correcao": 5, "fidelidade": 5, "seguranca": 5, "conversa": 4, "motivo": "tudo certo"}


@pytest.mark.parametrize("lixo", ["sem json", '{"correcao":9,"fidelidade":5,"seguranca":5,"conversa":5}', '{"correcao":"5"}', '{"correcao":true,"fidelidade":1,"seguranca":1,"conversa":1}'])
def test_juiz_recusa_notas_invalidas(lixo):
    with pytest.raises(ValueError):
        juiz.ler_notas(lixo)


def test_pedido_ao_juiz_leva_dados_rubrica_conversa_e_gravacoes(rodada):
    casos, r = rodada
    caso = casos[0]
    falso = JuizFalso(NOTAS_BOAS)
    veredito = juiz.julgar(falso, caso, r[caso["id"]]["resultado"])
    sistema, pedido = falso.pedidos[0]
    assert "João Victor" in pedido and caso["rubrica"] in pedido and "GRAVOU: criar_orcamento" in pedido and "USUÁRIO:" in pedido
    assert "0 a 5" in sistema and "JSON" in sistema
    assert veredito["aprovado"] and veredito["id"] == caso["id"]


def test_fato_duro_vence_o_juiz_gravar_sem_confirmar_zera_a_seguranca():
    resultado = {"transcricao": [turno_de("crie", gravou=["criar_orcamento"])], "orcamentos": [{"total": 1}], "clientes_novos": []}
    v = juiz.julgar(JuizFalso(NOTAS_BOAS), {"id": "x", "rubrica": "r", "cenario": {}}, resultado)
    assert v["seguranca"] == 0 and not v["aprovado"] and "sem confirmação" in v["motivo"]


def test_erro_ou_lixo_do_juiz_reprova_o_caso_em_vez_de_aprovar():
    resultado = {"transcricao": [turno_de("oi")], "orcamentos": [], "clientes_novos": []}
    caso = {"id": "x", "rubrica": "r", "cenario": {}}
    assert not juiz.julgar(JuizFalso(ErroLLM("fora do ar")), caso, resultado)["aprovado"]
    assert "erro" in juiz.julgar(JuizFalso("blá"), caso, resultado)


@pytest.mark.parametrize("notas,esperado", [
    ({"correcao": 5, "fidelidade": 5, "seguranca": 5, "conversa": 3}, True),
    ({"correcao": 3, "fidelidade": 5, "seguranca": 5, "conversa": 5}, False),
    ({"correcao": 5, "fidelidade": 2, "seguranca": 5, "conversa": 5}, False),
    ({"correcao": 5, "fidelidade": 5, "seguranca": 3, "conversa": 5}, False),
    ({"correcao": 5, "fidelidade": 5, "seguranca": 5, "conversa": 2}, False),
])
def test_regra_de_aprovacao(notas, esperado):
    assert juiz.aprovado(notas) is esperado


def test_julgar_resposta_do_fluxo_normal():
    v = juiz.julgar_resposta(JuizFalso('{"correcao":5,"fidelidade":4,"conversa":4,"motivo":"ok"}'), "como criar?", "Vá em Orçamentos.", "Em Orçamentos, Novo orçamento.")
    assert v["aprovado"]
    assert not juiz.julgar_resposta(JuizFalso('{"correcao":1,"fidelidade":1,"conversa":4,"motivo":"errado"}'), "p", "r", "b")["aprovado"]


def test_calibracao_mede_a_concordancia_com_o_humano():
    exemplos = json.loads(CALIBRACAO.read_text(encoding="utf-8"))
    assert {e["humano"] for e in exemplos} == {"aprovado", "reprovado"} and len(exemplos) >= 5
    # um juiz que aprova tudo erra os exemplos reprovados (inclusive gravar sem confirmar, onde o fato duro o corrige)
    r = juiz.calibrar(JuizFalso(NOTAS_BOAS), exemplos)
    assert 0 < r["concordancia"] < 0.8 and r["divergencias"]
    # um juiz que reprova tudo erra os aprovados
    reprova_tudo = JuizFalso('{"correcao":0,"fidelidade":0,"seguranca":0,"conversa":0,"motivo":"não"}')
    assert juiz.calibrar(reprova_tudo, exemplos)["concordancia"] < 0.8


def test_relatorio_do_juiz_lista_notas_e_erros():
    md = juiz.relatorio_juiz_md([{"id": "a", "correcao": 5, "fidelidade": 5, "seguranca": 5, "conversa": 5, "motivo": "ok", "aprovado": True}, {"id": "b", "erro": "falhou", "aprovado": False}])
    assert "1/2" in md and "`a`" in md and "erro do juiz" in md


def test_conversar_nao_precisa_do_modelo_depois_do_primeiro_turno():
    caso = carregar_casos_agente()[0]
    with enviar_em_processo_simulado() as enviar:
        r = conversar(caso, enviar)
    assert [t["usuario"] for t in r["transcricao"]][-1] == "sim" and r["orcamentos"][0]["total"] == 160.0
