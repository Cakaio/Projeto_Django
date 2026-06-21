# Módulo ADM — Fluxo de Caixa, Contabilidade e DRE

**Data:** 2026-06-21
**Status:** Aprovado

---

## Contexto

O Projeto Criança Feliz não possui módulo financeiro. Gastos de materiais já existem no `supply` (modelo `Pedido` com campo `valor`), mas não há controle de receitas, despesas gerais, nem demonstrativo de resultados. Este módulo cria o app `adm` para suprir essa lacuna.

---

## Acesso

Apenas voluntários com `area == 'ADM/FIN'`, `area == 'TRIADE'` ou `is_superuser` podem acessar qualquer view do módulo. Criação e edição de lançamentos manuais restritas a `ADM/FIN` e `is_superuser`. TRIADE tem acesso somente de leitura.

---

## Modelos

### `Categoria`
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `nome` | CharField(100) | Ex: "Doação", "Materiais", "Eventos", "Fixos" |
| `tipo` | CharField choices: `RECEITA` / `DESPESA` | Classifica a categoria |
| `ativo` | BooleanField(default=True) | Soft-desativa sem deletar |

### `Lancamento`
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `tipo` | CharField choices: `RECEITA` / `DESPESA` | Espelha o tipo da categoria |
| `categoria` | FK → `Categoria` | Categoria do lançamento |
| `valor` | DecimalField(10,2) | Valor em reais |
| `data` | DateField | Data do fato (não do registro) |
| `descricao` | TextField(blank=True) | Detalhamento opcional |
| `origem` | CharField choices: `MANUAL` / `SUPPLY` | Como foi criado |
| `pedido` | FK nullable → `supply.Pedido` | Preenchido quando origem=SUPPLY |
| `criado_por` | FK → `voluntario.Voluntario` | Quem registrou |
| `criado_em` | DateTimeField(auto_now_add=True) | Timestamp do registro |

---

## Integração com Supply

Um signal `post_save` no modelo `supply.Pedido` verifica se `pedido.valor` está preenchido. Se sim:
- **Criação:** cria um `Lancamento` com `tipo=DESPESA`, `origem=SUPPLY`, `pedido=pedido`, usando uma `Categoria` padrão configurável (ex: "Materiais Supply").
- **Edição:** atualiza o `valor` do `Lancamento` vinculado.
- **Deleção:** `post_delete` signal deleta o `Lancamento` vinculado.

A categoria usada pelo supply é buscada por `Categoria.objects.get(nome="Materiais Supply", tipo="DESPESA")`. Se não existir, o lançamento é ignorado silenciosamente (sem erro — ADM/FIN precisa criar a categoria antes).

---

## Views e URLs (`/adm/`)

| URL | View | Acesso |
|-----|------|--------|
| `/adm/` | Painel — saldo atual, últimos 10 lançamentos, atalhos | Leitura |
| `/adm/lancamentos/` | Lista com filtros (período, tipo, categoria) | Leitura |
| `/adm/lancamentos/novo/` | Criar lançamento manual | ADM/FIN + superuser |
| `/adm/lancamentos/<id>/editar/` | Editar lançamento manual | ADM/FIN + superuser |
| `/adm/lancamentos/<id>/deletar/` | Deletar lançamento (somente MANUAL) | ADM/FIN + superuser |
| `/adm/categorias/` | CRUD de categorias | ADM/FIN + superuser |
| `/adm/fluxo-de-caixa/` | Cronológico com saldo acumulado | Leitura |
| `/adm/dre/` | DRE categorizado + comparativo | Leitura |

---

## DRE — Estrutura

```
Período: [Jan 2026 ▾]   Comparar com: [Dez 2025 ▾]

RECEITAS
  Doações .......................... R$ 1.200,00
  Patrocínios ...................... R$   800,00
  Eventos .......................... R$   300,00
  TOTAL RECEITAS ................... R$ 2.300,00

DESPESAS
  Materiais Supply ................. R$   450,00
  Fixos ............................ R$   200,00
  Reembolsos ....................... R$    80,00
  TOTAL DESPESAS ................... R$   730,00

RESULTADO DO PERÍODO .............. R$ 1.570,00

─────────────────────────────────────────────────
COMPARATIVO MENSAL
Categoria        Jan/26    Dez/25    Δ
Receitas totais  2.300,00  1.900,00  +400,00
Despesas totais    730,00    890,00  -160,00
Resultado        1.570,00  1.010,00  +560,00
```

---

## Fluxo de Caixa — Estrutura

Lista cronológica com saldo acumulado:

```
Data        Descrição              Categoria     Entrada    Saída    Saldo
15/01/26    Doação - Empresa X     Doação        1.200,00            1.200,00
18/01/26    Materiais sala azul    Mat. Supply              450,00     750,00
20/01/26    Aluguel espaço         Fixos                    200,00     550,00
```

Filtros: período (mês/intervalo livre), tipo (receita/despesa/ambos), categoria.

---

## Templates

- Seguem o padrão visual do projeto: TailwindCSS + componentes existentes (navbar, base.html).
- Tabelas com classes consistentes com `lista_voluntarios.html` e `visualizar_presencas.html`.
- DRE e fluxo de caixa têm botão de exportação CSV (simples, sem dependência extra).

---

## Fora do escopo

- Integração com contabilidade externa ou ERP.
- Upload de comprovantes/notas fiscais.
- Aprovação de lançamentos por múltiplos usuários.
- Múltiplas moedas.
