# Backend: API Laravel (Lume Locações)

Laravel 10 (PHP 8.1+). Clientes, produtos, orçamentos, financeiro e painel. Dados fictícios de exemplo vêm no seeder.
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

## Endpoints

`GET /api/dashboard` · `apiResource` de `clientes`, `produtos`, `orcamentos` · `POST orcamentos/{id}/(enviar|aprovar|finalizar|cancelar)` ·
`GET pagamentos?status=(pendente|atrasado|pago|cancelado)` · `POST pagamentos/{id}/baixar` · `GET chat/sugestoes` · `POST chat`.

Erros de regra voltam como `{"message": "...", "detalhes": [...]}` (409 ou 422); validação como o padrão do Laravel (`errors`).
