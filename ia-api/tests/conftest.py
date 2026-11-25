import pytest

from app import main


@pytest.fixture(autouse=True)
def isolar_ambiente(tmp_path, monkeypatch):
    """Cada teste usa um log temporário, sem token e com o limitador zerado."""
    monkeypatch.setenv("IA_LOG_SEM_RESPOSTA", str(tmp_path / "sem_resposta.jsonl"))
    monkeypatch.delenv("IA_API_TOKEN", raising=False)
    main.limitador.limpar()
    main.limitador.maximo = 1000
    yield
    main.limitador.limpar()


@pytest.fixture
def log_sem_resposta(tmp_path):
    return tmp_path / "sem_resposta.jsonl"
