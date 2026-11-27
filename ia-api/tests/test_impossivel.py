"""Perguntas sobre dado que o sistema não guarda: respondidas na hora e nunca enviadas aos Agents."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.impossivel import ATRIBUTOS, ENTIDADES, conferir_contra_esquema, pergunta_impossivel
from evolucao.esquema import ESQUEMA


@pytest.mark.parametrize("pergunta,atributo", [
    ("Quantos Usuários que residem em Fortaleza temos?", "cidade"),
    ("quantos orçamentos em Fortaleza?", "cidade"),
    ("quantos usuários têm mais de 30 anos de idade?", "idade"),
    ("Quais produtos têm a marca Samsung?", "marca"),
    ("quantos clientes são mulheres?", "sexo"),
    ("quem criou o orçamento 3?", "quem criou"),
    ("quantos usuários logaram ontem? qual o último acesso", "acesso"),
])
def test_dado_que_nao_existe_e_reconhecido(pergunta, atributo):
    r = pergunta_impossivel(pergunta)
    assert r and atributo in r["atributo"] and "Não consigo responder" in r["resposta"]


@pytest.mark.parametrize("pergunta", [
    "Quantos clientes moram em Fortaleza?",            # clientes guarda cidade
    "quantos orçamentos do cliente que mora em Sobral?",  # cita clientes junto
    "Quantos clientes foram cadastrados nos últimos 7 dias?",
    "quantos usuários admin existem?",
    "como faço para cadastrar um cliente em Fortaleza?",   # dúvida de uso, não pedido de dado
    "cadastre um cliente de Fortaleza",
    "quantos produtos de iluminação?",
])
def test_o_que_existe_ou_nao_e_dado_passa(pergunta):
    assert pergunta_impossivel(pergunta) is None


def test_resposta_diz_o_que_o_sistema_guarda_e_quem_guarda_cidade():
    r = pergunta_impossivel("Quantos Usuários que residem em Fortaleza temos?")["resposta"]
    assert "usuários do sistema" in r and "e-mail" in r and "clientes" in r


def test_esquema_e_textos_andam_juntos():
    assert conferir_contra_esquema() == []
    # todo campo de entidade citado em "quem guarda" existe de fato
    assert all(e in ESQUEMA for _, _, quem in ATRIBUTOS.values() for e in quem) and set(ENTIDADES) == set(ESQUEMA)


def test_chat_responde_na_hora_sem_modelo_e_marca_impossivel(tmp_path, monkeypatch):
    monkeypatch.setenv("IA_LOG_SEM_RESPOSTA", str(tmp_path / "sem.jsonl"))
    r = TestClient(main.app).post("/chat", json={"pergunta": "Quantos Usuários que residem em Fortaleza temos?"}).json()
    assert r["impossivel"] is True and r["encontrou"] is True and r["gerada_por_llm"] is False and "consultas" not in r
    assert not (tmp_path / "sem.jsonl").exists()  # nada vai para a lista de perguntas sem resposta


def test_agents_nao_recebem_pergunta_impossivel(monkeypatch):
    chamadas = []
    monkeypatch.setattr(main, "provedor_llm", object())
    monkeypatch.setattr(main, "gerar_relatorios", lambda *a, **k: chamadas.append(a[2]) or [])
    corpo = {"perguntas": [{"pergunta": "Quantos Usuários que residem em Fortaleza temos?", "vezes": 3, "tipo": "dados"},
                           {"pergunta": "Quantos clientes foram cadastrados nos últimos 7 dias?", "vezes": 1, "tipo": "dados"}]}
    r = TestClient(main.app).post("/evolucao/propor", json=corpo).json()
    assert [p["pergunta"] for p in chamadas[0]] == ["Quantos clientes foram cadastrados nos últimos 7 dias?"]
    assert len(r["ignoradas"]) == 1 and "cidade" in r["ignoradas"][0]["motivo"]
