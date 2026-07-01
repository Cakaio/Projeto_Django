# Redesign da Gestão de Rondas — Design

**Data:** 2026-07-01
**App:** `ronda`
**Autor:** Tríade / PCF

## Objetivo

Reformular a Gestão de Rondas para ser mais intuitiva e flexível: cada linha da
ronda passa a ser um par **Horário + Local** (em vez da grade automática horário
× todos-os-locais), com CRUD de locais pelo site, criação de ronda para sábados
recentes (inclusive fechados), botões de editar/excluir/duplicar, exibição da
pontuação dos voluntários e um painel redesenhado.

## Contexto atual

- `LocalRonda` — lista global de locais (`nome`, `ativo`, `ordem`). CRUD já
  existe em `views.py` (`locais`, `local_criar/editar/deletar`) e `forms.py`.
- `ConfiguracaoRondaSabado` — uma por `Sabado` (OneToOne). Fluxo de status:
  `PENDENTE_SORTEIO` → `SORTEADA` → `APROVADA`/`REPROVADA`.
- `HorarioRonda` — faixa de horário (`hora_inicio`, `hora_fim`, `ordem`) de uma
  configuração.
- `EscalaRonda` — 2 voluntários por **(horário × local)** — modelo de grade.
- `ScoreRonda` — pontos por voluntário/ano; incrementado na aprovação.
- Disponibilidade: `sabado.DisponibilidadeVoluntario.vai_ao_projeto` (bool)
  indica quem confirmou presença. `unique_together = (sabado, voluntario)`.
- Áreas isentas de ronda: `AREAS_ISENTAS_RONDA = {TRIADE, SUPPLY, RECREACAO, MARKETING}`.
- Acesso à gestão: área `TRIADE` (ou superuser), via `@ronda_required`.

## Decisões (confirmadas)

1. **Estrutura por linha (Horário + Local).** No `HorarioRonda`, o campo `ordem`
   (número) é substituído por `local` (FK → `LocalRonda`). Cada registro passa a
   ser uma linha `Início + Fim + Local`. Sem tabela de associação nova.
2. **Janela de sábados:** últimos 30 dias + futuros (inclusive sábados já
   fechados). Editar não troca o sábado.
3. **Excluir ronda aprovada estorna os pontos** somados no `ScoreRonda`.
4. **Ano da pontuação:** usar `sabado.data.year` (não `timezone.now().year`),
   pois agora é possível criar ronda de sábado passado.
5. **3 locais pré-definidos** já existem no banco; serão apenas renomeados pela
   tela de Locais (a migração garante que existam 3 ativos).
6. **Extras incluídos:** contador de confirmados + aviso de pool insuficiente;
   última ronda ao lado do nome; painel com filtros/estatísticas; imprimir escala.

## Mudanças de modelo

### `HorarioRonda`
- **Remove** `ordem`.
- **Adiciona** `local = models.ForeignKey(LocalRonda, on_delete=PROTECT, related_name='horarios')`.
- `Meta.unique_together = ('configuracao', 'hora_inicio', 'hora_fim', 'local')`
  (permite mesma faixa de horário com locais diferentes).
- `Meta.ordering = ['hora_inicio', 'local__nome']`.

### `EscalaRonda`
- **Remove** o campo `local` (agora derivado de `horario.local`).
- `Meta.unique_together = ('horario', 'voluntario')`.
- `clean()`: máximo de 2 voluntários por `horario`.

### Migração de dados
As rondas existentes usam o modelo de grade (dados de teste). A migração:
1. Adiciona `HorarioRonda.local` como nullable temporariamente.
2. Para cada `HorarioRonda` antigo com escalas, identifica os locais distintos
   presentes nas suas `EscalaRonda`; para cada local, cria/ajusta um
   `HorarioRonda` (mesmos horários) apontando para aquele local e reatribui as
   escalas correspondentes. Horários sem escalas recebem o primeiro `LocalRonda`
   ativo.
3. Remove `EscalaRonda.local` e torna `HorarioRonda.local` obrigatório.
4. Rondas reais que não converterem de forma limpa podem ser recriadas pela
   Tríade (volume de dados atual é mínimo/teste).

### Seed de locais
Data migration garante ao menos 3 `LocalRonda` ativos caso a tabela esteja
vazia (nomes genéricos, ex.: "Portão", "Quadra", "Salão"); a Tríade renomeia
pela tela de Locais.

## Sorteio (`ronda/sorteio.py`)

- Itera por `HorarioRonda` (cada um já tem `local`).
- Pool = voluntários ativos (`data_saida__isnull=True`), não isentos, **e** que
  confirmaram presença no sábado (`DisponibilidadeVoluntario.vai_ao_projeto=True`).
- Prioriza menor pontuação anual (`ScoreRonda` do `sabado.data.year`), com
  desempate aleatório (shuffle antes do sort estável).
- **Não repete** o mesmo voluntário na mesma **faixa de horário** (mesma
  `hora_inicio`/`hora_fim`), mesmo que em locais diferentes: o controle de
  `ja_alocados` é feito por janela de horário, não por `HorarioRonda` isolado.
- 2 voluntários por linha; se o pool esvaziar, a linha fica incompleta (sem erro).

## Views e rotas

Novas/alteradas em `ronda/views.py` e `ronda/urls.py`:

| Rota | View | Descrição |
|------|------|-----------|
| `configuracoes/<pk>/editar/` | `configuracao_editar` | Edita horários+locais (não o sábado). Reusa form+formset. |
| `configuracoes/<pk>/deletar/` | `configuracao_deletar` | POST com confirmação. Se `APROVADA`, estorna pontos antes de apagar. |
| `configuracoes/<pk>/imprimir/` | `configuracao_imprimir` | View com layout de impressão da escala. |

Alterações:
- `ConfiguracaoRondaForm`: queryset de sábado = `data >= hoje - 30 dias`,
  excluindo já configurados, ordenado por `data`.
- `configuracao_aprovar`: incrementa `ScoreRonda` usando `sabado.data.year`.
- `configuracao_deletar`: para cada `EscalaRonda`, decrementa
  `ScoreRonda(voluntario, sabado.data.year)` sem descer abaixo de 0; depois apaga.
- `HorarioRondaForm`: troca o widget de `ordem` por `local` (Select de
  `LocalRonda` ativos).

## Telas (templates)

Todas seguem o design system PCF (header navy `linear-gradient(135deg,#0f172a…)`,
primária `#fe8210`, curva via `::after` com `background:hsl(var(--background))`).

### Painel (`painel_ronda.html`)
- Resumo no topo: contadores por status (ex.: "2 pendentes de aprovação").
- Filtro por status (Pendente/Sorteada/Aprovada/Reprovada).
- Próxima ronda futura em destaque.
- Atalhos para **Locais** e **Ranking**.
- Cada card: sábado, tema, status, nº de linhas, botões **Ver/Sortear**,
  **Editar**, **Excluir**.

### Criar/Editar ronda (`form_configuracao.html`)
- Seletor de sábado (só em criar).
- Linhas dinâmicas: `Início` / `Fim` / `Local (select)` + botões
  **adicionar**, **duplicar linha**, **remover** (JS clona a linha e reindexa o
  formset, padrão já usado no projeto).
- Contador de confirmados do sábado selecionado (via disponibilidade).

### Detalhe (`detalhe_configuracao.html`)
- Agrupado por faixa de horário → local → 2 nomes.
- Ao lado de cada nome: **pontuação do ano** + **última ronda** (badge
  "nunca fez" / data / "faz tempo" > 45 dias), reusando a lógica do ranking.
- Aviso quando o nº de confirmados é insuficiente para preencher as linhas.
- Botões: **Editar**, **Excluir**, **Sortear/Re-sortear**, **Aprovar**,
  **Reprovar**, **Imprimir**. Troca de voluntário (swap) mantida.

### Locais (`locais_ronda.html` + `form_local.html`)
- Lista com nome, ativo, ações (editar/desativar/remover).
- Já existe no código; será exposto no painel e ajustado ao design.

### Imprimir (`imprimir_ronda.html`)
- Layout limpo (CSS `@media print`) com a escala do sábado para mural/envio.

## Fora de escopo (YAGNI)

- Notificação automática por e-mail aos escalados (pode ser um projeto futuro).
- Regras de rodízio além da pontuação (ex.: cotas por área).

## Testes

Cobrir em `ronda/tests.py`:
- Sorteio só considera confirmados (`vai_ao_projeto=True`) e respeita isentos.
- Sorteio não repete voluntário na mesma faixa de horário entre locais.
- Pontuação incrementa por `sabado.data.year` na aprovação.
- Excluir ronda aprovada estorna os pontos (sem ficar negativo).
- Janela de sábado inclui últimos 30 dias e exclui já configurados.
- Editar altera horários/locais e não permite trocar o sábado.
- Migração de dados converte grade antiga em linhas horário+local.
