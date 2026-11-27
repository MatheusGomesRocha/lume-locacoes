"""Perguntas sobre uma informação que o sistema NÃO guarda ("quantos usuários moram em Fortaleza?").

Nenhuma consulta, hoje ou no futuro, responde isso: falta o dado, não a ferramenta. Por isso a pergunta é respondida na hora, no
chat, e NUNCA vai para os Agents (eles só têm o que fazer quando o dado existe e falta a consulta).

É código, não modelo: cruza a ENTIDADE citada com o ATRIBUTO pedido. O que cada entidade guarda está em GUARDA (conferido contra
o esquema em testes: se um campo novo aparece lá e aqui não, o teste acusa).
"""
import re
import unicodedata

from evolucao.esquema import ESQUEMA


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


# entidade do esquema -> (como a pessoa fala, como se escreve na resposta, o que o sistema guarda dela)
ENTIDADES: dict[str, tuple[re.Pattern, str, str]] = {
    "usuarios": (re.compile(r"\busuarios?\b"), "usuários do sistema", "nome, e-mail, perfil, grupo de permissões, se está ativo e a data de cadastro"),
    "clientes": (re.compile(r"\bclientes?\b"), "clientes", "nome, tipo (pessoa física ou empresa), documento, e-mail, telefone, cidade, observações e a data de cadastro"),
    "produtos": (re.compile(r"\bprodutos?\b|\bequipamentos?\b"), "produtos", "código, nome, categoria, descrição, valor da diária, valor de reposição, quantidade em estoque, se está ativo e a data de cadastro"),
    "orcamentos": (re.compile(r"\borcamentos?\b"), "orçamentos", "número, cliente, evento, status, datas de retirada e devolução, diárias, itens, desconto, total, observações e a data de criação"),
    "pagamentos": (re.compile(r"\bcobrancas?\b|\bpagamentos?\b|\bparcelas?\b"), "cobranças", "orçamento, valor, vencimento, data e forma de pagamento, situação e a data de criação"),
    "grupos": (re.compile(r"\bgrupos?\b"), "grupos de permissão", "nome, descrição, permissões, quantidade de usuários e a data de criação"),
}

_CIDADES = r"fortaleza|sobral|caucaia|maracanau|juazeiro do norte|crato|eusebio|aquiraz|sao paulo|rio de janeiro|recife|salvador|brasilia|belo horizonte|curitiba|porto alegre|natal|teresina"

# conceito -> (rótulo, como aparece na pergunta, entidades que GUARDAM isso)
ATRIBUTOS: dict[str, tuple[str, re.Pattern, set[str]]] = {
    "localizacao": ("cidade ou localização", re.compile(
        r"\b(resid\w*|mor(a|am|ando|adores?|adia)|cidades?|bairros?|estados?|enderecos?|localiza\w*|regiao|cep|municipios?)\b|\b(em|na|no|de|do|da) (" + _CIDADES + r")\b"), {"clientes"}),
    "idade": ("idade ou data de nascimento", re.compile(r"\b(idades?|nascimento|nasceu|nasceram|nascidos?|anos de idade|maiores de idade|menores de idade)\b"), set()),
    "genero": ("sexo ou gênero", re.compile(r"\b(sexo|generos?|homens|mulheres|masculin\w+|feminin\w+)\b"), set()),
    "cargo": ("cargo, salário ou departamento", re.compile(r"\b(salarios?|cargos?|departamentos?|setores?|ramal|turnos?)\b"), set()),
    "autoria": ("quem criou ou é responsável", re.compile(r"\b(quem (criou|cadastrou|fez|editou)|criad[oa]s? por|cadastrad[oa]s? por|feit[oa]s? por|vendedor\w*|atendentes?|responsaveis?)\b"), set()),
    "acesso": ("último acesso ou login", re.compile(r"\b(ultimo (acesso|login)|ultima vez|logaram|logou|acessaram|online)\b"), set()),
    "especificacao": ("marca, fornecedor, peso ou dimensões", re.compile(r"\b(marcas?|fornecedor\w*|fabricantes?|pesos?|altura|largura|comprimento|dimensoes|medidas|tamanhos?|voltagem|potencia)\b"), set()),
    "imagem": ("foto ou imagem", re.compile(r"\b(fotos?|imagens?|logo)\b"), set()),
}

_SO_DADOS = re.compile(r"^(quantos|quantas|quanto|quais|qual|quem|liste|listar|lista|mostre|mostrar|exiba|existe|existem|tem|temos|tenho|ha)\b|\b(eu tenho|temos|existem)\b")


def pergunta_impossivel(pergunta: str) -> dict | None:
    """{"entidades": [...], "atributo": rótulo, "resposta": texto} se a pergunta pede algo que o sistema não guarda; senão None."""
    t = _sem_acento(pergunta).strip()
    if not t or not _SO_DADOS.search(t):
        return None
    citadas = [e for e, (padrao, _, _) in ENTIDADES.items() if padrao.search(t)]
    if not citadas:
        return None
    for conceito, (rotulo, padrao, quem_guarda) in ATRIBUTOS.items():
        if not padrao.search(t):
            continue
        if set(citadas) & quem_guarda:  # alguma das entidades citadas guarda isso: não é impossível, a consulta pode existir
            continue
        e = citadas[0]
        _, nome, guarda = ENTIDADES[e]
        onde = [ENTIDADES[x][1] for x in quem_guarda if x in ENTIDADES]
        dica = f" Quem guarda {rotulo.split(' ou ')[0]} é o cadastro de {', '.join(onde)}." if onde else ""
        return {"entidades": citadas, "atributo": rotulo, "resposta": (
            f"Não consigo responder isso: o sistema não guarda {rotulo} de {nome}, então nenhuma consulta daria esse número.{dica} "
            f"De {nome} eu tenho: {guarda}. Posso responder algo com isso?")}
    return None


def conferir_contra_esquema() -> list[str]:
    """Para os testes: toda entidade do esquema tem texto aqui, e todo campo 'localizacao' guardado está declarado."""
    erros = [f"entidade {e} do esquema sem texto em ENTIDADES" for e in ESQUEMA if e not in ENTIDADES]
    erros += [f"{e} em ENTIDADES não existe no esquema" for e in ENTIDADES if e not in ESQUEMA]
    for e, c in (("clientes", "cidade"),):
        if c not in ESQUEMA[e]["campos"]:
            erros.append(f"{e}.{c} sumiu do esquema: ajuste ATRIBUTOS")
    return erros
