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
from dataclasses import dataclass, field
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


# Assunto de cada módulo, em termos já normalizados (raiz). Serve para saber se a pergunta
# já diz de que coisa se está falando ("produtos", "clientes") ou se só traz a ação ("excluir").
ASSUNTOS = {
    "Produtos": {raiz("produto"), raiz("catalogo")},
    "Clientes": {raiz("cliente")},
    "Orçamentos": {raiz("orcamento")},
    "Financeiro": {raiz("pagamento"), raiz("financeiro")},
    "Painel": {raiz("painel"), raiz("dashboard")},
    "Acesso": {raiz("usuario"), raiz("grupo"), raiz("permissao"), raiz("senha"), raiz("login")},
}
TODOS_OS_ASSUNTOS = set().union(*ASSUNTOS.values())

PESO_PERGUNTA_ANTERIOR = 0.6  # a pergunta anterior ajuda, mas a atual continua mandando
BONUS_MESMO_ASSUNTO = 1.15    # empurra respostas do mesmo módulo da conversa
MAX_TERMOS_PARA_CONTEXTO = 2  # perguntas com mais termos conhecidos que isso se bastam sozinhas


@dataclass
class Contexto:
    """O que veio antes na conversa. A API não guarda nada: o navegador manda isto a cada pergunta."""
    perguntas_anteriores: list[str] = field(default_factory=list)  # só o que o usuário escreveu, da mais antiga à mais nova
    ultimo_id: str | None = None  # id da última resposta que o assistente deu


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

    def _pontuar(self, consulta: dict[str, float], limite: int, assunto: str | None = None) -> list[Resultado]:
        """Cosseno entre a consulta (termo -> peso) e cada item. `assunto` dá um bônus ao módulo da conversa."""
        if not consulta:
            return []
        norma_consulta = math.sqrt(sum(v * v for v in consulta.values()))

        resultados = []
        for item, vetor, norma in zip(self.itens, self.vetores, self.normas):
            produto = sum(v * vetor.get(t, 0.0) for t, v in consulta.items())
            score = produto / (norma * norma_consulta)
            if score > 0 and assunto and item["modulo"] == assunto:
                score = min(1.0, score * BONUS_MESMO_ASSUNTO)
            if score > 0:
                resultados.append(Resultado(item["id"], item["modulo"], item["pergunta"], item["resposta"], round(score, 4)))
        resultados.sort(key=lambda r: r.score, reverse=True)
        return resultados[:limite]

    def _consulta(self, pergunta: str) -> dict[str, float]:
        termos = Counter(extrair_termos(pergunta))
        return {t: q * self.idf[t] for t, q in termos.items() if t in self.idf}

    def buscar(self, pergunta: str, limite: int = 3) -> list[Resultado]:
        return self._pontuar(self._consulta(pergunta), limite)

    def modulo_do_item(self, item_id: str | None) -> str | None:
        return next((i["modulo"] for i in self.itens if i["id"] == item_id), None)

    def _avaliar_contexto(self, pergunta: str, contexto: Contexto | None) -> tuple[dict[str, float], str | None, bool]:
        """Devolve (consulta, assunto da conversa, pergunta está incompleta?).

        "Incompleta" = poucos termos conhecidos e falta o assunto ("mas eu quero excluir") ou a ação
        ("e para clientes?"). Só nesse caso o que veio antes na conversa é usado.
        """
        consulta = self._consulta(pergunta)
        if contexto is None or not (contexto.perguntas_anteriores or contexto.ultimo_id):
            return consulta, None, False

        conhecidos = set(consulta)
        assuntos_citados = {m for m, termos in ASSUNTOS.items() if conhecidos & termos}
        tem_acao = bool(conhecidos - TODOS_OS_ASSUNTOS)
        incompleta = bool(conhecidos) and len(conhecidos) <= MAX_TERMOS_PARA_CONTEXTO and (not assuntos_citados or not tem_acao)
        if not incompleta:
            return consulta, None, False

        # Se a pergunta cita um assunto ("e para clientes?"), ele manda; senão vale o da última resposta.
        assunto = next(iter(assuntos_citados)) if len(assuntos_citados) == 1 else None
        if assunto is None and not assuntos_citados:
            assunto = self.modulo_do_item(contexto.ultimo_id)
        if assunto not in ASSUNTOS:
            assunto = None

        if contexto.perguntas_anteriores:
            for termo, qtd in Counter(extrair_termos(contexto.perguntas_anteriores[-1])).items():
                if termo not in self.idf or termo in consulta:
                    continue
                if assuntos_citados and termo in TODOS_OS_ASSUNTOS:
                    continue
                # A pergunta já traz a ação ("e para aprovar?"): falta só o assunto, então só ele vem da conversa.
                # Levar também a ação anterior ("criar") faria a pergunta antiga competir com a nova.
                if tem_acao and termo not in TODOS_OS_ASSUNTOS:
                    continue
                consulta[termo] = qtd * self.idf[termo] * PESO_PERGUNTA_ANTERIOR
        return consulta, assunto, True

    def assunto_da_conversa(self, pergunta: str, contexto: Contexto | None) -> str | None:
        """Módulo de que a conversa está tratando, quando a pergunta depende do contexto; senão None."""
        _, assunto, incompleta = self._avaliar_contexto(pergunta, contexto)
        return assunto if incompleta else None

    def buscar_com_contexto(self, pergunta: str, contexto: Contexto | None, limite: int = 3) -> tuple[list[Resultado], bool]:
        """Busca levando a conversa em conta. Devolve (resultados, o contexto mudou a melhor resposta?).

        Só entra em ação quando a pergunta está incompleta (ver `_avaliar_contexto`): os termos da pergunta
        anterior entram com peso menor e respostas do módulo da conversa ganham um pequeno bônus.
        Pergunta completa ("como aprovar um orçamento?") nunca é alterada pelo que veio antes.
        """
        sem_contexto = self.buscar(pergunta, limite)
        consulta, assunto, incompleta = self._avaliar_contexto(pergunta, contexto)
        if not incompleta:
            return sem_contexto, False
        com_contexto = self._pontuar(consulta, limite, assunto)
        mudou = bool(com_contexto) and (not sem_contexto or com_contexto[0].id != sem_contexto[0].id)
        return com_contexto, mudou


# Perguntas que pedem DADOS do sistema ("quantos...", "liste...") não são dúvidas
# de uso. O FAQ não sabe respondê-las, então é melhor recusar do que arriscar.
INICIOS_DE_PEDIDO_DE_DADOS = {"quantos", "quantas", "quanto", "liste", "listar", "lista", "mostre", "mostrar", "exiba"}


def pede_dados_do_sistema(pergunta: str) -> bool:
    palavras = normalizar(pergunta).split()
    return bool(palavras) and (palavras[0] in INICIOS_DE_PEDIDO_DE_DADOS or "eu tenho" in normalizar(pergunta))
