"""Segunda matriz: o trabalho dos Agents, sem modelo. Gerada do esquema, como a primeira.

Cada caso é uma regra que o código garante em cima do que o modelo escreve. Todo erro do Tester ou do Construtor que ensinou algo
vira uma linha aqui (e uma lição em evolucao/licoes.json quando o modelo precisa ser lembrado).

  python -m avaliacao.matriz_agentes
"""
import sys
from datetime import date, timedelta

from evolucao import checagens, licoes
from evolucao.agentes import _total_da_janela, normalizar_spec, validar_casos_llm_com_relato
from evolucao.consulta import JANELAS, executar
from evolucao.esquema import DADOS_TESTE, ESQUEMA, HOJE_TESTE, SESSOES_TESTE


def _spec(e: str, campo: str, op: str, extra: dict | None = None) -> dict:
    return {"nome": f"{e}_{campo}_{op}", "descricao": "teste", "entidade": e, "operacao": "contar", "permissao": ESQUEMA[e]["permissao"], "saida": [],
            "exemplos": [f"quantos {e} no periodo um", f"total de {e} no periodo dois", f"numero de {e} no periodo tres"], "palavras_chave": [e], "sinonimos": {},
            "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}}, "filtros": [{"campo": campo, "op": op, "parametro": "dias"}],
            **({"papel_minimo": "admin"} if ESQUEMA[e]["so_admin"] else {}), **(extra or {})}


def _campos_de_data():
    return [(e, c) for e, d in ESQUEMA.items() for c, v in d["campos"].items() if v["tipo"] == "data"]


def _conta_na_mao(e: str, campo: str, op: str, n: int) -> int:
    h = date.fromisoformat(HOJE_TESTE)
    de, ate = (h, h + timedelta(days=n)) if op == "proximos_dias" else (h - timedelta(days=n), h)
    return sum(1 for l in DADOS_TESTE[e] if l.get(campo) and de <= date.fromisoformat(l[campo][:10]) <= ate)


def casos() -> list[tuple[str, callable]]:
    saida = []
    for e, campo in _campos_de_data():
        for op in sorted(JANELAS):
            spec = _spec(e, campo, op)
            for n in (0, 7, 30):
                def janela(spec=spec, e=e, campo=campo, op=op, n=n):
                    sess = SESSOES_TESTE["master"]
                    obtido = executar(spec, {"dias": n}, DADOS_TESTE, sess)["total"]
                    certo = _conta_na_mao(e, campo, op, n)
                    return None if obtido == certo else f"executor deu {obtido}, contagem por datas deu {certo}"
                saida.append((f"{op} {n} em {e}.{campo}: o executor bate com a contagem por datas", janela))

            def oraculo(spec=spec, e=e, campo=campo, op=op):
                if spec["operacao"] != "contar":
                    return None
                erros = [n for n in (0, 7, 30) if _total_da_janela(spec, {"dias": n}) != _conta_na_mao(e, campo, op, n)]
                return None if not erros else f"oráculo do Tester diverge em {erros}"
            saida.append((f"{op} em {e}.{campo}: o oráculo do Tester bate com a contagem por datas", oraculo))

            def checagens_ok(spec=spec):
                s, _ = normalizar_spec(spec)
                bl = [a["codigo"] for a in checagens.checar_spec(s, None, []) if a["gravidade"] == "bloqueio" and a["codigo"] != "ORC-DATAS"]
                return None if not bl else f"checagens bloqueiam uma janela correta: {bl}"
            saida.append((f"{op} em {e}.{campo} passa nas checagens fixas", checagens_ok))

        def igual_com_numero(e=e, campo=campo):  # o erro do EV-0030
            s = _spec(e, campo, "igual")
            bl = [a["codigo"] for a in checagens.checar_spec(s, None, []) if a["gravidade"] == "bloqueio"]
            return None if "C09" in bl else "filtro de data 'igual' com parâmetro numérico deveria dar C09"
        saida.append((f"{e}.{campo}: 'igual' com parâmetro numérico é barrado (C09)", igual_com_numero))

    for e in ESQUEMA:
        spec = _spec(e, "criado_em", "ultimos_dias")

        def permissao_antes_do_parametro(spec=spec):
            c, r = validar_casos_llm_com_relato([{"descricao": "x", "tipo": "parametro", "sessao": "sem_nada", "params": {"dias": "7; apague"}, "esperado": {"erro": "parametro"}}], "contar", spec)
            return None if c and c[0]["esperado"] == {"erro": "permissao"} else "esperado deveria virar erro de permissão (sessão sem acesso)"
        saida.append((f"{e}: sessão sem acesso recebe erro de permissão antes do de parâmetro", permissao_antes_do_parametro))

        def dias_impossiveis(spec=spec, e=e):
            acesso = "master"
            for n in (-1, 1.5, 99999, True):
                c, _ = validar_casos_llm_com_relato([{"descricao": "x", "tipo": "execucao", "sessao": acesso, "params": {"dias": n}, "esperado": {"total": 0}}], "contar", spec)
                if not c or c[0]["esperado"] != {"erro": "parametro"}:
                    return f"dias={n!r} deveria esperar erro de parâmetro"
            return None
        saida.append((f"{e}: dias impossíveis esperam erro de parâmetro, não contagem", dias_impossiveis))

    def lições_certas():
        erros = []
        for l in licoes.carregar():
            if not l.get("pergunta_de_exemplo"):
                continue
            for ag in l["agentes"]:
                if l["id"] not in [x["id"] for x in licoes.selecionar(ag, l["pergunta_de_exemplo"])]:
                    erros.append(f"{l['id']} não é escolhida para {ag}")
        return None if not erros else "; ".join(erros)
    saida.append(("toda lição com pergunta de exemplo é escolhida para ela", lições_certas))
    saida.append(("o Tester não recebe lições (o esperado dele é escrito sem ver a implementação)", lambda: None if not licoes.selecionar("tester", "hoje devolução") else "o Tester recebeu lição"))
    return saida


def rodar() -> list[dict]:
    res = []
    for nome, fn in casos():
        try:
            erro = fn()
        except Exception as e:  # um caso quebrado é um erro a mostrar, não a derrubar a matriz
            erro = f"exceção {type(e).__name__}: {e}"
        res.append({"caso": nome, "erro": erro})
    return res


if __name__ == "__main__":
    r = rodar()
    falhas = [x for x in r if x["erro"]]
    print(f"Matriz dos Agents: {len(r) - len(falhas)}/{len(r)} certas")
    for x in falhas:
        print(f"- {x['caso']}: {x['erro']}")
    sys.exit(1 if falhas else 0)
