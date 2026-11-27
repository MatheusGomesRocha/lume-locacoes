"""Matriz de perguntas GERADA a partir do esquema: módulo x operação x restrições (valores, períodos), com o gabarito calculado à parte.

Para cada pergunta gerada, confere o caminho inteiro do chat, sem modelo:
  1. a pergunta acha a consulta do módulo certo e do tipo certo (contar x listar);
  2. os parâmetros extraídos são exatamente os do gabarito (valor, data certa pelo verbo, período);
  3. a execução nos dados de teste devolve o mesmo total de uma contagem feita direto nos dados (caminho independente do executor);
  4. consulta que não filtra algo que a pergunta pede NÃO responde (vira lacuna / oportunidade de proposta);
  5. período sem verbo numa consulta com várias datas vira pergunta de volta ("qual data?").
Rodar:  python -m avaliacao.matriz_esquema
"""
import itertools
from collections import defaultdict
from datetime import date, timedelta

from evolucao import checagens
from evolucao.consulta import executar
from evolucao.esquema import BOOL_PALAVRAS, DADOS_TESTE, ESQUEMA, HOJE_TESTE, SESSOES_TESTE, VOCABULARIO

# Falhas que conhecemos e ainda não corrigimos: "módulo/tipo" -> motivo. O objetivo é esta lista ficar vazia.
LACUNAS_CONHECIDAS: dict[str, str] = {}

PERIODOS = ["hoje", "ontem", "essa semana", "este mês", "nos últimos 15 dias"]


def _periodo(nome: str) -> tuple[str, str]:
    """Gabarito dos períodos, calculado aqui (sem usar o código do chat)."""
    h = date.fromisoformat(HOJE_TESTE)
    if nome == "hoje":
        d = (h, h)
    elif nome == "ontem":
        d = (h - timedelta(days=1),) * 2
    elif nome == "essa semana":
        d = (h - timedelta(days=h.weekday()), h)
    elif nome == "este mês":
        d = (h.replace(day=1), h)
    else:
        d = (h - timedelta(days=15), h)
    return d[0].isoformat(), d[1].isoformat()


def _saida_da_lista(ent: str) -> list[str]:
    return [c for c, d in ESQUEMA[ent]["campos"].items() if d["nivel"] == "normal" and d["tipo"] in ("texto", "numero")][:2]


def _verbo(ent: str, campo: str) -> str:
    voc = VOCABULARIO[ent]
    v = voc["datas"][campo]
    return voc["pago"][voc["genero"]] if v == "PAGO" else v


def spec_de_referencia(ent: str, operacao: str, data: str | None = None) -> dict:
    """A consulta de referência do módulo: um parâmetro para cada enum e cada bool com palavra; com `data`, mais o período dessa data.
    (O formato limita a 6 parâmetros e 8 filtros, por isso uma consulta por data: orçamentos não cabe com as três datas juntas.)"""
    campos, voc = ESQUEMA[ent]["campos"], VOCABULARIO[ent]
    params, filtros = {}, []
    for c, d in campos.items():
        if d["tipo"] == "enum":
            params[c] = {"tipo": "enum", "valores": list(d["valores"]), "obrigatorio": False}
            filtros.append({"campo": c, "op": "igual", "parametro": c})
        elif d["tipo"] == "bool" and c in BOOL_PALAVRAS:
            params[c] = {"tipo": "bool", "obrigatorio": False}
            filtros.append({"campo": c, "op": "igual", "parametro": c})
    if data:
        params[f"{data}_de"] = {"tipo": "data", "obrigatorio": False}
        params[f"{data}_ate"] = {"tipo": "data", "obrigatorio": False}
        filtros += [{"campo": data, "op": "maior_igual", "parametro": f"{data}_de"}, {"campo": data, "op": "menor_igual", "parametro": f"{data}_ate"}]
    a, m = voc["assunto"][0], voc["genero"] == "m"
    if data:
        v = _verbo(ent, data)
        ex = ([f"quantos {a} {v} hoje" if m else f"quantas {a} {v} hoje", f"total de {a} {v} esta semana", f"numero de {a} {v} ontem"] if operacao == "contar"
              else [f"quais {a} {v} hoje", f"liste os {a} {v} esta semana", f"mostre os {a} {v} ontem"])
    else:
        ex = ([f"quantos {a} existem" if m else f"quantas {a} existem", f"total de {a}", f"numero de {a}"] if operacao == "contar" else [f"quais {a} existem", f"liste os {a}", f"mostre os {a}"])
    spec = {"nome": f"{ent}_{operacao}_{data or 'base'}", "descricao": f"{operacao.capitalize()} {ESQUEMA[ent]['rotulo'].lower()}", "entidade": ent, "operacao": operacao,
            "permissao": ESQUEMA[ent]["permissao"], "saida": [] if operacao == "contar" else _saida_da_lista(ent), "exemplos": ex,
            "palavras_chave": [*voc["assunto"], *voc.get("outros_assuntos", {})], "sinonimos": {}, "parametros": params, "filtros": filtros}
    if ESQUEMA[ent]["so_admin"]:
        spec["papel_minimo"] = "admin"
    if operacao == "listar" and spec["saida"]:
        spec["ordenar_por"], spec["limite"] = spec["saida"][0], 50
    return spec


def specs_do_modulo(ent: str) -> list[dict]:
    return [spec_de_referencia(ent, op, d) for op in ("contar", "listar") for d in (None, *VOCABULARIO[ent]["datas"])]


def catalogo_para(ent: str) -> list[dict]:
    """Todas as consultas do módulo + a consulta base dos outros (a pergunta tem que achar o módulo certo no meio delas)."""
    return specs_do_modulo(ent) + [spec_de_referencia(o, op) for o in VOCABULARIO if o != ent for op in ("contar", "listar")]


# --- gerar perguntas + gabarito -------------------------------------------------------------------------------------------
def _linha_confere(l: dict, restr: list[tuple]) -> bool:
    for r in restr:
        if r[0] == "eq" and l.get(r[1]) != r[2]:
            return False
        if r[0] == "data" and not (r[2] <= str(l.get(r[1]))[:10] <= r[3]):
            return False
    return True


def _params(restr: list[tuple]) -> dict:
    p = {}
    for r in restr:
        if r[0] == "eq":
            p[r[1]] = r[2]
        else:
            p[f"{r[1]}_de"], p[f"{r[1]}_ate"] = r[2], r[3]
    return p


def _frase(op: str, assunto: str, genero: str, partes: list[str]) -> list[str]:
    r = " ".join(p for p in partes if p)
    if op == "contar":
        q = "quantos" if genero == "m" else "quantas"
        formas = [f"{q} {assunto} {r}", f"total de {assunto} {r}"]
    else:
        formas = [f"quais {assunto} {r}", f"liste {'os' if genero == 'm' else 'as'} {assunto} {r}"]
    saida = []
    for f in formas:
        f = " ".join(f.split())
        saida.append(f + ("?" if not f.startswith(("total", "liste")) else ""))
    return saida


def gerar(ent: str) -> list[dict]:
    """Perguntas do módulo. Cada uma: {pergunta, entidade, operacao, spec (a consulta certa), restr (gabarito), params}."""
    voc, saida = VOCABULARIO[ent], []
    valores = list(voc["valores"].items())
    base: list[tuple[list[tuple], list[str]]] = [([], [])]
    for (campo, valor), frase in valores:
        base.append(([("eq", campo, valor)], [frase]))
    for ((c1, v1), f1), ((c2, v2), f2) in itertools.combinations(valores, 2):
        if c1 != c2:
            base.append(([("eq", c1, v1), ("eq", c2, v2)], [f1, f2]))
    genero = voc["genero"]
    for restr, frases in base:
        casos = [(None, restr, frases)]
        for campo in voc["datas"]:
            if campo == "pago_em" and any(r[1] == "status" for r in restr):
                continue  # "pagas" já é a situação: não combina com outra situação
            casos.append((campo, restr, frases))
        for campo, rr0, ff0 in casos:
            periodos = PERIODOS if campo else [None]
            for per in periodos:
                rr, ff = list(rr0), list(ff0)
                if campo:
                    de, ate = _periodo(per)
                    rr.append(("data", campo, de, ate))
                    if campo == "pago_em":
                        rr.append(("eq", "status", "pago"))
                    ff = [*ff, _verbo(ent, campo), per]
                for op in ("contar", "listar"):
                    for q in _frase(op, voc["assunto"][0], genero, ff):
                        saida.append({"pergunta": q, "entidade": ent, "operacao": op, "spec": f"{ent}_{op}_{campo or 'base'}", "restr": rr, "params": _params(rr)})
                so_forma = all(r[0] != "eq" or r[1] == "forma" for r in rr0)
                if so_forma and campo in (None, "pago_em") and (campo == "pago_em" or any(r[0] == "eq" for r in rr0)):  # "orçamentos pagos no cartão": a palavra é outra, o dado é de cobranças
                    for outro, g in (voc.get("outros_assuntos") or {}).items():
                        pg = ([("pagos" if f == voc["pago"][genero] else f) for f in ff] if campo else ff)
                        saida.append({"pergunta": _frase("contar", outro, g, pg)[0], "entidade": ent, "operacao": "contar", "spec": f"{ent}_contar_{campo or 'base'}", "restr": rr, "params": _params(rr)})
    if len(voc["datas"]) == 1:  # período sem verbo, módulo com uma data só: a consulta usa essa data
        campo = next(iter(voc["datas"]))
        for per in PERIODOS[:2]:
            de, ate = _periodo(per)
            rr = [("data", campo, de, ate)]
            saida.append({"pergunta": _frase("contar", voc["assunto"][0], genero, [per])[0], "entidade": ent, "operacao": "contar", "spec": f"{ent}_contar_{campo}", "restr": rr, "params": _params(rr)})
    vistos, unicos = set(), []
    for c in saida:
        if c["pergunta"] not in vistos:
            vistos.add(c["pergunta"])
            unicos.append(c)
    return unicos


# --- rodar ----------------------------------------------------------------------------------------------------------------
def _chat(pergunta: str, catalogo: list[dict]) -> dict:
    from app import main
    antes = main.provedor_llm
    main.provedor_llm = None
    try:
        return main._agente(pergunta, [], main.PerguntaIn(pergunta=pergunta, hoje=HOJE_TESTE, catalogo=catalogo)) or {}
    finally:
        main.provedor_llm = antes


def rodar() -> dict:
    sessao = SESSOES_TESTE["master"]
    total, falhas, avisos = 0, defaultdict(list), {"lacuna_explicita": 0, "lacuna_pelo_modelo": 0}
    invalidas = {}

    def falha(chave: str, pergunta: str, motivo: str):
        falhas[chave].append({"pergunta": pergunta, "motivo": motivo})

    for ent in VOCABULARIO:
        catalogo = catalogo_para(ent)
        por_nome = {s["nome"]: s for s in catalogo}
        for s in catalogo:
            ruins = [a["mensagem"] for a in checagens.checar_spec(s) if a["gravidade"] == "bloqueio"]
            if ruins:
                invalidas[s["nome"]] = ruins
        for c in gerar(ent):
            total += 1
            r = _chat(c["pergunta"], catalogo)
            consultas = r.get("consultas") or []
            if not consultas:
                falha(f"{ent}/rota", c["pergunta"], f"não achou a consulta (respondeu: {str(r.get('resposta'))[:90]})")
                continue
            args = consultas[0]["args"]
            sem_data = c["spec"].endswith("_base")  # pergunta sem período: qualquer consulta do módulo e do tipo serve (a data é opcional e o número sai igual)
            if args["nome"] != c["spec"] and not (sem_data and args["nome"].startswith(f"{ent}_{c['operacao']}_")):
                falha(f"{ent}/rota", c["pergunta"], f"achou {args['nome']} em vez de {c['spec']}")
                continue
            if args.get("params", {}) != c["params"]:
                falha(f"{ent}/parametros", c["pergunta"], f"extraiu {args.get('params')} e o gabarito é {c['params']}")
                continue
            try:
                total_chat = executar(por_nome[args["nome"]], args["params"], DADOS_TESTE, sessao)["total"]
            except Exception as e:  # noqa: BLE001
                falha(f"{ent}/execucao", c["pergunta"], f"erro ao executar: {e}")
                continue
            direto = sum(1 for l in DADOS_TESTE.get(ent, []) if _linha_confere(l, c["restr"]))
            if total_chat != direto:
                falha(f"{ent}/execucao", c["pergunta"], f"a consulta devolveu {total_chat} e a contagem direta é {direto}")

        # Consulta que não filtra o que a pergunta pede NUNCA responde com o total geral (vira lacuna ou segue para o modelo, que também confere).
        voc, genero = VOCABULARIO[ent], VOCABULARIO[ent]["genero"]
        q_ = "quantos" if genero == "m" else "quantas"
        base = spec_de_referencia(ent, "contar")
        sem = [(f"{q_} {voc['assunto'][0]} {_verbo(ent, campo)} hoje?", base, f"data {campo}") for campo in voc["datas"]]
        for (campo, valor), frase in voc["valores"].items():
            incompleta = {**base, "parametros": {k: v for k, v in base["parametros"].items() if k != campo}, "filtros": [f for f in base["filtros"] if f["campo"] != campo]}
            sem.append((f"{q_} {voc['assunto'][0]} {frase}?", incompleta, f"valor {campo}"))
        for q, spec, o_que in sem:
            total += 1
            r = _chat(q, [spec])
            if r.get("consultas"):
                falha(f"{ent}/lacuna", q, f"respondeu com o total geral, sem filtrar {o_que}")
            elif r.get("encontrou") is False:
                avisos["lacuna_explicita"] += 1
            else:
                avisos["lacuna_pelo_modelo"] += 1
        if len(voc["datas"]) > 1:  # várias datas e a pergunta não diz qual: não escolhe uma por conta própria
            q = f"{q_} {voc['assunto'][0]} hoje?"
            total += 1
            r = _chat(q, catalogo)
            if r.get("consultas"):
                falha(f"{ent}/ambiguidade", q, f"escolheu uma data sozinho: {r['consultas'][0]['args']['nome']}")
    return {"total": total, "falhas": dict(falhas), "invalidas": invalidas, "avisos": avisos}


def novas_falhas(r: dict) -> dict:
    return {k: v for k, v in r["falhas"].items() if k not in LACUNAS_CONHECIDAS}


if __name__ == "__main__":
    r = rodar()
    n = sum(len(v) for v in r["falhas"].values())
    print(f"Matriz do esquema: {r['total'] - n}/{r['total']} perguntas certas  {r['avisos']}")
    for k, v in r["invalidas"].items():
        print(f"- consulta de referência inválida {k}: {v}")
    for k, v in sorted(r["falhas"].items()):
        print(f"\n{k}: {len(v)} falhas")
        for f in v[:4]:
            print(f"   • {f['pergunta']} -> {f['motivo']}")
