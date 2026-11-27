"""A matriz de perguntas gerada do esquema tem que passar inteira, e cobrir cada entidade."""
from avaliacao import matriz
from evolucao.esquema import ESQUEMA


def test_matriz_passa_inteira_em_processo():
    res = matriz.rodar(matriz.em_processo())
    assert [f"{r['id']} {r['pergunta']}: {r['erro']}" for r in res if r["erro"]] == []


def test_matriz_cobre_todas_as_entidades_e_os_quatro_grupos():
    casos = matriz.gerar_casos()
    assert {c["grupo"] for c in casos} == {"impossivel", "possivel", "consulta", "nao_consulta"}
    for e in ESQUEMA:
        assert any(e in c["pergunta"].lower() or matriz.ENTIDADES[e][1] in c["pergunta"].lower() for c in casos), e
    assert len(casos) > 100 and len({c["id"] for c in casos}) == len(casos)


def test_campo_novo_no_esquema_tira_a_pergunta_da_lista_de_impossiveis(monkeypatch):
    import copy
    from app import impossivel
    novo = copy.deepcopy(ESQUEMA)
    novo["usuarios"]["campos"]["cidade"] = {"tipo": "texto", "rotulo": "Cidade", "valores": [], "nivel": "normal"}
    monkeypatch.setattr(impossivel, "ESQUEMA", novo)
    assert "usuarios" in impossivel.quem_guarda("localizacao")
