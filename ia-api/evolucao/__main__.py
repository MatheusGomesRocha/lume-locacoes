"""python -m evolucao rodar | listar | ver ID | decidir ID --aprovar|--reprovar --por NOME | desativar NOME --por NOME"""
import argparse
import os
import sys
from pathlib import Path

from evolucao.pipeline import ErroDecisao, Repositorio, evoluir, ler_sem_resposta


def principal(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evolucao")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rodar", help="Analista -> Construtor -> Tester sobre as perguntas sem resposta")
    r.add_argument("--entrada", default=os.getenv("IA_LOG_SEM_RESPOSTA", str(Path(__file__).resolve().parent.parent / "data" / "perguntas_sem_resposta.jsonl")))
    r.add_argument("--max", type=int, default=20)
    sub.add_parser("listar")
    v = sub.add_parser("ver")
    v.add_argument("id")
    d = sub.add_parser("decidir")
    d.add_argument("id")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--aprovar", action="store_true")
    g.add_argument("--reprovar", action="store_true")
    d.add_argument("--por", required=True)
    x = sub.add_parser("desativar")
    x.add_argument("nome")
    x.add_argument("--por", required=True)
    a = ap.parse_args(argv)
    repo = Repositorio()
    try:
        if a.cmd == "rodar":
            from app.llm import LimitadorDiario, criar_provedor_do_ambiente, limite_diario_do_ambiente
            provedor = criar_provedor_do_ambiente()
            if provedor is None:
                print("Sem modelo: defina GEMINI_API_KEY para os Agents trabalharem.", file=sys.stderr)
                return 2
            perguntas = ler_sem_resposta(Path(a.entrada), a.max)
            if not perguntas:
                print("Nenhuma pergunta sem resposta.")
                return 0
            for rel in evoluir(provedor, LimitadorDiario(limite_diario_do_ambiente()), perguntas, repo):
                print(f"{rel['id']}  {rel['decisao_do_analista']:<15} {rel['veredito'] or '-':<22} {rel['titulo']}")
        elif a.cmd == "listar":
            for rel in repo.propostas():
                print(f"{rel['id']}  {rel['status']:<10} {rel['decisao_do_analista']:<15} {rel['veredito'] or '-':<22} {rel['titulo']}")
        elif a.cmd == "ver":
            print(repo.obter(a.id)["texto"])
        elif a.cmd == "decidir":
            rel = repo.decidir(a.id, a.aprovar, a.por)
            print(f"{rel['id']} {rel['status']} por {rel['decisao']['por']}")
        else:
            print("Desativada:", repo.desativar(a.nome, a.por)["spec"]["nome"])
    except ErroDecisao as e:
        print(f"Não foi possível: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
