"""Cache das respostas do modelo, para não pagar (nem esperar) duas vezes pela mesma conversa.

O que entra: a resposta de ajuda redigida a partir do FAQ e a decisão de ferramenta (qual consulta/ação o modelo pediu).
O que NUNCA entra: respostas montadas com dados do sistema (os números mudam) e falhas do modelo.
A chave inclui a pergunta, o contexto da conversa e uma "versão" (FAQ + instruções + ferramentas): se qualquer um deles
mudar, as respostas antigas deixam de valer sozinhas.
Fica na memória do processo (some quando o servidor reinicia, o que no plano gratuito do Render acontece com frequência).
"""
import hashlib
import threading
import time
import unicodedata
from collections import OrderedDict
from typing import Any, Callable


def normalizar_texto(t: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.split()).strip(" ?!.,;:")


def versao_do_conteudo(*partes: str) -> str:
    h = hashlib.sha1()
    for p in partes:
        h.update(p.encode("utf-8"))
    return h.hexdigest()[:12]


def chave_da_conversa(tipo: str, versao: str, pergunta: str, historico: list[str], ultimo_id: str | None, extra: str = "") -> str:
    contexto = "|".join(normalizar_texto(h) for h in historico[-3:])
    return "\x1f".join([tipo, versao, normalizar_texto(pergunta), contexto, ultimo_id or "", extra])


class CacheDeRespostas:
    def __init__(self, maximo: int = 500, ttl: float = 86_400, agora: Callable[[], float] = time.monotonic):
        self.maximo, self.ttl, self._agora = maximo, ttl, agora
        self._itens: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._trava = threading.Lock()
        self.acertos = 0
        self.erros = 0

    @property
    def ativo(self) -> bool:
        return self.maximo > 0 and self.ttl > 0

    def obter(self, chave: str) -> Any | None:
        if not self.ativo:
            return None
        with self._trava:
            item = self._itens.get(chave)
            if item is None or self._agora() - item[0] > self.ttl:
                self._itens.pop(chave, None)
                self.erros += 1
                return None
            self._itens.move_to_end(chave)
            self.acertos += 1
            return item[1]

    def guardar(self, chave: str, valor: Any) -> None:
        if not self.ativo or valor is None:
            return
        with self._trava:
            self._itens[chave] = (self._agora(), valor)
            self._itens.move_to_end(chave)
            while len(self._itens) > self.maximo:
                self._itens.popitem(last=False)

    def limpar(self) -> None:
        with self._trava:
            self._itens.clear()

    def estatisticas(self) -> dict:
        total = self.acertos + self.erros
        return {"ativo": self.ativo, "itens": len(self._itens), "acertos": self.acertos, "erros": self.erros,
                "taxa_de_acerto": round(self.acertos / total, 3) if total else None}


def cache_do_ambiente(env: dict | None = None) -> CacheDeRespostas:
    import os

    e = env if env is not None else os.environ

    def numero(nome: str, padrao: float) -> float:
        try:
            return float(e.get(nome, padrao))
        except ValueError:
            return padrao

    return CacheDeRespostas(int(numero("IA_CACHE_MAX", 500)), numero("IA_CACHE_TTL", 86_400))
