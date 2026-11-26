"""Ferramentas que a Lumi pode pedir (tool use / function calling).

Regra de ouro: o modelo só PEDE. Quem executa é o sistema, no navegador do usuário:
  - consultas (ler dados): o front lê pela mesma API das telas e devolve o resultado para cá;
  - cadastros: o front abre o MESMO formulário da tela, preenchido, e o usuário confere e salva;
  - exclusões: o front mostra um cartão com botão "Confirmar" e só então chama a mesma API de exclusão.
Esta API não grava nem lê nada do sistema. Aqui ficam só a lista de ferramentas, a validação do que o
modelo pediu (a saída do modelo é dado não confiável) e o filtro que evita gastar o LLM à toa.
"""
import json
import re
import unicodedata
from typing import Any

STATUS_ORCAMENTO = ["rascunho", "enviado", "aprovado", "finalizado", "cancelado"]
SITUACOES_COBRANCA = ["todos", "pendente", "atrasado", "pago", "cancelado"]
MODULOS = ["cliente", "produto", "orcamento"]

MAX_TEXTO = 200
MAX_ITENS = 20
MAX_BYTES_RESULTADO = 8000
MAX_RESULTADOS = 3
DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _texto(descricao: str) -> dict:
    return {"type": "STRING", "description": descricao}


def _numero(descricao: str) -> dict:
    return {"type": "NUMBER", "description": descricao}


def _declaracao(nome: str, descricao: str, propriedades: dict | None = None, obrigatorios: list[str] | None = None) -> dict:
    d: dict[str, Any] = {"name": nome, "description": descricao}
    if propriedades:
        d["parameters"] = {"type": "OBJECT", "properties": propriedades}
        if obrigatorios:
            d["parameters"]["required"] = obrigatorios
    return d


# --- Consultas (somente leitura; o front executa) ---
CONSULTAS: dict[str, dict] = {d["name"]: d for d in [
    _declaracao("resumo_painel", "Números do Painel: recebido no mês, a receber, em atraso, orçamentos em aberto, orçamentos por status, produtos mais alugados e próximos eventos."),
    _declaracao("consultar_orcamentos", "Lista e conta orçamentos, com a soma dos totais. Use para 'quantos orçamentos aprovados', 'orçamentos da Ana', 'eventos de dezembro'.", {
        "status": {"type": "STRING", "enum": STATUS_ORCAMENTO, "description": "Filtrar por status."},
        "busca": _texto("Parte do nome do cliente, do evento ou do número do orçamento."),
        "retirada_de": _texto("Data inicial da retirada, AAAA-MM-DD."),
        "retirada_ate": _texto("Data final da retirada, AAAA-MM-DD."),
    }),
    _declaracao("consultar_clientes", "Lista e conta clientes.", {"busca": _texto("Parte do nome, documento, e-mail ou cidade.")}),
    _declaracao("consultar_produtos", "Lista e conta produtos do acervo, com diária e estoque.", {
        "busca": _texto("Parte do nome ou do código."),
        "categoria": _texto("Nome exato da categoria."),
        "ativo": {"type": "BOOLEAN", "description": "true só ativos, false só inativos."},
    }),
    _declaracao("consultar_cobrancas", "Lista e soma as cobranças (parcelas) do financeiro.", {
        "situacao": {"type": "STRING", "enum": SITUACOES_COBRANCA, "description": "Situação das cobranças. Padrão: todos."},
    }),
]}

# --- Ações (o usuário confere e confirma no chat; o modelo não grava nada) ---
ACOES: dict[str, dict] = {d["name"]: d for d in [
    _declaracao("cadastrar_cliente", "Abre o formulário de novo cliente, já preenchido com o que o usuário informou. Não invente dados.", {
        "nome": _texto("Nome do cliente ou da empresa."),
        "tipo": {"type": "STRING", "enum": ["PF", "PJ"], "description": "PF pessoa física, PJ empresa."},
        "documento": _texto("CPF ou CNPJ."), "email": _texto("E-mail."), "telefone": _texto("Telefone."),
        "cidade": _texto("Cidade."), "observacoes": _texto("Observações."),
    }),
    _declaracao("cadastrar_produto", "Abre o formulário de novo produto, já preenchido com o que o usuário informou. Não invente dados.", {
        "codigo": _texto("Código do produto."), "nome": _texto("Nome."), "categoria": _texto("Categoria."), "descricao": _texto("Descrição."),
        "valor_diaria": _numero("Valor da diária em reais."), "valor_reposicao": _numero("Valor de reposição em reais."),
        "quantidade": _numero("Quantidade em estoque."),
    }),
    _declaracao("cadastrar_orcamento", "Abre o formulário de novo orçamento, já preenchido com o que o usuário informou. Não invente dados.", {
        "cliente": _texto("Nome do cliente."), "evento": _texto("Nome do evento."),
        "data_retirada": _texto("AAAA-MM-DD."), "data_devolucao": _texto("AAAA-MM-DD."),
        "desconto": _numero("Desconto em reais."), "observacoes": _texto("Observações."),
        "itens": {"type": "ARRAY", "description": "Produtos do orçamento.", "items": {"type": "OBJECT", "properties": {
            "produto": _texto("Nome ou código do produto."), "quantidade": _numero("Quantidade."),
        }}},
    }),
    _declaracao("excluir_registro", "Pede a exclusão de um cliente, produto ou orçamento. O usuário ainda precisa confirmar com um botão.", {
        "modulo": {"type": "STRING", "enum": MODULOS, "description": "O que excluir."},
        "busca": _texto("Nome, código ou número que identifica o registro."),
    }, ["modulo", "busca"]),
]}

TODAS = {**CONSULTAS, **ACOES}


def declaracoes() -> list[dict]:
    """Formato que o Gemini espera em `tools`."""
    return [{"functionDeclarations": list(TODAS.values())}]


# --- Validação: a saída do modelo é dado não confiável ---

def _limpar_texto(v: Any) -> str | None:
    if isinstance(v, (str, int, float)) and not isinstance(v, bool):
        t = str(v).strip()
        return t[:MAX_TEXTO] if t else None
    return None


def _limpar_numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        n = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return n if -1e9 < n < 1e9 else None


def _limpar_data(v: Any) -> str | None:
    t = _limpar_texto(v)
    return t if t and DATA_ISO.match(t) else None


def _limpar_enum(v: Any, validos: list[str]) -> str | None:
    t = _limpar_texto(v)
    if t is None:
        return None
    for x in validos:
        if t.lower() == x.lower():
            return x
    return None


def _so(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def validar_chamada(nome: Any, args: Any) -> dict | None:
    """Devolve {"nome", "args"} limpo, ou None se a ferramenta não existe ou faltam argumentos essenciais."""
    if not isinstance(nome, str) or nome not in TODAS:
        return None
    a = args if isinstance(args, dict) else {}

    if nome == "resumo_painel":
        limpo: dict = {}
    elif nome == "consultar_orcamentos":
        limpo = _so({"status": _limpar_enum(a.get("status"), STATUS_ORCAMENTO), "busca": _limpar_texto(a.get("busca")),
                     "retirada_de": _limpar_data(a.get("retirada_de")), "retirada_ate": _limpar_data(a.get("retirada_ate"))})
    elif nome == "consultar_clientes":
        limpo = _so({"busca": _limpar_texto(a.get("busca"))})
    elif nome == "consultar_produtos":
        ativo = a.get("ativo")
        limpo = _so({"busca": _limpar_texto(a.get("busca")), "categoria": _limpar_texto(a.get("categoria")), "ativo": ativo if isinstance(ativo, bool) else None})
    elif nome == "consultar_cobrancas":
        limpo = {"situacao": _limpar_enum(a.get("situacao"), SITUACOES_COBRANCA) or "todos"}
    elif nome == "cadastrar_cliente":
        limpo = _so({"nome": _limpar_texto(a.get("nome")), "tipo": _limpar_enum(a.get("tipo"), ["PF", "PJ"]), "documento": _limpar_texto(a.get("documento")),
                     "email": _limpar_texto(a.get("email")), "telefone": _limpar_texto(a.get("telefone")), "cidade": _limpar_texto(a.get("cidade")),
                     "observacoes": _limpar_texto(a.get("observacoes"))})
    elif nome == "cadastrar_produto":
        qtd = _limpar_numero(a.get("quantidade"))
        limpo = _so({"codigo": _limpar_texto(a.get("codigo")), "nome": _limpar_texto(a.get("nome")), "categoria": _limpar_texto(a.get("categoria")),
                     "descricao": _limpar_texto(a.get("descricao")), "valor_diaria": _limpar_numero(a.get("valor_diaria")),
                     "valor_reposicao": _limpar_numero(a.get("valor_reposicao")), "quantidade": int(qtd) if qtd is not None else None})
    elif nome == "cadastrar_orcamento":
        itens = []
        for bruto in (a.get("itens") if isinstance(a.get("itens"), list) else [])[:MAX_ITENS]:
            if not isinstance(bruto, dict):
                continue
            produto, qtd = _limpar_texto(bruto.get("produto")), _limpar_numero(bruto.get("quantidade"))
            if produto:
                itens.append({"produto": produto, "quantidade": max(1, int(qtd)) if qtd is not None else 1})
        limpo = _so({"cliente": _limpar_texto(a.get("cliente")), "evento": _limpar_texto(a.get("evento")), "data_retirada": _limpar_data(a.get("data_retirada")),
                     "data_devolucao": _limpar_data(a.get("data_devolucao")), "desconto": _limpar_numero(a.get("desconto")),
                     "observacoes": _limpar_texto(a.get("observacoes")), "itens": itens or None})
    else:  # excluir_registro
        modulo, busca = _limpar_enum(a.get("modulo"), MODULOS), _limpar_texto(a.get("busca"))
        if not modulo or not busca:
            return None
        limpo = {"modulo": modulo, "busca": busca}
    return {"nome": nome, "args": limpo}


def eh_consulta(nome: str) -> bool:
    return nome in CONSULTAS


def validar_resultados(brutos: Any) -> list[dict]:
    """Resultados que o front devolveu depois de executar as consultas. Só aceita consultas conhecidas e de tamanho razoável."""
    saida = []
    for r in (brutos if isinstance(brutos, list) else [])[:MAX_RESULTADOS]:
        if not isinstance(r, dict) or not isinstance(r.get("nome"), str) or r["nome"] not in CONSULTAS:
            continue
        chamada = validar_chamada(r["nome"], r.get("args"))
        resultado = r.get("resultado")
        texto = json.dumps(resultado, ensure_ascii=False)
        if chamada is None or len(texto) > MAX_BYTES_RESULTADO:
            continue
        saida.append({"nome": r["nome"], "args": chamada["args"], "resultado": resultado})
    return saida


# --- Filtro barato: só gasta uma chamada de LLM se a frase parece pedir dados ou uma ação ---

def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


_ACAO = re.compile(r"\b(cadastr\w*|cri(?:e|ar|a|ando)|fac[aeo]|fazer|faz|ger[ae]|gerar|mont[ae]|montar|elabor\w+|prepar\w+|nov[oa]s?|adicion\w*|inclu\w+|registr\w*|exclu\w+|apag\w+|delet\w+|remov\w+|remova|tire|tirar)\b")
_DADOS = re.compile(r"\b(quanto|quantos|quantas|total|soma|lista\w*|liste|mostr\w+|resumo|me\s+d[aeê]|tenho|temos|ha|faturamento|receb\w+|atras\w+|pendente\w*|vencid\w+|proxim\w+|mais\s+alugad\w+|quais|qual\s+o\s+valor)\b")
_COMO = re.compile(r"^\s*(como|onde|posso|pode|e\s+possivel|por\s*que|o\s+que\s+(e|significa)|qual\s+a\s+diferenca|quando)\b")


_USUARIO = re.compile(r"\busuari[oa]s?\b")
_ALVO_CERTO = re.compile(r"\b(clientes?|produtos?|orcamentos?)\b")


def fala_de_usuario_do_sistema(pergunta: str) -> bool:
    """"cadastre o usuário X": o agente não tem ferramenta de usuários e não pode adivinhar que era cliente."""
    p = _sem_acento(pergunta)
    return bool(_USUARIO.search(p)) and not _ALVO_CERTO.search(p)


def pede_acao(pergunta: str) -> bool:
    """Pede para criar/cadastrar/excluir algo (e não é uma dúvida de 'como fazer')."""
    p = _sem_acento(pergunta)
    return bool(_ACAO.search(p)) and not _COMO.search(p)


def parece_pedido_de_acao_ou_dados(pergunta: str, historico: list[str] | None = None) -> bool:
    """True se vale perguntar ao LLM se isto é uma consulta/ação. Dúvidas de 'como fazer' seguem para o FAQ."""
    p = _sem_acento(pergunta)
    if _DADOS.search(p):
        return True
    if _COMO.search(p):
        return False
    if _ACAO.search(p):
        return True
    # resposta curta a uma pergunta de esclarecimento ("tripé" depois de "quero excluir um produto")
    if historico and len(p.split()) <= 6:
        anterior = _sem_acento(historico[-1])
        return bool(_ACAO.search(anterior) and not _COMO.search(anterior)) or bool(_DADOS.search(anterior))
    return False
