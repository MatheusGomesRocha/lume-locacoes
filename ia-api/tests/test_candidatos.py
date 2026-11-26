"""Ciclo com perguntas reais: logs -> candidatos -> casos aprovados."""
import json

from app.busca import BaseConhecimento
from avaliacao.candidatos import aprovar, gerar, ler_registros
from avaliacao.coletar import CASOS

from app.main import PASTA_DADOS

base = BaseConhecimento(PASTA_DADOS / "faq.json")
CASOS_ATUAIS = json.loads(CASOS.read_text(encoding="utf-8"))

LOGS = [
    {"pergunta": "como adicionar uma pessoa no sistema", "tipo": "nao_encontrou", "feedback": None},
    {"pergunta": "Como adicionar uma pessoa no sistema?", "tipo": "nao_encontrou", "feedback": None},   # repetida
    {"pergunta": "como criar um orçamento", "tipo": "ajuda", "feedback": "negativo"},                    # 👎, mas já é caso? não: texto igual ao faq-01
    {"pergunta": "como faço um orçamento rápido", "tipo": "ajuda", "feedback": "positivo"},               # deu certo: ignora
    {"pergunta": "quantos clientes?", "tipo": "consulta", "feedback": None},                              # consulta ok: ignora
    {"pergunta": "oi", "tipo": "erro", "feedback": None},
]


def test_gera_candidatos_agrupando_repetidas_e_ignorando_o_que_deu_certo():
    cands = gerar(LOGS, CASOS_ATUAIS, base)
    perguntas = [c["pergunta"] for c in cands]
    assert perguntas[0].lower().startswith("como adicionar uma pessoa")  # a mais repetida vem primeiro
    assert cands[0]["vezes"] == 2 and cands[0]["motivo"] == "sem resposta no FAQ"
    assert "como faço um orçamento rápido" not in perguntas and "quantos clientes?" not in perguntas
    assert cands[0]["aprovado"] is False and cands[0]["espera"] == {}
    assert len(cands[0]["sugestoes_do_faq"]) <= 3


def test_pergunta_que_ja_e_caso_nao_vira_candidato():
    ja = CASOS_ATUAIS[0]["pergunta"]
    assert gerar([{"pergunta": ja, "tipo": "nao_encontrou"}], CASOS_ATUAIS, base) == []


def test_so_entra_nos_casos_o_que_foi_aprovado_com_espera():
    cands = [
        {"pergunta": "como adicionar uma pessoa", "espera": {"fonte": "acesso-usuario-criar"}, "aprovado": True},
        {"pergunta": "sem espera", "espera": {}, "aprovado": True},
        {"pergunta": "nao aprovado", "espera": {"encontrou": False}, "aprovado": False},
    ]
    novos, qtd = aprovar(cands, CASOS_ATUAIS)
    assert qtd == 1 and novos[-1]["grupo"] == "real" and novos[-1]["espera"] == {"fonte": "acesso-usuario-criar"}
    assert len({c["id"] for c in novos}) == len(novos)
    assert aprovar(cands, novos)[1] == 0  # rodar de novo não duplica


def test_le_json_do_laravel_e_jsonl_do_ia_api(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"data": [{"pergunta": "x", "tipo": "erro"}]}), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text('{"pergunta": "y", "melhor_score": 0.1}\n', encoding="utf-8")
    assert ler_registros(tmp_path / "a.json")[0]["pergunta"] == "x"
    assert gerar(ler_registros(tmp_path / "b.jsonl"), [], base)[0]["motivo"] == "sem resposta no FAQ"
