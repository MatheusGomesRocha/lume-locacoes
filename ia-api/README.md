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
| POST   | `/chat`   | `{"pergunta": "...", "historico": [...], "ultimo_id": "..."}` → resposta, fonte, confiança, perguntas relacionadas e `usou_contexto` |

### Contexto da conversa

A API não guarda conversa. Para entender acompanhamentos como "mas eu quero excluir", quem chama envia
`historico` (as últimas perguntas do usuário, no máximo 6) e `ultimo_id` (id da última resposta dada). Os dois são opcionais.

Quando a pergunta está incompleta (poucos termos e sem assunto, ou sem ação), a busca soma os termos da pergunta
anterior com peso menor e dá um pequeno bônus às respostas do mesmo módulo. Perguntas completas nunca são alteradas.
`usou_contexto` é `true` quando isso mudou a melhor resposta.

## LLM (opcional)

Com `GEMINI_API_KEY` definida, o fluxo do `/chat` vira um RAG completo:

1. a busca (TF-IDF + contexto da conversa) escolhe até 3 trechos do FAQ;
2. o Gemini redige a resposta usando **só** esses trechos (instruções em `app/llm.py`);
3. a resposta traz `"gerada_por_llm": true`; a fonte continua sendo a melhor entrada do FAQ.

O LLM **nunca é chamado** quando o FAQ não acha nada, e a API cai na resposta
pronta do FAQ se: não houver chave, o teto diário (`IA_LLM_LIMITE_DIARIO`) acabar, ou o provedor falhar. O chat nunca fica mudo.

### Ferramentas: consultar dados, cadastrar e excluir

Com o LLM ligado, pedidos como "quantos orçamentos aprovados eu tenho?", "quero cadastrar um cliente" e "exclui o produto
tripé" viram **ferramentas** (`app/ferramentas.py`). O modelo só **pede**; quem executa é o front, pela mesma API das telas:

| Pedido | O que a `ia-api` devolve | O que o front faz |
|---|---|---|
| Consulta (`consultar_*`, `resumo_painel`) | `consultas: [{nome, args}]` | lê pela API, devolve em `resultados`; a 2ª volta traz a resposta redigida |
| Cadastro (`cadastrar_*`) | `acoes: [...]` | abre o **mesmo formulário** da tela, preenchido; o usuário confere e salva |
| Exclusão (`excluir_registro`) | `acoes: [...]` | acha o registro e mostra o botão **Confirmar exclusão**; a API de exclusão aplica as regras de sempre |

Garantias: a saída do modelo é validada (ferramenta desconhecida é descartada, argumentos são limpos e limitados); nenhuma
ferramenta grava ou exclui sozinha; as consultas devolvem poucos campos (sem documento, e-mail, telefone ou observações);
dúvidas de "como fazer" não gastam chamada de roteamento e seguem direto para o FAQ. Campos extras do `/chat`:
`hoje` (AAAA-MM-DD, para "este mês") e `resultados` (2ª volta).

A chave fica só no servidor. Crie uma em https://aistudio.google.com/apikey (plano gratuito; os limites mudam,
veja o AI Studio). Os termos do plano gratuito permitem que o Google use o conteúdo enviado, então não coloque dados
sensíveis no FAQ.

## Variáveis de ambiente

| Variável | Padrão | Para que serve |
|----------|--------|----------------|
| `IA_ORIGENS_PERMITIDAS` | `http://localhost:5173,http://127.0.0.1:5173` | Sites que podem chamar a API pelo navegador (CORS), separados por vírgula |
| `IA_API_TOKEN` | vazio | Se definido, exige o header `X-API-Token`. **Não use com o GitHub Pages**: o token ficaria visível no navegador |
| `GEMINI_API_KEY` | _(vazio: LLM desligado)_ | Chave do Google AI Studio |
| `IA_LLM_MODELO` | `gemini-flash-lite-latest` | Modelo do Gemini; troque se o Google renomear |
| `IA_LLM_LIMITE_DIARIO` | `200` | Chamadas ao LLM por dia; `0` desliga |
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
