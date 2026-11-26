"""Busca semântica (embeddings): acha a pergunta certa mesmo quando as palavras são outras.

O TF-IDF (app/busca.py) compara palavras: "como adicionar uma pessoa no sistema" não casa com
"Como cadastrar um usuário?". Um embedding transforma o texto num vetor de números em que frases
de sentido parecido ficam perto, então a comparação passa a ser por significado.

Desenho (busca híbrida):
  - o TF-IDF continua sendo a primeira tentativa: é de graça, instantâneo e não depende de rede;
  - só quando ele não tem certeza (nota baixa) a pergunta é transformada em vetor e comparada com o FAQ;
  - o resultado semântico só vale se a nota passar do limite E se vencer o segundo lugar por uma margem,
    para "capital da França" não virar "como excluir um produto" por acaso;
  - sem chave, sem cota ou com erro de rede, tudo segue só com o TF-IDF.
Os vetores do FAQ são calculados uma vez, em segundo plano, quando a API sobe (1 chamada em lote).
"""
import hashlib
import logging
import math
import os
import threading
from typing import Protocol

import httpx

log = logging.getLogger("lume.semantica")

URL_EMBEDDING = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:{metodo}"
MODELO_PADRAO = "gemini-embedding-001"
DIMENSOES = 256  # vetores curtos bastam para ~50 frases e deixam a comparação instantânea

# Abaixo da nota do TF-IDF indicada aqui, vale a pena perguntar ao embedding.
NOTA_LEXICAL_CONFIANTE = float(os.getenv("IA_SEMANTICA_SE_LEXICAL_ABAIXO", "0.45"))
LIMITE_SEMANTICO = float(os.getenv("IA_LIMITE_SEMANTICO", "0.78"))
MARGEM_SEMANTICA = float(os.getenv("IA_MARGEM_SEMANTICA", "0.03"))
MAX_CONSULTAS_EM_MEMORIA = 500


class ErroEmbedding(Exception):
    """Qualquer falha ao obter vetores. Quem chama segue só com o TF-IDF."""


class Embedder(Protocol):
    def documentos(self, textos: list[str]) -> list[list[float]]: ...
    def consulta(self, texto: str) -> list[float]: ...


class EmbedderGemini:
    def __init__(self, chave: str, modelo: str = MODELO_PADRAO, cliente: httpx.Client | None = None, tempo_limite: float = 10.0):
        self.chave = chave
        self.modelo = modelo
        self._cliente = cliente or httpx.Client(timeout=tempo_limite)

    def _pedido(self, texto: str, tarefa: str) -> dict:
        return {"model": f"models/{self.modelo}", "content": {"parts": [{"text": texto}]},
                "taskType": tarefa, "outputDimensionality": DIMENSOES}

    def _post(self, metodo: str, corpo: dict) -> dict:
        try:
            r = self._cliente.post(URL_EMBEDDING.format(modelo=self.modelo, metodo=metodo), json=corpo, headers={"x-goog-api-key": self.chave})
        except httpx.HTTPError as e:
            raise ErroEmbedding(f"falha de rede: {type(e).__name__}") from e
        if r.status_code != 200:
            raise ErroEmbedding(f"o provedor respondeu {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise ErroEmbedding("resposta em formato inesperado") from e

    def documentos(self, textos: list[str]) -> list[list[float]]:
        corpo = {"requests": [self._pedido(t, "RETRIEVAL_DOCUMENT") for t in textos]}
        try:
            return [list(map(float, e["values"])) for e in self._post("batchEmbedContents", corpo)["embeddings"]]
        except (KeyError, TypeError, ValueError) as e:
            raise ErroEmbedding("resposta em formato inesperado") from e

    def consulta(self, texto: str) -> list[float]:
        try:
            return list(map(float, self._post("embedContent", self._pedido(texto, "RETRIEVAL_QUERY"))["embedding"]["values"]))
        except (KeyError, TypeError, ValueError) as e:
            raise ErroEmbedding("resposta em formato inesperado") from e


def cosseno(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def texto_do_item(item: dict) -> str:
    """O que representa o item no índice: a pergunta e as formas alternativas de perguntar."""
    return item["pergunta"] + ". " + "; ".join(item.get("palavras_chave", []))


class IndiceSemantico:
    def __init__(self, itens: list[dict], embedder: Embedder, permitir=lambda: True):
        self.itens = itens
        self.embedder = embedder
        self._permitir = permitir  # teto diário compartilhado com o LLM
        self._vetores: list[list[float]] | None = None
        self._consultas: dict[str, list[float]] = {}
        self._trava = threading.Lock()
        self.erro: str | None = None

    @property
    def pronto(self) -> bool:
        return self._vetores is not None

    def construir(self) -> bool:
        """Calcula os vetores do FAQ (1 chamada em lote). False = falhou; a API segue sem semântica."""
        try:
            vetores = self.embedder.documentos([texto_do_item(i) for i in self.itens])
            if len(vetores) != len(self.itens):
                raise ErroEmbedding("quantidade de vetores diferente da de itens")
        except ErroEmbedding as e:
            self.erro = str(e)
            log.warning("índice semântico indisponível (%s); seguindo só com TF-IDF", e)
            return False
        self._vetores = vetores
        self.erro = None
        return True

    def construir_em_segundo_plano(self) -> None:
        threading.Thread(target=self.construir, name="indice-semantico", daemon=True).start()

    def _vetor_da_consulta(self, pergunta: str) -> list[float] | None:
        chave = hashlib.sha256(pergunta.strip().lower().encode()).hexdigest()
        with self._trava:
            if chave in self._consultas:
                return self._consultas[chave]
        if not self._permitir():
            return None
        try:
            vetor = self.embedder.consulta(pergunta)
        except ErroEmbedding as e:
            log.warning("embedding da pergunta falhou (%s)", e)
            return None
        with self._trava:
            if len(self._consultas) >= MAX_CONSULTAS_EM_MEMORIA:
                self._consultas.pop(next(iter(self._consultas)))
            self._consultas[chave] = vetor
        return vetor

    def buscar(self, pergunta: str, limite: int = 4) -> list[tuple[dict, float]]:
        """[(item, cosseno)] do mais parecido para o menos; vazio se o índice não está pronto ou a consulta falhou."""
        if self._vetores is None:
            return []
        vetor = self._vetor_da_consulta(pergunta)
        if vetor is None:
            return []
        notas = sorted(((item, cosseno(vetor, v)) for item, v in zip(self.itens, self._vetores)), key=lambda x: x[1], reverse=True)
        return notas[:limite]


def vencedor_confiavel(notas: list[tuple[dict, float]]) -> bool:
    """O primeiro lugar passa do limite e abre vantagem sobre o segundo?"""
    if not notas or notas[0][1] < LIMITE_SEMANTICO:
        return False
    return len(notas) == 1 or notas[0][1] - notas[1][1] >= MARGEM_SEMANTICA


def criar_indice_do_ambiente(itens: list[dict], permitir=lambda: True) -> IndiceSemantico | None:
    """Liga a busca semântica se houver GEMINI_API_KEY (e IA_SEMANTICA != 0)."""
    chave = os.getenv("GEMINI_API_KEY", "").strip()
    if not chave or os.getenv("IA_SEMANTICA", "1") == "0":
        return None
    return IndiceSemantico(itens, EmbedderGemini(chave, os.getenv("IA_EMBEDDING_MODELO", MODELO_PADRAO).strip() or MODELO_PADRAO), permitir)
