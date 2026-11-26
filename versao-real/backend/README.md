# Backend: API Laravel (Lume Locações)

Laravel 12 (PHP 8.2+). Clientes, produtos, orçamentos, financeiro e painel. Dados fictícios de exemplo vêm no seeder.
**Não há login nesta versão**: use só em ambiente local ou atrás de uma proteção sua.

## Rodar

```bash
composer install
cp .env.example .env          # no Windows: copy .env.example .env
php artisan key:generate
touch database/database.sqlite   # Windows: type nul > database\database.sqlite
php artisan migrate --seed
php artisan serve                # http://localhost:8000/api/health
php artisan test                 # 82 testes
```

Para MySQL, troque o bloco `DB_*` do `.env` (há um exemplo comentado). `php artisan migrate:fresh --seed` recria os dados de exemplo.

## Assistente (chat)

O navegador chama `POST /api/chat`, o Laravel repassa para a API Python (`IA_API_URL`, padrão `http://127.0.0.1:8001`)
e devolve a resposta. Suba também a pasta `ia-api` para o chat funcionar. Se ela estiver fora do ar, o chat responde 503 com uma mensagem amigável e o resto do sistema segue normal.

## Regras de negócio (`app/Services`)

- **Total** = (soma dos itens × diárias) − desconto, mínimo 0. **Diárias** = dias entre retirada e devolução, mínimo 1.
- **Número**: `AAAA/0001`, reinicia a cada ano, nunca repete.
- **Status**: rascunho → enviado → aprovado → finalizado; cancelar vale para rascunho, enviado e aprovado. Só rascunho/enviado editam; só rascunho/cancelado excluem.
- **Aprovar** confere estoque no período (só orçamentos **aprovados** seguram estoque) e cria a cobrança com vencimento na retirada.
- **Preço congelado**: itens já no orçamento mantêm o preço; itens novos usam o preço atual do produto.
- Cliente com orçamentos e produto usado em orçamento não podem ser excluídos.

Essas regras existem também em `versao-real/frontend/src/lib/regras.ts` (usadas pela demonstração). Mudou uma, mude as duas.

## Acesso: login, níveis e permissões

- **Login** em `POST /api/login` (`email`, `senha`) devolve um `token`. Todas as outras rotas, menos `GET /api/health`, exigem
  `Authorization: Bearer <token>`. O banco guarda só o hash do token (tabela `tokens_acesso`); vale 7 dias, `POST /api/logout` revoga.
  Login tem limite de 10 tentativas por minuto por e-mail + IP e a mesma resposta para e-mail inexistente e senha errada.
- **Níveis**: `master` (um só, criado pelo seeder), `admin` e `usuario`.
  - O master tem todas as permissões, num grupo "Master" que ninguém altera ou exclui, e só ele mexe nos próprios dados.
    Cria e edita grupos e promove administradores.
  - O admin cadastra e edita só usuários comuns (sempre criados como `usuario`) e escolhe o grupo deles; não mexe no master nem em outros admins.
  - Todo usuário tem **exatamente um grupo** (obrigatório). Grupo é uma lista de permissões `modulo.acao` (catálogo em `app/Support/Acesso.php`).
- **Verificação**: cada rota tem `->middleware('pode:modulo.acao')` (basta uma das listadas). A permissão vem do grupo a cada requisição,
  então mudar o grupo, desativar o usuário ou trocar a senha vale na hora. `usuarios.*` só tem efeito para admin e master.
- **Primeiro acesso**: o seeder cria o master com `MASTER_EMAIL` e `MASTER_SENHA` (ver `.env.example`). Em produção, sem `MASTER_SENHA` nenhum usuário é criado.
  Fora de produção vale `master@lume.com` / `lume1234`, com contas de exemplo (`admin@`, `atendimento@`, `financeiro@lume.com`, mesma senha).

## Endpoints

Públicos: `GET health`, `POST login`. Logado: `POST logout` · `GET|PUT eu` (minha conta) · `GET dashboard` · `clientes`, `produtos`, `orcamentos` (CRUD) ·
`POST orcamentos/{id}/(enviar|aprovar|finalizar|cancelar)` · `GET pagamentos?status=(pendente|atrasado|pago|cancelado)` · `POST pagamentos/{id}/baixar` ·
`GET chat/sugestoes` · `POST chat` · `chat-logs` (registro das conversas) · `faq-itens` (respostas do master às perguntas sem resposta; só o master, e o `chat` as anexa a cada pergunta) · `usuarios` (CRUD, admin/master) · `grupos` (listar: admin/master; criar, editar, excluir: master).

Erros de regra voltam como `{"message": "...", "detalhes": [...]}` (401, 403, 409 ou 422); validação como o padrão do Laravel (`errors`).
