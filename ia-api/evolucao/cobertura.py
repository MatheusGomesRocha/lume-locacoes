"""Cobertura: tudo o que a pergunta restringe (período, forma de pagamento, situação…) tem que estar entre os filtros que a consulta aplica.

Uma consulta que ignora um pedaço da pergunta devolve um número certo para outra pergunta ("5 no cartão" para "no cartão ESSA SEMANA").
Aqui o código (nunca o modelo) compara o que foi pedido com o que a consulta sabe filtrar:
  restricoes_da_pergunta  -> o que a pergunta restringe
  nao_cobertas            -> o que a consulta NÃO filtra (se sobrar algo, não se responde: vira oportunidade de proposta dos Agents)
  filtros_aplicados       -> o que a consulta aplicou, em palavras (o texto da resposta cita isso)
"""
import re
from datetime import date

from evolucao.consulta import JANELAS, campos_de_data_pedidos, campos_de_periodo, palavras, periodo_da_pergunta, raiz, sem_acento
from evolucao.esquema import BOOL_PALAVRAS, ESQUEMA

# Valor que implica outro campo: "o que foi pago hoje" já filtra pela data de pagamento, não precisa de parâmetro de situação.
_IMPLICA = {("pagamentos", "status", "pago"): "pago_em"}
_SINONIMOS = {"cartao": ["credito", "debito"], "dinheiro": ["especie"]}
_BONITO = {"cartao": "cartão"}
_NAO_VALE_DE_FORA = {"master", "admin", "usuario"}  # palavras comuns demais para dizer que a pergunta é de outro módulo


def _hoje(hoje) -> str:
    try:
        return date.fromisoformat(str(hoje)).isoformat()
    except ValueError:
        return date.today().isoformat()


def restricoes_da_pergunta(pergunta: str, entidade: str, hoje=None) -> list[dict]:
    """[{tipo: periodo}, {tipo: enum, campo, valor}] — o que a pergunta restringe nesta entidade."""
    saida: list[dict] = []
    if periodo_da_pergunta(pergunta, _hoje(hoje)):
        pedidos = campos_de_data_pedidos(pergunta, entidade)
        rotulos = [str(((ESQUEMA.get(entidade) or {}).get("campos", {}).get(c) or {}).get("rotulo", c)).lower() for c in pedidos]
        saida.append({"tipo": "periodo", "campos": pedidos, "rotulo": f"período ({' ou '.join(rotulos)})" if rotulos else "período"})
    esquema = ESQUEMA.get(entidade) or {}
    q = {raiz(p) for p in palavras(pergunta)}
    do_assunto = {raiz(p) for p in palavras(esquema.get("rotulo", entidade))} | {raiz(entidade)}
    for campo, d in (esquema.get("campos") or {}).items():
        if d["tipo"] == "bool" and campo in BOOL_PALAVRAS:
            sim, nao = BOOL_PALAVRAS[campo]
            valor = False if raiz(nao) in q else True if raiz(sim) in q else None
            if valor is not None:
                saida.append({"tipo": "bool", "campo": campo, "valor": valor, "rotulo": f"{str(d.get('rotulo', campo)).lower()} ({'sim' if valor else 'não'})"})
            continue
        if d["tipo"] != "enum":
            continue
        for v in d.get("valores") or []:
            candidatos = {raiz(sem_acento(v)), *(raiz(s) for s in _SINONIMOS.get(sem_acento(v), []))}
            if candidatos & do_assunto:  # "usuários" não é o perfil "usuario"
                continue
            if candidatos & q:
                rotulo = str(d.get("rotulo", campo)).lower()
                saida.append({"tipo": "enum", "campo": campo, "valor": v, "rotulo": f"{rotulo} ({_BONITO.get(v, v)})"})
                break
    # Valor que é de OUTRO módulo ("no Pix" numa consulta de orçamentos): a consulta não tem como filtrar, então não responde com o total geral.
    proprios = {sem_acento(str(v)) for d in (esquema.get("campos") or {}).values() if d["tipo"] == "enum" for v in d.get("valores") or []}
    for outro, esq in ESQUEMA.items():
        if outro == entidade:
            continue
        for campo, d in (esq.get("campos") or {}).items():
            if d["tipo"] != "enum":
                continue
            for v in d.get("valores") or []:
                c = sem_acento(str(v))
                if len(c) < 3 or c in _NAO_VALE_DE_FORA or c in proprios or raiz(c) in do_assunto:
                    continue
                if raiz(c) in q and not any(x.get("valor") == v for x in saida):
                    saida.append({"tipo": "fora", "campo": campo, "valor": v, "rotulo": f"{str(d.get('rotulo', campo)).lower()} ({_BONITO.get(v, v)})"})
    return saida


def _cobre(r: dict, spec: dict) -> bool:
    params = spec.get("parametros") or {}
    filtros = spec.get("filtros") or []
    if r["tipo"] == "periodo":
        campos, pedidos = campos_de_periodo(spec), set(r.get("campos") or [])
        return bool(campos) and (bool(campos & pedidos) if pedidos else len(campos) == 1)
    if r["tipo"] == "fora":
        return False
    if r["tipo"] == "bool":
        for f in filtros:
            if f.get("campo") == r["campo"] and f.get("op") == "igual" and (params.get(f.get("parametro"), {}).get("tipo") == "bool" or f.get("valor") is r["valor"]):
                return True
        return False
    implica = _IMPLICA.get((spec.get("entidade"), r["campo"], r["valor"]))
    for f in filtros:
        if implica and f.get("campo") == implica:
            return True
        if f.get("campo") != r["campo"] or f.get("op") != "igual":
            continue
        if "valor" in f and sem_acento(str(f["valor"])) == sem_acento(r["valor"]):
            return True
        p = params.get(f.get("parametro"), {})
        if p.get("tipo") == "enum" and r["valor"] in (p.get("valores") or []):
            return True
    return False


def nao_cobertas(pergunta: str, spec: dict, hoje=None) -> list[dict]:
    """O que a pergunta restringe e a consulta não filtra. Vazio = a consulta responde a pergunta inteira.
    Período sem verbo ("orçamentos de hoje") numa consulta com várias datas vem marcado `ambiguo`: aí a Lumi pergunta qual data, não é lacuna."""
    saida = []
    for r in restricoes_da_pergunta(pergunta, spec.get("entidade", ""), hoje):
        if _cobre(r, spec):
            continue
        campos = campos_de_periodo(spec)
        if r["tipo"] == "periodo" and not r.get("campos") and len(campos) > 1:
            nomes = [str(((ESQUEMA.get(spec.get("entidade")) or {}).get("campos", {}).get(c) or {}).get("rotulo", c)).lower() for c in sorted(campos)]
            r = {**r, "ambiguo": True, "rotulo": "período (qual data: " + ", ".join(nomes) + ")"}
        saida.append(r)
    return saida


def texto_da_lacuna(spec: dict, faltam: list[dict]) -> str:
    """Conversa, sem termos técnicos: o que já sabe fazer, o que ainda não, e que o pedido foi anotado para a equipe."""
    rotulo = str((ESQUEMA.get(spec.get("entidade")) or {}).get("rotulo", "registros")).lower()
    verbo = {"contar": "contar", "listar": "listar", "somar": "somar valores de"}.get(spec.get("operacao"), "consultar")
    itens = [r["rotulo"] for r in faltam]
    lista = itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]
    return f"Já consigo {verbo} {rotulo}, mas ainda não consigo filtrar por {lista}. Registrei a sua pergunta para a equipe liberar isso."


def _data_br(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def filtros_aplicados(spec: dict, params: dict) -> list[str]:
    """O que a consulta realmente filtrou, em palavras: ["forma: cartão", "pago em: 23/11/2026 a 27/11/2026"]."""
    campos = (ESQUEMA.get(spec.get("entidade")) or {}).get("campos", {})
    saida: list[str] = []
    datas: dict[str, dict] = {}
    for f in spec.get("filtros") or []:
        campo, op = f.get("campo"), f.get("op")
        rotulo = str((campos.get(campo) or {}).get("rotulo", campo)).lower()
        valor = params.get(f["parametro"]) if f.get("parametro") else f.get("valor")
        if valor in (None, ""):
            continue
        if op in JANELAS:
            saida.append(f"{rotulo}: {'últimos' if op == 'ultimos_dias' else 'próximos'} {valor} dias")
        elif (campos.get(campo) or {}).get("tipo") == "data" and op in ("maior_igual", "menor_igual", "igual"):
            d = datas.setdefault(rotulo, {})
            if op in ("maior_igual", "igual"):
                d["de"] = str(valor)
            if op in ("menor_igual", "igual"):
                d["ate"] = str(valor)
        elif op == "igual":
            saida.append(f"{rotulo}: {_BONITO.get(str(valor), valor)}")
        elif op == "diferente":
            saida.append(f"{rotulo}: não {_BONITO.get(str(valor), valor)}")
    for rotulo, d in datas.items():
        de, ate = d.get("de"), d.get("ate")
        if de and ate and de != ate:
            saida.append(f"{rotulo}: {_data_br(de)} a {_data_br(ate)}")
        elif de or ate:
            saida.append(f"{rotulo}: {_data_br(de or ate)}")
    return saida


def periodo_perdido(pergunta: str, chamadas: list[dict], hoje=None) -> bool:
    """A pergunta cita um período, o modelo pediu consultas fixas (consultar_*) e nenhuma levou data? O número viria do total geral."""
    consultas = [c for c in chamadas if str(c.get("nome", "")).startswith("consultar_")]
    if not consultas or not any(r["tipo"] == "periodo" for r in restricoes_da_pergunta(pergunta, "", hoje)):
        return False
    datas = lambda a: any(str(k).endswith(("_de", "_ate", "_dias")) and v not in (None, "") for k, v in (a or {}).items())  # noqa: E731
    return not any(datas(c.get("args")) for c in consultas)


_CITA_DATA = re.compile(r"\b(hoje|ontem|anteontem|semana|mes|dia|dias|periodo|de\s+\d{1,2}|\d{1,2}/\d{1,2})\b|\d{1,2}/\d{1,2}")


def texto_cita_filtros(texto: str, spec: dict, params: dict) -> bool:
    """O texto falado diz o que foi filtrado? Período (hoje, semana, datas) e valores (cartão, pago…) têm que aparecer; senão vale o texto de código."""
    t = sem_acento(texto)
    for f in filtros_aplicados(spec, params):
        valor = sem_acento(f.split(": ", 1)[-1])
        if "/" in f or "dias" in f:
            if not _CITA_DATA.search(t):
                return False
        elif valor.replace("nao ", "") not in t and raiz(valor.replace("nao ", "")) not in t:
            return False
    return True


def data_ambigua(pergunta: str, spec: dict, specs: list[dict], hoje=None) -> list[str]:
    """Período sem verbo e o catálogo tem consultas do mesmo assunto para datas diferentes (criação, retirada, devolução)? Devolve os nomes das datas
    possíveis: a Lumi pergunta qual, em vez de escolher uma por conta própria. Vazio = não há dúvida."""
    r = next((x for x in restricoes_da_pergunta(pergunta, spec.get("entidade", ""), hoje) if x["tipo"] == "periodo"), None)
    if not r or r.get("campos"):
        return []
    campos = set()
    for s in specs:
        if s.get("entidade") == spec.get("entidade") and s.get("operacao") == spec.get("operacao") and not nao_cobertas(pergunta, s, hoje):
            campos |= campos_de_periodo(s)
    if len(campos) < 2:
        return []
    return [str(((ESQUEMA.get(spec.get("entidade")) or {}).get("campos", {}).get(c) or {}).get("rotulo", c)).lower() for c in sorted(campos)]


def desempatar(pergunta: str, candidatas: list[dict], hoje=None) -> dict | None:
    """Duas consultas do mesmo módulo e tipo respondem a pergunta por igual (uma só tem uma data a mais, opcional)? Sem período na pergunta,
    vale a mais simples (menos parâmetros). Com período, ou se o empate persistir, não escolhe: None."""
    from evolucao.consulta import pontuar, tipo_da_pergunta
    tipo = tipo_da_pergunta(pergunta)
    boas = [s for s in candidatas if (not tipo or s.get("operacao") == tipo) and pontuar(pergunta, s) >= 0.5]
    if len(boas) < 2 or len({(s.get("entidade"), s.get("operacao")) for s in boas}) != 1:
        return None
    if any(r["tipo"] == "periodo" for r in restricoes_da_pergunta(pergunta, boas[0].get("entidade", ""), hoje)):
        return None
    menor = min(len(s.get("parametros") or {}) for s in boas)
    simples = [s for s in boas if len(s.get("parametros") or {}) == menor]
    return simples[0] if len(simples) == 1 else None
