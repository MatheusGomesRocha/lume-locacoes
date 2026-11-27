"""Orquestra os 3 Agents e guarda o resultado para o Master decidir. Nada entra no catálogo sem a decisão dele."""
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from evolucao import checagens, relatorio
from evolucao.agentes import Analista, Construtor, ErroAgente, Tester
from evolucao.consulta import sem_acento

PASTA = Path(os.getenv("IA_PASTA_EVOLUCAO", Path(__file__).resolve().parent.parent / "data" / "evolucao"))


class ErroDecisao(Exception):
    pass


def ler_sem_resposta(caminho: Path, limite: int = 40) -> list[dict]:
    """O JSONL que a API já grava, agrupado por pergunta (sem diferenciar acento, caixa ou pontuação) e do mais frequente ao menos."""
    if not Path(caminho).exists():
        return []
    contagem: Counter = Counter()
    original: dict[str, dict] = {}
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linha)
        except json.JSONDecodeError:
            continue
        q = str(d.get("pergunta", "")).strip()
        if len(q) < 4:
            continue
        chave = " ".join(sem_acento(q).replace("?", " ").split())
        contagem[chave] += 1
        original.setdefault(chave, {"pergunta": q[:300], "tipo": d.get("tipo", "faq")})
    return [{**original[k], "vezes": n} for k, n in contagem.most_common(limite)]


class Repositorio:
    """Propostas pendentes/decididas e o catálogo aprovado, em JSON (simples de ler e de auditar)."""

    def __init__(self, pasta: Path | None = None):
        self.pasta = Path(pasta or PASTA)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def _ler(self, nome: str) -> list[dict]:
        f = self.pasta / nome
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def _gravar(self, nome: str, dados: list[dict]) -> None:
        (self.pasta / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")

    def propostas(self) -> list[dict]:
        return self._ler("propostas.json")

    def catalogo(self, so_ativas: bool = True) -> list[dict]:
        return [e for e in self._ler("catalogo.json") if e["ativa"] or not so_ativas]

    def specs_ativas(self) -> list[dict]:
        return [e["spec"] for e in self.catalogo()]

    def proximo_id(self) -> str:
        return f"EV-{len(self.propostas()) + 1:04d}"

    def salvar(self, rel: dict) -> None:
        todas = self.propostas()
        todas.append(rel)
        self._gravar("propostas.json", todas)

    def obter(self, id_: str) -> dict:
        for r in self.propostas():
            if r["id"] == id_:
                return r
        raise ErroDecisao(f"proposta {id_} não existe")

    def decidir(self, id_: str, aprovar: bool, por: str, agora=datetime.now) -> dict:
        if not por.strip():
            raise ErroDecisao("diga quem está decidindo")
        todas = self.propostas()
        rel = next((r for r in todas if r["id"] == id_), None)
        if rel is None:
            raise ErroDecisao(f"proposta {id_} não existe")
        if rel["status"] != "pendente":
            raise ErroDecisao(f"{id_} já foi decidida ({rel['status']})")
        if aprovar:
            if not rel.get("pacote"):
                raise ErroDecisao("não há consulta para aprovar: este item é só registro")
            if rel["veredito"] == "reprovar_recomendado":
                raise ErroDecisao("o Tester encontrou bloqueios ou testes que falharam: reprove ou peça uma nova construção")
            achados = checagens.checar_spec(rel["pacote"]["spec"], rel["proposta"], self.specs_ativas())  # refaz as checagens: o arquivo pode ter sido mexido
            if checagens.tem_bloqueio(achados):
                raise ErroDecisao("as checagens fixas, refeitas agora, encontraram bloqueios: " + "; ".join(a["mensagem"] for a in achados if a["gravidade"] == "bloqueio"))
        rel["status"] = "aprovada" if aprovar else "reprovada"
        rel["decisao"] = {"por": por.strip(), "em": agora().isoformat(timespec="seconds")}
        self._gravar("propostas.json", todas)
        if aprovar:
            cat = self._ler("catalogo.json")
            cat.append({"id": id_, "spec": rel["pacote"]["spec"], "ativa": True, "aprovada_por": por.strip(), "aprovada_em": rel["decisao"]["em"], "selo": rel["avaliacao"]["selo"]})
            self._gravar("catalogo.json", cat)
        return rel

    def desativar(self, nome: str, por: str, agora=datetime.now) -> dict:
        cat = self._ler("catalogo.json")
        item = next((e for e in cat if e["spec"]["nome"] == nome and e["ativa"]), None)
        if item is None:
            raise ErroDecisao(f"não há consulta ativa chamada {nome}")
        item.update(ativa=False, desativada_por=por.strip(), desativada_em=agora().isoformat(timespec="seconds"))
        self._gravar("catalogo.json", cat)
        return item


def consulta_equivalente(prop: dict, catalogo: list[dict]) -> dict | None:
    """A consulta aprovada que já faz o que esta proposta pede (mesma entidade, operação, campos filtrados e, em listar, saída coberta)?"""
    forma = lambda f: {(x.get("campo"), x.get("op")) for x in (f or [])}  # noqa: E731
    for s in catalogo:
        if (s.get("entidade") == prop.get("entidade") and s.get("operacao") == prop.get("operacao") and forma(s.get("filtros")) == forma(prop.get("filtros"))
                and (s.get("campo_soma") or None) == (prop.get("campo_soma") or None) and set(prop.get("saida") or []) <= set(s.get("saida") or [])):
            return s
    return None


def gerar_relatorios(provedor, limitador, perguntas: list[dict], catalogo: list[dict], proximo_id, ignoradas: list[dict] | None = None) -> list[dict]:
    """Roda Agent 1 -> 2 -> 3 sem guardar nada: quem chama decide onde ficam os relatórios. `proximo_id(i)` dá o id do i-ésimo.
    Proposta que repete uma consulta já aprovada (mesma forma, ou o mesmo nome) não vira relatório: vai para `ignoradas`."""
    relatorios = []
    for i, prop in enumerate(Analista(provedor, limitador).propor(perguntas, catalogo)):
        id_ = proximo_id(i)
        if prop["decisao"] == "criar_consulta" and (ja := consulta_equivalente(prop, catalogo)) and ignoradas is not None:
            ignoradas.extend({"pergunta": q, "motivo": f"já respondida pela consulta aprovada “{ja['nome']}”"} for q in prop.get("perguntas", []))
            continue
        pacote = avaliacao = None
        barrada = checagens.checar_proposta(prop)
        if prop["decisao"] == "criar_consulta" and checagens.tem_bloqueio(barrada):  # proposta ruim não chega ao Construtor
            avaliacao = Tester._sem_execucao(barrada, "a proposta foi barrada antes de construir: o Construtor não foi chamado")
        elif prop["decisao"] == "criar_consulta":
            try:
                pacote = Construtor(provedor, limitador).construir(prop, catalogo)
                nome = pacote["spec"].get("nome")
                if ignoradas is not None and nome in checagens.nomes_ja_usados(catalogo):  # C01: o nome já é de uma consulta/ferramenta que existe
                    ignoradas.extend({"pergunta": q, "motivo": f"já existe a consulta “{nome}”"} for q in prop.get("perguntas", []))
                    continue
                avaliacao = Tester(provedor, limitador).avaliar(prop, pacote, catalogo)
            except ErroAgente as e:
                prop = {**prop, "decisao": "nao_suportado", "motivo": f"{prop.get('motivo', '')} (a construção falhou: {e})".strip()}
                pacote = avaliacao = None
        else:
            prop["achados"] = checagens.checar_proposta(prop)
        relatorios.append(relatorio.montar(id_, prop, pacote, avaliacao))
    return relatorios


def evoluir(provedor, limitador, perguntas: list[dict], repo: Repositorio) -> list[dict]:
    """Versão da linha de comando: guarda os relatórios no disco."""
    base = len(repo.propostas())
    relatorios = gerar_relatorios(provedor, limitador, perguntas, repo.specs_ativas(), lambda i: f"EV-{base + i + 1:04d}")
    for rel in relatorios:
        repo.salvar(rel)
    return relatorios
