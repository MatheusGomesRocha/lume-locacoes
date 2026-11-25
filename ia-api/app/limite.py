"""Limite de requisições por visitante (janela deslizante, em memória).

A API do GitHub Pages é pública. Sem limite, qualquer um poderia martelar o servidor.
"""
import threading
import time
from collections import defaultdict, deque


class LimitadorDeRequisicoes:
    def __init__(self, maximo: int, janela_segundos: float = 60.0, relogio=time.monotonic):
        self.maximo = maximo
        self.janela = janela_segundos
        self._relogio = relogio
        self._registros: dict[str, deque] = defaultdict(deque)
        self._trava = threading.Lock()

    def permitir(self, chave: str) -> bool:
        """True se a chave ainda pode fazer uma requisição agora (e já a contabiliza)."""
        if self.maximo <= 0:  # 0 desliga o limite
            return True
        agora = self._relogio()
        with self._trava:
            if len(self._registros) > 5000:
                self._purgar(agora)
            fila = self._registros[chave]
            while fila and agora - fila[0] >= self.janela:
                fila.popleft()
            if len(fila) >= self.maximo:
                return False
            fila.append(agora)
            return True

    def _purgar(self, agora: float) -> None:
        """Remove quem não faz requisições há mais tempo que a janela."""
        for chave in [c for c, f in self._registros.items() if not f or agora - f[-1] >= self.janela]:
            del self._registros[chave]

    def limpar(self) -> None:
        with self._trava:
            self._registros.clear()
