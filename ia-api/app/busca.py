"""Busca nas perguntas frequentes (a etapa de "recuperação" de um RAG).

Aqui NÃO há IA generativa: a pergunta do usuário é comparada com as
perguntas do FAQ por similaridade de texto (TF-IDF + cosseno), em Python puro.
O mesmo desenho serve depois para trocar TF-IDF por embeddings.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Palavras que não ajudam a diferenciar uma pergunta da outra.
STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "pra", "com", "sem", "e", "ou",
    "que", "se", "ao", "aos", "meu", "minha", "meus", "minhas", "seu", "sua", "como",
    "qual", "quais", "quando", "onde", "porque", "eh", "ser", "esta", "esse", "essa",
    "faco", "fazer", "posso", "pode", "preciso", "quero", "consigo", "tem", "ha",
    "mais", "muito", "ja", "so", "me", "te", "lhe", "isso", "isto", "aqui", "voce",
    "sistema", "tela", "eu", "nao", "uso", "usar", "sobre", "vez", "vezes",
}

# Palavras diferentes que, para o sistema, querem dizer a mesma coisa.
SINONIMOS = {
    "deletar": "excluir", "apagar": "excluir", "remover": "excluir",
    "exclusao": "excluir", "excluido": "excluir", "eliminar": "excluir",
    "aprovacao": "aprovar", "liberar": "aprovar", "aprovo": "aprovar", "aprovei": "aprovar",
    "cancelo": "cancelar", "devolvo": "devolver", "retiro": "retirar", "excluo": "excluir",
    "deleto": "excluir", "apago": "excluir", "removo": "excluir",
    "pendente": "pendencia", "pendencias": "pendencia",
    "devolucao": "devolver", "devolvido": "devolver", "devolvida": "devolver",
    "retirada": "retirar", "retirado": "retirar",
    "cancelamento": "cancelar",
    "criacao": "criar", "novo": "criar", "nova": "criar", "cadastro": "cadastrar",
    "mandar": "enviar", "envio": "enviar",
    "planilha": "excel", "xlsx": "excel",
    "valores": "valor", "preco": "valor", "precos": "valor",
    "zerado": "zero", "danificado": "avaria", "quebrado": "avaria", "defeito": "avaria",
    "email": "mail", "e-mail": "mail",
    "qrcode": "qr", "etiqueta": "qr",
    "erro": "problema", "falha": "problema", "travou": "problema", "travado": "problema", "impossivel": "problema",
    "cobranca": "pagamento", "cobrancas": "pagamento", "recebimento": "pagamento", "receber": "pagamento",
    "baixa": "pagamento", "pagar": "pagamento", "pago": "pagamento", "fatura": "pagamento",
    "atrasado": "atraso", "vencido": "atraso", "vencida": "atraso",
    "inativar": "inativo", "desativar": "inativo", "desativado": "inativo",
    "estoque": "disponibilidade", "disponivel": "disponibilidade", "indisponivel": "disponibilidade",
    "locacao": "orcamento", "aluguel": "orcamento",
    "equipamento": "produto", "equipamentos": "produto", "item": "produto", "itens": "produto",
}

TAMANHO_RAIZ = 6  # "aprovar", "aprovado", "aprovação" viram a mesma raiz: "aprova"

PESO_PERGUNTA = 3
PESO_PALAVRAS_CHAVE = 2
PESO_RESPOSTA = 1


def normalizar(texto: str) -> str:
    """minúsculas, sem acento e sem pontuação."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def raiz(palavra: str) -> str:
    palavra = SINONIMOS.get(palavra, palavra)
    if len(palavra) > 3 and palavra.endswith("s"):
        palavra = palavra[:-1]
    return palavra[:TAMANHO_RAIZ]


# Frases com "não" mudam o sentido da pergunta: "não consigo aprovar" é um problema,
# não um "como aprovar". Elas viram o termo "problema" antes de descartar as palavras comuns.
FRASES_DE_PROBLEMA = (
    ("nao consigo", "problema"), ("nao consegui", "problema"), ("nao funciona", "problema"),
    ("nao deixa", "problema"), ("nao aparece", "problema"), ("nao da para", "problema"),
    ("nao aprova", "problema aprovar"),
)


def extrair_termos(texto: str) -> list[str]:
    termos = []
    normalizado = normalizar(texto)
    for frase, troca in FRASES_DE_PROBLEMA:
        normalizado = normalizado.replace(frase, troca)
    for palavra in normalizado.split():
        if palavra in STOPWORDS or (len(palavra) < 2 and not palavra.isdigit()):
            continue
        termos.append(raiz(palavra))
    return termos


@dataclass
class Resultado:
    id: str
    modulo: str
    pergunta: str
    resposta: str
    score: float


class BaseConhecimento:
    def __init__(self, caminho_faq: Path):
        with open(caminho_faq, encoding="utf-8") as f:
            self.itens = json.load(f)

        # 1) conta os termos de cada item, com pesos diferentes por campo
        contagens = []
        for item in self.itens:
            c = Counter()
            for termo in extrair_termos(item["pergunta"]):
                c[termo] += PESO_PERGUNTA
            for chave in item.get("palavras_chave", []):
                for termo in extrair_termos(chave):
                    c[termo] += PESO_PALAVRAS_CHAVE
            for termo in extrair_termos(item["resposta"]):
                c[termo] += PESO_RESPOSTA
            contagens.append(c)

        # 2) IDF: termos raros pesam mais que termos que aparecem em todo item
        n = len(self.itens)
        df = Counter(t for c in contagens for t in c)
        self.idf = {t: math.log((n + 1) / (d + 1)) + 1 for t, d in df.items()}

        # 3) vetor TF-IDF de cada item e sua norma (para o cosseno)
        self.vetores = [{t: q * self.idf[t] for t, q in c.items()} for c in contagens]
        self.normas = [math.sqrt(sum(v * v for v in vet.values())) or 1.0 for vet in self.vetores]

    def buscar(self, pergunta: str, limite: int = 3) -> list[Resultado]:
        termos = Counter(extrair_termos(pergunta))
        consulta = {t: q * self.idf[t] for t, q in termos.items() if t in self.idf}
        if not consulta:
            return []
        norma_consulta = math.sqrt(sum(v * v for v in consulta.values()))

        resultados = []
        for item, vetor, norma in zip(self.itens, self.vetores, self.normas):
            produto = sum(v * vetor.get(t, 0.0) for t, v in consulta.items())
            score = produto / (norma * norma_consulta)
            if score > 0:
                resultados.append(Resultado(item["id"], item["modulo"], item["pergunta"], item["resposta"], round(score, 4)))
        resultados.sort(key=lambda r: r.score, reverse=True)
        return resultados[:limite]


# Perguntas que pedem DADOS do sistema ("quantos...", "liste...") não são dúvidas
# de uso. O FAQ não sabe respondê-las, então é melhor recusar do que arriscar.
INICIOS_DE_PEDIDO_DE_DADOS = {"quantos", "quantas", "quanto", "liste", "listar", "lista", "mostre", "mostrar", "exiba"}


def pede_dados_do_sistema(pergunta: str) -> bool:
    palavras = normalizar(pergunta).split()
    return bool(palavras) and (palavras[0] in INICIOS_DE_PEDIDO_DE_DADOS or "eu tenho" in normalizar(pergunta))
