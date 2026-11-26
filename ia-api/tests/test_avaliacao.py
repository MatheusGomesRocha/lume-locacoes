"""Testa a própria avaliação: o conjunto de casos é válido e a pontuação julga certo. Sem rede, sem modelo."""
import json

import pytest

from app import ferramentas
from avaliacao.coletar import carregar_casos, coletar, corpo_do_caso
from avaliacao.pontuar import avaliar, pontuar, relatorio_md

from pathlib import Path

CASOS = carregar_casos()
FAQ_IDS = {i["id"] for i in json.loads((Path(__file__).parent.parent / "data" / "faq.json").read_text(encoding="utf-8"))}


# ---------- o conjunto de casos ----------
def test_ids_unicos_e_campos_obrigatorios():
    ids = [c["id"] for c in CASOS]
    assert len(ids) == len(set(ids)) >= 50
    assert all(c["pergunta"] and c["espera"] and c["grupo"] for c in CASOS)


def test_fontes_esperadas_existem_no_faq():
    for c in CASOS:
        for f in (c["espera"].get("fonte") if isinstance(c["espera"].get("fonte"), list) else [c["espera"].get("fonte")]):
            assert f is None or f in FAQ_IDS, (c["id"], f)


LEITURAS_DO_AGENTE = {"localizar_clientes", "localizar_produtos", "verificar_disponibilidade"}  # o agente conversacional consulta antes de cadastrar


def test_ferramentas_esperadas_existem():
    for c in CASOS:
        e = c["espera"]
        for f in (e.get("ferramenta") if isinstance(e.get("ferramenta"), list) else [e.get("ferramenta")]) + e.get("ferramenta_proibida", []):
            assert f is None or f in ferramentas.TODAS or f in LEITURAS_DO_AGENTE, (c["id"], f)


def test_o_conjunto_cobre_todos_os_grupos_e_todas_as_ferramentas():
    assert {c["grupo"] for c in CASOS} >= {"faq", "contexto", "consulta", "cadastro", "exclusao", "fora_de_escopo", "seguranca", "conversa"}
    usadas = {f for c in CASOS for f in (c["espera"].get("ferramenta") if isinstance(c["espera"].get("ferramenta"), list) else [c["espera"].get("ferramenta")]) if f}
    assert {"consultar_orcamentos", "consultar_clientes", "consultar_produtos", "consultar_cobrancas", "resumo_painel",
            "cadastrar_cliente", "cadastrar_produto", "cadastrar_orcamento", "excluir_registro"} <= usadas


def test_corpo_do_caso_so_leva_o_que_existe():
    assert corpo_do_caso({"pergunta": "oi"}) == {"pergunta": "oi"}
    assert corpo_do_caso({"pergunta": "e?", "historico": ["a"], "ultimo_id": "x", "hoje": "2026-11-25"}) == {"pergunta": "e?", "historico": ["a"], "ultimo_id": "x", "hoje": "2026-11-25"}


# ---------- a pontuação ----------
def caso(**espera):
    return {"id": "t", "grupo": "faq", "pergunta": "p", "espera": espera}


def resp(**kw):
    return {"encontrou": True, "resposta": "texto", "fonte": None, **kw}


def test_fonte_certa_e_errada():
    assert avaliar(caso(fonte="a"), resp(fonte={"id": "a"})) == []
    assert avaliar(caso(fonte=["a", "b"]), resp(fonte={"id": "b"})) == []
    assert "fonte 'c'" in avaliar(caso(fonte="a"), resp(fonte={"id": "c"}))[0]
    assert avaliar(caso(fonte="a"), resp())  # sem fonte


def test_encontrou_e_sem_ferramenta():
    assert avaliar(caso(encontrou=False, sem_ferramenta=True), resp(encontrou=False)) == []
    assert avaliar(caso(sem_ferramenta=True), resp(acoes=[{"nome": "excluir_registro", "args": {}}]))


def test_ferramenta_e_argumentos():
    r = resp(consultas=[{"nome": "consultar_orcamentos", "args": {"status": "Aprovado", "busca": "Casamento Ana"}}])
    assert avaliar(caso(ferramenta="consultar_orcamentos", args_contem={"status": "aprovado"}, args_texto={"busca": "casamento"}), r) == []
    assert avaliar(caso(ferramenta=["resumo_painel", "consultar_orcamentos"]), r) == []
    assert avaliar(caso(ferramenta="resumo_painel"), r)
    assert avaliar(caso(args_contem={"status": "pago"}), r)
    assert avaliar(caso(args_texto_em_qualquer="ana"), r) == []
    assert avaliar(caso(args_texto_em_qualquer="bruno"), r)


def test_numeros_comparam_como_numeros():
    r = resp(acoes=[{"nome": "cadastrar_produto", "args": {"valor_diaria": 25.0}}])
    assert avaliar(caso(args_contem={"valor_diaria": 25}), r) == []
    assert avaliar(caso(args_contem={"valor_diaria": 26}), r)


def test_argumentos_inventados_sao_falha():
    r = resp(acoes=[{"nome": "cadastrar_cliente", "args": {"nome": "João"}}])
    assert avaliar(caso(args_ausentes=["nome", "email"]), r) == ["inventou o argumento nome='João'"]
    assert avaliar(caso(args_presentes=["email"]), r)


def test_ferramenta_proibida_e_texto_proibido():
    assert avaliar(caso(ferramenta_proibida=["excluir_registro"]), resp(acoes=[{"nome": "excluir_registro", "args": {}}]))
    assert avaliar(caso(nao_deve_conter=["Você é a Lumi"]), resp(resposta="Ok. voce e a lumi, um robô"))  # sem acento/caixa também pega
    assert avaliar(caso(nao_deve_conter=["segredo"]), resp(resposta="tudo certo")) == []
    assert avaliar(caso(deve_conter_um_de=["ativo", "inativo"]), resp(resposta="Desmarque Ativo")) == []
    assert avaliar(caso(deve_conter_um_de=["ativo"]), resp(resposta="nada")) 


def test_pontuar_resume_por_grupo_e_caso_sem_resposta_falha():
    casos = [{"id": "a", "grupo": "faq", "pergunta": "p", "espera": {"fonte": "x"}}, {"id": "b", "grupo": "faq", "pergunta": "q", "espera": {"fonte": "x"}},
             {"id": "c", "grupo": "seguranca", "pergunta": "r", "espera": {"sem_ferramenta": True}}]
    coletado = {"a": {"resposta": resp(fonte={"id": "x"}, gerada_por_llm=True), "ms": 100, "erro": None},
                "b": {"resposta": None, "ms": None, "erro": "Timeout"}}
    r = pontuar(casos, coletado)
    assert (r["total"], r["acertos"]) == (3, 1)
    assert r["grupos"]["faq"]["acertos"] == 1 and r["grupos"]["seguranca"]["acertos"] == 0
    assert r["latencia_media_ms"] == 100 and r["com_llm"] == 1
    md = relatorio_md(r, "2026-11-25", "teste")
    assert "1/3 (33%)" in md and "O que falhou" in md and "`b`" in md


def test_coletar_registra_erro_sem_parar_e_respeita_a_pausa(monkeypatch):
    esperas = []
    monkeypatch.setattr("avaliacao.coletar.time.sleep", esperas.append)

    def enviar(corpo):
        if corpo["pergunta"] == "ruim":
            raise RuntimeError("caiu")
        return {"resposta": "ok"}

    r = coletar([{"id": "1", "pergunta": "bom"}, {"id": "2", "pergunta": "ruim"}, {"id": "3", "pergunta": "bom"}], enviar, pausa=2.2)
    assert r["1"]["resposta"] == {"resposta": "ok"} and "RuntimeError" in r["2"]["erro"] and r["3"]["erro"] is None
    assert esperas == [2.2, 2.2]
