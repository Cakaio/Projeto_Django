# Design System (Tailwind compilado) — Projeto Criança Feliz

Este diretório gera o CSS do site: **`../static/css/pcf.css`** (commitado). O
PythonAnywhere **não** roda build — só faz `git pull`. Portanto, sempre que
mexer em `input.css`, no `tailwind.config.js` **ou adicionar classes Tailwind
novas nos templates**, é preciso recompilar e commitar o `pcf.css` atualizado.

## Como compilar

```bash
cd tailwindcss
npm install        # só na primeira vez
npm run build      # gera ../static/css/pcf.css (minificado)
# ou, durante o desenvolvimento:
npm run watch      # recompila a cada alteração
```

## Como funciona

- `input.css` — tokens (variáveis shadcn re-tematizadas para a paleta quente),
  base additiva, `@keyframes` e todos os componentes `.pcf-*` (botões, cards,
  seções "ilha", efeitos: orbs, grid, glass, live-dots).
- `tailwind.config.js` — paleta da marca (`brand`, `ink`, `night`, `cat`),
  fonte Archivo, `content` (todos os templates dos apps), `safelist` de `.pcf-*`
  (o design system nunca é purgado) e **`preflight: false`** (o Bootstrap ainda
  é carregado nas telas legadas durante a migração; sai no ciclo final).

## Importante

- **Não commitar `node_modules/`** (já está no `.gitignore`).
- Utilitárias Tailwind só entram no `pcf.css` se aparecerem **estaticamente**
  em algum template escaneado. Classes montadas dinamicamente em JS não são
  detectadas — prefira classes fixas ou use `.pcf-*`/CSS escopado.
