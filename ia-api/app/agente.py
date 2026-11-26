"""Agente de conversa: cria orçamentos e clientes conversando, sem formulário, e só grava depois do "sim" do usuário.

Como funciona (a API não guarda nada, então o estado viaja com cada mensagem):
  - o modelo (Gemini) só entende o pedido inicial ("orçamento para João Victor, 2 mesas, 20 cadeiras...");
  - daí em diante QUEM DECIDE O PRÓXIMO PASSO É O CÓDIGO, sem modelo: é previsível, testável e não gasta cota;
  - para ler dados, o agente pede "consultas" (localizar_clientes, localizar_produtos, verificar_disponibilidade)
    que o front executa com as permissões do usuário logado e devolve em `resultados`;
  - para gravar, o agente devolve `executar` SÓ depois de uma resposta afirmativa na etapa "confirmar".

Cada chamada devolve um dict: {texto, agente (estado novo ou None para encerrar), consultas?, opcoes?, executar?}.
"""
import json
import re
import unicodedata
from datetime import date

FLUXOS = ("orcamento", "cliente")
MAX_ITENS = 15
MAX_CANDIDATOS = 6
MAX_ESTADO_BYTES = 8000


# --------------------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------------------
def _n(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn").strip()


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data_br(iso: str) -> str:
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def diarias(retirada: str, devolucao: str) -> int:
    """Mesma regra do sistema: dias entre retirada e devolução, no mínimo 1 diária."""
    return max(1, (date.fromisoformat(devolucao) - date.fromisoformat(retirada)).days)


def calcular_total(itens: list[dict], n_diarias: int, desconto: float = 0.0) -> float:
    """(soma dos itens × diárias) − desconto, nunca negativo, em centavos exatos."""
    centavos = sum(round(i["valor_diaria"] * 100) * i["quantidade"] for i in itens) * n_diarias
    return max(0, centavos - round(desconto * 100)) / 100


def _palavras(texto: str, singular: bool = False) -> list[str]:
    ps = re.split(r"[^a-z0-9]+", _n(texto))
    return [_singular(p) if singular else p for p in ps if p]


def casa_nome(busca: str, nome: str, singular: bool = False) -> bool:
    """Cada palavra da busca é uma PALAVRA INTEIRA do nome: "Maria" não é "Mariana" e "Vitor" não é "Vitória".
    O front já filtra assim; repetir aqui garante que o agente nunca escolha um nome que o usuário não disse."""
    alvo, q = set(_palavras(nome, singular)), _palavras(busca, singular)
    return bool(q) and all(p in alvo for p in q)


def _singular(texto: str) -> str:
    """"mesas redondas" -> "mesa redonda": o cadastro usa o singular, o usuário fala no plural."""
    def um(p: str) -> str:
        if len(p) > 4 and p.endswith("oes"):
            return p[:-3] + "ao"
        if len(p) > 3 and p.endswith("s") and not p.endswith("ss"):
            return p[:-1]
        return p
    return " ".join(um(p) for p in _n(texto).split())


_DATA = re.compile(r"(?<!\d)(?:(\d{4})-(\d{2})-(\d{2})|(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?)(?!\d)")


def extrair_datas(texto: str, hoje: str | None) -> list[str]:
    """Datas citadas na mensagem, na ordem: 26/11/2026, 26/11/26, 26/11 (sem ano = próxima ocorrência) e 2026-11-26."""
    base = date.fromisoformat(hoje) if hoje else date.today()
    achadas: list[str] = []
    for ia, im, idia, d, m, a in _DATA.findall(texto):
        try:
            if ia:
                dt = date(int(ia), int(im), int(idia))
            else:
                ano = int(a) + (2000 if a and len(a) == 2 else 0) if a else base.year
                dt = date(ano, int(m), int(d))
                if not a and dt < base:
                    dt = date(ano + 1, int(m), int(d))
        except ValueError:
            continue
        achadas.append(dt.isoformat())
    return achadas


_QTD = re.compile(r"^\s*(\d{1,4})\s*(?:x|un\.?|unidades?|peças?)?\s*(?:de\s+)?(.+?)\s*$", re.I)


def extrair_itens(texto: str) -> list[dict]:
    """"2 mesas e 20 cadeiras" -> [{produto: "mesas", quantidade: 2}, {produto: "cadeiras", quantidade: 20}]."""
    itens = []
    for pedaco in re.split(r",|;|\be\b|\+", texto, flags=re.I):
        m = _QTD.match(pedaco)
        if m and _n(m.group(2)):
            itens.append({"produto": m.group(2).strip()[:60], "quantidade": int(m.group(1))})
    return [i for i in itens if i["quantidade"] >= 1][:MAX_ITENS]


_SIM = {"sim", "s", "confirmo", "confirmar", "confirmado", "pode", "pode criar", "pode sim", "ok", "isso", "isso mesmo", "certo", "claro", "vai", "bora", "positivo", "criar", "pode cadastrar", "cadastrar", "confirmar e criar"}
_NAO = {"nao", "n", "cancelar", "cancela", "cancele", "desisti", "esquece", "deixa", "deixa pra la", "nenhum", "parar", "para"}


def _afirmativo(msg: str) -> bool:
    t = _n(msg).strip(" .!")
    return t in _SIM or t.startswith("sim ") or t.startswith("sim,")


def _negativo(msg: str) -> bool:
    t = _n(msg).strip(" .!")
    return t in _NAO or t.startswith("cancel") or (t.startswith("nao") and len(t) <= 12)


def _parece_pergunta(msg: str) -> bool:
    t = _n(msg)
    return "?" in msg or bool(re.match(r"^(como|qual e|quais|o que|quanto|por que|porque|onde|quando)\b", t))


def _escolher(msg: str, rotulos: list[str]) -> int | None:
    """Qual opção a pessoa quis: pelo número ("2"), pelo texto completo ou por um trecho que só uma opção tem."""
    t = _n(msg).strip(" .!")
    if t.isdigit() and 1 <= int(t) <= len(rotulos):
        return int(t) - 1
    for i, r in enumerate(rotulos):
        if t and t == _n(r):
            return i
    achadas = [i for i, r in enumerate(rotulos) if len(t) >= 3 and t in _n(r)]
    return achadas[0] if len(achadas) == 1 else None


# --------------------------------------------------------------------------------------------------
# Estado: vem do navegador, então nada dele é confiável. Só passa o que tem a forma esperada.
# --------------------------------------------------------------------------------------------------
def _txt(v, limite=120) -> str | None:
    return v.strip()[:limite] if isinstance(v, str) and v.strip() else None


def _num(v, minimo=0.0, maximo=10_000_000.0) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and minimo <= v <= maximo else None


def _iso(v) -> str | None:
    try:
        return date.fromisoformat(v).isoformat() if isinstance(v, str) else None
    except ValueError:
        return None


def _sanear_item(i) -> dict | None:
    if not isinstance(i, dict) or not _txt(i.get("produto"), 60):
        return None
    q = i.get("quantidade")
    if not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= 9999:
        return None
    item = {"produto": _txt(i["produto"], 60), "quantidade": q}
    if isinstance(i.get("produto_id"), int) and not isinstance(i["produto_id"], bool):
        item["produto_id"] = i["produto_id"]
        item["nome"] = _txt(i.get("nome")) or item["produto"]
        item["valor_diaria"] = _num(i.get("valor_diaria")) or 0.0
    for chave in ("buscado", "nao_achado"):
        if i.get(chave) is True:
            item[chave] = True
    cand = [c for c in (i.get("cand") or []) if isinstance(c, dict) and isinstance(c.get("id"), int) and _txt(c.get("nome"))][:MAX_CANDIDATOS] if isinstance(i.get("cand"), list) else []
    if cand:
        item["cand"] = [{"id": c["id"], "nome": _txt(c["nome"]), "valor_diaria": _num(c.get("valor_diaria")) or 0.0} for c in cand]
    return item


def sanear(estado) -> dict | None:
    """Estado válido ou None (None = ignora e segue como conversa nova)."""
    try:
        if not isinstance(estado, dict) or len(json.dumps(estado)) > MAX_ESTADO_BYTES or estado.get("fluxo") not in FLUXOS:
            return None
        bruto = estado.get("rascunho")
        if not isinstance(bruto, dict) or not _txt(estado.get("aguardando"), 30):
            return None
        r: dict = {}
        for chave in ("cliente_nome", "evento", "observacoes"):
            if _txt(bruto.get(chave), 200):
                r[chave] = _txt(bruto[chave], 200)
        if isinstance(bruto.get("cliente_id"), int) and not isinstance(bruto["cliente_id"], bool):
            r["cliente_id"] = bruto["cliente_id"]
        for chave in ("data_retirada", "data_devolucao"):
            if _iso(bruto.get(chave)):
                r[chave] = bruto[chave]
        r["desconto"] = _num(bruto.get("desconto")) or 0.0
        for chave in ("cliente_buscado", "cliente_nao_achado", "disp_verificada", "devolucao_assumida", "duplicado_aceito", "contato_perguntado"):
            if bruto.get(chave) is True:
                r[chave] = True
        cand = bruto.get("cliente_cand")
        if isinstance(cand, list):
            r["cliente_cand"] = [{"id": c["id"], "nome": _txt(c.get("nome")), "cidade": _txt(c.get("cidade"), 60)} for c in cand if isinstance(c, dict) and isinstance(c.get("id"), int) and _txt(c.get("nome"))][:MAX_CANDIDATOS]
        novo = bruto.get("cliente_novo")
        if isinstance(novo, dict) and _txt(novo.get("nome")):
            r["cliente_novo"] = {"nome": _txt(novo["nome"])}
            if novo.get("tipo") in ("PF", "PJ"):
                r["cliente_novo"]["tipo"] = novo["tipo"]
            for chave in ("documento", "email", "telefone", "cidade"):
                if _txt(novo.get(chave), 80):
                    r["cliente_novo"][chave] = _txt(novo[chave], 80)
        r["avisos"] = [_txt(a, 200) for a in bruto.get("avisos", []) if _txt(a, 200)][:5] if isinstance(bruto.get("avisos"), list) else []
        r["itens"] = [i for i in (_sanear_item(x) for x in bruto.get("itens", [])[:MAX_ITENS]) if i] if isinstance(bruto.get("itens"), list) else []
        escolhas = [_txt(x, 120) for x in estado.get("escolhas", []) if _txt(x, 120)][:MAX_CANDIDATOS + 3] if isinstance(estado.get("escolhas"), list) else []
        indice = estado.get("indice") if isinstance(estado.get("indice"), int) and 0 <= estado["indice"] < MAX_ITENS else 0
        return {"fluxo": estado["fluxo"], "aguardando": _txt(estado["aguardando"], 30), "rascunho": r, "escolhas": escolhas, "indice": indice}
    except Exception:  # noqa: BLE001 - estado malformado nunca derruba a conversa
        return None


# --------------------------------------------------------------------------------------------------
# Respostas
# --------------------------------------------------------------------------------------------------
def _resp(e: dict, aguardando: str, texto: str, opcoes: list[str] | None = None, **extra) -> dict:
    e["aguardando"] = aguardando
    e["escolhas"] = opcoes or []
    saida = {"texto": texto, "agente": e, **extra}
    if opcoes:
        saida["opcoes"] = opcoes
    return saida


def _fim(texto: str) -> dict:
    return {"texto": texto, "agente": None}


CANCELADO = "Tudo bem, cancelei. Nada foi criado nem alterado."


def _resumo(e: dict) -> str:
    r = e["rascunho"]
    linhas = []
    novo = r.get("cliente_novo")
    if e["fluxo"] == "cliente":
        linhas.append(f"Vou cadastrar este cliente:\n• Nome: {novo['nome']}\n• Tipo: {'empresa' if novo.get('tipo') == 'PJ' else 'pessoa física'}")
        for rotulo, chave in (("Documento", "documento"), ("E-mail", "email"), ("Telefone", "telefone"), ("Cidade", "cidade")):
            if novo.get(chave):
                linhas.append(f"• {rotulo}: {novo[chave]}")
        linhas.append("\nPosso cadastrar? Nada é salvo até você confirmar.")
        return "\n".join(linhas)
    n = diarias(r["data_retirada"], r["data_devolucao"])
    linhas.append("Confira o orçamento antes de eu criar:")
    if novo:
        extra = ", ".join(f"{v}" for k, v in novo.items() if k not in ("nome", "tipo"))
        linhas.append(f"• Cliente NOVO: {novo['nome']} ({'empresa' if novo.get('tipo') == 'PJ' else 'pessoa física'}{', ' + extra if extra else ''}) — será cadastrado junto")
    else:
        linhas.append(f"• Cliente: {r['cliente_nome']}")
    linhas.append(f"• Evento: {r['evento']}")
    periodo = f"• Retirada {_data_br(r['data_retirada'])} → devolução {_data_br(r['data_devolucao'])} ({n} {'diária' if n == 1 else 'diárias'})"
    if r.get("devolucao_assumida"):
        periodo += " — usei a mesma data para devolução; me diga se for outra"
    linhas.append(periodo)
    for i in r["itens"]:
        linhas.append(f"• {i['quantidade']} × {i['nome']} — {_brl(i['valor_diaria'])}/dia = {_brl(i['valor_diaria'] * i['quantidade'] * n)}")
    if r.get("desconto"):
        linhas.append(f"• Desconto: {_brl(r['desconto'])}")
    linhas.append(f"• Total: {_brl(calcular_total(r['itens'], n, r.get('desconto', 0)))}")
    linhas += [f"⚠ {a}" for a in r.get("avisos", [])]
    linhas.append("\nPosso criar? Ele fica como rascunho. Nada é salvo até você confirmar.")
    return "\n".join(linhas)


# --------------------------------------------------------------------------------------------------
# Início
# --------------------------------------------------------------------------------------------------
def iniciar(nome_ferramenta: str, args: dict, hoje: str | None) -> dict | None:
    """Começa uma conversa a partir do que o modelo entendeu. None = não há dados para trabalhar: o front abre o formulário de sempre."""
    if nome_ferramenta == "cadastrar_cliente":
        nome = _txt(args.get("nome"))
        if not nome:
            return None
        novo = {"nome": nome}
        if args.get("tipo") in ("PF", "PJ"):
            novo["tipo"] = args["tipo"]
        for chave in ("documento", "email", "telefone", "cidade"):
            if _txt(args.get(chave), 80):
                novo[chave] = _txt(args[chave], 80)
        e = {"fluxo": "cliente", "aguardando": "", "escolhas": [], "indice": 0, "rascunho": {"cliente_nome": nome, "cliente_novo": novo, "itens": [], "avisos": []}}
        if len(novo) > 2:
            e["rascunho"]["contato_perguntado"] = True
        return _avancar(e, hoje)
    if nome_ferramenta != "cadastrar_orcamento":
        return None
    itens = [i for i in (_sanear_item({"produto": x.get("produto"), "quantidade": int(x["quantidade"]) if isinstance(x.get("quantidade"), (int, float)) and x["quantidade"] >= 1 else 1}) for x in args.get("itens", []) if isinstance(x, dict)) if i] if isinstance(args.get("itens"), list) else []
    cliente = _txt(args.get("cliente"))
    if not cliente and not itens:
        return None
    r: dict = {"itens": itens[:MAX_ITENS], "avisos": [], "desconto": _num(args.get("desconto")) or 0.0}
    if cliente:
        r["cliente_nome"] = cliente
    if _txt(args.get("evento"), 200):
        r["evento"] = _txt(args["evento"], 200)
    if _txt(args.get("observacoes"), 200):
        r["observacoes"] = _txt(args["observacoes"], 200)
    ret, dev = _iso(args.get("data_retirada")), _iso(args.get("data_devolucao"))
    if ret and not dev:  # uma data só (a do evento): vale para retirada e devolução, e o resumo avisa
        dev, r["devolucao_assumida"] = ret, True
    if ret and dev and dev >= ret:
        r["data_retirada"], r["data_devolucao"] = ret, dev
    elif ret and dev:
        r["devolucao_assumida"] = False
    return _avancar({"fluxo": "orcamento", "aguardando": "", "escolhas": [], "indice": 0, "rascunho": r}, hoje)


# --------------------------------------------------------------------------------------------------
# Próximo passo: olha o que falta e faz UMA pergunta (ou pede UMA rodada de consultas)
# --------------------------------------------------------------------------------------------------
def _avancar(e: dict, hoje: str | None) -> dict:
    r = e["rascunho"]
    orc = e["fluxo"] == "orcamento"

    consultas = []
    if r.get("cliente_nome") and not r.get("cliente_id") and not r.get("cliente_buscado") and (orc or not r.get("duplicado_aceito")) and not (orc and r.get("cliente_novo")):
        consultas.append({"nome": "localizar_clientes", "args": {"busca": r["cliente_nome"]}})
    pendentes = [i for i in r["itens"] if "produto_id" not in i and not i.get("buscado")]
    if orc and pendentes:
        consultas.append({"nome": "localizar_produtos", "args": {"buscas": [_singular(i["produto"]) for i in pendentes]}})
    if consultas:
        return _resp(e, "consulta", "", consultas=consultas)

    if orc and not r.get("cliente_id") and not r.get("cliente_novo"):
        if r.get("cliente_cand"):
            rotulos = [f"{c['nome']}" + (f" — {c['cidade']}" if c.get("cidade") else "") for c in r["cliente_cand"]]
            return _resp(e, "escolher_cliente", f"Qual {r['cliente_nome']} deseja selecionar?", rotulos)
        if r.get("cliente_nao_achado"):
            return _resp(e, "cliente_inexistente", f"Não encontramos esse usuário: “{r['cliente_nome']}”. O que prefere?", [f"Cadastrar “{r['cliente_nome']}” como novo cliente", "Informar outro nome", "Cancelar"])
        return _resp(e, "cliente_nome", "Para qual cliente é o orçamento?")

    if r.get("cliente_novo"):
        if e["fluxo"] == "cliente" and r.get("cliente_cand") and not r.get("duplicado_aceito"):
            rotulos = [c["nome"] + (f" — {c['cidade']}" if c.get("cidade") else "") for c in r["cliente_cand"]]
            return _resp(e, "cliente_duplicado", "Já existe cliente com nome parecido: " + "; ".join(rotulos) + ". Quer cadastrar mesmo assim?", ["Cadastrar mesmo assim", "Cancelar"])
        if not r["cliente_novo"].get("tipo"):
            return _resp(e, "tipo_cliente", f"{r['cliente_novo']['nome']} é pessoa física ou empresa?", ["Pessoa física", "Empresa"])
        if not r.get("contato_perguntado"):
            return _resp(e, "contatos_cliente", "Quer informar telefone, e-mail, cidade ou CPF/CNPJ? Pode mandar tudo numa mensagem só, ou dizer “pular”.", ["Pular"])

    if orc:
        for n, i in enumerate(r["itens"]):
            if i.get("cand"):
                e["indice"] = n
                return _resp(e, "escolher_produto", f"Qual “{i['produto']}” deseja selecionar?", [f"{c['nome']} — {_brl(c['valor_diaria'])}/dia" for c in i["cand"]])
            if i.get("nao_achado"):
                e["indice"] = n
                return _resp(e, "produto_inexistente", f"Não encontramos o produto “{i['produto']}” entre os ativos. O que prefere?", [f"Remover “{i['produto']}” do orçamento", "Informar outro produto", "Cancelar"])
        if not r["itens"]:
            return _resp(e, "itens", "Quais produtos e quantidades vão no orçamento? Ex.: 2 mesas e 20 cadeiras.")
        if not r.get("evento"):
            return _resp(e, "evento", "Qual é o evento? (Ex.: Casamento, Aniversário)")
        if not (r.get("data_retirada") and r.get("data_devolucao")):
            if r.get("data_retirada"):
                return _resp(e, "devolucao", "E qual a data de devolução?")
            return _resp(e, "datas", "Qual data de retirada e data de devolução?")
        if not r.get("disp_verificada"):
            return _resp(e, "consulta", "", consultas=[{"nome": "verificar_disponibilidade", "args": {"retirada": r["data_retirada"], "devolucao": r["data_devolucao"], "itens": [{"produto_id": i["produto_id"], "quantidade": i["quantidade"]} for i in r["itens"]]}}])
        if hoje and r["data_retirada"] < hoje and not any("passado" in a for a in r["avisos"]):
            r["avisos"].append("A data de retirada já passou.")

    return _resp(e, "confirmar", _resumo(e), ["Confirmar", "Cancelar"])


# --------------------------------------------------------------------------------------------------
# Resultados das consultas
# --------------------------------------------------------------------------------------------------
def _aplicar_resultados(e: dict, resultados: list, hoje: str | None) -> dict:
    r = e["rascunho"]
    for item in resultados if isinstance(resultados, list) else []:
        nome, dado = (item.get("nome"), item.get("resultado")) if isinstance(item, dict) else (None, None)
        if not isinstance(dado, dict):
            continue
        if "erro" in dado:
            return _fim(f"Não consegui consultar os dados agora ({str(dado['erro'])[:80]}). Não criei nada.")
        if nome == "localizar_clientes":
            r["cliente_buscado"] = True
            linhas = [c for c in dado.get("linhas", []) if isinstance(c, dict) and isinstance(c.get("id"), int) and _txt(c.get("nome")) and casa_nome(r.get("cliente_nome", ""), c["nome"])][:MAX_CANDIDATOS]
            if e["fluxo"] == "cliente":
                if linhas:
                    r["cliente_cand"] = [{"id": c["id"], "nome": c["nome"], "cidade": _txt(c.get("cidade"), 60)} for c in linhas]
            elif len(linhas) == 1:  # mais de um (mesmo com nome igual a um deles) sempre pergunta qual
                r["cliente_id"], r["cliente_nome"] = linhas[0]["id"], linhas[0]["nome"]
            elif linhas:
                r["cliente_cand"] = [{"id": c["id"], "nome": c["nome"], "cidade": _txt(c.get("cidade"), 60)} for c in linhas]
            else:
                r["cliente_nao_achado"] = True
        elif nome == "localizar_produtos":
            pendentes = [i for i in r["itens"] if "produto_id" not in i and not i.get("buscado")]
            grupos = dado.get("itens", []) if isinstance(dado.get("itens"), list) else []
            for item_r, grupo in zip(pendentes, grupos):
                item_r["buscado"] = True
                linhas = [c for c in (grupo.get("linhas", []) if isinstance(grupo, dict) else []) if isinstance(c, dict) and isinstance(c.get("id"), int) and _txt(c.get("nome"))
                          and (casa_nome(item_r["produto"], c["nome"], True) or (_txt(c.get("codigo"), 40) and _n(c["codigo"]) == _n(item_r["produto"])))][:MAX_CANDIDATOS]
                exatos = [c for c in linhas if _singular(c["nome"]) == _singular(item_r["produto"])]
                if len(exatos) == 1 or len(linhas) == 1:
                    _fixar_produto(item_r, exatos[0] if exatos else linhas[0])
                elif linhas:
                    item_r["cand"] = [{"id": c["id"], "nome": c["nome"], "valor_diaria": _num(c.get("valor_diaria")) or 0.0} for c in linhas]
                else:
                    item_r["nao_achado"] = True
        elif nome == "verificar_disponibilidade":
            r["disp_verificada"] = True
            for f in [f for f in dado.get("faltas", []) if isinstance(f, dict)][:5]:
                r["avisos"].append(f"Estoque no período: {f.get('disponivel', 0)} de {f.get('produto', 'produto')} disponíveis e o orçamento pede {f.get('solicitado', 0)} (só aprovar exige estoque).")
    return _avancar(e, hoje)


def _fixar_produto(item: dict, c: dict) -> None:
    item["produto_id"], item["nome"], item["valor_diaria"] = c["id"], c["nome"], _num(c.get("valor_diaria")) or 0.0
    item.pop("cand", None)
    item.pop("nao_achado", None)


# --------------------------------------------------------------------------------------------------
# Continuar a conversa com a resposta do usuário
# --------------------------------------------------------------------------------------------------
_CAMPOS_TEXTO_LIVRE = {"cliente_nome", "evento", "produto_novo", "itens", "datas", "devolucao", "contatos_cliente"}


def continuar(estado, mensagem: str, resultados, hoje: str | None) -> dict | None:
    """Próximo passo da conversa. None = a mensagem não é resposta à pergunta do agente: segue o fluxo normal (e a conversa do agente é encerrada)."""
    e = sanear(estado)
    if e is None:
        return None
    r, passo = e["rascunho"], e["aguardando"]
    msg = mensagem.strip()

    if passo == "consulta":
        if not resultados:
            return _fim("Não consegui consultar os dados agora. Não criei nada; tente de novo em instantes.")
        return _aplicar_resultados(e, resultados, hoje)

    if _negativo(msg) and passo != "contatos_cliente":
        return _fim(CANCELADO)
    if passo in _CAMPOS_TEXTO_LIVRE and _parece_pergunta(msg):
        return None

    if passo == "cliente_nome":
        r.update(cliente_nome=msg[:120], cliente_buscado=False, cliente_nao_achado=False, cliente_cand=[])
        return _avancar(e, hoje)

    if passo == "cliente_inexistente":
        i = _escolher(msg, e["escolhas"])
        if i == 0:
            r["cliente_novo"] = {"nome": r["cliente_nome"]}
        elif i == 1:
            return _resp(e, "cliente_nome", "Qual o nome do cliente?")
        elif i == 2:
            return _fim(CANCELADO)
        elif i is None and len(msg) >= 2 and not _parece_pergunta(msg):
            r.update(cliente_nome=msg[:120], cliente_buscado=False, cliente_nao_achado=False)
        else:
            return _resp(e, passo, "Não entendi. Responda com o número da opção ou digite outro nome.", e["escolhas"])
        return _avancar(e, hoje)

    if passo == "escolher_cliente":
        i = _escolher(msg, e["escolhas"])
        if i is None or i >= len(r.get("cliente_cand", [])):
            return _resp(e, passo, "Não entendi qual. Responda com o número ou o nome completo.", e["escolhas"])
        c = r["cliente_cand"][i]
        r.update(cliente_id=c["id"], cliente_nome=c["nome"], cliente_cand=[])
        return _avancar(e, hoje)

    if passo == "escolher_produto":
        item = r["itens"][e["indice"]] if e["indice"] < len(r["itens"]) else None
        i = _escolher(msg, e["escolhas"]) if item else None
        if item is None or i is None or i >= len(item.get("cand", [])):
            return _resp(e, passo, "Não entendi qual. Responda com o número ou o nome completo.", e["escolhas"])
        _fixar_produto(item, item["cand"][i])
        return _avancar(e, hoje)

    if passo == "produto_inexistente":
        item = r["itens"][e["indice"]] if e["indice"] < len(r["itens"]) else None
        i = _escolher(msg, e["escolhas"])
        if item is None or i == 2:
            return _fim(CANCELADO)
        if i == 0:
            r["itens"].remove(item)
        elif i == 1:
            return _resp(e, "produto_novo", f"Qual produto no lugar de “{item['produto']}”?")
        else:
            return _resp(e, passo, "Não entendi. Responda com o número da opção ou digite o nome de outro produto.", e["escolhas"])
        return _avancar(e, hoje)

    if passo == "produto_novo":
        item = r["itens"][e["indice"]] if e["indice"] < len(r["itens"]) else None
        if item is None:
            return _fim(CANCELADO)
        item.update(produto=msg[:60], buscado=False)
        item.pop("nao_achado", None)
        return _avancar(e, hoje)

    if passo == "itens":
        itens = extrair_itens(msg)
        if not itens:
            return _resp(e, passo, "Não entendi. Diga a quantidade e o produto, por exemplo: 2 mesas e 20 cadeiras.")
        r["itens"] = itens
        return _avancar(e, hoje)

    if passo == "evento":
        limpo = re.sub(r"^(?:(?:é|e|será|sera|vai ser)\s+)?(?:(?:o|a|um|uma)\s+)?(?:evento\s+(?:de\s+|do\s+|da\s+)?)?", "", msg.strip(), flags=re.I).strip(" .") or msg.strip()
        r["evento"] = (limpo[:1].upper() + limpo[1:])[:120]
        return _avancar(e, hoje)

    if passo in ("datas", "devolucao"):
        return _ler_datas(e, msg, hoje)

    if passo == "tipo_cliente":
        t = _n(msg)
        if re.search(r"\b(empresa|juridica|pj|cnpj)\b", t):
            r["cliente_novo"]["tipo"] = "PJ"
        elif re.search(r"\b(fisica|pessoa|pf|cpf)\b", t):
            r["cliente_novo"]["tipo"] = "PF"
        else:
            return _resp(e, passo, "Não entendi. É pessoa física ou empresa?", e["escolhas"])
        return _avancar(e, hoje)

    if passo == "contatos_cliente":
        if not _negativo(msg) and _n(msg) not in ("pular", "pula", "nao", "nenhum"):
            _ler_contatos(r["cliente_novo"], msg)
        r["contato_perguntado"] = True
        return _avancar(e, hoje)

    if passo == "cliente_duplicado":
        i = _escolher(msg, e["escolhas"])
        if i == 0:
            r["duplicado_aceito"] = True
            return _avancar(e, hoje)
        return _fim(CANCELADO) if i == 1 else _resp(e, passo, "Responda “Cadastrar mesmo assim” ou “Cancelar”.", e["escolhas"])

    if passo == "confirmar":
        return _confirmar(e, msg, hoje)
    return None


def _dias_depois(msg: str) -> int | None:
    """"no dia seguinte" -> 1, "mesmo dia" -> 0, "3 dias depois" / "3 diárias" -> 3. None = a mensagem não diz."""
    t = _n(msg)
    if re.search(r"mesmo dia", t):
        return 0
    if re.search(r"dia seguinte|outro dia|dia depois|amanha", t):
        return 1
    m = re.search(r"(\d{1,2})\s*(?:dias?\s+(?:depois|apos|de\s+aluguel)|diarias?)", t)
    return int(m.group(1)) if m and 0 < int(m.group(1)) <= 60 else None


def _somar_dias(iso: str, n: int) -> str:
    return date.fromordinal(date.fromisoformat(iso).toordinal() + n).isoformat()


def _ler_datas(e: dict, msg: str, hoje: str | None) -> dict:
    r = e["rascunho"]
    datas = extrair_datas(msg, hoje)
    depois = _dias_depois(msg)
    if e["aguardando"] == "devolucao" and not datas and depois is not None and r.get("data_retirada"):
        datas = [_somar_dias(r["data_retirada"], depois)]
        e["aguardando"] = "datas_ok"
    elif len(datas) == 1 and depois is not None:  # "dia 26/11, devolvendo no dia seguinte"
        datas = [datas[0], _somar_dias(datas[0], depois)]
    if not datas:
        return _resp(e, e["aguardando"], "Não entendi a data. Use o formato dia/mês/ano, por exemplo 26/11/2026.")
    if e["aguardando"] == "datas_ok":
        ret, dev = r["data_retirada"], datas[0]
    elif e["aguardando"] == "devolucao":
        ret, dev = r["data_retirada"], datas[0]
    elif len(datas) == 1:
        r["data_retirada"] = datas[0]
        r.pop("data_devolucao", None)
        return _resp(e, "devolucao", f"Retirada em {_data_br(datas[0])}. E qual a data de devolução?")
    else:
        ret, dev = datas[0], datas[1]
    if dev < ret:
        return _resp(e, "datas", "A devolução não pode ser antes da retirada. Qual data de retirada e data de devolução?")
    r.update(data_retirada=ret, data_devolucao=dev, devolucao_assumida=False, disp_verificada=False, avisos=[])
    return _avancar(e, hoje)


def _ler_contatos(novo: dict, msg: str) -> None:
    resto = msg
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", resto)
    if m:
        novo["email"], resto = m.group(0)[:80], resto.replace(m.group(0), " ")
    for achado in re.findall(r"\(?\d[\d .()/-]{8,}\d", resto):
        digitos = re.sub(r"\D", "", achado)
        formatado_como_doc = bool(re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", achado))
        if len(digitos) == 14 or (len(digitos) == 11 and (formatado_como_doc or re.search(r"cpf", _n(msg)))):
            novo["documento"] = achado.strip()[:80]
        elif 10 <= len(digitos) <= 11:
            novo["telefone"] = achado.strip()[:80]
        resto = resto.replace(achado, " ")
    c = re.search(r"cidade\s*(?:é|e|:|de)?\s*([^,;\n]+)", resto, flags=re.I)
    if c:
        novo["cidade"] = c.group(1).strip()[:80]
    else:
        sobra = re.sub(r"(?i)\b(telefone|tel|fone|celular|whatsapp|e-?mail|cpf|cnpj|é|e|de|em|mora|moro|:)\b", " ", resto)
        sobra = re.sub(r"[,;:]", " ", sobra).strip()
        if sobra and len(sobra) <= 40 and not re.search(r"\d", sobra):
            novo["cidade"] = sobra[:80]


def _completo(e: dict) -> bool:
    r = e["rascunho"]
    novo = r.get("cliente_novo")
    if novo and not novo.get("tipo"):
        return False
    if e["fluxo"] == "cliente":
        return bool(novo)
    return bool((r.get("cliente_id") or novo) and r.get("evento") and r.get("data_retirada") and r.get("data_devolucao")
                and r["itens"] and all("produto_id" in i for i in r["itens"]))


def _confirmar(e: dict, msg: str, hoje: str | None) -> dict:
    """Única porta de saída para gravar: só uma resposta afirmativa, nesta etapa, gera `executar`."""
    r = e["rascunho"]
    if _afirmativo(msg):
        if not _completo(e):  # estado incompleto (ou adulterado): não grava, volta a perguntar o que falta
            return _avancar(e, hoje)
        executar = []
        novo = r.get("cliente_novo")
        if novo:
            executar.append({"nome": "criar_cliente", "args": {**{"documento": None, "email": None, "telefone": None, "cidade": None, "observacoes": None}, **novo}})
        if e["fluxo"] == "orcamento":
            executar.append({"nome": "criar_orcamento", "args": {
                "cliente_id": r.get("cliente_id"), "cliente_novo": bool(novo), "evento": r["evento"],
                "data_retirada": r["data_retirada"], "data_devolucao": r["data_devolucao"], "desconto": r.get("desconto", 0.0),
                "observacoes": r.get("observacoes", ""), "itens": [{"produto_id": i["produto_id"], "quantidade": i["quantidade"]} for i in r["itens"]]}})
        return {"texto": "Confirmado. Estou criando agora.", "agente": None, "executar": executar}
    if _negativo(msg):
        return _fim(CANCELADO)
    if e["fluxo"] == "orcamento":
        mudou = False
        datas = extrair_datas(msg, hoje)
        if len(datas) >= 2 and datas[1] >= datas[0]:
            r.update(data_retirada=datas[0], data_devolucao=datas[1], devolucao_assumida=False)
            mudou = True
        elif len(datas) == 1:
            r.update(data_retirada=datas[0], data_devolucao=datas[0], devolucao_assumida=True)
            mudou = True
        d = re.search(r"desconto\D{0,12}(\d+(?:[.,]\d+)?)\s*(%|reais|r\$)?", _n(msg))
        if d:
            valor = float(d.group(1).replace(",", "."))
            if d.group(2) == "%" and all("valor_diaria" in i for i in r["itens"]):
                bruto = calcular_total(r["itens"], diarias(r["data_retirada"], r["data_devolucao"]))
                valor = round(bruto * valor / 100, 2)
            r["desconto"] = valor
            mudou = True
        if mudou:
            r.update(disp_verificada=False, avisos=[])
            return _avancar(e, hoje)
    return _resp(e, "confirmar", "Responda “sim” para eu criar ou “não” para cancelar. Se quiser mudar a data ou o desconto, é só me dizer.", ["Confirmar", "Cancelar"])
