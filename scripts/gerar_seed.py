"""Gera shared/seed.json: dados FICTÍCIOS do Lume Locações.

Datas são guardadas como deslocamento em dias a partir de "hoje" (ex.: -20 = 20 dias atrás),
então o painel nunca fica velho. O mesmo arquivo alimenta o Laravel (seeder) e o localStorage.
Rodar:  python3 scripts/gerar_seed.py
"""
import json
import random
from pathlib import Path

rng = random.Random(2026)

CLIENTES = [
    ("Buffet Sabor & Arte", "PJ", "Fortaleza", "Cozinha de eventos para casamentos e formaturas."),
    ("Cerimonial Aurora", "PJ", "Fortaleza", "Cliente recorrente, paga sempre em dia."),
    ("Eventos Maré Alta", "PJ", "Aquiraz", ""),
    ("Studio Lira Fotografia", "PJ", "Fortaleza", "Aluga cenários para ensaios."),
    ("Colégio Nova Geração", "PJ", "Eusébio", "Formaturas e feira de ciências."),
    ("Agência Quadro Branco", "PJ", "Fortaleza", "Ativações de marca e confraternizações."),
    ("Hotel Pôr do Sol", "PJ", "Caucaia", "Eventos de fim de ano."),
    ("Atlética Pioneiros", "PJ", "Maracanaú", ""),
    ("Mariana Albuquerque", "PF", "Fortaleza", "Casamento em março."),
    ("Rafael Nogueira", "PF", "Fortaleza", ""),
    ("Camila Teixeira", "PF", "Eusébio", "Aniversário de 15 anos da filha."),
    ("Bruno Carvalho", "PF", "Sobral", "Retira os itens no galpão."),
    ("Juliana Freitas", "PF", "Fortaleza", ""),
    ("Diego Monteiro", "PF", "Caucaia", "Prefere pagar no Pix."),
]

# (código, nome, categoria, descrição, diária, reposição, quantidade)
PRODUTOS = [
    ("LUZ-001", "Refletor LED RGB 200W", "Iluminação", "Refletor com controle DMX e efeito estroboscópico.", 85, 900, 24),
    ("LUZ-002", "Par LED 54x3W", "Iluminação", "Iluminação de ambiente com 7 canais DMX.", 45, 480, 36),
    ("LUZ-003", "Moving Head Beam 230", "Iluminação", "Cabeça móvel para pista de dança.", 260, 3200, 8),
    ("LUZ-004", "Globo de Espelhos 50 cm", "Iluminação", "Globo com motor silencioso.", 70, 420, 6),
    ("LUZ-005", "Varal de Luzes 10 m", "Iluminação", "Cordão com 20 lâmpadas de filamento.", 55, 260, 30),
    ("LUZ-006", "Fita LED Cenográfica 5 m", "Iluminação", "Fita RGB com controle remoto.", 30, 150, 40),
    ("SOM-001", "Caixa Ativa 15\" 500 W", "Som", "Caixa amplificada para ambientes de até 150 pessoas.", 120, 2400, 12),
    ("SOM-002", "Subwoofer 18\" Ativo", "Som", "Reforço de graves para pista.", 180, 3600, 6),
    ("SOM-003", "Mesa de Som 12 canais", "Som", "Mesa analógica com efeitos.", 150, 2800, 4),
    ("SOM-004", "Microfone sem fio", "Som", "Microfone de mão UHF com receptor.", 60, 700, 16),
    ("MOB-001", "Cadeira Tiffany Branca", "Mobiliário", "Cadeira empilhável em acrílico.", 9, 120, 220),
    ("MOB-002", "Mesa Redonda 1,5 m", "Mobiliário", "Mesa para 8 lugares, madeira.", 35, 480, 40),
    ("MOB-003", "Sofá Chesterfield 3 lugares", "Mobiliário", "Sofá em couro sintético capitonê.", 220, 3500, 5),
    ("MOB-004", "Puff de Veludo", "Mobiliário", "Puff redondo, várias cores.", 40, 260, 30),
    ("MOB-005", "Banqueta Alta Preta", "Mobiliário", "Banqueta para bancada de bar.", 22, 190, 48),
    ("MOB-006", "Aparador Rústico", "Mobiliário", "Aparador em madeira de demolição.", 90, 1100, 10),
    ("DEC-001", "Painel Redondo Cenográfico", "Decoração", "Painel de 1,8 m com sustentação.", 110, 650, 14),
    ("DEC-002", "Arranjo Floral Artificial", "Decoração", "Arranjo de mesa em tons neutros.", 65, 320, 60),
    ("DEC-003", "Cortina de Voal 3 m", "Decoração", "Cortina branca com varão.", 40, 210, 26),
    ("DEC-004", "Letreiro Neon \"Amor\"", "Decoração", "Neon de LED, 1,2 m, branco quente.", 190, 1400, 3),
    ("DEC-005", "Tapete Persa 2x3 m", "Decoração", "Tapete estampado, tons de azul.", 75, 800, 12),
    ("EST-001", "Tenda 5x5 m", "Estrutura", "Tenda piramidal com cobertura branca.", 480, 5200, 6),
    ("EST-002", "Tenda 10x10 m", "Estrutura", "Tenda com laterais, montagem inclusa.", 1100, 14000, 3),
    ("EST-003", "Palco Modular 2x1 m", "Estrutura", "Módulo de palco, altura regulável.", 170, 1900, 12),
    ("EST-004", "Treliça Q30 3 m", "Estrutura", "Box truss de alumínio.", 150, 1700, 16),
    ("BUF-001", "Chafing Dish Inox", "Buffet", "Rechaud retangular com 2 cubas.", 45, 380, 28),
    ("BUF-002", "Mesa de Doces Vitrine", "Buffet", "Expositor de doces em vidro.", 130, 1200, 8),
    ("BUF-003", "Climatizador Industrial", "Buffet", "Climatizador evaporativo móvel.", 300, 4200, 5),
    ("BUF-004", "Fogão Industrial 4 bocas", "Buffet", "Fogão para cozinha de apoio.", 160, 1800, 4),
    ("BUF-005", "Coqueteleira e Kit Bar", "Buffet", "Kit de bar com 12 peças.", 50, 300, 10),
]

EVENTOS = ["Casamento", "Formatura", "Aniversário", "Confraternização", "Feira de Ciências", "Lançamento de Marca", "Festa Junina", "Churrasco de Fim de Ano", "Chá de Bebê", "Inauguração"]

# (status, quantidade, intervalo de retirada em dias a partir de hoje)
PLANO = [("finalizado", 13, (-175, -12)), ("aprovado", 6, (-2, 30)), ("enviado", 5, (5, 45)), ("rascunho", 3, (10, 60)), ("cancelado", 3, (-40, 20))]


def sobrepoe(a_ini, a_fim, b_ini, b_fim):
    return a_ini <= b_fim and a_fim >= b_ini


def gerar():
    clientes = [dict(id=i + 1, nome=n, tipo=t, documento=(f"{rng.randint(10,99)}.{rng.randint(100,999)}.{rng.randint(100,999)}/0001-{rng.randint(10,99)}" if t == "PJ" else f"{rng.randint(100,999)}.{rng.randint(100,999)}.{rng.randint(100,999)}-{rng.randint(10,99)}"),
                       email=f"contato{i + 1:02d}@example.com", telefone=f"(85) 90000-{i + 1:04d}", cidade=c, observacoes=o)
                for i, (n, t, c, o) in enumerate(CLIENTES)]
    produtos = [dict(id=i + 1, codigo=c, nome=n, categoria=cat, descricao=d, valor_diaria=float(v), valor_reposicao=float(r), quantidade=q, ativo=True)
                for i, (c, n, cat, d, v, r, q) in enumerate(PRODUTOS)]
    prod = {p["id"]: p for p in produtos}
    produtos[7]["ativo"] = False  # um produto inativo para testar o filtro

    orcamentos, pagamentos, ocupados = [], [], []  # ocupados: (ini, fim, produto_id, qtd) de aprovados/finalizados
    for status, qtd, (lo, hi) in PLANO:
        for _ in range(qtd):
            retirada = rng.randint(lo, hi)
            if status == "finalizado":
                retirada = min(retirada, -6)
            dur = rng.randint(1, 4)
            devolucao = retirada + dur
            cliente = rng.choice(clientes)
            itens = []
            for pid in rng.sample([p["id"] for p in produtos if p["ativo"]], rng.randint(3, 7)):
                q = max(1, int(prod[pid]["quantidade"] * rng.choice([0.1, 0.15, 0.2, 0.3, 0.4])))
                if status in ("aprovado", "finalizado"):
                    usados = sum(o[3] for o in ocupados if o[2] == pid and sobrepoe(retirada, devolucao, o[0], o[1]))
                    q = min(q, prod[pid]["quantidade"] - usados)
                if q >= 1:
                    itens.append(dict(produto_id=pid, quantidade=q))
                    if status in ("aprovado", "finalizado"):
                        ocupados.append((retirada, devolucao, pid, q))
            if not itens:
                continue
            desconto = rng.choice([0, 0, 0, 50, 100, 150, 200])
            oid = len(orcamentos) + 1
            orcamentos.append(dict(id=oid, cliente_id=cliente["id"], status=status, evento=f"{rng.choice(EVENTOS)} {cliente['nome'].split()[0]}",
                                   criado_dias=retirada - rng.randint(8, 25), retirada_dias=retirada, devolucao_dias=devolucao, desconto=float(desconto),
                                   observacoes=rng.choice(["", "", "Montagem às 14h.", "Retirada pelo cliente.", "Entrega e montagem inclusas."]), itens=itens))
    # numeração e pagamentos dependem da ordem de criação
    orcamentos.sort(key=lambda o: (o["criado_dias"], o["id"]))
    for novo_id, o in enumerate(orcamentos, start=1):
        o["id"] = novo_id
    finalizados_atrasados = 0
    for o in orcamentos:
        if o["status"] in ("aprovado", "finalizado"):
            if o["status"] == "finalizado":
                if finalizados_atrasados < 1 and o["retirada_dias"] > -60:
                    pago, finalizados_atrasados = None, 1  # um recebível atrasado
                else:
                    pago = min(-1, o["retirada_dias"] + rng.randint(-5, 3))
            else:
                pago = rng.choice([None, None, None, min(-1, o["retirada_dias"] - 2)]) if o["retirada_dias"] <= 7 else None
            pagamentos.append(dict(orcamento_id=o["id"], vencimento_dias=o["retirada_dias"], pago_dias=pago, forma=(rng.choice(["pix", "pix", "cartao", "boleto"]) if pago is not None else None)))
    # as duas cobranças pagas mais recentes entram "hoje": o painel nunca abre com "Recebido no mês" zerado
    pagos = sorted((p for p in pagamentos if p["pago_dias"] is not None), key=lambda p: -p["pago_dias"])
    for p in pagos[:2]:
        p["pago_dias"] = 0
    return dict(clientes=clientes, produtos=produtos, orcamentos=orcamentos, pagamentos=pagamentos)


if __name__ == "__main__":
    dados = gerar()
    raiz = Path(__file__).resolve().parent.parent
    texto = json.dumps(dados, ensure_ascii=False, indent=1)
    # a mesma fonte alimenta o Laravel e o front (cada projeto leva a sua cópia)
    for destino in (raiz / "shared" / "seed.json",
                    raiz / "versao-real" / "backend" / "database" / "seeders" / "data" / "seed.json",
                    raiz / "versao-real" / "frontend" / "src" / "data" / "seed.json"):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    por_status = {}
    for o in dados["orcamentos"]:
        por_status[o["status"]] = por_status.get(o["status"], 0) + 1
    print({k: len(v) for k, v in dados.items()}, por_status)
