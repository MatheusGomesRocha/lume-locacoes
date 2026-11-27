"""O que uma consulta criada pelos Agents pode tocar: entidades, campos, permissões e dados de teste.

Nenhum Agent escreve código: a consulta é uma ESPECIFICAÇÃO (dados) montada só com estas peças. O que não está
aqui não existe para eles. Campos `pessoal` e `secreto` nunca saem em consulta gerada.
"""
import re

DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIPOS = ("texto", "numero", "data", "bool", "enum")
PAPEIS = ("master", "admin", "usuario")


def _c(tipo: str, rotulo: str, valores: list[str] | None = None, nivel: str = "normal") -> dict:
    return {"tipo": tipo, "rotulo": rotulo, "valores": valores or [], "nivel": nivel}


ESQUEMA: dict[str, dict] = {
    "clientes": {"rotulo": "Clientes", "permissao": "clientes.ver", "so_admin": False, "campos": {
        "nome": _c("texto", "Nome"), "tipo": _c("enum", "Tipo", ["PF", "PJ"]), "cidade": _c("texto", "Cidade"),
        "observacoes": _c("texto", "Observações"), "criado_em": _c("data", "Cadastrado em"),
        "documento": _c("texto", "CPF/CNPJ", nivel="pessoal"), "email": _c("texto", "E-mail", nivel="pessoal"),
        "telefone": _c("texto", "Telefone", nivel="pessoal"),
    }},
    "produtos": {"rotulo": "Produtos", "permissao": "produtos.ver", "so_admin": False, "campos": {
        "codigo": _c("texto", "Código"), "nome": _c("texto", "Nome"), "categoria": _c("texto", "Categoria"),
        "valor_diaria": _c("numero", "Valor da diária"), "valor_reposicao": _c("numero", "Valor de reposição"),
        "quantidade": _c("numero", "Quantidade em estoque"), "ativo": _c("bool", "Ativo"),
        "criado_em": _c("data", "Cadastrado em"),
    }},
    "orcamentos": {"rotulo": "Orçamentos", "permissao": "orcamentos.ver", "so_admin": False, "campos": {
        "numero": _c("texto", "Número"), "cliente_nome": _c("texto", "Cliente"), "evento": _c("texto", "Evento"),
        "status": _c("enum", "Status", ["rascunho", "enviado", "aprovado", "finalizado", "cancelado"]),
        "data_retirada": _c("data", "Data de retirada"), "data_devolucao": _c("data", "Data de devolução"),
        "diarias": _c("numero", "Diárias"), "desconto": _c("numero", "Desconto"), "total": _c("numero", "Total"),
        "criado_em": _c("data", "Criado em"),
    }},
    "pagamentos": {"rotulo": "Cobranças", "permissao": "financeiro.ver", "so_admin": False, "campos": {
        "orcamento_numero": _c("texto", "Orçamento"), "valor": _c("numero", "Valor"), "vencimento": _c("data", "Vencimento"),
        "pago_em": _c("data", "Pago em"), "status": _c("enum", "Situação", ["pendente", "pago", "cancelado"]),
        "forma": _c("enum", "Forma", ["pix", "cartao", "boleto", "dinheiro"]), "criado_em": _c("data", "Criado em"),
    }},
    "usuarios": {"rotulo": "Usuários do sistema", "permissao": "usuarios.ver", "so_admin": True, "campos": {
        "nome": _c("texto", "Nome"), "papel": _c("enum", "Perfil", list(PAPEIS)), "grupo_nome": _c("texto", "Grupo"),
        "ativo": _c("bool", "Ativo"), "criado_em": _c("data", "Cadastrado em"),
        "email": _c("texto", "E-mail", nivel="pessoal"), "senha": _c("texto", "Senha", nivel="secreto"),
    }},
    "grupos": {"rotulo": "Grupos de permissão", "permissao": "usuarios.ver", "so_admin": True, "campos": {
        "nome": _c("texto", "Nome do grupo"), "descricao": _c("texto", "Descrição"), "sistema": _c("bool", "Grupo do sistema"),
        "usuarios_count": _c("numero", "Usuários no grupo"), "permissoes_count": _c("numero", "Quantidade de permissões"),
        "criado_em": _c("data", "Criado em"),
    }},
}

# Mesmas chaves "modulo.acao" do front (versao-real/frontend/src/lib/permissoes.ts).
PERMISSOES_VALIDAS = {
    "painel.ver", "financeiro.ver", "financeiro.baixar", "assistente.usar", "assistente.conversas",
    *{f"{m}.{a}" for m in ("produtos", "clientes", "usuarios") for a in ("ver", "criar", "editar", "excluir")},
    *{f"orcamentos.{a}" for a in ("ver", "criar", "editar", "excluir", "enviar", "aprovar", "finalizar", "cancelar")},
}

# Regras de negócio de cada módulo que as consultas geradas precisam respeitar (checadas em checagens.py).
REGRAS_DE_MODULO = {
    "orcamentos": [
        "ORC-DATAS: data de retirada e data de devolução são obrigatórias em todo orçamento; quem mostra uma, mostra a outra.",
        "ORC-PERIODO: filtro de período usa data_retirada, data_devolucao ou criado_em (quando o orçamento foi criado), e 'de' nunca pode ser depois de 'até'.",
    ],
    "usuarios": ["USR-ADMIN: só master e administrador consultam usuários; e-mail e senha nunca saem."],
    "grupos": ["USR-ADMIN: só master e administrador consultam grupos de permissão."],
    "pagamentos": ["FIN-PERM: cobranças só com a permissão do Financeiro (financeiro.ver)."],
    "clientes": ["CLI-PESSOAL: documento, e-mail e telefone são dados pessoais e não saem em consulta gerada."],
    "produtos": [],
}

# Qual data a pergunta quer, pelo verbo: "criados hoje" é criado_em, "retirados hoje" é data_retirada, "pagos hoje" é pago_em.
# Chave = raiz da palavra (sem acento, singular/masculino); a consulta de período precisa filtrar por um dos campos citados.
VERBOS_DE_DATA: dict[str, dict[str, str]] = {
    "orcamentos": {"criado": "criado_em", "feito": "criado_em", "retirado": "data_retirada", "retirada": "data_retirada", "retiram": "data_retirada",
                   "devolvido": "data_devolucao", "devolucao": "data_devolucao", "devolvem": "data_devolucao", "volta": "data_devolucao", "voltam": "data_devolucao"},
    "pagamentos": {"pago": "pago_em", "pagou": "pago_em", "pagaram": "pago_em", "vencido": "vencimento", "vence": "vencimento", "vencem": "vencimento", "vencimento": "vencimento", "vencendo": "vencimento",
                   "criado": "criado_em"},
    "clientes": {"cadastrado": "criado_em", "criado": "criado_em"},
    "produtos": {"cadastrado": "criado_em", "criado": "criado_em"},
    "usuarios": {"cadastrado": "criado_em", "criado": "criado_em"},
    "grupos": {"criado": "criado_em"},
}

# Campo lógico (bool) -> (palavra do "sim", palavra do "não"): "produtos ativos" / "produtos inativos".
BOOL_PALAVRAS: dict[str, tuple[str, str]] = {"ativo": ("ativo", "inativo")}

# Como as pessoas falam de cada módulo. A matriz de testes gerada usa isto para montar perguntas; "valores" e "datas" dizem como se fala cada
# valor de campo e cada data ("pagas", "no cartão", "com retirada"). Módulo novo no esquema: declare aqui e a matriz ganha as perguntas dele.
VOCABULARIO: dict[str, dict] = {
    "clientes": {"assunto": ["clientes"], "genero": "m", "valores": {("tipo", "PF"): "do tipo PF", ("tipo", "PJ"): "do tipo PJ"}, "datas": {"criado_em": "cadastrados"}},
    "produtos": {"assunto": ["produtos"], "genero": "m", "valores": {("ativo", True): "ativos", ("ativo", False): "inativos"}, "datas": {"criado_em": "cadastrados"}},
    "orcamentos": {"assunto": ["orçamentos"], "genero": "m",
                   "valores": {("status", "rascunho"): "em rascunho", ("status", "enviado"): "enviados", ("status", "aprovado"): "aprovados",
                               ("status", "finalizado"): "finalizados", ("status", "cancelado"): "cancelados"},
                   "datas": {"criado_em": "criados", "data_retirada": "com retirada", "data_devolucao": "com devolução"}},
    "pagamentos": {"assunto": ["cobranças", "pagamentos"], "genero": "f", "outros_assuntos": {"orçamentos": "m"},
                   "valores": {("status", "pendente"): "pendentes", ("status", "cancelado"): "canceladas", ("forma", "pix"): "no Pix", ("forma", "cartao"): "no cartão",
                               ("forma", "boleto"): "no boleto", ("forma", "dinheiro"): "em dinheiro"},
                   "datas": {"pago_em": "PAGO", "vencimento": "com vencimento", "criado_em": "criadas"},
                   "pago": {"m": "pagos", "f": "pagas"}},  # "pagas hoje" = situação paga E data de pagamento (PAGO = usa o dicionário "pago")
    "usuarios": {"assunto": ["usuários"], "genero": "m", "valores": {("ativo", True): "ativos", ("ativo", False): "inativos", ("papel", "admin"): "admin"},
                 "datas": {"criado_em": "cadastrados"}},
    "grupos": {"assunto": ["grupos de permissão"], "genero": "m", "valores": {}, "datas": {"criado_em": "criados"}},
}

# Dados pequenos e fixos para os testes (as armadilhas são de propósito: nomes parecidos, inativos, datas).
# "Hoje" dos testes: as datas de DADOS_TESTE e os casos com "últimos N dias" são calculados a partir dele.
HOJE_TESTE = "2026-11-26"

DADOS_TESTE: dict[str, list[dict]] = {
    "grupos": [
        {"nome": "Master", "descricao": "Acesso total", "sistema": True, "usuarios_count": 1, "permissoes_count": 30, "criado_em": "2026-01-10"},
        {"nome": "Administração", "descricao": None, "sistema": True, "usuarios_count": 1, "permissoes_count": 20, "criado_em": "2026-01-10"},
        {"nome": "Vendas", "descricao": "Time comercial", "sistema": False, "usuarios_count": 2, "permissoes_count": 8, "criado_em": "2026-11-18"},
    ],
    "usuarios": [
        {"nome": "Matheus Gomes", "papel": "master", "grupo_nome": "Master", "ativo": True, "email": "m@x.com", "senha": "hash1", "criado_em": "2026-01-10"},
        {"nome": "Ana Lima", "papel": "admin", "grupo_nome": "Administração", "ativo": True, "email": "a@x.com", "senha": "hash2", "criado_em": "2026-02-03"},
        {"nome": "Bruno Reis", "papel": "usuario", "grupo_nome": "Vendas", "ativo": True, "email": "b@x.com", "senha": "hash3", "criado_em": "2026-11-20"},
        {"nome": "Carla Dias", "papel": "usuario", "grupo_nome": "Vendas", "ativo": False, "email": "c@x.com", "senha": "hash4", "criado_em": "2026-11-26"},
    ],
    "clientes": [
        {"nome": "Maria Souza", "tipo": "PF", "cidade": "Fortaleza", "observacoes": None, "criado_em": "2026-11-25", "documento": "111", "email": "ms@x.com", "telefone": "8599"},
        {"nome": "Mariana Albuquerque", "tipo": "PF", "cidade": "Sobral", "observacoes": None, "criado_em": "2026-11-10", "documento": "222", "email": None, "telefone": None},
        {"nome": "Padaria Sol", "tipo": "PJ", "cidade": "Fortaleza", "observacoes": "Cliente antigo", "criado_em": "2026-11-20", "documento": "333", "email": None, "telefone": None},
    ],
    "produtos": [
        {"codigo": "MS-01", "nome": "Mesa Redonda 1,5 m", "categoria": "Mesas", "valor_diaria": 35.0, "valor_reposicao": 400.0, "quantidade": 40, "ativo": True, "criado_em": "2026-10-01"},
        {"codigo": "CD-01", "nome": "Cadeira Tiffany Branca", "categoria": "Cadeiras", "valor_diaria": 9.0, "valor_reposicao": 90.0, "quantidade": 200, "ativo": True, "criado_em": "2026-11-24"},
        {"codigo": "RF-01", "nome": "Refletor LED", "categoria": "Iluminação", "valor_diaria": 85.0, "valor_reposicao": 700.0, "quantidade": 10, "ativo": True, "criado_em": "2026-11-02"},
        {"codigo": "VR-09", "nome": "Varal de Luzes", "categoria": "Iluminação", "valor_diaria": 60.0, "valor_reposicao": 300.0, "quantidade": 5, "ativo": False, "criado_em": "2026-11-26"},
    ],
    "orcamentos": [
        {"numero": "ORC-2026-0001", "cliente_nome": "Maria Souza", "evento": "Casamento", "status": "aprovado", "data_retirada": "2026-11-26", "data_devolucao": "2026-11-27", "diarias": 1, "desconto": 0.0, "total": 160.0, "criado_em": "2026-11-20"},
        {"numero": "ORC-2026-0002", "cliente_nome": "Padaria Sol", "evento": "Inauguração", "status": "rascunho", "data_retirada": "2026-12-05", "data_devolucao": "2026-12-06", "diarias": 1, "desconto": 10.0, "total": 300.0, "criado_em": "2026-11-24"},
        {"numero": "ORC-2026-0003", "cliente_nome": "Mariana Albuquerque", "evento": "Aniversário", "status": "cancelado", "data_retirada": "2026-10-10", "data_devolucao": "2026-10-11", "diarias": 1, "desconto": 0.0, "total": 90.0, "criado_em": "2026-10-05"},
        {"numero": "ORC-2026-0004", "cliente_nome": "Maria Souza", "evento": "Formatura", "status": "aprovado", "data_retirada": "2026-12-20", "data_devolucao": "2026-12-22", "diarias": 2, "desconto": 0.0, "total": 500.0, "criado_em": "2026-11-26"},
    ],
    "pagamentos": [
        {"orcamento_numero": "ORC-2026-0001", "valor": 160.0, "vencimento": "2026-11-20", "pago_em": None, "status": "pendente", "forma": None, "criado_em": "2026-11-20"},
        {"orcamento_numero": "ORC-2026-0004", "valor": 250.0, "vencimento": "2026-12-01", "pago_em": "2026-11-30", "status": "pago", "forma": "pix", "criado_em": "2026-11-26"},
        {"orcamento_numero": "ORC-2026-0004", "valor": 250.0, "vencimento": "2026-12-20", "pago_em": None, "status": "pendente", "forma": None, "criado_em": "2026-11-26"},
    ],
}

# Quem pergunta nos testes de permissão.
SESSOES_TESTE = {
    "master": {"papel": "master", "permissoes": sorted(PERMISSOES_VALIDAS), "hoje": HOJE_TESTE},
    "admin": {"papel": "admin", "permissoes": sorted(PERMISSOES_VALIDAS), "hoje": HOJE_TESTE},
    "vendedor": {"papel": "usuario", "permissoes": ["clientes.ver", "produtos.ver", "orcamentos.ver", "orcamentos.criar", "painel.ver"], "hoje": HOJE_TESTE},
    "sem_nada": {"papel": "usuario", "permissoes": [], "hoje": HOJE_TESTE},
}
