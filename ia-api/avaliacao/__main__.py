"""Uso (a partir da pasta ia-api):

  python -m avaliacao --url https://lume-ia.onrender.com        # coleta + pontua contra a API publicada
  python -m avaliacao --local                                    # coleta + pontua em processo (precisa de GEMINI_API_KEY)
  python -m avaliacao --pontuar avaliacao/respostas.json         # só pontua respostas já coletadas (sem rede)

Opções: --grupo faq, --minimo 0.85 (sai com erro se a taxa geral ficar abaixo), --md relatorio.md, --salvar respostas.json
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from avaliacao.coletar import carregar_casos, coletar, enviar_em_processo, enviar_por_http
from avaliacao.pontuar import pontuar, relatorio_md, taxa


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="avaliacao")
    origem = p.add_mutually_exclusive_group(required=True)
    origem.add_argument("--url")
    origem.add_argument("--local", action="store_true")
    origem.add_argument("--pontuar", metavar="ARQUIVO")
    p.add_argument("--token")
    p.add_argument("--grupo")
    p.add_argument("--pausa", type=float, default=2.2)
    p.add_argument("--minimo", type=float)
    p.add_argument("--md")
    p.add_argument("--salvar")
    a = p.parse_args(argv)

    casos = carregar_casos(a.grupo)
    if a.pontuar:
        coletado, onde = json.loads(Path(a.pontuar).read_text(encoding="utf-8")), a.pontuar
    else:
        enviar = enviar_por_http(a.url, a.token) if a.url else enviar_em_processo()
        coletado, onde = coletar(casos, enviar, a.pausa), a.url or "a aplicação em processo"
        if a.salvar:
            Path(a.salvar).write_text(json.dumps(coletado, ensure_ascii=False, indent=1), encoding="utf-8")

    resultado = pontuar([c for c in casos if c["id"] in coletado], coletado)
    texto = relatorio_md(resultado, date.today().isoformat(), onde)
    print(texto)
    if a.md:
        Path(a.md).write_text(texto, encoding="utf-8")
    if a.minimo is not None and taxa(resultado["acertos"], resultado["total"]) < a.minimo:
        print(f"Abaixo do mínimo de {a.minimo:.0%}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
