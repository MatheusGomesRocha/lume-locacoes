# Frontend: React (Lume Locações)

React 18 + Vite + TypeScript + Tailwind. Fala com o Laravel por HTTP (`VITE_DRIVER=http`, o padrão).

```bash
npm install
cp .env.example .env.local      # ajuste VITE_API_URL se o Laravel não estiver em localhost:8000
npm run dev                     # http://localhost:5173
npm test                        # 138 testes
npm run build
```

O código escolhe de onde vêm os dados em `src/api/index.ts`:

- `http.ts` conversa com o Laravel.
- `local.ts` guarda tudo no `localStorage` (usado pela versão de demonstração), com as regras de `src/lib/regras.ts`.

A mascote **Lumi** está em `src/components/Lumi.tsx` e a conversa em `Chat.tsx`. O tempo de "digitando…" vem de `src/lib/chat.ts`
(entre 0,9 s e 2,5 s, proporcional ao tamanho da resposta).
