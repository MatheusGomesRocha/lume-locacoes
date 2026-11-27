"""Impõe a regra: todo erro encontrado fica protegido nas quatro camadas, ou declara por que uma camada não se aplica, ou está aberto de propósito."""
import json
import re
from pathlib import Path

import pytest

from avaliacao import matriz_agentes
from evolucao import licoes

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = json.loads((RAIZ / "evolucao" / "erros_conhecidos.json").read_text(encoding="utf-8"))
CAMADAS = ("codigo", "checagem_fixa", "licao", "matriz")
ERROS = REGISTRO["erros"]


def _resolve(ref: dict) -> str | None:
    """None quando a referência existe de verdade; senão, o motivo."""
    if "teste" in ref:
        arquivo, _, nome = ref["teste"].partition("::")
        caminho = RAIZ / arquivo
        if not caminho.exists():
            return f"arquivo não existe: {arquivo}"
        return None if re.search(rf"def {re.escape(nome)}\b", caminho.read_text(encoding="utf-8")) else f"teste não existe: {ref['teste']}"
    if "arquivo" in ref:
        return None if (RAIZ / ref["arquivo"]).exists() else f"arquivo não existe: {ref['arquivo']}"
    if "checagem" in ref:
        fonte = "".join((RAIZ / "evolucao" / n).read_text(encoding="utf-8") for n in ("checagens.py", "agentes.py", "relatorio.py"))
        return None if f'"{ref["checagem"]}"' in fonte else f"checagem não existe: {ref['checagem']}"
    if "licao" in ref:
        ids = {x["id"] for x in json.loads((RAIZ / "evolucao" / "licoes.json").read_text(encoding="utf-8"))}
        return None if ref["licao"] in ids else f"lição não existe: {ref['licao']}"
    if "matriz" in ref:
        return None if any(ref["matriz"] in nome for nome, _ in matriz_agentes.casos()) else f"nenhum caso da matriz tem “{ref['matriz']}”"
    return f"referência desconhecida: {ref}"


def test_ids_unicos_e_status_validos():
    ids = [e["id"] for e in ERROS]
    assert len(ids) == len(set(ids))
    assert all(e["status"] in ("fechado", "aberto") for e in ERROS)


@pytest.mark.parametrize("erro", ERROS, ids=lambda e: e["id"])
def test_cada_erro_declara_as_quatro_camadas_com_referencia_que_existe(erro):
    assert set(erro["camadas"]) == set(CAMADAS), "faltou declarar uma das quatro camadas"
    for nome in CAMADAS:
        c = erro["camadas"][nome]
        if "nao_se_aplica" in c:
            assert len(c["nao_se_aplica"].strip()) >= 15, f"{nome}: explique por que não se aplica"
        elif "lacuna" in c:
            assert erro["status"] == "aberto", f"{nome}: erro fechado não pode ter lacuna ({c['lacuna']})"
        else:
            motivo = _resolve(c)
            assert motivo is None, f"{nome}: {motivo}"


def test_so_os_erros_declarados_abertos_tem_lacuna():
    for e in ERROS:
        tem = any("lacuna" in c for c in e["camadas"].values())
        assert tem == (e["status"] == "aberto"), f"{e['id']}: status e lacunas não combinam"


def test_toda_checagem_fixa_e_toda_licao_tem_um_erro_de_origem_ou_e_antiga():
    """As checagens C14 e C15 e as lições L08 e L09 nasceram de erros registrados: se alguém apagar o registro, o teste avisa."""
    usados = {tuple(c.values())[0] for e in ERROS for c in e["camadas"].values() if "checagem" in c or "licao" in c}
    for esperado in ("C14", "C15", "L08-periodo-ate-depois-de-de", "L09-tipo-da-pergunta"):
        assert esperado in usados
