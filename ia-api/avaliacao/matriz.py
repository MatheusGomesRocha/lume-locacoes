"""Matriz de perguntas gerada a partir do ESQUEMA: entidade x campo x tipo de resposta.

Em vez de depender de alguém lembrar de testar "usuários por cidade" ou "clientes dos últimos 15 dias", o código gera as perguntas
e sabe a resposta certa de cada uma:

  impossivel   o sistema não guarda o dado -> a Lumi diz isso na hora (e a pergunta NUNCA vai para os Agents)
  possivel     o dado existe -> não pode ser tratada como impossível
  consulta     já existe consulta aprovada -> a mesma pergunta com outro período usa ela (só muda o parâmetro)
  nao_consulta uma consulta aprovada de OUTRA entidade não pode responder esta pergunta

Os casos "impossivel" e "consulta" não gastam o modelo (a API responde por código), então rodam também contra a API publicada.

  python -m avaliacao.matriz                         # em processo
  python -m avaliacao.matriz --url https://lume-ia.onrender.com [--token X] [--md matriz.md] [--json casos.json]
"""
import argparse
import json
import sys
import urllib.request

from app.impossivel import ATRIBUTOS, ENTIDADES, pergunta_impossivel
from evolucao.esquema import ESQUEMA

HOJE = "2026-11-26"
FRASE_DO_CONCEITO = {
    "localizacao": "moram em Fortaleza", "idade": "têm mais de 30 anos de idade", "genero": "são mulheres", "cargo": "têm cargo de gerente",
    "autoria": "foram criados por Bruno", "acesso": "tiveram o último acesso ontem", "especificacao": "têm a marca Samsung", "imagem": "têm foto",
}
VERBO_DE_CRIACAO = {"clientes": "cadastrados", "produtos": "cadastrados", "usuarios": "cadastrados", "orcamentos": "criados", "pagamentos": "criadas", "grupos": "criados"}
JANELAS = [("nos últimos 15 dias", 15), ("nos últimos 30 dias", 30), ("nas últimas 2 semanas", 14), ("hoje", 0), ("no último mês", 30), ("nos últimos 3 dias", 3)]


def _spec_de_janela(e: str) -> dict:
    nome, verbo = ENTIDADES[e][1], VERBO_DE_CRIACAO[e]
    spec = {
        "nome": f"{e}_recentes", "descricao": f"Conta {nome} {verbo} nos últimos dias", "entidade": e, "operacao": "contar", "permissao": ESQUEMA[e]["permissao"], "saida": [],
        "exemplos": [f"Quantos {nome} {verbo} nos últimos 7 dias existem no sistema?", f"Quantos {nome} {verbo} nos últimos 30 dias?", f"{nome.capitalize()} {verbo} hoje"],
        "palavras_chave": [e, verbo], "sinonimos": {}, "parametros": {"dias": {"tipo": "numero", "obrigatorio": True}},
        "filtros": [{"campo": "criado_em", "op": "ultimos_dias", "parametro": "dias"}],
    }
    if ESQUEMA[e]["so_admin"]:
        spec["papel_minimo"] = "admin"
    return spec


def gerar_casos() -> list[dict]:
    casos = []
    # 1) dado que o sistema não guarda
    for e in ESQUEMA:
        for conceito, (rotulo, _, quem) in ATRIBUTOS.items():
            if e in quem:
                casos.append({"grupo": "possivel", "pergunta": f"Quantos {ENTIDADES[e][1]} {FRASE_DO_CONCEITO[conceito]}?", "esperado": {"impossivel": False}, "so_local": True})
            else:
                casos.append({"grupo": "impossivel", "pergunta": f"Quantos {ENTIDADES[e][1]} {FRASE_DO_CONCEITO[conceito]}?", "esperado": {"impossivel": True}})
    # 2) o que o esquema guarda nunca é "impossível"
    for e, d in ESQUEMA.items():
        for campo, c in d["campos"].items():
            if c["nivel"] == "normal":
                casos.append({"grupo": "possivel", "pergunta": f"Quantos {ENTIDADES[e][1]} por {c['rotulo'].lower()}?", "esperado": {"impossivel": False}, "so_local": True})
    # 3) mesma consulta, outro período; e consulta de outra entidade não responde esta
    com_data = [e for e, d in ESQUEMA.items() if "criado_em" in d["campos"]]
    for e in com_data:
        spec, nome, verbo = _spec_de_janela(e), ENTIDADES[e][1], VERBO_DE_CRIACAO[e]
        for frase, dias in JANELAS:
            casos.append({"grupo": "consulta", "pergunta": f"Quantos {nome} foram {verbo} {frase}?", "catalogo": [spec],
                          "esperado": {"consulta": {"nome": spec["nome"], "params": {"dias": dias}}}})
        for o in com_data:
            if o != e:
                casos.append({"grupo": "nao_consulta", "pergunta": f"Quantos {ENTIDADES[o][1]} foram {VERBO_DE_CRIACAO[o]} nos últimos 15 dias?", "catalogo": [spec],
                              "esperado": {"nao_consulta": spec["nome"]}, "so_local": True})
    for i, c in enumerate(casos, 1):
        c["id"] = f"M{i:03d}"
    return casos


def conferir(caso: dict, r: dict) -> str | None:
    """None se a resposta está certa; senão, o que deu errado."""
    esp = caso["esperado"]
    if "impossivel" in esp:
        return None if bool(r.get("impossivel")) == esp["impossivel"] else f"impossivel={r.get('impossivel')!r}, esperado {esp['impossivel']}"
    if "consulta" in esp:
        achou = ((r.get("consultas") or [{}])[0]).get("args")
        return None if achou == esp["consulta"] else f"veio {achou}, esperado {esp['consulta']}"
    if "nao_consulta" in esp:
        usou = [c["args"].get("nome") for c in (r.get("consultas") or []) if c.get("nome") == "catalogo"]
        return None if esp["nao_consulta"] not in usou else f"respondeu com a consulta {esp['nao_consulta']}, de outra entidade"
    return "caso sem esperado"


def _local(c: dict) -> dict:
    """Casos que na API passariam pelo modelo (e gastariam cota): aqui só a parte de código, direto."""
    if "impossivel" in c["esperado"]:
        return {"impossivel": bool(pergunta_impossivel(c["pergunta"]))}
    from app.main import specs_validas
    from evolucao.consulta import buscar_consulta
    spec = buscar_consulta(c["pergunta"], specs_validas(c.get("catalogo", [])))
    return {"consultas": [{"nome": "catalogo", "args": {"nome": spec["nome"]}}]} if spec else {}


def rodar(enviar, incluir_local: bool = True) -> list[dict]:
    """enviar(payload) -> resposta do /chat. incluir_local=False pula os casos que dependeriam do modelo (rodar contra a API publicada)."""
    saida = []
    for c in gerar_casos():
        if c.get("so_local") and not incluir_local:
            continue
        r = _local(c) if c.get("so_local") else enviar({"pergunta": c["pergunta"], "catalogo": c.get("catalogo", []), "hoje": HOJE})
        saida.append({**c, "erro": conferir(c, r)})
    return saida


def em_processo():
    from fastapi.testclient import TestClient
    from app import main
    main.limitador.maximo = 10**9  # a API limita a 30 perguntas por minuto por visitante; a matriz tem mais que isso
    cliente = TestClient(main.app)
    return lambda payload: cliente.post("/chat", json=payload).json()


def por_http(url: str, token: str | None, pausa: float = 2.4):
    """Contra a API publicada: ~25 perguntas por minuto (o limite dela é 30) e, se vier 429, espera e tenta de novo."""
    import time
    import urllib.error

    def enviar(payload):
        req = urllib.request.Request(url.rstrip("/") + "/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **({"X-Api-Token": token} if token else {})})
        for _ in range(4):
            time.sleep(pausa)
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    return {"erro_http": e.code}
                time.sleep(20)
        return {"erro_http": 429}
    return enviar


def relatorio_md(res: list[dict]) -> str:
    falhas = [r for r in res if r["erro"]]
    L = [f"# Matriz de perguntas: {len(res) - len(falhas)}/{len(res)} certas", ""]
    for g in ("impossivel", "possivel", "consulta", "nao_consulta"):
        d = [r for r in res if r["grupo"] == g]
        L.append(f"- {g}: {sum(1 for r in d if not r['erro'])}/{len(d)}")
    if falhas:
        L += ["", "## Falhas"] + [f"- {r['id']} ({r['grupo']}) “{r['pergunta']}”: {r['erro']}" for r in falhas]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="avaliacao.matriz")
    p.add_argument("--url"), p.add_argument("--token"), p.add_argument("--md"), p.add_argument("--json")
    a = p.parse_args(argv)
    res = rodar(por_http(a.url, a.token) if a.url else em_processo(), incluir_local=not a.url)
    md = relatorio_md(res)
    print(md)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(md)
    if a.json:
        json.dump([{k: v for k, v in r.items() if k != "erro"} for r in gerar_casos()], open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if any(r["erro"] for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
