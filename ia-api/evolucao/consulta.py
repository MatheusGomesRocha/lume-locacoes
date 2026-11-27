"""Consulta declarativa: o formato, o executor e a busca. É DADO, não código: o executor é a única coisa que roda.

Formato (tudo opcional que não esteja marcado):
  nome, descricao, entidade, operacao ("contar" | "listar" | "somar"), campo_soma, saida [campos], ordenar_por, limite,
  filtros [{campo, op, parametro | valor}], parametros {nome: {tipo, valores?, obrigatorio?}}, permissao, papel_minimo,
  exemplos [frases], palavras_chave [palavras], sinonimos {valor: [palavras]}
O executor aplica as mesmas regras que o front aplicará: permissão primeiro, parâmetros validados, filtro por PALAVRA INTEIRA
("maria" não acha "Mariana"), nada além do que o esquema permite.
"""
import re
import unicodedata
from datetime import date, timedelta

from evolucao.esquema import DATA_ISO, ESQUEMA

OPERACOES = ("contar", "listar", "somar")
OPS_POR_TIPO = {
    "texto": {"igual", "diferente", "contem"},
    "numero": {"igual", "diferente", "maior_igual", "menor_igual"},
    "data": {"igual", "maior_igual", "menor_igual", "ultimos_dias"},
    "bool": {"igual"},
    "enum": {"igual", "diferente"},
}
CHAVES_DA_SPEC = ("nome", "descricao", "entidade", "operacao", "campo_soma", "saida", "ordenar_por", "limite", "filtros",
                  "parametros", "permissao", "papel_minimo", "exemplos", "palavras_chave", "sinonimos")


class ErroConsulta(Exception):
    codigo = "erro"


class PermissaoNegada(ErroConsulta):
    codigo = "permissao"


class ParametroInvalido(ErroConsulta):
    codigo = "parametro"


def sem_acento(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def palavras(t) -> list[str]:
    return [p for p in re.split(r"[^a-z0-9]+", sem_acento(t)) if p]


def casa_palavras(busca, texto) -> bool:
    alvo = set(palavras(texto))
    q = palavras(busca)
    return bool(q) and all(p in alvo for p in q)


def _valor_do_param(definicao: dict, bruto):
    tipo = definicao.get("tipo")
    if tipo == "bool":
        if isinstance(bruto, bool):
            return bruto
        raise ParametroInvalido("valor lógico esperado")
    if tipo == "numero":
        if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
            raise ParametroInvalido("número esperado")
        return float(bruto)
    if not isinstance(bruto, str) or not bruto.strip() or len(bruto) > 120:
        raise ParametroInvalido("texto esperado")
    if tipo == "data":
        try:
            if not DATA_ISO.match(bruto):
                raise ValueError
            date.fromisoformat(bruto)
        except ValueError:
            raise ParametroInvalido("data inválida (use AAAA-MM-DD)") from None
    if tipo == "enum" and bruto not in definicao.get("valores", []):
        raise ParametroInvalido(f"valor fora da lista: {bruto}")
    return bruto.strip()


def validar_parametros(spec: dict, params: dict) -> dict:
    defs = spec.get("parametros") or {}
    if not isinstance(params, dict):
        raise ParametroInvalido("parâmetros inválidos")
    extras = set(params) - set(defs)
    if extras:
        raise ParametroInvalido(f"parâmetro desconhecido: {sorted(extras)[0]}")
    saida = {}
    for nome, d in defs.items():
        if params.get(nome) is None:
            if d.get("obrigatorio"):
                raise ParametroInvalido(f"falta o parâmetro {nome}")
            continue
        saida[nome] = _valor_do_param(d, params[nome])
    return saida


MAX_DIAS = 3650


def _janela(hoje, dias) -> tuple[str, str]:
    """"Nos últimos N dias" = de (hoje - N) até hoje, inclusive. N = 0 é só hoje."""
    try:
        h = date.fromisoformat(str(hoje))
    except ValueError:
        raise ErroConsulta("falta a data de hoje") from None
    if isinstance(dias, bool) or not isinstance(dias, (int, float)) or dias != int(dias) or not 0 <= dias <= MAX_DIAS:
        raise ParametroInvalido(f"quantidade de dias inválida (0 a {MAX_DIAS})")
    return (h - timedelta(days=int(dias))).isoformat(), h.isoformat()


def _confere(op: str, atual, esperado, tipo: str, hoje=None) -> bool:
    if op == "ultimos_dias":
        de, ate = _janela(hoje, esperado)
        return atual is not None and de <= str(atual)[:10] <= ate
    if op == "contem":
        return atual is not None and casa_palavras(esperado, atual)
    if atual is None:
        return op == "diferente"
    if tipo == "texto" and op in ("igual", "diferente"):
        atual, esperado = sem_acento(atual), sem_acento(esperado)
    if op == "igual":
        return atual == esperado
    if op == "diferente":
        return atual != esperado
    return atual >= esperado if op == "maior_igual" else atual <= esperado


def executar(spec: dict, params: dict, dados: dict[str, list[dict]], sessao: dict) -> dict:
    """Roda a consulta. Ordem fixa: permissão -> parâmetros -> filtros -> operação."""
    ent = ESQUEMA[spec["entidade"]]
    if spec.get("permissao") not in sessao.get("permissoes", []):
        raise PermissaoNegada("sem a permissão " + str(spec.get("permissao")))
    if ent["so_admin"] and sessao.get("papel") not in ("master", "admin"):
        raise PermissaoNegada("só master e administrador")
    valores = validar_parametros(spec, params)
    linhas = list(dados.get(spec["entidade"], []))
    for f in spec.get("filtros", []):
        campo = ent["campos"][f["campo"]]
        if "parametro" in f:
            if f["parametro"] not in valores:
                continue  # filtro opcional sem valor: não filtra
            esperado = valores[f["parametro"]]
        else:
            esperado = f["valor"]
        linhas = [l for l in linhas if _confere(f["op"], l.get(f["campo"]), esperado, campo["tipo"], sessao.get("hoje"))]
    saida: dict = {"total": len(linhas)}
    if spec["operacao"] == "somar":
        saida["soma"] = round(sum(float(l.get(spec["campo_soma"]) or 0) for l in linhas), 2)
    elif spec["operacao"] == "listar":
        if spec.get("ordenar_por"):
            linhas.sort(key=lambda l: (l.get(spec["ordenar_por"]) is None, l.get(spec["ordenar_por"])))
        mostradas = linhas[: int(spec.get("limite") or 20)]
        saida["linhas"] = [{c: l.get(c) for c in spec["saida"]} for l in mostradas]
    return saida


# --- busca: "essa pergunta é para esta consulta?" e "qual valor o usuário citou?" ---
_VAZIAS = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "no", "na", "nos", "nas", "em", "eu", "meu", "minha", "me", "no", "sistema",
           "que", "e", "ou", "para", "pra", "por", "tipo", "tenho", "temos", "ha", "tem", "quantos", "quantas", "qual", "quais", "quanto", "ver", "mostre", "liste"}


def _termos(t) -> set[str]:
    return {p for p in palavras(t) if p not in _VAZIAS and len(p) > 1}


def _termos_da_entidade(nome: str) -> set[str]:
    """"clientes" -> {clientes, cliente}; "orcamentos" -> {orcamentos, orcamento}: a pergunta pode vir no singular."""
    r = sem_acento((ESQUEMA.get(nome) or {}).get("rotulo", nome)).lower()
    return {r, r.rstrip("s")} if r else set()


def _fala_de_outra_entidade(q: set[str], entidade: str) -> bool:
    """A pergunta cita outra entidade (ex.: produtos) e nunca a desta consulta (clientes)? Então não é desta consulta."""
    if entidade not in ESQUEMA or q & _termos_da_entidade(entidade):
        return False
    return any(q & _termos_da_entidade(o) for o in ESQUEMA if o != entidade)


def pontuar(pergunta: str, spec: dict) -> float:
    """0 a 1: o quanto a pergunta se parece com os exemplos e palavras-chave desta consulta."""
    q = _termos(pergunta)
    if not q or _fala_de_outra_entidade(q, spec.get("entidade", "")):
        return 0.0
    valores = {p for lista in (spec.get("sinonimos") or {}).values() for s in lista for p in _termos(s)}
    melhor = 0.0
    for ex in spec.get("exemplos", []):
        e = _termos(ex)
        if e:
            melhor = max(melhor, len(q & e) / len(q | e))
    chaves = {p for k in spec.get("palavras_chave", []) for p in _termos(k)} | _termos(spec.get("entidade", ""))
    if chaves:
        melhor = max(melhor, 0.9 * len(q & (chaves | valores)) / len(q) * (1 if q & chaves else 0))
    return round(melhor, 3)


def buscar_consulta(pergunta: str, specs: list[dict], minimo: float = 0.5, margem: float = 0.1) -> dict | None:
    """A consulta que responde a pergunta, ou None quando não há uma com clareza (nunca adivinha entre duas)."""
    notas = sorted(((pontuar(pergunta, s), s) for s in specs), key=lambda x: -x[0])
    if not notas or notas[0][0] < minimo:
        return None
    if len(notas) > 1 and notas[0][0] - notas[1][0] < margem:
        return None
    return notas[0][1]


def _dias_da_pergunta(pergunta: str) -> int | None:
    """"últimos 7 dias" -> 7; "2 semanas" -> 14; "último mês" -> 30; "hoje" -> 0. Sem nada disso, None (o chat pergunta)."""
    t = sem_acento(pergunta)
    m = re.search(r"\b(\d{1,4})\s*(dias?|semanas?|mes(?:es)?)\b", t)
    if m:
        n = int(m.group(1))
        return min(MAX_DIAS, n * (7 if m.group(2).startswith("semana") else 30 if m.group(2).startswith("mes") else 1))
    if re.search(r"\b(ultima|ultimas|passada)\s+semana\b", t):
        return 7
    if re.search(r"\b(ultimo|ultimos|passado)\s+mes\b", t):
        return 30
    if re.search(r"\bhoje\b", t):
        return 0
    return None


def extrair_parametros(pergunta: str, spec: dict) -> dict:
    """Preenche parâmetros enum citados na pergunta, por palavra inteira (valor, rótulo ou sinônimo)."""
    achados = {}
    q = set(palavras(pergunta))
    dias_da_pergunta = _dias_da_pergunta(pergunta)
    por_janela = {f.get("parametro") for f in spec.get("filtros", []) if f.get("op") == "ultimos_dias"}
    for nome, d in (spec.get("parametros") or {}).items():
        if d.get("tipo") == "numero" and nome in por_janela and dias_da_pergunta is not None:
            achados[nome] = dias_da_pergunta
        if d.get("tipo") != "enum":
            continue
        for v in d.get("valores", []):
            candidatos = {sem_acento(v), *(p for s in (spec.get("sinonimos") or {}).get(v, []) for p in palavras(s))}
            if candidatos & q:
                achados[nome] = v
                break
    return achados
