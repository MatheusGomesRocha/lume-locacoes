"""Teste de mutação: toda quebra feita de propósito numa consulta boa tem que ser percebida por alguma checagem fixa."""
from avaliacao import mutacao


def test_a_base_do_teste_de_mutacao_passa_limpa():
    r = mutacao.rodar()
    assert not r["base_com_bloqueio"], r["base_com_bloqueio"]


def test_nenhuma_quebra_passa_sem_ser_percebida():
    r = mutacao.rodar()
    novos = [s for s in r["sobreviventes"] if s["mutante"] not in mutacao.SOBREVIVENTES_CONHECIDOS]
    assert not novos, "\n".join(f"{s['mutante']}: esperado {s['esperado']}, achou {s['obtido']}" for s in novos)
    assert r["total"] >= 40  # a lista de quebras não pode encolher em silêncio


def test_verbo_da_pergunta_manda_na_data_do_periodo():
    from evolucao import cobertura
    assert cobertura.campos_de_data_pedidos("quantos orçamentos foram criados hoje?", "orcamentos") == ["criado_em"]
    assert cobertura.campos_de_data_pedidos("o que será devolvido hoje?", "orcamentos") == ["data_devolucao"]
    assert cobertura.campos_de_data_pedidos("quantas cobranças foram pagas essa semana?", "pagamentos") == ["pago_em"]
    assert cobertura.campos_de_data_pedidos("orçamentos de hoje", "orcamentos") == []  # sem verbo: a Lumi pergunta qual data
    spec = mutacao.corpus()["orcamentos"]
    spec = {**spec, "operacao": "contar", "saida": [], **mutacao._periodo("data_retirada")}
    faltam = cobertura.nao_cobertas("quantos orçamentos foram criados hoje?", spec, "2026-11-27")
    assert faltam and "criado em" in faltam[0]["rotulo"]  # filtra pela retirada: não responde "criados"
    assert not cobertura.nao_cobertas("quantos orçamentos retiram hoje?", spec, "2026-11-27")
