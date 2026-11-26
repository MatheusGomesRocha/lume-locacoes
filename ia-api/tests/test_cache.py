"""Cache das respostas do modelo: a mesma conversa não gasta duas chamadas, e nada de dados do sistema é guardado."""
from app import main
from app.cache import CacheDeRespostas, cache_do_ambiente, chave_da_conversa, normalizar_texto, versao_do_conteudo
from app.llm import Decisao, ErroLLM, LimitadorDiario
from fastapi.testclient import TestClient

client = TestClient(main.app)


# ---------- o cache em si ----------
def test_guarda_e_devolve_e_conta_acertos():
    c = CacheDeRespostas()
    assert c.obter("a") is None
    c.guardar("a", "resposta")
    assert c.obter("a") == "resposta"
    assert c.estatisticas() == {"ativo": True, "itens": 1, "acertos": 1, "erros": 1, "taxa_de_acerto": 0.5}


def test_vence_depois_do_ttl():
    t = [0.0]
    c = CacheDeRespostas(ttl=10, agora=lambda: t[0])
    c.guardar("a", "x")
    t[0] = 9
    assert c.obter("a") == "x"
    t[0] = 11
    assert c.obter("a") is None


def test_descarta_o_menos_usado_quando_enche():
    c = CacheDeRespostas(maximo=2)
    c.guardar("a", 1); c.guardar("b", 2)
    c.obter("a")  # a vira o mais recente
    c.guardar("c", 3)
    assert c.obter("b") is None and c.obter("a") == 1 and c.obter("c") == 3


def test_none_nao_e_guardado_e_desligado_nao_guarda_nada():
    c = CacheDeRespostas()
    c.guardar("a", None)
    assert c.obter("a") is None and c.estatisticas()["itens"] == 0
    off = CacheDeRespostas(maximo=0)
    off.guardar("a", "x")
    assert off.obter("a") is None and off.ativo is False


def test_configuracao_pelo_ambiente():
    c = cache_do_ambiente({"IA_CACHE_MAX": "10", "IA_CACHE_TTL": "60"})
    assert (c.maximo, c.ttl) == (10, 60)
    assert cache_do_ambiente({"IA_CACHE_TTL": "0"}).ativo is False
    assert cache_do_ambiente({"IA_CACHE_MAX": "abc"}).maximo == 500


def test_chave_ignora_acento_caixa_espacos_e_pontuacao_mas_nao_o_contexto():
    k = lambda p, h=(), u=None: chave_da_conversa("ajuda", "v1", p, list(h), u)
    assert k("Como  criar um ORÇAMENTO?") == k("como criar um orcamento")
    assert k("e para editar?", ["excluir produto"], "prod-excluir") != k("e para editar?", ["cadastrar cliente"], "cli-cadastro")
    assert k("oi") != chave_da_conversa("ajuda", "v2", "oi", [], None)
    assert chave_da_conversa("ajuda", "v1", "oi", [], None) != chave_da_conversa("decisao", "v1", "oi", [], None)
    assert normalizar_texto("  Olá,  Mundo!! ") == "ola, mundo"


def test_versao_muda_quando_o_conteudo_muda():
    assert versao_do_conteudo("a", "b") == versao_do_conteudo("a", "b") != versao_do_conteudo("a", "c")


# ---------- na API ----------
class Provedor:
    def __init__(self, texto="Resposta do modelo.", decisao=None, erro=None):
        self.texto, self.decisao, self.erro, self.gerar_chamadas, self.decidir_chamadas = texto, decisao or Decisao(texto="AJUDA"), erro, 0, 0

    def gerar(self, sistema, usuario):
        self.gerar_chamadas += 1
        if self.erro:
            raise self.erro
        return self.texto

    def decidir(self, sistema, usuario, tools):
        self.decidir_chamadas += 1
        return self.decisao


def ligar(monkeypatch, provedor, limite=100):
    monkeypatch.setattr(main, "provedor_llm", provedor)
    monkeypatch.setattr(main, "limitador_llm", LimitadorDiario(limite))
    return provedor


def chat(**corpo):
    r = client.post("/chat", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def test_mesma_pergunta_de_ajuda_so_chama_o_modelo_uma_vez(monkeypatch):
    p = ligar(monkeypatch, Provedor())
    a, b = chat(pergunta="Como criar um orçamento?"), chat(pergunta="como criar um orcamento")
    assert p.gerar_chamadas == 1
    assert a["em_cache"] is False and b["em_cache"] is True
    assert a["resposta"] == b["resposta"] == "Resposta do modelo." and b["gerada_por_llm"] is True


def test_cache_nao_gasta_a_cota_diaria(monkeypatch):
    p = ligar(monkeypatch, Provedor(), limite=1)
    chat(pergunta="Como criar um orçamento?")
    assert chat(pergunta="Como criar um orçamento?")["gerada_por_llm"] is True  # veio do cache, mesmo com a cota esgotada
    assert main.limitador_llm.usadas == 1 and p.gerar_chamadas == 1


def test_contexto_diferente_nao_reaproveita(monkeypatch):
    p = ligar(monkeypatch, Provedor())
    chat(pergunta="e para editar?", historico=["como excluir produto"], ultimo_id="prod-excluir")
    outra = chat(pergunta="e para editar?", historico=["como cadastrar cliente"], ultimo_id="cli-cadastro")
    assert p.gerar_chamadas == 2 and outra["fonte"]["id"] == "cli-editar"


def test_falha_do_modelo_nao_vai_para_o_cache(monkeypatch):
    p = ligar(monkeypatch, Provedor(erro=ErroLLM("fora do ar")))
    assert chat(pergunta="Como criar um orçamento?")["gerada_por_llm"] is False
    p.erro = None
    assert chat(pergunta="Como criar um orçamento?")["gerada_por_llm"] is True  # tentou o modelo de novo
    assert p.gerar_chamadas == 2


def test_decisao_de_ferramenta_tambem_e_reaproveitada(monkeypatch):
    p = ligar(monkeypatch, Provedor(decisao=Decisao(chamadas=[{"nome": "consultar_clientes", "args": {}}])))
    a = chat(pergunta="quantos clientes tenho?", hoje="2026-11-25")
    b = chat(pergunta="Quantos clientes tenho", hoje="2026-11-25")
    assert p.decidir_chamadas == 1 and a["consultas"] == b["consultas"] and b["em_cache"] is True


def test_decisao_depende_da_data_de_hoje(monkeypatch):
    p = ligar(monkeypatch, Provedor())
    chat(pergunta="quanto recebi este mês?", hoje="2026-11-25")
    chat(pergunta="quanto recebi este mês?", hoje="2026-12-02")
    assert p.decidir_chamadas == 2


def test_resposta_com_dados_do_sistema_nunca_e_guardada(monkeypatch):
    p = ligar(monkeypatch, Provedor(texto="Você tem 3."))
    corpo = {"pergunta": "quantos aprovados?", "resultados": [{"nome": "consultar_orcamentos", "args": {}, "resultado": {"total": 3}}]}
    chat(**corpo)
    corpo["resultados"][0]["resultado"] = {"total": 4}
    chat(**corpo)
    assert p.gerar_chamadas == 2 and main.cache.estatisticas()["itens"] == 0


def test_mudar_o_conteudo_invalida_o_cache(monkeypatch):
    p = ligar(monkeypatch, Provedor())
    chat(pergunta="Como criar um orçamento?")
    monkeypatch.setattr(main, "VERSAO_DO_CONTEUDO", "outra-versao")
    chat(pergunta="Como criar um orçamento?")
    assert p.gerar_chamadas == 2


def test_health_mostra_cache_e_chamadas_do_dia(monkeypatch):
    ligar(monkeypatch, Provedor())
    chat(pergunta="Como criar um orçamento?"); chat(pergunta="Como criar um orçamento?")
    h = client.get("/health").json()
    assert h["llm_chamadas_hoje"] == 1 and h["cache"]["acertos"] == 1 and h["cache"]["taxa_de_acerto"] == 0.5
