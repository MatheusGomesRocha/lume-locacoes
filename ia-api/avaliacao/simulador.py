"""Faz o papel do front nas avaliações do agente: executa as consultas que ele pede e as gravações que ele confirmou,
contra um "banco" de brincadeira definido por cada caso. Assim a conversa inteira roda sem navegador e sem Laravel.

A conversa devolve uma transcrição (o que o usuário disse, o que o agente respondeu, o que consultou e o que gravou),
que é o que o pontuador exato e o juiz (LLM) avaliam.
"""
import unicodedata
from datetime import date

HOJE = "2026-11-25"


def _n(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn").strip()


def _casa(busca: str, nome: str) -> bool:
    """Mesma ideia do front: todas as palavras da busca aparecem no nome (sem acento, sem maiúsculas)."""
    alvo = _n(nome)
    return all(p in alvo for p in _n(busca).split())


class Loja:
    """Os dados do cenário e o que foi gravado nele."""

    def __init__(self, cenario: dict | None):
        c = cenario or {}
        self.clientes = [dict(x) for x in c.get("clientes", [])]
        self.produtos = [{"ativo": True, **x} for x in c.get("produtos", [])]
        self.sem_permissao = set(c.get("sem_permissao", []))
        self.orcamentos: list[dict] = []
        self.novos_clientes: list[dict] = []

    # ---- leitura (o que o front faz com as consultas) ----
    def consulta(self, chamada: dict):
        nome, a = chamada["nome"], chamada["args"]
        if nome == "localizar_clientes":
            if "clientes" in self.sem_permissao:
                return {"erro": "o usuário não tem permissão para ver estes dados"}
            return {"linhas": [{"id": c["id"], "nome": c["nome"], "cidade": c.get("cidade")} for c in self.clientes if _casa(a["busca"], c["nome"])][:6]}
        if nome == "localizar_produtos":
            if "produtos" in self.sem_permissao:
                return {"erro": "o usuário não tem permissão para ver estes dados"}
            return {"itens": [{"busca": b, "linhas": [{"id": p["id"], "nome": p["nome"], "valor_diaria": p["valor_diaria"]} for p in self.produtos if p["ativo"] and _casa(b, p["nome"])][:6]} for b in a["buscas"]]}
        if nome == "verificar_disponibilidade":
            faltas = []
            for i in a["itens"]:
                p = next((x for x in self.produtos if x["id"] == i["produto_id"]), None)
                if p and i["quantidade"] > p.get("quantidade", 10**6):
                    faltas.append({"produto": p["nome"], "solicitado": i["quantidade"], "disponivel": p["quantidade"]})
            return {"faltas": faltas}
        return {"erro": "consulta desconhecida"}

    # ---- escrita (só chega aqui o que o agente devolveu em `executar`, depois do "sim") ----
    def gravar(self, executar: list[dict]) -> list[str]:
        feito = []
        novo_id = None
        for g in executar:
            a = g["args"]
            if g["nome"] == "criar_cliente":
                novo_id = max([c["id"] for c in self.clientes] + [0]) + 1
                self.clientes.append({"id": novo_id, "nome": a["nome"], "cidade": a.get("cidade")})
                self.novos_clientes.append(a)
                feito.append("criar_cliente")
            elif g["nome"] == "criar_orcamento":
                cid = novo_id if a.get("cliente_novo") else a["cliente_id"]
                assert any(c["id"] == cid for c in self.clientes), "orçamento com cliente inexistente"
                n = max(1, (date.fromisoformat(a["data_devolucao"]) - date.fromisoformat(a["data_retirada"])).days)
                bruto = sum(round(next(p for p in self.produtos if p["id"] == i["produto_id"])["valor_diaria"] * 100) * i["quantidade"] for i in a["itens"]) * n
                self.orcamentos.append({"cliente_id": cid, "evento": a["evento"], "diarias": n, "total": max(0, bruto - round(a.get("desconto", 0) * 100)) / 100, "itens": a["itens"], "status": "rascunho"})
                feito.append("criar_orcamento")
        return feito


def conversar(caso: dict, enviar, hoje: str = HOJE) -> dict:
    """Roda os turnos do caso. `enviar(corpo, caso_ou_none) -> resposta` fala com a API (o caso só vai no 1º envio de cada pergunta, para a decisão simulada)."""
    loja = Loja(caso.get("cenario"))
    estado = None
    transcricao = []
    for turno in caso["turnos"]:
        corpo = {"pergunta": turno["usuario"], "hoje": hoje}
        if estado:
            corpo["agente"] = estado
        resp = enviar(corpo, caso if not estado else None)
        consultadas = []
        for _ in range(4):  # a mesma pergunta é reenviada com os resultados, como o front faz
            if not resp.get("consultas"):
                break
            resultados = [{"nome": c["nome"], "args": c["args"], "resultado": loja.consulta(c)} for c in resp["consultas"][:3]]
            consultadas += [c["nome"] for c in resp["consultas"][:3]]
            corpo = {**corpo, "resultados": resultados}
            if resp.get("agente"):
                corpo["agente"] = resp["agente"]
            resp = enviar(corpo, None)
        estado = resp.get("agente")
        executar = resp.get("executar") or []
        transcricao.append({
            "usuario": turno["usuario"], "agente": resp.get("resposta", ""), "opcoes": resp.get("opcoes", []), "consultas": consultadas,
            "acoes": [x["nome"] for x in resp.get("acoes", [])], "fonte": (resp.get("fonte") or {}).get("id"),
            "pediu_gravar": [x["nome"] for x in executar], "gravou": loja.gravar(executar) if executar else [],
        })
    return {"transcricao": transcricao, "orcamentos": loja.orcamentos, "clientes_novos": loja.novos_clientes}
