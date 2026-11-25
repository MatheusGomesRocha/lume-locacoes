# ia-api: assistente Lumi (FAQ com busca por similaridade)

API em Python (FastAPI) que responde dúvidas sobre **como usar o sistema**. Ela compara a pergunta com uma base de
perguntas frequentes (`data/faq.json`) usando TF-IDF e similaridade de cosseno, a parte de "busca" de um RAG, sem
modelo de linguagem e sem custo por pergunta.

Ela **não** consulta os dados do sistema (valores, listas, totais). Perguntas desse tipo recebem uma recusa educada.

## Rodar local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   |   source .venv/bin/activate  (Linux/macOS)
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --port 8001 --reload
pytest -q                       # 73 testes
```

Docs interativas: http://127.0.0.1:8001/docs

## Endpoints

| Método | Rota      | O que faz |
|--------|-----------|-----------|
| GET    | `/health` | Saúde do serviço (usado pelo Render) |
| GET    | `/faq`    | Lista as perguntas da base (a tela usa para sugestões) |
| POST   | `/chat`   | `{"pergunta": "..."}` → resposta, fonte, confiança e perguntas relacionadas |

## Variáveis de ambiente

| Variável | Padrão | Para que serve |
|----------|--------|----------------|
| `IA_ORIGENS_PERMITIDAS` | `http://localhost:5173,http://127.0.0.1:5173` | Sites que podem chamar a API pelo navegador (CORS), separados por vírgula |
| `IA_API_TOKEN` | vazio | Se definido, exige o header `X-API-Token`. **Não use com o GitHub Pages**: o token ficaria visível no navegador |
| `IA_LIMITE_POR_MINUTO` | `30` | Perguntas por minuto por visitante (429 depois disso) |
| `IA_LIMITE_CONFIANCA` | `0.30` | Abaixo disso a pergunta vira "não encontrei" e é registrada |

Perguntas sem resposta vão para `data/perguntas_sem_resposta.jsonl`: é a lista do que falta incluir no FAQ.

## Hospedar no Render (plano gratuito)

1. Suba o repositório no GitHub.
2. Render → **New → Blueprint** → escolha o repositório (ele lê o `render.yaml` da raiz).
3. Em `IA_ORIGENS_PERMITIDAS`, informe a origem do seu Pages, por exemplo `https://SEU-USUARIO.github.io` (só a origem, sem `/nome-do-repo`).
4. Quando terminar, teste `https://lume-ia.onrender.com/health`.

O plano gratuito "dorme" após ~15 min sem uso e a primeira pergunta depois disso pode levar de 30 a 60 s.
A tela mostra "digitando…" nesse tempo e o cliente espera até 30 s antes de avisar que está indisponível.
