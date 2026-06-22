# Sistema de Rondas — Design Spec

**Data:** 2026-06-22
**Autor:** Claude Code (revisado por vbasilioo)

---

## Visão Geral

Sistema de escala rotativa de voluntários para rondas nos sábados do PCF. A Tríade configura os horários de cada sábado, dispara o sorteio (automático toda sexta às 17h ou manual), revisa/troca voluntários, aprova e publica para todos verem.

O algoritmo garante equidade: voluntários com menor score (número de rondas feitas no ano) são sempre priorizados. Score reseta em 1º de janeiro de cada ano.

---

## Novo App Django: `ronda`

Localização: `ronda/` na raiz do projeto.
Prefixo de URL: `/ronda/`
Registrado em `INSTALLED_APPS` após `sabado`.

---

## Áreas Isentas (nunca entram no sorteio)

```python
AREAS_ISENTAS_RONDA = {'TRIADE', 'SUPPLY', 'RECREACAO', 'MARKETING'}
```

Voluntários dessas áreas são excluídos da pool mesmo que `data_saida__isnull=True`.

---

## Models (`ronda/models.py`)

### `LocalRonda`

Local físico onde ocorre a ronda.

| Campo   | Tipo                              | Notas                        |
|---------|-----------------------------------|------------------------------|
| `nome`  | `CharField(max_length=100)`       | Ex: "Brinquedoteca", "Campus", "Prédios" |
| `ativo` | `BooleanField(default=True)`      | Inativo = excluído do sorteio |
| `ordem` | `PositiveSmallIntegerField(default=0)` | Ordem de exibição       |

Seed inicial (migration): Brinquedoteca (ordem=1), Campus (ordem=2), Prédios (ordem=3).

`Meta.ordering = ['ordem', 'nome']`

---

### `ConfiguracaoRondaSabado`

Configuração da ronda para um sábado específico. Só pode existir uma por `Sabado`.

| Campo         | Tipo                                        | Notas                                    |
|---------------|---------------------------------------------|------------------------------------------|
| `sabado`      | `OneToOneField(sabado.Sabado, on_delete=CASCADE)` | Um sábado = uma configuração       |
| `status`      | `CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE_SORTEIO')` | Ver abaixo |
| `criado_por`  | `FK(Voluntario, SET_NULL, null=True)`       | Quem criou a configuração                |
| `criado_em`   | `DateTimeField(default=timezone.now)`       |                                          |
| `sorteado_em` | `DateTimeField(null=True, blank=True)`      | Quando o sorteio foi executado           |
| `aprovado_por`| `FK(Voluntario, SET_NULL, null=True, blank=True, related_name='rondas_aprovadas')` | |
| `aprovado_em` | `DateTimeField(null=True, blank=True)`      |                                          |
| `observacao`  | `TextField(blank=True)`                     | Motivo de reprovação ou notas            |

```python
STATUS_CHOICES = (
    ('PENDENTE_SORTEIO', 'Pendente de Sorteio'),
    ('SORTEADA',         'Sorteada — Aguardando Aprovação'),
    ('APROVADA',         'Aprovada'),
    ('REPROVADA',        'Reprovada'),
)
```

Fluxo de status:
```
PENDENTE_SORTEIO → SORTEADA → APROVADA
                            → REPROVADA → PENDENTE_SORTEIO (re-sortear)
```

---

### `HorarioRonda`

Faixa de horário dentro de uma configuração. Ex: 08h–09h, 11h–12h.

| Campo           | Tipo                                              | Notas                       |
|-----------------|---------------------------------------------------|-----------------------------|
| `configuracao`  | `FK(ConfiguracaoRondaSabado, on_delete=CASCADE, related_name='horarios')` | |
| `hora_inicio`   | `TimeField`                                       | Ex: 08:00                   |
| `hora_fim`      | `TimeField`                                       | Ex: 09:00                   |
| `ordem`         | `PositiveSmallIntegerField(default=0)`            | Ordem de exibição           |

`Meta.ordering = ['ordem', 'hora_inicio']`
`unique_together = ('configuracao', 'hora_inicio', 'hora_fim')`

---

### `EscalaRonda`

Resultado do sorteio: um voluntário em um horário+local específico.

| Campo           | Tipo                                              | Notas                                    |
|-----------------|---------------------------------------------------|------------------------------------------|
| `horario`       | `FK(HorarioRonda, on_delete=CASCADE, related_name='escalas')` |                        |
| `local`         | `FK(LocalRonda, on_delete=PROTECT)`               |                                          |
| `voluntario`    | `FK(Voluntario, on_delete=CASCADE, related_name='escalas_ronda')` |               |
| `is_substituto` | `BooleanField(default=False)`                     | True = inserido manualmente pela Tríade  |
| `voluntario_original` | `FK(Voluntario, SET_NULL, null=True, blank=True, related_name='escalas_substituidas')` | Quem foi trocado |
| `criado_em`     | `DateTimeField(default=timezone.now)`             |                                          |

`unique_together = ('horario', 'local', 'voluntario')`

Regra: máximo 2 voluntários por `(horario, local)` — validada no `clean()` do model e na view de swap.

Score é incrementado em `ConfiguracaoRondaSabado.aprovar()` para o `voluntario` de cada `EscalaRonda` (substituto leva o ponto, não o original).

---

### `ScoreRonda`

Acumulador anual de rondas feitas por voluntário.

| Campo        | Tipo                                             | Notas                                    |
|--------------|--------------------------------------------------|------------------------------------------|
| `voluntario` | `FK(Voluntario, on_delete=CASCADE, related_name='scores_ronda')` |               |
| `ano`        | `PositiveSmallIntegerField`                      | Ex: 2026                                 |
| `pontos`     | `PositiveSmallIntegerField(default=0)`           | Total de rondas feitas no ano            |

`unique_together = ('voluntario', 'ano')`

**Manipulação manual:** a Tríade pode editar `pontos` diretamente via tela de ranking/score.

Helper: `ScoreRonda.incrementar(voluntario, ano)` — `get_or_create` + `F('pontos') + 1`.

---

## Algoritmo de Sorteio

Executado por `ronda.sorteio.executar_sorteio(configuracao)` (função pura, testável).

```
Para cada HorarioRonda da ConfiguracaoRondaSabado (em ordem):
  Para cada LocalRonda ativo (em ordem):
    Já alocados neste horário ← set de voluntários já em EscalaRonda deste HorarioRonda
    Pool ← Voluntario.objects
              .filter(data_saida__isnull=True)
              .exclude(area__in=AREAS_ISENTAS_RONDA)
              .exclude(pk__in=já_alocados)
    Scores ← {vol.pk: ScoreRonda.get(vol, ano_atual).pontos ou 0 para vol em Pool}
    Pool ordenada ← sorted(Pool, key=lambda v: (Scores[v.pk], random()))
    Seleciona os 2 primeiros → cria EscalaRonda(horario, local, voluntario, is_substituto=False)

configuracao.status = 'SORTEADA'
configuracao.sorteado_em = timezone.now()
configuracao.save()
```

**Nota sobre aleatoriedade com equidade:** dentro do mesmo score, a ordem é aleatória. Isso é implementado embaralhando o queryset antes de ordenar pelo score (Python sort é estável, então a aleatoriedade dentro do grupo é preservada).

---

## URLs (`ronda/urls.py`) — prefixo `/ronda/`

### Área restrita (Tríade + superusuário)

| Name                          | URL                                          | View / descrição                              |
|-------------------------------|----------------------------------------------|-----------------------------------------------|
| `painel`                      | `painel/`                                    | Painel da Tríade: lista de configurações, atalhos |
| `ranking`                     | `ranking/`                                   | Tabela de todos os elegíveis com score e histórico |
| `score_editar`                | `score/<int:pk>/editar/`                     | Editar pontos de um ScoreRonda                |
| `locais`                      | `locais/`                                    | CRUD de LocalRonda                            |
| `local_criar`                 | `locais/novo/`                               |                                               |
| `local_editar`                | `locais/<int:pk>/editar/`                    |                                               |
| `local_deletar`               | `locais/<int:pk>/deletar/`                   |                                               |
| `configuracao_criar`          | `configuracoes/nova/`                        | Criar ConfiguracaoRondaSabado + HorarioRondas |
| `configuracao_detalhe`        | `configuracoes/<int:pk>/`                    | Ver escala, fazer swaps, aprovar/reprovar     |
| `configuracao_sortear`        | `configuracoes/<int:pk>/sortear/`            | POST — dispara o algoritmo                    |
| `configuracao_aprovar`        | `configuracoes/<int:pk>/aprovar/`            | POST — aprova e incrementa scores             |
| `configuracao_reprovar`       | `configuracoes/<int:pk>/reprovar/`           | POST — reprova (requer observacao)            |
| `escala_swap`                 | `escalas/<int:pk>/swap/`                     | POST — troca voluntário na EscalaRonda        |

### Área pública (todos os voluntários logados)

| Name             | URL              | View / descrição                                              |
|------------------|------------------|---------------------------------------------------------------|
| `ronda_publica`  | `sabado/`        | Lista das configurações aprovadas; a mais recente em destaque |

---

## Permissões

```python
RONDA_GESTAO = {'TRIADE'}  # + is_superuser
```

- Área restrita: `area='TRIADE'` ou `is_superuser` → `PermissionDenied` caso contrário
- Área pública (`ronda_publica`): qualquer voluntário logado

---

## Views detalhadas

### `PainelRondaView` (LoginRequired, TemplateView)
- Permissão: RONDA_GESTAO
- Contexto: lista de `ConfiguracaoRondaSabado` ordenadas por `sabado__data DESC`
- Mostra status com badge colorido por status
- Atalho para criar nova configuração

### `RankingRondaView` (LoginRequired, ListView)
- Permissão: RONDA_GESTAO
- Lista todos os voluntários elegíveis (sem áreas isentas, `data_saida__isnull=True`)
- Anota `score_atual` = `ScoreRonda.pontos` do ano corrente (0 se não existe)
- Anota `ultima_ronda` = data do último sábado em que foi escalado e aprovado
- Filtro por área via GET param `?area=`
- Badge visual: verde (≥1 ronda), cinza ("Nunca fez"), laranja (última há >30 dias)

### `ScoreEditarView` (LoginRequired, UpdateView)
- Permissão: RONDA_GESTAO
- Edita apenas o campo `pontos` de `ScoreRonda`
- Cria o registro se não existir (via `get_or_create`)

### CRUD `LocalRonda`
- Permissão: RONDA_GESTAO
- Padrão idêntico ao CRUD de `Categoria` em `adm`

### `ConfiguracaoRondaCriarView` (LoginRequired, View)
- Permissão: RONDA_GESTAO
- Formulário inline: seleciona `Sabado` (só futuros sem configuração existente) + adiciona N `HorarioRonda` via formset
- Salva com `status='PENDENTE_SORTEIO'`

### `ConfiguracaoRondaDetalheView` (LoginRequired, TemplateView)
- Permissão: RONDA_GESTAO
- Exibe a grade completa: linhas = HorarioRonda, colunas = LocalRonda, células = 2 voluntários
- Para cada voluntário: nome, área, score atual
- Botão de swap por célula (abre inline select de substituto)
- Botões de Aprovar / Reprovar (POST, disabled se status ≠ SORTEADA)
- Botão "Re-sortear" se status = REPROVADA ou PENDENTE_SORTEIO

### `SortearView` (LoginRequired, View — POST only)
- Permissão: RONDA_GESTAO
- Guarda: `configuracao.status in ('PENDENTE_SORTEIO', 'REPROVADA')`
- Deleta EscalaRonda existentes da configuração
- Chama `executar_sorteio(configuracao)`
- Redireciona para `configuracao_detalhe`

### `AprovarRondaView` (LoginRequired, View — POST only)
- Permissão: RONDA_GESTAO
- Guarda: `status == 'SORTEADA'`
- Para cada `EscalaRonda`: `ScoreRonda.incrementar(escala.voluntario, ano_atual)`
- `configuracao.status = 'APROVADA'`, `aprovado_por`, `aprovado_em`
- Redireciona para `configuracao_detalhe`

### `ReprovarRondaView` (LoginRequired, View — POST only)
- Permissão: RONDA_GESTAO
- Guarda: `status == 'SORTEADA'`
- `observacao` obrigatória (igual ao padrão de RejeitarReembolsoView)
- `configuracao.status = 'REPROVADA'`

### `EscalaSwapView` (LoginRequired, View — POST only)
- Permissão: RONDA_GESTAO
- Recebe `voluntario_novo_pk` do POST
- Valida: novo voluntário é elegível, não está já neste horário
- Atualiza `EscalaRonda`: `voluntario_original = escala.voluntario`, `voluntario = novo`, `is_substituto = True`
- Não incrementa score aqui — score só sobe na aprovação

### `RondaPublicaView` (LoginRequired, ListView)
- Acessível a todos os voluntários logados
- Lista `ConfiguracaoRondaSabado.objects.filter(status='APROVADA').order_by('-sabado__data')`
- A mais recente fica em destaque no topo (card expandido)
- As demais ficam como histórico compactado

---

## Sorteio Automático (Sexta 17h)

Management command: `python manage.py sortear_rondas`

Lógica:
1. Verifica se hoje é sexta-feira
2. Busca `ConfiguracaoRondaSabado` com `status='PENDENTE_SORTEIO'` cujo `sabado.data` é o próximo sábado
3. Se encontrar e tiver pelo menos 1 `HorarioRonda` cadastrado → executa `executar_sorteio(configuracao)`
4. Se não encontrar configuração → loga aviso, não falha

Agendamento no PythonAnywhere: **Scheduled Task** configurada para rodar toda sexta às 17h:
```
/home/pcf/virtualenv/.../bin/python /home/pcf/pcf.pythonanywhere.com/manage.py sortear_rondas
```

---

## Navbar

### Menu "Mais" (desktop) — nova entrada visível para todos:
```html
{% if ronda_aprovada_recente %}
<a class="pcf-dd-item" href="{% url 'ronda:ronda_publica' %}">
  Rondas do Sábado
</a>
{% endif %}
```

Exibida apenas quando houver pelo menos uma ronda aprovada. Avaliado via context processor ou verificação na view base.

### Menu "Mais" — entrada restrita (Tríade/superuser):
```html
{% if user.is_superuser or user.area == 'TRIADE' %}
<a class="pcf-dd-item" href="{% url 'ronda:painel' %}">
  Gestão de Rondas
</a>
{% endif %}
```

---

## Templates

### Área restrita (`ronda/templates/`)

| Template                      | Descrição                                                                 |
|-------------------------------|---------------------------------------------------------------------------|
| `painel_ronda.html`           | Lista de configurações com status badges, botão nova configuração         |
| `ranking_ronda.html`          | Tabela de voluntários elegíveis com score, última ronda, badges visuais   |
| `form_score.html`             | Editar pontos de um voluntário                                            |
| `locais_ronda.html`           | Lista de locais com Editar/Ativar/Desativar                               |
| `form_local.html`             | Criar/editar local                                                        |
| `form_configuracao.html`      | Criar configuração: select Sábado + formset de horários                   |
| `detalhe_configuracao.html`   | Grade horário × local, swaps inline, botões aprovar/reprovar/re-sortear  |

### Área pública

| Template              | Descrição                                                                 |
|-----------------------|---------------------------------------------------------------------------|
| `ronda_publica.html`  | Ronda mais recente em destaque (grade completa), histórico abaixo         |

---

## Testes (`ronda/tests.py`)

| Classe de teste                     | O que verifica                                                     |
|-------------------------------------|--------------------------------------------------------------------|
| `LocalRondaModelTest`               | CRUD básico, seed                                                  |
| `ScoreRondaIncrementarTest`         | `incrementar()` cria e soma corretamente                           |
| `SorteioAlgoritmoTest`              | Score 0 antes de score 1, área isenta excluída, max 2 por célula   |
| `SorteioEquidadeTest`               | Com 6 vol score 0 e 1 vol score 1: vol score 1 fica por último     |
| `SorteioSemElegiveisSuficientesTest`| Menos de 6×N elegíveis → sorteia quem tem, não quebra             |
| `AprovarRondaViewTest`              | Aprovação incrementa scores dos voluntários escalados              |
| `ReprovarRondaViewTest`             | Reprovação sem motivo não reprova; com motivo → REPROVADA          |
| `SwapViewTest`                      | Swap válido atualiza voluntario_original; inelegível → 400         |
| `RondaPublicaPermissaoTest`         | Qualquer logado vê; não-logado → redirect login                    |
| `PainelPermissaoTest`               | Tríade e superuser acessam; outras áreas → 403                     |
| `SortearCommandTest`                | Command em dia não-sexta não executa; em sexta executa             |

---

## Convenções de CSS

- Templates da área restrita: classes prefixadas `rd-` em blocos `<style>` auto-contidos
- Header dark navy: `linear-gradient(135deg,#0f172a 0%,#1e293b 55%,#0f3460 100%)`
- Cor primária: `#fe8210`
- Badges de status:
  - `PENDENTE_SORTEIO` → cinza
  - `SORTEADA` → azul
  - `APROVADA` → verde
  - `REPROVADA` → vermelho
- Badges de score no ranking:
  - 0 rondas → `badge-secondary` ("Nunca fez")
  - ≥1 ronda → `badge-success` ("N rondas")
  - Última ronda há >45 dias → `badge-warning` + data
