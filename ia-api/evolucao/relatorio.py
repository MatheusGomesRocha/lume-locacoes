"""O relatório que o Master lê antes de aprovar ou reprovar: tudo que foi feito, em português, e o que NÃO foi provado."""
from evolucao.esquema import ESQUEMA

ROTULO_OP = {"igual": "é igual a", "diferente": "é diferente de", "contem": "contém a palavra", "maior_igual": "é maior ou igual a", "menor_igual": "é menor ou igual a", "ultimos_dias": "foi nos últimos (dias)", "proximos_dias": "será nos próximos (dias)"}
VEREDITO = {"aprovar_recomendado": "✅ Recomendo APROVAR", "revisar_com_atencao": "⚠️ Pode aprovar, mas leia os avisos", "reprovar_recomendado": "⛔ Recomendo REPROVAR"}
REGRAS_VERIFICADAS = [
    ("C01", "Nome válido e que não colide com outra ferramenta"), ("C02", "Só leitura (contar, listar ou somar)"),
    ("C03", "Entidade existe no esquema"), ("C04", "Todo campo usado existe"), ("C05", "Nenhum dado pessoal ou secreto"),
    ("C06", "Permissão é a mesma da tela"), ("C07", "Entidade restrita exige administrador"), ("C08", "Lista tem campos e limite"),
    ("C09", "Filtros e parâmetros coerentes com os tipos"), ("C10", "Sem texto com cara de SQL, script ou instrução"),
    ("C11", "Busca: exemplos próprios acham a consulta e não confundem com outra"), ("F01", "Entidade e operação são as propostas"),
    ("F02", "Filtros são os propostos"), ("ORC-DATAS", "Orçamento: data de retirada e de devolução andam juntas"),
    ("ORC-PERIODO", "Orçamento: período só por data de retirada ou de devolução"), ("USR-ADMIN", "Usuários: e-mail e senha nunca saem"), ("FIN-PERM", "Cobranças exigem financeiro.ver"),
]


def descrever(spec: dict) -> str:
    ent = ESQUEMA.get(spec.get("entidade"), {})
    campos = ent.get("campos", {})
    acao = {"contar": "Conta", "listar": "Lista", "somar": f"Soma o campo “{spec.get('campo_soma')}” de"}.get(spec.get("operacao"), "Faz algo com")
    partes = [f"{acao} {ent.get('rotulo', spec.get('entidade'))}"]
    for f in spec.get("filtros", []):
        rot = campos.get(f.get("campo"), {}).get("rotulo", f.get("campo"))
        valor = f"“{f['parametro']}” (vem da pergunta)" if "parametro" in f else f"“{f.get('valor')}”"
        partes.append(f"onde {rot} {ROTULO_OP.get(f.get('op'), f.get('op'))} {valor}")
    if spec.get("operacao") == "listar":
        partes.append(f"mostrando {', '.join(spec.get('saida', []))} (até {spec.get('limite')} linhas)")
    return " ".join(partes) + "."


def montar(id_: str, proposta: dict, pacote: dict | None, avaliacao: dict | None) -> dict:
    """Estrutura do relatório (o que a tela do Master mostra) + o mesmo em texto."""
    rel = {"id": id_, "titulo": proposta.get("titulo") or "(sem título)", "decisao_do_analista": proposta.get("decisao"), "motivo": proposta.get("motivo"),
           "perguntas": proposta.get("perguntas", []), "vezes": proposta.get("vezes", 0), "status": "pendente", "proposta": proposta, "pacote": pacote, "avaliacao": avaliacao}
    rel["veredito"] = avaliacao["veredito"] if avaliacao else None
    rel["texto"] = _texto(rel)
    return rel


def _texto(r: dict) -> str:
    p, pac, av = r["proposta"], r["pacote"], r["avaliacao"]
    L = [f"# {r['id']} · {r['titulo']}", "", "## 1. De onde veio (Agent 1, Analista)",
         f"{r['vezes']} pergunta(s) sem resposta:" if r["vezes"] else "Perguntas sem resposta:"] + [f"- “{q}”" for q in r["perguntas"]]
    L += ["", f"Decisão do Analista: **{p.get('decisao')}**. {p.get('motivo', '')}"]
    if not pac:
        L += ["", "Nada foi criado: não há consulta para aprovar. Este item serve só de registro."]
        if av:
            L += ["", "Achados que barraram a proposta:"] + [f"- ⛔ {a['codigo']}: {a['mensagem']}" for a in av["achados"]] + ["", f"**{VEREDITO[av['veredito']]}**"]
        return "\n".join(L)
    spec = pac["spec"]
    L += ["", "## 2. O que foi criado (Agent 2, Construtor)", f"**{spec.get('nome')}**: {descrever(spec)}", f"Permissão exigida: `{spec.get('permissao')}`"
          + (f" · Papel mínimo: {spec['papel_minimo']}" if spec.get("papel_minimo") else ""), "Perguntas de exemplo (busca):"] + [f"- “{e}”" for e in spec.get("exemplos", [])]
    if pac.get("regras_declaradas"):
        L += ["", "Regras que o Construtor DIZ ter seguido (declaração dele, não é prova):"] + [f"- {x}" for x in pac["regras_declaradas"]]
    L += ["", "## 3. O que foi VERIFICADO (checagens fixas, sem modelo)"]
    por_codigo = {a["codigo"] for a in av["achados"] if a["gravidade"] == "bloqueio"}
    L += [f"- {'❌' if c in por_codigo else '✅'} {c} · {t}" for c, t in REGRAS_VERIFICADAS]
    L += ["", f"## 4. Testes (Agent 3, Tester) — resultado esperado selado ANTES de rodar",
          f"Selo: `{av['selo']}`", f"Esperado escrito e selado em {av['selado_em']}; executado em {av['executado_em']}.",
          f"{av['resumo']['passaram']} de {av['resumo']['casos']} casos passaram."]
    L += [f"- {'✅' if c['passou'] else '❌'} [{c['origem']}] {c['descricao']} → esperado {c['esperado']}, obtido {c['obtido']}" for c in av["casos"]]
    ruido = av.get("ruido") or {}
    if ruido.get("reclassificados") or ruido.get("descartados"):
        L += ["", "Casos do Tester que o código corrigiu ou descartou antes de rodar (erro de montagem do teste, não da consulta):"]
        L += [f"- 🔧 corrigido: {x}" for x in ruido.get("reclassificados", [])] + [f"- 🗑️ descartado: {x}" for x in ruido.get("descartados", [])]
    L += ["", "## 5. Achados"] + ([f"- {'⛔' if a['gravidade'] == 'bloqueio' else '⚠️'} {a['codigo']}: {a['mensagem']}" for a in av["achados"]] or ["- Nenhum."])
    L += ["", "## 6. Veredito do Tester", f"**{VEREDITO[av['veredito']]}**", "", "## 7. Se você aprovar",
          "- A consulta entra no catálogo, com o seu nome e a data. Ela só LÊ dados e só para quem tem a permissão acima.",
          "- Você pode desativá-la a qualquer momento (o registro da aprovação fica).", "", "## 8. O que esta verificação NÃO prova"]
    L += [f"- {x}" for x in (av["limites"] or [])] + [
        "- Os testes usam dados de exemplo: o resultado em produção depende dos dados reais.",
        "- O selo prova a ORDEM (esperado antes do resultado); não protege contra alguém com acesso ao servidor.",
        "- O Tester é um modelo: ele pode deixar de pensar num caso. Por isso as checagens fixas existem e crescem."]
    return "\n".join(L)
