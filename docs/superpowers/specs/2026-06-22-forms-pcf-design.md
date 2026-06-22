# Forms PCF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o módulo `forms_pcf` com dois formulários (Feedback Anônimo de Área e Pedido de Reembolso), caixas de entrada por permissão, fluxo de aprovação/rejeição de reembolsos com criação automática de `Lancamento`, e gestão de receptores de e-mail.

**Architecture:** Novo Django app `forms_pcf` com seus próprios models, views, forms e templates. Integra com `adm.Lancamento` (aprovação de reembolso cria lançamento do tipo DESPESA com origem=REEMBOLSO) e com o sistema de e-mail existente. O app `adm` recebe um card "Reembolsos" no painel e uma tela de gestão de receptores.

**Tech Stack:** Django 4.2, Python, HTML/CSS (PCF design system — dark navy header, fin- prefixed classes, Bootstrap 5, shadcn/ui CSS vars), e-mail via Django `send_mail`, `FileField` para comprovantes (MEDIA_ROOT).

---

## Global Constraints

- Todos os templates estendem `base.html` e usam o PCF design system: header `linear-gradient(135deg,#0f172a 0%,#1e293b 55%,#0f3460 100%)`, wave ellipse `clip-path:ellipse(55% 100% at 50% 100%)`, cor primária `#fe8210`, fonte Inter, CSS vars `hsl(var(--background))` / `hsl(var(--card))` / `hsl(var(--border))` / `hsl(var(--foreground))` / `hsl(var(--muted-foreground))` / `hsl(var(--accent))`
- Classes CSS prefixadas com `fp-` (forms_pcf) em blocos `<style>` auto-contidos por template
- Acesso requer login (`@login_required` ou `LoginRequiredMixin`) em todas as URLs do módulo
- Timezone: sempre `timezone.now()`, nunca `datetime.now()`; `USE_TZ = True`
- Custom user model: `voluntario.Voluntario` — importar de lá, nunca do `auth.User`
- Área dos voluntários definida em `voluntario.models.LISTA_AREAS`
- Comprovantes salvos em `MEDIA_ROOT` (já configurado); usar `FileField`
- E-mail via `django.core.mail.send_mail` com `settings.EMAIL_HOST_USER` como remetente
- Língua: todo texto de UI, modelos e comentários em português brasileiro
- `adm.Lancamento.ORIGEM_CHOICES` deve incluir `('REEMBOLSO', 'Reembolso')` — adicionar neste projeto

---

## Permissões

| Recurso | Quem acessa |
|---|---|
| Enviar feedback anônimo | Qualquer voluntário logado |
| Enviar pedido de reembolso | Qualquer voluntário logado |
| Inbox de feedbacks | `area='PROJETOS'` + `area='TRIADE'` + superusuário |
| Inbox / aprovação de reembolsos | `area='ADM/FIN'` + superusuário |
| Gestão de receptores de e-mail | `area='ADM/FIN'` + superusuário |
| Card "Reembolsos" no painel ADM | `area='ADM/FIN'` + superusuário |

---

## Models (`forms_pcf/models.py`)

### `FeedbackArea`
| Campo | Tipo | Notas |
|---|---|---|
| `area` | `CharField(max_length=30, choices=LISTA_AREAS)` | Área que relata a dor |
| `descricao` | `TextField` | Texto livre da dor/problema |
| `criado_em` | `DateTimeField(default=timezone.now)` | Sem `criado_por` — garante anonimato |

### `PedidoReembolso`
| Campo | Tipo | Notas |
|---|---|---|
| `solicitante` | `FK(Voluntario, on_delete=SET_NULL, null=True)` | Quem solicitou |
| `valor` | `DecimalField(max_digits=10, decimal_places=2)` | |
| `descricao` | `TextField` | Descrição do gasto |
| `data_gasto` | `DateField` | Data em que o gasto ocorreu |
| `categoria` | `FK(adm.Categoria, on_delete=PROTECT)` | Filtrado para tipo=DESPESA no form |
| `comprovante` | `FileField(upload_to='reembolsos/')` | Obrigatório |
| `status` | `CharField(max_length=15, choices=STATUS_CHOICES, default='PENDENTE')` | PENDENTE / APROVADO / REJEITADO |
| `observacao_adm` | `TextField(blank=True)` | Motivo de rejeição |
| `aprovado_por` | `FK(Voluntario, null=True, blank=True, related_name='reembolsos_aprovados')` | |
| `aprovado_em` | `DateTimeField(null=True, blank=True)` | |
| `lancamento` | `OneToOneField(adm.Lancamento, null=True, blank=True, on_delete=SET_NULL)` | Criado na aprovação |
| `criado_em` | `DateTimeField(default=timezone.now)` | |

`STATUS_CHOICES = (('PENDENTE','Pendente'),('APROVADO','Aprovado'),('REJEITADO','Rejeitado'))`

### `ReceptorNotificacaoReembolso`
| Campo | Tipo | Notas |
|---|---|---|
| `email` | `EmailField(unique=True)` | |
| `nome` | `CharField(max_length=100)` | Para exibição |
| `ativo` | `BooleanField(default=True)` | Só ativos recebem e-mail |

---

## URLs (`forms_pcf/urls.py`) — prefixo `/forms/`

| Name | URL | View |
|---|---|---|
| `feedback` | `feedback/` | `EnviarFeedbackView` |
| `feedback_sucesso` | `feedback/sucesso/` | template estático |
| `feedback_inbox` | `feedback/inbox/` | `FeedbackInboxView` |
| `reembolso` | `reembolso/` | `EnviarReembolsoView` |
| `reembolso_sucesso` | `reembolso/sucesso/` | template estático |
| `reembolso_inbox` | `reembolso/inbox/` | `ReembolsoInboxView` |
| `reembolso_aprovar` | `reembolso/<int:pk>/aprovar/` | `AprovarReembolsoView` |
| `reembolso_rejeitar` | `reembolso/<int:pk>/rejeitar/` | `RejeitarReembolsoView` |

### URLs em `/adm/` (adicionadas a `adm/urls.py`)

| Name | URL | View |
|---|---|---|
| `receptores_reembolso` | `notificacoes-reembolso/` | `ReceptoresReembolsoView` |
| `receptor_criar` | `notificacoes-reembolso/novo/` | `ReceptorFormView` |
| `receptor_editar` | `notificacoes-reembolso/<int:pk>/editar/` | `ReceptorFormView` |
| `receptor_deletar` | `notificacoes-reembolso/<int:pk>/deletar/` | `ReceptorDeleteView` |

---

## Views

### `EnviarFeedbackView` (LoginRequired, FormView)
- Form: `FeedbackAreaForm` (campos: `area`, `descricao`)
- Salva `FeedbackArea` — **sem** registrar `request.user` (anonimato)
- Redireciona para `forms_pcf:feedback_sucesso`

### `FeedbackInboxView` (LoginRequired, ListView)
- Permissão: `area in ['PROJETOS','TRIADE']` ou `is_superuser`; senão `PermissionDenied`
- Lista `FeedbackArea` ordenados por `-criado_em`
- Exibe: área (badge colorido por área), data, preview da descrição; clique expande o texto completo (sem página separada — toggle inline)

### `EnviarReembolsoView` (LoginRequired, FormView)
- Form: `PedidoReembolsoForm` (campos: `valor`, `descricao`, `data_gasto`, `categoria`, `comprovante`)
  - `categoria` QuerySet filtrado: `Categoria.objects.filter(tipo='DESPESA', ativo=True)`
  - `comprovante` obrigatório
- Salva `PedidoReembolso` com `solicitante=request.user`, `status='PENDENTE'`
- Após salvar: dispara e-mail para todos `ReceptorNotificacaoReembolso.objects.filter(ativo=True)`
  - Assunto: `"[PCF] Novo pedido de reembolso — R$ {valor}"`
  - Corpo: nome do solicitante, área, valor, data do gasto, descrição, link para inbox
- Redireciona para `forms_pcf:reembolso_sucesso`

### `ReembolsoInboxView` (LoginRequired, ListView)
- Permissão: `area='ADM/FIN'` ou `is_superuser`; senão `PermissionDenied`
- Filtra por `status` via query param `?status=PENDENTE` (default: PENDENTE)
- Exibe tabs: Pendentes / Aprovados / Rejeitados com contagens
- Cada linha: solicitante, área do solicitante, valor, data gasto, data envio, link comprovante, botões Aprovar/Rejeitar (só para PENDENTE)

### `AprovarReembolsoView` (LoginRequired, View — POST only)
- Permissão: `area='ADM/FIN'` ou `is_superuser`
- Busca `PedidoReembolso` com `status='PENDENTE'`; senão 404
- Cria `adm.Lancamento`:
  - `tipo` derivado da categoria (DESPESA)
  - `categoria` = pedido.categoria
  - `valor` = pedido.valor
  - `data` = `timezone.now().date()`
  - `descricao` = f"Reembolso: {pedido.descricao}"
  - `origem` = `'REEMBOLSO'`
  - `criado_por` = `request.user`
- Atualiza pedido: `status='APROVADO'`, `aprovado_por=request.user`, `aprovado_em=timezone.now()`, `lancamento=lancamento`
- Redireciona para `forms_pcf:reembolso_inbox`

### `RejeitarReembolsoView` (LoginRequired, View — POST only)
- Permissão: `area='ADM/FIN'` ou `is_superuser`
- Recebe `observacao_adm` do POST (obrigatório — valida no frontend e backend)
- Atualiza pedido: `status='REJEITADO'`, `observacao_adm=...`, `aprovado_por=request.user`, `aprovado_em=timezone.now()`
- Redireciona para `forms_pcf:reembolso_inbox`

### Views de gestão de receptores (`adm/views.py`)
- `ReceptoresReembolsoView`: lista todos os `ReceptorNotificacaoReembolso`
- `ReceptorFormView`: cria ou edita (detecta `pk` na URL)
- `ReceptorDeleteView`: confirmação de remoção
- Permissão: `area='ADM/FIN'` ou `is_superuser`

---

## Alteração em `adm/models.py`

Adicionar `('REEMBOLSO', 'Reembolso')` em `ORIGEM_CHOICES`:

```python
ORIGEM_CHOICES = (
    ('MANUAL', 'Manual'),
    ('SUPPLY', 'Supply'),
    ('REEMBOLSO', 'Reembolso'),
)
```

Gerar e aplicar migration correspondente.

---

## Painel ADM (`adm/templates/painel_adm.html`)

Adicionar um 5º card de ação rápida "Reembolsos" abaixo dos 4 existentes (ou expandir o grid para 2×3):
- Cor: azul (`#0ea5e9` / `#0284c7`)
- Ícone: recibo/dinheiro
- Descrição: "Aprovar ou rejeitar pedidos de reembolso dos voluntários"
- Link para `forms_pcf:reembolso_inbox`
- Badge com contagem de pendentes (`PedidoReembolso.objects.filter(status='PENDENTE').count()`)

---

## Templates

### `forms_pcf/templates/`

| Template | Descrição |
|---|---|
| `feedback_form.html` | Formulário clean: header dark navy, select de área + textarea, botão laranja |
| `feedback_sucesso.html` | Página de confirmação: ícone check, mensagem de agradecimento, link para início |
| `feedback_inbox.html` | Lista de feedbacks: badge de área, data, texto expansível por toggle JS |
| `reembolso_form.html` | Formulário: valor, descrição, data, categoria (select), upload de comprovante |
| `reembolso_sucesso.html` | Confirmação de envio com aviso de prazo |
| `reembolso_inbox.html` | Tabs Pendente/Aprovado/Rejeitado, ações Aprovar/Rejeitar inline |
| `reembolso_rejeitar_modal.html` | Inline form colapsável (toggle JS) com campo obrigatório de motivo — sem modal separado |

### `adm/templates/` (novos)

| Template | Descrição |
|---|---|
| `receptores_reembolso.html` | Lista de receptores com status ativo/inativo, Editar/Remover |
| `form_receptor.html` | Formulário: nome, email, ativo (checkbox) |

---

## Registro em `INSTALLED_APPS` e `urls.py`

- Adicionar `'forms_pcf'` em `INSTALLED_APPS` (`TESTE/settings.py`)
- Adicionar `path('forms/', include('forms_pcf.urls', namespace='forms_pcf'))` em `TESTE/urls.py`

---

## Testes (`forms_pcf/tests.py`)

- `FeedbackAreaModelTest`: salvar feedback sem usuário, verificar ausência de `criado_por`
- `EnviarFeedbackViewTest`: POST válido → cria `FeedbackArea`, redireciona para sucesso
- `FeedbackInboxPermissionTest`: PROJETOS vê, TRIADE vê, superuser vê, outros → 403
- `PedidoReembolsoModelTest`: campos obrigatórios, status default PENDENTE
- `EnviarReembolsoViewTest`: POST com arquivo → cria pedido, dispara e-mail (mock `send_mail`)
- `AprovarReembolsoViewTest`: aprovação → cria `Lancamento` com origem=REEMBOLSO, status=APROVADO
- `RejeitarReembolsoViewTest`: rejeição sem motivo → não rejeita; com motivo → status=REJEITADO
- `ReembolsoInboxPermissionTest`: ADM/FIN vê, superuser vê, outros → 403
- `ReceptorNotificacaoTest`: só receptores ativos recebem e-mail
