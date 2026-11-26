"""Ciclo com perguntas reais: transforma o que os usuários perguntaram em candidatos a caso de avaliação.

  1) exporte os logs:   curl -H "Authorization: Bearer TOKEN" https://SUA-API/api/chat-logs > logs.json
                        (ou use o arquivo perguntas_sem_resposta.jsonl que a ia-api grava sozinha)
  2) gere candidatos:   python -m avaliacao.candidatos logs.json --saida candidatos.json
  3) REVISE o arquivo:  para cada pergunta, preencha "espera" (ex.: {"fonte": "acesso-usuario-criar"}) e ponha "aprovado": true;
                        se for dúvida legítima que o FAQ não cobre, escreva o item novo no faq.json primeiro;
                        se não é assunto do sistema, use {"encontrou": false, "sem_ferramenta": true}
  4) incorpore:         python -m avaliacao.candidatos --aprovar candidatos.json
                        (os aprovados entram no casos.json e passam a valer em toda rodada)

O script nunca decide qual é a resposta certa: só separa o que merece revisão (não encontrou, 👎, erro),
agrupa repetidas, ignora o que já é caso e sugere os itens do FAQ mais parecidos.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.busca import BaseConhecimento, normalizar

RAIZ = Path(__file__).resolve().parent.parent
CASOS = Path(__file__).with_name("casos.json")
TIPOS_QUE_MERECEM_REVISAO = {"nao_encontrou", "erro"}


def ler_registros(caminho: Path) -> list[dict]:
    texto = caminho.read_text(encoding="utf-8").strip()
    if not texto:
        return []
    if caminho.suffix == ".jsonl":
        return [json.loads(linha) for linha in texto.splitlines() if linha.strip()]
    dados = json.loads(texto)
    return dados.get("data", dados) if isinstance(dados, dict) else dados  # a API do Laravel devolve {"data": [...]}


def motivo_da_revisao(r: dict) -> str | None:
    if r.get("feedback") == "negativo":
        return "avaliada com 👎"
    if r.get("tipo") in TIPOS_QUE_MERECEM_REVISAO:
        return {"nao_encontrou": "sem resposta no FAQ", "erro": "erro ao responder"}[r["tipo"]]
    if r.get("melhor_score") is not None and r.get("tipo", "faq") in ("faq", "assunto"):  # linha do perguntas_sem_resposta.jsonl
        return "sem resposta no FAQ"
    return None


def gerar(registros: list[dict], casos_existentes: list[dict], base: BaseConhecimento) -> list[dict]:
    ja_cobertas = {normalizar(c["pergunta"]) for c in casos_existentes}
    vistas: dict[str, dict] = {}
    contagem: Counter = Counter()
    for r in registros:
        pergunta = (r.get("pergunta") or "").strip()
        motivo = motivo_da_revisao(r)
        chave = normalizar(pergunta)
        if not pergunta or not motivo or chave in ja_cobertas:
            continue
        contagem[chave] += 1
        vistas.setdefault(chave, {"pergunta": pergunta, "motivos": set()})["motivos"].add(motivo)
    saida = []
    for n, (chave, qtd) in enumerate(contagem.most_common(), 1):  # as mais repetidas primeiro
        v = vistas[chave]
        saida.append({
            "id": f"real-{n:02d}", "grupo": "real", "pergunta": v["pergunta"], "vezes": qtd, "motivo": "; ".join(sorted(v["motivos"])),
            "sugestoes_do_faq": [{"id": x.id, "pergunta": x.pergunta, "nota": x.score} for x in base.buscar(v["pergunta"], 3)],
            "espera": {}, "precisa_modelo": True, "aprovado": False,
        })
    return saida


def aprovar(candidatos: list[dict], casos: list[dict]) -> tuple[list[dict], int]:
    """Junta os candidatos aprovados (com "espera" preenchida) aos casos. Devolve (casos, quantos entraram)."""
    existentes = {c["id"] for c in casos}
    textos = {normalizar(c["pergunta"]) for c in casos}
    novos = []
    for c in candidatos:
        if not c.get("aprovado") or not c.get("espera") or normalizar(c["pergunta"]) in textos:
            continue
        n = 1
        while f"real-{n:02d}" in existentes:
            n += 1
        id_ = f"real-{n:02d}"
        existentes.add(id_)
        novos.append({"id": id_, "grupo": "real", "pergunta": c["pergunta"], "espera": c["espera"], "precisa_modelo": c.get("precisa_modelo", True)})
    return casos + novos, len(novos)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="avaliacao.candidatos")
    p.add_argument("entradas", nargs="*", help="logs exportados (.json ou .jsonl)")
    p.add_argument("--saida", default="candidatos.json")
    p.add_argument("--aprovar", metavar="ARQUIVO", help="incorpora ao casos.json os candidatos revisados e aprovados")
    a = p.parse_args(argv)

    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    if a.aprovar:
        novos, qtd = aprovar(json.loads(Path(a.aprovar).read_text(encoding="utf-8")), casos)
        CASOS.write_text(json.dumps(novos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{qtd} caso(s) incorporado(s) ao casos.json (total {len(novos)}).")
        return 0
    if not a.entradas:
        p.error("informe os arquivos de log ou use --aprovar")
    registros = [r for caminho in a.entradas for r in ler_registros(Path(caminho))]
    candidatos = gerar(registros, casos, BaseConhecimento(RAIZ / "data" / "faq.json"))
    Path(a.saida).write_text(json.dumps(candidatos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(registros)} registros lidos, {len(candidatos)} candidato(s) para revisar em {a.saida}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
