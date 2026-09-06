# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Projeto Criança Feliz** — a community program management system tracking volunteers, attendees (children), weekly activities, Saturday events, and supplies. Hosted on PythonAnywhere at `pcf.pythonanywhere.com`.

## Commands

### Django (Python backend)
```bash
python manage.py runserver          # Start dev server on localhost:8000
python manage.py migrate            # Apply migrations
python manage.py makemigrations     # Generate migrations from model changes
python manage.py collectstatic      # Gather static files (production)
python manage.py test               # Run all tests
python manage.py test <app>         # Run tests for a specific app
python manage.py shell              # Interactive Django shell

# Management commands
python manage.py lembrete_disponibilidade   # Daily: email + push to volunteers who haven't answered the poll (--dry-run available)
python manage.py gerar_chaves_vapid         # One-off: generate the VAPID key pair for push (run on the server)
python manage.py seed_sabado                # Seed Saturday event data
python manage.py seed_admin                 # Seed admin volunteer user
```

### Frontend (Next.js + shadcn/ui)
```bash
npm install       # Install dependencies
npm run dev       # Start Next.js dev server
npm run build     # Production build
npm run lint      # ESLint
```

## Environment Setup

Requires a `.env` file (loaded via `python-decouple`) with:
- `SECRET_KEY`
- `DATA_BASE_ENGINE`, `DATA_BASE_NAME`, `DATA_BASE_USER`, `DATA_BASE_PASSWORD`, `DATA_BASE_HOST`, `DATA_BASE_PORT`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`

## Architecture

### Django Project Config
- **Project package**: `TESTE/` (settings, urls, wsgi, asgi, root views)
- **Custom user model**: `voluntario.Voluntario` (extends `AbstractUser`) — set in `AUTH_USER_MODEL`
- **Login**: Django's built-in `LoginView` → redirects to `inicio`; root `/` redirects to `/login/`
- **Custom context processor**: `atendido.novos_context.atendidos_filtrados` — available in all templates
- **Session**: 90-day cookie, persists across browser close (`SESSION_EXPIRE_AT_BROWSER_CLOSE = False`)
- **Timezone**: `America/Sao_Paulo`; `USE_TZ = True` — use `timezone.now()` not `datetime.now()` for **datetimes**, and `timezone.localdate()` not `timezone.now().date()` for **dates**. `timezone.now()` is UTC, so `.date()` on it rolls over to tomorrow after 21:00 local — which silently shifts anything comparing "today" to a date field (poll deadlines, scheduled commands, dashboards). Several call sites still use the wrong form; fix them as you touch them.

### Django Apps

| App | Responsibility |
|-----|---------------|
| `atendido` | Attendees (children), families, guardians, attendance |
| `voluntario` | Volunteers (custom user), talents, occurrences/discipline, attendance |
| `semanario` | Weekly activity plans per room, activities, materials, competencies |
| `sabado` | Saturday event dates, themes, volunteer availability polls |
| `supply` | Inventory items, stock movements, purchase orders |

### Key Model Relationships
- `Atendido` → `Familia` → `ResponsavelAtendido`
- `AtendidoInclusivo` extends `Atendido` (one-to-one, special needs detail)
- `PresencaAtendido` / `PresencaVoluntario` track attendance per `Sabado`
- `Semanario` groups `Atividade` records (with `Material` and `competencia` fields) by room and `Sabado`
- `Atividade.save()` auto-computes `dimensao_competencia` from the competency-to-dimension map in `semanario/models.py`
- `Movimentacao` records stock changes for `Item`; `Item.quantidade_atual` is computed from movement history
- `Voluntario` has `area` (choice field) and `talentos` (many-to-many with `Talento`)
- `DisponibilidadeVoluntario` records each volunteer's answer to the `Sabado` availability poll (`unique_together = ("sabado", "voluntario")`)
- `Ocorrencia` is the disciplinary record (alerta/advertência/suspensão) with soft delete (`deleted_at`, `deleted_by`)
- `Regra` is the admin-managed rule catalog; `Ocorrencia.REGRAS` is a hardcoded choice list in the model

### Active Volunteer Definition
Volunteers are **active** when `data_saida__isnull=True` (departure date not set). `is_active` from `AbstractUser` exists separately — filter on `data_saida` for program logic, `is_active` for auth/login.

### Auto-Alert System
When a volunteer is marked absent (`AUSENTE`) via the attendance registration view, a daemon thread calls `verificar_faltas_e_gerar_alertas(voluntario, sabado, registrado_por)`. This function (in `voluntario/views.py`) automatically creates `Ocorrencia` records and sends emails for consecutive absences (rule AL13). Reset logic fires when the volunteer is present.

### Access Control for Attendance Registration
Only volunteers in `TRIADE` or `GESTAO_DE_TALENTOS` areas can register volunteer attendance at `/voluntario/presencas/`. This is enforced in `RegistrarPresencasVoluntarios` view.

### Sabado Availability Poll
`Sabado.enquete_aberta` (property) returns `True` if today is before `data - 1 day` — this is the **single** closing rule; the view, the home page and the reminder command all consult it. The management command `lembrete_disponibilidade` runs **daily** while the poll is open, emailing and pushing to non-responders of the *nearest* open Saturday only. It takes `--dry-run`.

Creating a `Sabado` in the Django admin pushes a notification to every active volunteer (`SabadoAdmin.save_model`) — that is what "opening the form" means, since there is no create view.

### Frontend
The Django app uses standard HTML templates (`/templates/`) with:
- `base.html` as the root layout
- `navbar.html` / `footer.html` as partials
- App-specific templates under each app's `templates/` directory
- Static assets in `/static/` (images, JS, admin overrides)
- `semanario/views_ajax.py` handles AJAX endpoints for the semanario planner

A separate **Next.js 16 + React 19 + TailwindCSS 4 + shadcn/ui** frontend is also present (package.json at root). It uses Radix UI, Recharts, React Hook Form + Zod, and date-fns.

### Data Import/Export
`django-import-export` is installed and enabled for bulk Excel/CSV operations on `Atendido`, `Familia`, `ResponsavelAtendido`, and `AtendidoInclusivo` via the Django admin.

## Notificações push (PWA)

O app `notificacoes` implementa Web Push via VAPID. **O push só funciona se as
três variáveis estiverem no `.env` do servidor** — sem elas `enviar_push` devolve
0 e grava um aviso no log, sem erro visível em tela.

Ordem obrigatória para ligar (a segunda depende da primeira):

1. `pip install -r requirements.txt` no virtualenv da web app — `gerar_chaves_vapid`
   importa `py_vapid`, que vem junto do `pywebpush`.
2. `python manage.py gerar_chaves_vapid` **no servidor**, e colar as três linhas
   no `.env`. Gerar de novo invalida TODAS as inscrições e obriga cada voluntário
   a reativar as notificações no aparelho.
3. `migrate`, `collectstatic --noinput`, Reload.
4. Uma **Scheduled Task diária** chamando `manage.py lembrete_disponibilidade`.
   Sem ela o lembrete da enquete nunca roda. Use `--dry-run` para conferir antes.

Gatilhos ligados hoje: abertura da enquete (`SabadoAdmin.save_model`), lembrete
diário da enquete (comando), novo pedido de reembolso e reembolso aprovado
(`forms_pcf/views.py`), ronda aprovada (`ronda/views.py`), ocorrências
(`voluntario/views.py`), pedido de material (`supply/views.py`) e avisos manuais.

Regras que já custaram bug:
- Comando agendado usa `enviar_push` **síncrono**; view usa `enviar_push_async`.
  Thread daemon morre junto com o processo do comando.
- O import de `notificacoes.services` dentro de views/admin é **local**, não no
  topo: no topo ele entra na cadeia de carregamento dos apps e uma dependência
  faltando derruba o site inteiro.
- `tag` igual **substitui** a notificação anterior na bandeja. Use tag por
  registro (`reembolso-{pk}`) quando cada evento importa, e tag fixa por assunto
  (`enquete-{pk}`) quando o novo aviso deve mesmo substituir o antigo.
- O service worker é `templates/sw.js`, servido pelo Django — **não** está em
  `/static/`. Editá-lo exige bumpar `const VERSAO`, não `collectstatic`.

## Conventions

- Language: All UI, models, and code comments are in **Brazilian Portuguese**
- Room system: Attendees and `Semanario` plans belong to one of 7 color-coded rooms (VIOLETA → VERMELHO) plus "Família Feliz"; the room choices (`LISTA_SALAS`) are defined in both `atendido/models.py` and `semanario/models.py`
- Volunteer areas: 7 program rooms + MARKETING, ADM/FIN, CR/RE, EVENTOS, GESTAO_DE_TALENTOS, RECREACAO, SUPPLY, PROJETOS, TRIADE (`LISTA_AREAS` in `voluntario/models.py`)
- Competency framework: Activities map to competencies defined per room in `COMPETENCIAS_SALAS`, which roll up to 7 developmental dimensions in `DIMENSOES_COMPETENCIAS` (`semanario/models.py`)
- Soft delete: `Ocorrencia` records are never hard-deleted; use `soft_delete(deleted_by)` and filter `deleted_at__isnull=True` for active records
- Media uploads: Volunteer/attendee profile photos and activity photos stored in `MEDIA_ROOT` (`BASE_DIR/media/`)
