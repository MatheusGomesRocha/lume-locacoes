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
    r = cliente.post("/evolucao/propor", json={"perguntas": [{"pergunta": "quantos usuários master?"}], "catalogo": [SPEC], "proximo_numero": 7}).json()
    assert r == {"relatorios": [{"id": "EV-0007"}]} and visto["ids"] == ["EV-0007", "EV-0008"] and len(visto["catalogo"]) == 1


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
