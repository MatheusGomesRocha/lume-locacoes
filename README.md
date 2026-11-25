# Lume Locações (versão real)

Sistema de locação de equipamentos para eventos: **orçamentos, financeiro, painel, produtos e clientes**, com a assistente **Lumi**
(chat que tira dúvidas sobre o sistema). Todos os dados de exemplo são fictícios.

A versão de demonstração (só front-end, para o GitHub Pages) fica em outro repositório: [lume-locacoes-repo](https://github.com/MatheusGomesRocha/lume-locacoes-repo), com site em https://matheusgomesrocha.github.io/lume-locacoes-repo/.

| Pasta | O que é |
|-------|---------|
| `versao-real/backend` | API Laravel 12 + banco próprio (SQLite ou MySQL) com dados de exemplo |
| `versao-real/frontend` | Front React que usa a API Laravel |
| `ia-api` | API Python da assistente Lumi (FastAPI), usada pelas duas versões |
| `shared/seed.json` | Dados fictícios (fonte única), copiados para o backend e o front por `scripts/gerar_seed.py` |
| `render.yaml` | Receita para hospedar a `ia-api` no Render |

## Testar tudo local (versão real)

Três terminais:

```bash
# 1) API Python (porta 8001)
cd ia-api && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements-dev.txt
python -m uvicorn app.main:app --port 8001 --reload

# 2) Laravel (porta 8000). Detalhes em versao-real/backend/README.md
cd versao-real/backend && composer install && cp .env.example .env && php artisan key:generate
touch database/database.sqlite && php artisan migrate --seed && php artisan serve

# 3) React (porta 5173)
cd versao-real/frontend && npm install && cp .env.example .env.local && npm run dev
```

Abra http://localhost:5173.

## Demonstração online (GitHub Pages + Render)

A API Python não roda no GitHub Pages (ele só serve arquivos estáticos), por isso ela fica no Render e a demonstração chama por HTTPS.

1. **Render:** siga `ia-api/README.md` (Blueprint com o `render.yaml`) e anote a URL, por exemplo `https://lume-ia.onrender.com`.
2. No Render, ajuste `IA_ORIGENS_PERMITIDAS` para `https://matheusgomesrocha.github.io`.
3. No repositório da demo, crie a variável `IA_API_URL` com a URL do Render (veja o README de lá).

A demo é gerada a partir de `versao-real/frontend`. Depois de mudar o front, exporte e publique:

```bash
python scripts/exportar_pages.py    # gera/atualiza a pasta versao-pages (um repositório git à parte, ignorado aqui)
cd versao-pages && git add -A && git commit -m "Atualiza demonstração" && git push
```

O push na `main` do repositório da demo dispara o CI/CD que testa e publica.

## Testes

| Parte | Comando | Testes |
|-------|---------|--------|
| `ia-api` | `pytest -q` | 73 |
| Laravel | `php artisan test` | 82 |
| React | `npm test` | 138 |

O workflow `Testes` roda tudo a cada push.

## Limites desta versão

- **Sem login.** Qualquer pessoa que alcance a API mexe nos dados. Antes de expor o Laravel na internet, adicione autenticação.
- A demonstração guarda dados só no navegador de quem usa e começa com os mesmos dados fictícios (há o botão "Restaurar dados de exemplo").
- A Lumi só explica **como usar** o sistema; ela não lê valores ou listas dele.
