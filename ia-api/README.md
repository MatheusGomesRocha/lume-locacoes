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

### Agente conversacional (criar orçamento e cliente falando no chat)

Quando o pedido já traz dados ("Crie um orçamento para João Victor, com 2 mesas e 20 cadeiras para o evento de Casamento no dia 26/11/2026"), a Lumi conduz uma **conversa**, sem formulário. Sem dados ("quero criar um orçamento"), o formulário de sempre continua.

- **Quem faz o quê.** O Gemini só entende o pedido inicial (`decidir_acao`). Daí em diante o **código** decide cada passo (`app/agente.py`): é previsível, testável e não gasta cota. A API continua sem guardar nada: o estado da conversa (`agente`) volta em cada resposta e o front o devolve na mensagem seguinte.
- **Leituras** (o front executa com as permissões de quem está logado, em até 5 voltas): `localizar_clientes`, `localizar_produtos`, `verificar_disponibilidade`.
- **Cenários tratados:** cliente inexistente ("Não encontramos esse usuário": cadastrar, outro nome ou cancelar), mais de um cliente/produto parecido ("Qual João Victor deseja selecionar?"), produto inexistente (remover/trocar), sem data ("Qual data de retirada e data de devolução?"), sem evento ou itens, uma data só (vale para retirada e devolução, e o resumo avisa), devolução antes da retirada, estoque insuficiente (só aviso: rascunho não exige estoque), cliente novo cadastrado na própria conversa (tipo, contatos opcionais), cliente já existente, usuário sem permissão, pergunta de ajuda no meio do fluxo (sai do agente e responde), estado adulterado.
- **Regra de ouro:** o agente **nunca grava sem autorização**. O resumo (com o total calculado pela mesma regra do sistema) termina em "Confirmar / Cancelar"; só uma resposta afirmativa **nessa etapa** gera `executar`. Qualquer outra coisa repete o pedido de confirmação; "não"/"cancelar" encerra sem gravar. Quem grava é o front, pela mesma API das telas (mesmas regras e permissões).
- **Protocolo** (`POST /chat`): a requisição ganha `agente` (estado) e `resultados`; a resposta ganha `agente`, `opcoes` (botões), `consultas` e `executar`.

### Golden set do agente e LLM-as-judge

```bash
python -m avaliacao --agente --minimo 1.0     # 15 conversas, decisão do modelo simulada (é o que o CI roda; sem chave)
python -m avaliacao --agente --url https://lume-ia.onrender.com --juiz    # com o Gemini de verdade + juiz (semanal)
python -m avaliacao --calibrar-juiz           # o juiz concorda com as notas humanas? (abaixo de 80%, não confie nele)
```

- `avaliacao/casos_agente.json`: cada caso tem o cenário (clientes, produtos, estoque, permissões), os turnos do usuário, o que esperar em cada um e uma **rubrica** em português para o juiz. `simulador.py` faz o papel do front (executa consultas e gravações num banco de brincadeira).
- **Pontuação exata** (`pontuar_agente.py`): ferramentas consultadas, textos-chave, opções, o que foi gravado, totais e a invariante "nada é gravado sem confirmação".
- **Juiz** (`juiz.py`): um modelo lê a conversa inteira, com os dados do cenário e a rubrica, e dá notas 0–5 de correção, fidelidade (nada inventado), segurança e conversa. Temperatura 0, saída em JSON, modelo configurável (`IA_JUIZ_MODELO`, de preferência diferente do assistente). **Fatos duros vencem o juiz**: gravar sem confirmação zera a segurança mesmo que o modelo aprove. Roda só no CI semanal/manual, nunca em produção.

### Cache

A mesma conversa não paga duas vezes (`app/cache.py`): a resposta de ajuda redigida pelo modelo e a decisão de ferramenta ficam em
memória por até 24 h (`IA_CACHE_TTL`, em segundos; `0` desliga) e até `IA_CACHE_MAX` itens. A chave é a pergunta (sem acento, caixa
ou pontuação) + o contexto da conversa + uma versão do conteúdo (FAQ, instruções, ferramentas): editou o FAQ, o cache antigo deixa de valer.
**Nunca** entram no cache respostas montadas com dados do sistema (os números mudam) nem falhas do modelo. `/health` mostra
`llm_chamadas_hoje` e as estatísticas do cache (`acertos`, `erros`, `taxa_de_acerto`).

## Avaliação

75 perguntas com a resposta esperada (`avaliacao/casos.json`), em 8 grupos. Cada caso diz o que **precisa** acontecer (fonte do FAQ, ferramenta chamada,
argumentos certos, texto que deve ou não aparecer); não compara frase com frase, porque o modelo pode redigir de formas diferentes.

```bash
python -m avaliacao --local --pausa 0                  # em processo, sem LLM (só o que não depende do modelo)
python -m avaliacao --url https://lume-ia.onrender.com # a API de verdade, com o Gemini (3 chamadas/s no máx.; leva ~3 min)
python -m avaliacao --pontuar resultados.json --minimo 0.9 --md relatorio.md   # só pontua um arquivo já coletado; sai com erro abaixo do mínimo
```

Última rodada **na API hospedada, com o Gemini** (2026-11-25, 75 casos, disparada pelo workflow semanal): **72/75 (96%)**.
FAQ e acesso 24/25, contexto 8/8, consulta 12/12, cadastro 6/6, exclusão 5/5, fora de escopo 5/5, conversa 2/2, segurança 6/6, **sinônimos 4/6**.
Sem LLM (em processo, é o que o CI roda a cada commit) os 46 casos que não dependem do modelo dão 100%.

Falhas conhecidas (e o porquê):
- `sinonimo-01` "como adiciono uma pessoa no sistema": a busca semântica não passou do limite de confiança (prefere "não encontrei" a arriscar).
- `sinonimo-04` "equipamento parar de aparecer nos pedidos novos": o TF-IDF acerta o assunto errado (produto → editar) com nota média e o embedding não abre vantagem suficiente.
- `acesso-06` "onde vejo as perguntas que fizeram pra Lumi?": o embedding escolheu "O que o assistente pode fazer?" no lugar de "Onde vejo as perguntas...". É o custo de deixar o significado vencer o TF-IDF quando este tem nota média; ajustar isso pede mais perguntas reais para calibrar (é para isso que serve o ciclo de `avaliacao.candidatos`).

O que a primeira rodada achou e foi corrigido: "e para aprovar?" depois de "como criar um orçamento" respondia sobre **criar** (o verbo antigo
competia com o novo) e "oi" / "obrigado" respondiam "não encontrei".

### Avaliação automática e ciclo com perguntas reais

- **A cada commit (CI):** `python -m avaliacao --local --sem-modelo --minimo 1.0` roda os casos que não dependem do Gemini (46) e reprova se algum quebrar.
- **Toda segunda (GitHub Actions, `avaliacao-semanal.yml`):** roda todos os casos contra a API publicada, com o Gemini, e reprova abaixo de 90%. O relatório vai para o resumo da execução e para um artefato. Também dá para disparar à mão.
- **Perguntas reais viram testes** (`avaliacao/candidatos.py`): exporte os logs (tela de Conversas / `GET /chat-logs` / `perguntas_sem_resposta.jsonl`), gere `candidatos.json` com `python -m avaliacao.candidatos logs.json`, revise (preencha `espera` e `aprovado`) e incorpore com `--aprovar candidatos.json`. O script só separa e sugere; quem decide a resposta certa é uma pessoa.

### FAQ extra (respostas do master)

O master responde às perguntas sem resposta pela tela de Conversas. As respostas ficam no banco do sistema (Laravel) ou no navegador (demo), nunca na ia-api, e vão no campo `faq_extra` (até 100 itens: `id`, `modulo`, `pergunta`, `resposta`, `palavras_chave`) de cada `POST /chat`. A API monta uma base com o FAQ do arquivo mais esses itens (guardada em memória por conteúdo) e a resposta em cache muda junto quando os extras mudam. Os itens extras entram só na busca por palavras (TF-IDF), por isso a pergunta original vai nas `palavras_chave`.

### Busca semântica (embeddings)

O TF-IDF compara palavras; "adicionar uma pessoa" não casa com "cadastrar um usuário". Por isso, quando a nota do TF-IDF fica abaixo de `0.45`, a pergunta vira um vetor (`gemini-embedding-001`) e é comparada, por cosseno, com os vetores do FAQ (calculados 1 vez na partida, em segundo plano).
O resultado semântico só vale se passar de `0.74` **e** vencer o 2º lugar por `0.02` (calibrado em 20 perguntas reais: os acertos ficaram em 0.74–0.80 com margem ≥0.02; perguntas fora do assunto, em até 0.71 com margem ≤0.016), para perguntas fora do assunto continuarem sem resposta. Sem chave, sem cota ou com erro de rede, segue só o TF-IDF. A resposta traz `"busca": "lexical" | "semantica"` e o `/health` mostra `semantica`.

## Variáveis de ambiente

| Variável | Padrão | Para que serve |
|----------|--------|----------------|
| `IA_ORIGENS_PERMITIDAS` | `http://localhost:5173,http://127.0.0.1:5173` | Sites que podem chamar a API pelo navegador (CORS), separados por vírgula |
| `IA_API_TOKEN` | vazio | Se definido, exige o header `X-API-Token`. **Não use com o GitHub Pages**: o token ficaria visível no navegador |
| `GEMINI_API_KEY` | _(vazio: LLM desligado)_ | Chave do Google AI Studio |
| `IA_JUIZ_MODELO` | Modelo do juiz da avaliação (padrão: o mesmo do assistente). |
| `IA_LLM_MODELO` | `gemini-flash-lite-latest` | Modelo do Gemini; troque se o Google renomear |
| `IA_LLM_LIMITE_DIARIO` | `200` | Chamadas ao LLM por dia; `0` desliga |
| `IA_CACHE_TTL` | `86400` | Segundos que uma resposta fica no cache; `0` desliga |
| `IA_CACHE_MAX` | `500` | Máximo de itens no cache |
| `IA_LIMITE_POR_MINUTO` | `30` | Perguntas por minuto por visitante (429 depois disso) |
| `IA_SEMANTICA` | `1` | `0` desliga a busca semântica |
| `IA_LIMITE_SEMANTICO` / `IA_MARGEM_SEMANTICA` | `0.74` / `0.02` | Nota mínima e vantagem sobre o 2º lugar para aceitar a busca semântica |
| `IA_SEMANTICA_SE_LEXICAL_ABAIXO` | `0.45` | Só consulta o embedding se o TF-IDF ficar abaixo disso |
| `IA_LIMITE_CONFIANCA` | `0.30` | Abaixo disso a pergunta vira "não encontrei" e é registrada |

Perguntas sem resposta vão para `data/perguntas_sem_resposta.jsonl`: é a lista do que falta incluir no FAQ.

## Hospedar no Render (plano gratuito)

1. Suba o repositório no GitHub.
2. Render → **New → Blueprint** → escolha o repositório (ele lê o `render.yaml` da raiz).
3. Em `IA_ORIGENS_PERMITIDAS`, informe a origem do seu Pages, por exemplo `https://SEU-USUARIO.github.io` (só a origem, sem `/nome-do-repo`).
4. Quando terminar, teste `https://lume-ia.onrender.com/health`.

O plano gratuito "dorme" após ~15 min sem uso e a primeira pergunta depois disso pode levar de 30 a 60 s.
A tela mostra "digitando…" nesse tempo e o cliente espera até 30 s antes de avisar que está indisponível.
