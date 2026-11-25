"""Testes do limitador de requisições (com relógio falso, sem esperar de verdade)."""
from app.limite import LimitadorDeRequisicoes


class Relogio:
    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora


def test_permite_ate_o_maximo_e_bloqueia_o_excedente():
    lim = LimitadorDeRequisicoes(3, 60, Relogio())
    assert [lim.permitir("a") for _ in range(5)] == [True, True, True, False, False]


def test_libera_depois_da_janela():
    r = Relogio()
    lim = LimitadorDeRequisicoes(2, 60, r)
    assert lim.permitir("a") and lim.permitir("a") and not lim.permitir("a")
    r.agora += 61
    assert lim.permitir("a") is True


def test_visitantes_diferentes_nao_se_afetam():
    lim = LimitadorDeRequisicoes(1, 60, Relogio())
    assert lim.permitir("a") is True
    assert lim.permitir("a") is False
    assert lim.permitir("b") is True


def test_maximo_zero_desliga_o_limite():
    lim = LimitadorDeRequisicoes(0, 60, Relogio())
    assert all(lim.permitir("a") for _ in range(100))


def test_limpar_zera_a_contagem():
    lim = LimitadorDeRequisicoes(1, 60, Relogio())
    lim.permitir("a")
    assert lim.permitir("a") is False
    lim.limpar()
    assert lim.permitir("a") is True


def test_purga_remove_visitantes_antigos():
    r = Relogio()
    lim = LimitadorDeRequisicoes(5, 60, r)
    for i in range(5001):
        lim.permitir(f"ip{i}")
    r.agora += 120
    lim.permitir("novo")  # dispara a purga (mais de 5000 chaves)
    assert len(lim._registros) == 1
