"""Uso (a partir da pasta ia-api):

  python -m avaliacao --url https://lume-ia.onrender.com        # coleta + pontua contra a API publicada
  python -m avaliacao --local                                    # coleta + pontua em processo (precisa de GEMINI_API_KEY)
  python -m avaliacao --pontuar avaliacao/respostas.json         # só pontua respostas já coletadas (sem rede)

  python -m avaliacao --agente [--juiz]                          # conversas do agente (golden set) e, se pedido, o juiz
  python -m avaliacao --calibrar-juiz                            # o juiz concorda com as notas humanas?

Opções: --grupo faq, --sem-modelo, --minimo 0.85 (sai com erro se a taxa geral ficar abaixo), --md relatorio.md, --salvar respostas.json
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
    origem = p.add_mutually_exclusive_group()
    origem.add_argument("--url")
    origem.add_argument("--local", action="store_true")
    origem.add_argument("--pontuar", metavar="ARQUIVO")
    p.add_argument("--token")
    p.add_argument("--grupo")
    p.add_argument("--sem-modelo", action="store_true", help="pula os casos que dependem do Gemini (para o CI)")
    p.add_argument("--pausa", type=float, default=2.2)
    p.add_argument("--minimo", type=float)
    p.add_argument("--md")
    p.add_argument("--salvar")
    p.add_argument("--agente", action="store_true", help="golden set do agente (conversas); com --url usa o modelo de verdade")
    p.add_argument("--juiz", action="store_true", help="com --agente: chama o LLM-as-judge (precisa de GEMINI_API_KEY)")
    p.add_argument("--minimo-juiz", type=float, help="com --juiz: sai com erro se o juiz aprovar menos que isto")
    p.add_argument("--calibrar-juiz", action="store_true", help="compara o juiz com as notas humanas de avaliacao/calibracao_juiz.json")
    a = p.parse_args(argv)
    if a.agente or a.calibrar_juiz:
        from avaliacao.rodar_agente import principal
        return principal(a)
    if not (a.url or a.local or a.pontuar):
        p.error("escolha --url, --local, --pontuar ou --agente")

    casos = carregar_casos(a.grupo, a.sem_modelo)
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
