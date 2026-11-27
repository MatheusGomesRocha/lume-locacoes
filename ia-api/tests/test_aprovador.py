"""Agent 4 (Aprovador): as 5 condições, a reprodução da pergunta no chat e a decisão composta. O modelo é simulado."""
import copy
import json

from evolucao import aprovador
from evolucao.aprovador import ITENS_DO_APROVADOR, reproduzir, revisar, risco_da_consulta
from evolucao.esquema import HOJE_TESTE
from evolucao.pipeline import gerar_relatorios

from tests.test_evolucao import Modelo

PERGUNTAS = ["quais os nomes dos clientes cadastrados hoje?", "quem foi cadastrado hoje?"]
PROPOSTA = {
    "titulo": "Nomes dos clientes cadastrados em um período", "decisao": "criar_consulta", "motivo": "Pedido de lista de nomes.", "perguntas": PERGUNTAS, "vezes": 2,
    "entidade": "clientes", "operacao": "listar", "campo_soma": None, "saida": ["nome"],
    "filtros": [{"campo": "criado_em", "op": "maior_igual", "parametro": "de"}, {"campo": "criado_em", "op": "menor_igual", "parametro": "ate"}],
    "parametros": {"de": {"tipo": "data", "obrigatorio": True}, "ate": {"tipo": "data", "obrigatorio": True}},
    "expectativas": [{"descricao": "hoje", "params": {"de": HOJE_TESTE, "ate": HOJE_TESTE}, "esperado_total": 0},
                     {"descricao": "tudo", "params": {"de": "2000-01-01", "ate": HOJE_TESTE}, "esperado_total": 5}],
}
SPEC = {
    "nome": "clientes_cadastrados_periodo", "descricao": "Lista os nomes dos clientes cadastrados entre duas datas.", "entidade": "clientes", "operacao": "listar",
    "saida": ["nome"], "ordenar_por": "nome", "limite": 50, "permissao": "clientes.ver", "filtros": PROPOSTA["filtros"], "parametros": PROPOSTA["parametros"],
    "exemplos": ["quais os nomes dos clientes cadastrados hoje?", "quem foi cadastrado hoje?", "listar clientes cadastrados ontem", "nomes dos clientes cadastrados esta semana"],
    "palavras_chave": ["clientes", "cadastrados"], "sinonimos": {},
}


class Aprovador:
    """Responde ao APROVADOR com um JSON combinado e guarda o que recebeu (para provar o que ele NÃO vê)."""

    def __init__(self, decisao="aprovar", itens_falhos=(), duvidas=(), cru=None):
        self.saida = cru or {"decisao": decisao, "motivo": "tudo certo", "duvidas": list(duvidas), "riscos": [],
                             "itens": [{"item": i, "ok": i not in itens_falhos, "evidencia": "visto"} for i in ITENS_DO_APROVADOR]}
        self.recebido = []

    def gerar(self, sistema, usuario):
        assert "o APROVADOR" in sistema
        self.recebido.append(usuario)
        return json.dumps(self.saida, ensure_ascii=False)


def relatorio_pronto(spec=None, proposta=None, catalogo=None, casos=None):
    spec = spec or copy.deepcopy(SPEC)
    prop = proposta or copy.deepcopy(PROPOSTA)
    casos = casos if casos is not None else [
        {"descricao": "sem permissão", "tipo": "permissao", "sessao": "sem_nada", "params": {"de": HOJE_TESTE, "ate": HOJE_TESTE}, "esperado": {"erro": "permissao"}},
        {"descricao": "falta de", "tipo": "parametro", "sessao": "master", "params": {"ate": HOJE_TESTE}, "esperado": {"erro": "parametro"}},
        {"descricao": "tudo", "tipo": "execucao", "sessao": "master", "params": {"de": "2000-01-01", "ate": HOJE_TESTE}, "esperado": {"total": 5}},
    ]
    m = Modelo(propostas=[prop], spec=spec, casos=casos)
    return gerar_relatorios(m, None, [{"pergunta": q, "vezes": 1, "tipo": "dados"} for q in prop["perguntas"]], catalogo or [], lambda i: f"EV-{i + 1:04d}")[0]


def test_reproducao_escolhe_a_consulta_e_preenche_as_datas():
    r = reproduzir(SPEC, PERGUNTAS, [])
    assert r["ok"], r
    assert r["casos"][0]["parametros"] == {"de": HOJE_TESTE, "ate": HOJE_TESTE} and r["casos"][0]["consulta_escolhida"] == SPEC["nome"]


def test_reproducao_reprova_quando_a_pergunta_cai_em_outra_consulta_ou_nao_acha():
    outra = {**SPEC, "nome": "nomes_clientes_antiga", "exemplos": SPEC["exemplos"]}
    cai_em_outra = reproduzir({**SPEC, "exemplos": ["algo totalmente diferente aqui", "outra coisa qualquer", "mais uma coisa"], "palavras_chave": ["zzz"]}, PERGUNTAS, [outra])
    assert not cai_em_outra["ok"] and "não chega" in cai_em_outra["casos"][0]["motivo"]
    sem_param = {**SPEC, "parametros": {**SPEC["parametros"], "mes": {"tipo": "texto", "obrigatorio": True}}}
    assert "não consegue preencher" in reproduzir(sem_param, PERGUNTAS, [])["casos"][0]["motivo"]
    assert not reproduzir(SPEC, [], [])["ok"]


def test_risco_so_e_baixo_para_leitura_livre_sem_dado_pessoal():
    assert risco_da_consulta(SPEC, [])["nivel"] == "baixo"
    assert risco_da_consulta({**SPEC, "saida": ["nome", "email"]}, [])["nivel"] == "alto"            # pessoal
    assert risco_da_consulta({**SPEC, "entidade": "usuarios", "saida": ["nome"], "filtros": []}, [])["nivel"] == "alto"  # restrita
    assert risco_da_consulta(SPEC, [{"nome": SPEC["nome"]}])["nivel"] == "alto"                        # altera o que existe
    assert risco_da_consulta({**SPEC, "entidade": "nada"}, [])["nivel"] == "alto"


def test_aprova_quando_todas_as_condicoes_valem_e_o_modelo_nao_ve_o_raciocinio_dos_outros():
    rel = relatorio_pronto()
    assert rel["veredito"] == "aprovar_recomendado", rel["texto"]
    ap = Aprovador()
    rev = revisar(rel, [], ap)
    assert rev["decisao"] == "aprovar" and [c["id"] for c in rev["condicoes"]] == ["C1", "C2", "C3", "C4", "C5"] and all(c["ok"] for c in rev["condicoes"])
    visto = ap.recebido[0]
    assert "Pedido de lista de nomes" not in visto and '"regras_declaradas"' not in visto and '"motivo": "Pedido' not in visto  # raciocínio do Construtor e motivo do Analista ficam de fora
    for chave in ("PERGUNTAS_ORIGINAIS", "CONSULTA_FINAL", "RELATORIO_DO_TESTER", "TESTE_DE_REPRODUCAO", "RISCO_CALCULADO"):
        assert chave in visto


def test_modelo_discordando_deixa_pendente_e_formato_ruim_nunca_aprova():
    rel = relatorio_pronto()
    assert revisar(rel, [], Aprovador("deixar_pendente", duvidas=["período"]))["decisao"] == "deixar_pendente"
    assert revisar(rel, [], Aprovador("aprovar", itens_falhos=["generica"]))["decisao"] == "deixar_pendente"   # disse aprovar mas marcou item falho
    assert revisar(rel, [], Aprovador("aprovar", duvidas=["não sei"]))["decisao"] == "deixar_pendente"
    assert revisar(rel, [], Aprovador(cru={"decisao": "aprovar", "motivo": "ok", "itens": []}))["decisao"] == "deixar_pendente"  # não avaliou os 10 itens
    assert revisar(rel, [], Aprovador(cru="lixo"))["decisao"] == "deixar_pendente"
    assert revisar(rel, [], None)["decisao"] == "deixar_pendente"  # sem modelo
    assert revisar(rel, [], Aprovador("reprovar"))["decisao"] == "reprovar"


def test_condicao_de_codigo_que_falha_nem_chama_o_modelo():
    rel = relatorio_pronto()
    rel["avaliacao"]["veredito"] = "revisar_com_atencao"
    ap = Aprovador()
    rev = revisar(rel, [], ap)
    assert rev["decisao"] == "deixar_pendente" and not ap.recebido and not rev["condicoes"][1]["ok"]
    rel["avaliacao"]["veredito"] = "reprovar_recomendado"
    assert revisar(rel, [], Aprovador())["decisao"] == "reprovar"


def test_campo_pessoal_reprova_e_pergunta_que_nao_chega_na_consulta_bloqueia():
    rel = relatorio_pronto()
    rel["pacote"]["spec"] = {**rel["pacote"]["spec"], "saida": ["nome", "email"]}
    rev = revisar(rel, [], Aprovador())
    assert rev["decisao"] == "reprovar" and not next(c for c in rev["condicoes"] if c["id"] == "C3")["ok"]
    rel = relatorio_pronto()
    rel["perguntas"] = ["como emito uma nota fiscal?"]
    rev = revisar(rel, [], Aprovador())
    assert rev["decisao"] == "deixar_pendente" and not next(c for c in rev["condicoes"] if c["id"] == "C4")["ok"]


def test_item_sem_consulta_nao_tem_o_que_revisar():
    rev = revisar({"perguntas": ["x"], "pacote": None, "avaliacao": None}, [], Aprovador())
    assert rev["decisao"] == "deixar_pendente" and rev["condicoes"][0]["id"] == "C0"


def test_endpoint_revisar_devolve_a_revisao_sem_alterar_nada(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    rel = relatorio_pronto()
    copia = copy.deepcopy(rel)
    monkeypatch.setattr(main, "provedor_llm", Aprovador())
    monkeypatch.delenv("IA_APROVADOR_MODELO", raising=False)
    c = TestClient(main.app)
    r = c.post("/evolucao/revisar", json={"relatorio": rel, "catalogo": []}).json()
    assert r["decisao"] == "aprovar" and len(r["condicoes"]) == 5 and rel == copia
    monkeypatch.setattr(main, "provedor_llm", None)
    assert c.post("/evolucao/revisar", json={"relatorio": rel, "catalogo": []}).status_code == 503
