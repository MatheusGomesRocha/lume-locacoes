"""Código fixo de checagem: o que dá para provar com certeza é provado aqui, sem modelo e sem humor.

Cada checagem devolve achados {codigo, gravidade, mensagem}. "bloqueio" reprova; "aviso" o Master precisa ler.
Quando o Tester (Agent 3) descobrir um tipo de falha que vale para toda consulta, ele vira uma checagem nova aqui.
"""
import re

from app import ferramentas
from evolucao.consulta import CHAVES_DA_SPEC, OPERACOES, OPS_POR_TIPO, buscar_consulta, pontuar
from evolucao.esquema import ESQUEMA, PERMISSOES_VALIDAS, TIPOS

NOME_OK = re.compile(r"^[a-z][a-z0-9_]{2,59}$")
SUSPEITO = re.compile(r"(;|--|/\*|\b(select|insert|update|delete|drop|union|exec)\b|<script|\bignore\b.*\b(regras|instru)|\bsystem prompt\b)", re.I)
MAX_LIMITE = 50
MAX_SAIDA = 8


def _a(codigo: str, gravidade: str, mensagem: str) -> dict:
    return {"codigo": codigo, "gravidade": gravidade, "mensagem": mensagem}


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _textos(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _textos(v)


def nomes_ja_usados(catalogo: list[dict] | None = None) -> set[str]:
    usados = set(ferramentas.CONSULTAS) | set(ferramentas.ACOES) | {"localizar_clientes", "localizar_produtos", "verificar_disponibilidade", "criar_cliente", "criar_orcamento"}
    return usados | {s.get("nome") for s in (catalogo or [])}


def checar_proposta(p: dict) -> list[dict]:
    """O que o Analista (Agent 1) entregou está completo e dentro do esquema?"""
    f = []
    if p.get("decisao") not in ("criar_consulta", "nao_suportado", "faq", "ja_existe"):
        return [_a("P01", "bloqueio", "decisão da proposta inválida")]
    if not p.get("perguntas"):
        f.append(_a("P02", "bloqueio", "a proposta não diz de quais perguntas ela nasceu"))
    if p["decisao"] != "criar_consulta":
        if not str(p.get("motivo", "")).strip():
            f.append(_a("P03", "bloqueio", "decisão sem motivo"))
        return f
    if p.get("entidade") not in ESQUEMA:
        f.append(_a("P04", "bloqueio", f"entidade fora do esquema: {p.get('entidade')}"))
    elif p.get("operacao") not in OPERACOES:
        f.append(_a("P05", "bloqueio", f"operação não permitida (só leitura: {', '.join(OPERACOES)}): {p.get('operacao')}"))
    if any(SUSPEITO.search(t) for t in _textos(p)):
        f.append(_a("P06", "bloqueio", "a proposta tem texto com cara de comando ou instrução"))
    return f


def checar_spec(spec: dict, proposta: dict | None = None, catalogo: list[dict] | None = None) -> list[dict]:
    """A consulta que o Construtor (Agent 2) criou obedece ao esquema, às permissões e às regras dos módulos?"""
    f: list[dict] = []
    extras = set(spec) - set(CHAVES_DA_SPEC)
    if extras:
        f.append(_a("C00", "aviso", f"chaves desconhecidas ignoradas: {sorted(extras)}"))
    nome = spec.get("nome", "")
    if not isinstance(nome, str) or not NOME_OK.match(nome):
        f.append(_a("C01", "bloqueio", "nome inválido (minúsculas, números e _; 3 a 60 letras)"))
    elif nome in nomes_ja_usados(catalogo):
        f.append(_a("C01", "bloqueio", f"o nome “{nome}” já existe e colidiria com outra ferramenta"))
    if spec.get("operacao") not in OPERACOES:
        f.append(_a("C02", "bloqueio", f"operação não permitida (só leitura): {spec.get('operacao')}"))
    ent = ESQUEMA.get(spec.get("entidade"))
    if not ent:
        f.append(_a("C03", "bloqueio", f"entidade fora do esquema: {spec.get('entidade')}"))
        return f
    campos = ent["campos"]

    usados = []
    for fl in spec.get("filtros", []):
        usados.append(("filtro", fl.get("campo")))
    usados += [("saída", c) for c in spec.get("saida", [])]
    if spec.get("ordenar_por"):
        usados.append(("ordenação", spec["ordenar_por"]))
    if spec.get("campo_soma"):
        usados.append(("soma", spec["campo_soma"]))
    for onde, c in usados:
        if c not in campos:
            f.append(_a("C04", "bloqueio", f"{onde} usa um campo que não existe em {spec['entidade']}: {c}"))
        elif campos[c]["nivel"] != "normal":
            f.append(_a("C05", "bloqueio", f"{onde} usa o campo {campos[c]['nivel']} “{c}”: dados pessoais e segredos nunca saem em consulta gerada"))

    if spec.get("permissao") not in PERMISSOES_VALIDAS:
        f.append(_a("C06", "bloqueio", f"permissão inexistente: {spec.get('permissao')}"))
    elif spec["permissao"] != ent["permissao"]:
        f.append(_a("C06", "bloqueio", f"a permissão tem que ser a da tela ({ent['permissao']}), veio {spec['permissao']}"))
    if ent["so_admin"] and spec.get("papel_minimo") != "admin":
        f.append(_a("C07", "bloqueio", f"{spec['entidade']} é restrito a administradores: papel_minimo deve ser “admin”"))

    if spec.get("operacao") == "listar":
        if not spec.get("saida"):
            f.append(_a("C08", "bloqueio", "consulta de lista precisa dizer quais campos mostra"))
        if len(spec.get("saida", [])) > MAX_SAIDA:
            f.append(_a("C08", "bloqueio", f"saída com mais de {MAX_SAIDA} campos"))
    lim = spec.get("limite")
    if spec.get("operacao") == "listar" and (not isinstance(lim, int) or isinstance(lim, bool) or not 1 <= lim <= MAX_LIMITE):
        f.append(_a("C08", "bloqueio", f"limite obrigatório entre 1 e {MAX_LIMITE}"))
    if spec.get("operacao") == "somar" and campos.get(spec.get("campo_soma"), {}).get("tipo") != "numero":
        f.append(_a("C13", "bloqueio", "só se soma campo numérico"))

    params = spec.get("parametros") or {}
    citados = set()
    for fl in spec.get("filtros", []):
        c = campos.get(fl.get("campo"))
        if not c:
            continue
        if fl.get("op") not in OPS_POR_TIPO[c["tipo"]]:
            f.append(_a("C09", "bloqueio", f"operador “{fl.get('op')}” não serve para o campo {fl['campo']} ({c['tipo']})"))
        if ("parametro" in fl) == ("valor" in fl):
            f.append(_a("C09", "bloqueio", f"o filtro de {fl['campo']} precisa de um parâmetro OU de um valor fixo"))
        if "parametro" in fl:
            citados.add(fl["parametro"])
            d = params.get(fl["parametro"])
            if d is None:
                f.append(_a("C09", "bloqueio", f"o filtro usa o parâmetro {fl['parametro']}, que não foi declarado"))
            elif d.get("tipo") != ("numero" if fl.get("op") == "ultimos_dias" else c["tipo"]):
                esperado_tipo = "numero (a quantidade de dias)" if fl.get("op") == "ultimos_dias" else c["tipo"]
                f.append(_a("C09", "bloqueio", f"o parâmetro {fl['parametro']} é {d.get('tipo')} mas o filtro de {fl['campo']} pede {esperado_tipo}"))
            elif c["tipo"] == "enum" and not set(d.get("valores", [])) <= set(c["valores"]):
                f.append(_a("C09", "bloqueio", f"o parâmetro {fl['parametro']} aceita valores que o campo não tem"))
        elif c["tipo"] == "enum" and fl.get("valor") not in c["valores"]:
            f.append(_a("C09", "bloqueio", f"valor fixo fora da lista do campo {fl['campo']}: {fl.get('valor')}"))
    for p, d in params.items():
        if d.get("tipo") not in TIPOS:
            f.append(_a("C09", "bloqueio", f"tipo de parâmetro inválido em {p}"))
        if p not in citados:
            f.append(_a("C09", "aviso", f"o parâmetro {p} foi declarado e nenhum filtro o usa"))

    if any(SUSPEITO.search(t) for t in _textos({k: v for k, v in spec.items() if k != "nome"})):
        f.append(_a("C10", "bloqueio", "a consulta tem texto com cara de SQL, script ou instrução"))

    ex = spec.get("exemplos") or []
    if not 3 <= len(ex) <= 10 or len(set(map(str.lower, map(str, ex)))) != len(ex) or any(len(str(e)) > 200 for e in ex):
        f.append(_a("C11", "bloqueio", "a busca precisa de 3 a 10 perguntas de exemplo, diferentes entre si, de até 200 letras"))
    if len(str(spec.get("descricao", ""))) > 200 or not str(spec.get("descricao", "")).strip():
        f.append(_a("C11", "bloqueio", "descrição obrigatória, de até 200 letras"))
    for e in ex:
        if pontuar(str(e), spec) < 0.5:
            f.append(_a("C11", "bloqueio", f"o próprio exemplo não encontra a consulta: “{e}”"))
            break
    for outra in catalogo or []:
        outro = buscar_consulta(ex[0], [outra, spec]) if ex else None
        if outro is outra:
            f.append(_a("C11", "bloqueio", f"a busca confunde esta consulta com “{outra.get('nome')}”"))

    f += _regras_de_modulo(spec)
    if proposta and proposta.get("decisao") == "criar_consulta":
        f += _fidelidade(spec, proposta)
    return f


def _regras_de_modulo(spec: dict) -> list[dict]:
    f = []
    ent, saida = spec["entidade"], spec.get("saida", [])
    if ent == "orcamentos":
        if ("data_retirada" in saida) != ("data_devolucao" in saida) and (set(saida) & {"data_retirada", "data_devolucao"}):
            f.append(_a("ORC-DATAS", "bloqueio", "quem mostra a data de retirada tem que mostrar a de devolução (e vice-versa): as duas são obrigatórias no orçamento"))
        for x in spec.get("filtros", []):
            if x.get("campo") not in ESQUEMA["orcamentos"]["campos"]:
                continue
            if ESQUEMA["orcamentos"]["campos"][x["campo"]]["tipo"] == "data" and x["campo"] not in ("data_retirada", "data_devolucao", "criado_em"):
                f.append(_a("ORC-PERIODO", "bloqueio", "filtro de período em orçamento só pode usar data_retirada, data_devolucao ou criado_em (quando o orçamento foi criado)"))
    if ent == "pagamentos" and spec.get("permissao") != "financeiro.ver":
        f.append(_a("FIN-PERM", "bloqueio", "cobranças exigem financeiro.ver"))
    if ent == "usuarios" and set(saida) & {"email", "senha"}:
        f.append(_a("USR-ADMIN", "bloqueio", "e-mail e senha de usuários nunca saem"))
    return f


def _fidelidade(spec: dict, p: dict) -> list[dict]:
    """O que foi construído é o que foi proposto? (o Construtor não pode mudar o pedido no caminho)"""
    f = []
    if spec.get("entidade") != p.get("entidade"):
        f.append(_a("F01", "bloqueio", f"a proposta era sobre {p.get('entidade')} e a consulta é sobre {spec.get('entidade')}"))
    if spec.get("operacao") != p.get("operacao"):
        f.append(_a("F01", "bloqueio", f"a proposta pedia “{p.get('operacao')}” e a consulta faz “{spec.get('operacao')}”"))
    quer = {(x.get("campo"), x.get("op")) for x in p.get("filtros", [])}
    tem = {(x.get("campo"), x.get("op")) for x in spec.get("filtros", [])}
    if quer - tem:
        f.append(_a("F02", "bloqueio", f"faltam filtros pedidos na proposta: {sorted(map(str, quer - tem))}"))
    if tem - quer:
        f.append(_a("F02", "aviso", f"a consulta tem filtros que a proposta não pediu: {sorted(map(str, tem - quer))}"))
    return f


def tem_bloqueio(achados: list[dict]) -> bool:
    return any(a["gravidade"] == "bloqueio" for a in achados)
