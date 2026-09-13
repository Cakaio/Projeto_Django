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
python manage.py importar_acervo <pasta>    # Importa uma arvore de pastas para o Acervo (--dry-run, --resumo, --somente)
python manage.py sincronizar_acervo_drive   # Daily: traz do Google Drive o que ainda nao esta no Acervo (--dry-run)
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

## Acervo ← Google Drive

O Acervo se enche por dois caminhos, e os dois usam as MESMAS regras
(`acervo/importacao.py`) — não existe um jeito pelo botão e outro pelo comando.

**Pasta local** (`importar_acervo`): baixe a pasta do Drive como .zip, e rode.
Serve para migração e para lote vindo de qualquer lugar. Tem `--dry-run`,
`--resumo`, `--somente`.

**Sincronização automática** (`sincronizar_acervo_drive`, e o botão "Trazer do
Drive" na tela do acervo): o Django lê o Drive direto. Incremental —
`Documento.origem_drive_id` guarda o ID do arquivo no Drive, então o que já
entrou nunca volta, mesmo que alguém renomeie ou mova o arquivo lá.

Em ambos, cada subpasta do primeiro nível vira uma Coleção.

**Dois modos de autenticação.** A escolha depende de uma coisa só: quem
configura tem direito de COMPARTILHAR a pasta do Drive?

*Conta de serviço* — o PCF é uma identidade própria; alguém precisa compartilhar
a pasta com o e-mail dela. Preferível quando possível: não depende de nenhuma
pessoa continuar no projeto.

*OAuth de usuário* — o PCF lê o Drive COMO uma pessoa, com a permissão que ela
já tem. É a saída quando a pasta é da organização e quem configura consegue LER
mas não consegue COMPARTILHAR (o Google mostra "Pedir para compartilhar" no
diálogo, e `files.get` no ID da pasta devolve 404 para a conta de serviço).
Custo: o acesso morre se a pessoa sair da organização ou revogar a permissão.

Se as duas estiverem no `.env`, a conta de serviço vence.

Para ligar com CONTA DE SERVIÇO:

1. Google Cloud Console: criar projeto, ativar a **Google Drive API**, criar uma
   **conta de serviço** e baixar o JSON da chave.
2. Compartilhar a pasta do Drive com o e-mail dela, como **Leitor**.
3. Subir o JSON para o servidor, FORA do repositório, e no `.env`:
   `ACERVO_DRIVE_CREDENCIAIS=/home/pcf/segredos/drive.json`
   `ACERVO_DRIVE_PASTA_ID=<o trecho depois de /folders/ na URL da pasta>`

Para ligar com OAUTH:

1. Google Cloud Console: ativar a **Google Drive API** e criar um **OAuth client
   ID** do tipo "App para computador"; baixar o JSON.
2. Na MÁQUINA de quem tem acesso à pasta (precisa de navegador):
   `python manage.py autorizar_acervo_drive client_secret.json`
3. Colar as três linhas `ACERVO_DRIVE_OAUTH_*` que ele imprime no `.env` do
   servidor, junto com `ACERVO_DRIVE_PASTA_ID`.

**Publique a tela de consentimento OAuth ("In production").** Em "Testing", o
Google expira o refresh token em 7 dias e a sincronização para sozinha toda
semana, sem erro visível.

Depois, em qualquer um dos modos:

4. `pip install -r requirements.txt`, `migrate`, Reload.
5. `manage.py sincronizar_acervo_drive --verificar` — diagnostica a conexão.
6. Scheduled Task diária: `manage.py sincronizar_acervo_drive`.

`ACERVO_DRIVE_IGNORAR` no `.env` (nomes separados por vírgula) exclui pastas de
vez. Precisa ser configuração, e não flag: o botão da tela e a tarefa agendada
não passam flag nenhuma, então uma exclusão feita só no comando seria desfeita
na primeira rodada automática. `--exceto` exclui só naquela rodada. A exclusão
permanente vence o `--somente`.

A sincronização aceita **só documento e planilha** (`FORMATOS_DE_DOCUMENTO` em
`acervo/importacao.py`), diferente do formulário manual, que aceita imagem. A
diferença tem razão: no formulário uma pessoa escolhe cada arquivo e sabe que
aquela foto é a ficha digitalizada; na varredura automática de um Drive de
trabalho, "imagem" é foto de evento aos milhares — no acervo real eram 5,9 GB
numa pasta só. `ACERVO_DRIVE_FORMATOS` no `.env` sobrepõe a lista.

`--pasta` e `ACERVO_DRIVE_PASTA_ID` aceitam a URL inteira do Drive, não só o ID:
`l` e `1` são indistinguíveis a olho nu num ID, e digitá-lo à mão já gerou um
404 que parecia problema de permissão.

Decisões que já custaram pensamento:
- **`origem_drive_id` é `null=True`, não string vazia.** `unique` trata strings
  vazias como iguais, e dois documentos cadastrados na tela colidiriam.
- **O ano nunca é chutado.** Sai de um número de 4 dígitos no nome do arquivo e
  depois nas pastas acima. Sem achar, o arquivo é pulado — a data de upload do
  Drive é de quando alguém mexeu no arquivo, não do documento.
- **`Documento.clean()` exige dizer de quem é o documento.** Veio da coleção de
  postulações e não generaliza: a sincronização preenche com o nome do projeto.
  Se o acervo passar a guardar muita coisa que não é de ninguém, o certo é
  relaxar a regra por coleção, não seguir preenchendo.
- **`arquivos_da_arvore` carrega os nomes das pastas** de cada arquivo. Sem
  isso, "Postulações/2023/joao.pdf" perderia o ano, que está na pasta do meio.
- **`supportsAllDrives` e `includeItemsFromAllDrives`** na listagem: sem os dois,
  pasta em Drive compartilhado volta VAZIA, sem erro nenhum.
- **O que os testes não cobrem:** autenticação real, exportação de Google Docs
  pela API de verdade, paginação com muitos arquivos e Drive compartilhado.
  `acervo/tests_drive.py` usa um dublê; essas partes só se provam no servidor.

## Bazar (distribuicao de roupa por pontos)

App `bazar`. Substitui ficha e dinheiro ficticio: cada atendido recebe uma cota
de pontos, cada categoria de peca custa pontos, e a tela de atendimento faz a
conta enquanto o voluntario marca.

**Nao existe cadastro de participante.** O Bazar aponta para o `Atendido` que o
projeto ja mantem — nome, salinha, data de nascimento e a numeracao de camisa,
calca e calcado, que a tela mostra porque economiza tempo na fila. Recadastrar
criaria duas verdades sobre a mesma crianca.

Tres telas: `/bazar/` (atendimento, qualquer voluntario logado), `/bazar/painel/`
(coordenacao: TRIADE e EVENTOS) e o admin, onde a cota, as categorias e o
estoque inicial sao configurados uma vez, antes do evento.

Decisoes que ja custaram pensamento:
- **A troca de etapa e MANUAL.** Evento atrasa. Se o relogio virasse sozinho as
  11h com a fila da primeira etapa ainda andando, o sistema passaria a liberar
  retirada extra para quem nem foi atendido, e ninguem perceberia na hora.
- **A 2a etapa nao tem limite de pontos** (decisao da lideranca): ali o objetivo
  deixa de ser racionar e passa a ser esvaziar o estoque. `saldo_de` devolve
  None nessa etapa, e a tela mostra "sem limite" em vez de um zero enganoso.
- **Estoque AVISA, nao bloqueia.** Contagem de bazar e aproximada; travar a
  entrega porque a planilha diz que acabou seria deixar a crianca sem a peca que
  ja esta na mao do voluntario.
- **O alerta de estoque e medido ANTES de gravar.** Depois do bulk_create os
  itens da propria retirada ja contam como distribuidos, e quem levasse
  exatamente o que restava disparava alerta indevido. Foi bug real.
- **`ItemRetirada.pontos_unitarios` e copia, nao referencia.** Corrigir o valor
  de uma categoria no meio do evento nao pode reescrever o que ja saiu.
- **Rascunho nao consome nada.** So `finalizada_em` preenchido conta para saldo,
  estoque e relatorio. Se a tela cair no meio, nada foi gasto.
- **Uma retirada finalizada por atendido por etapa**, por UniqueConstraint com
  `condition` — e a trava contra passar duas vezes pela mesma fila.
- **Um Bazar aberto por vez**: dois abertos seriam duas telas gravando em
  edicoes diferentes no mesmo dia.
- O CSV do relatorio tem **uma linha por peca** (a planilha soma por categoria,
  salinha ou etapa sem desmontar nada) e comeca com BOM, senao o Excel abre
  "Joao" como "JoA£o".

O link do Bazar fica fixo na sidebar e na busca global (a pedido). A tela
de atendimento se explica sozinha quando nao ha edicao aberta.

FALTA: o modo de contingencia (ficha fisica impressa e lancamento posterior).

## O que entra no Financeiro sozinho (e o que não entra)

Três coisas podiam virar `Lancamento` sem ninguém digitar. Hoje são duas:

| Origem | Automático? | Quando nasce | Área |
|--------|-------------|--------------|------|
| Reembolso | **sim** | na **aprovação** | a de quem pediu, salvo escolha em contrário |
| Contribuição de parceiro | **sim** | ao registrar | nenhuma (é receita) |
| Pedido do Supply | **NÃO** — desligado em 09/2026 | — | — |

**O Supply não lança mais no Financeiro.** O espelho (`post_save` em
`adm/signals.py`) morreu a pedido da coordenação, e o motivo não é técnico: o
jeito como o Supply registra pedido nem sempre é o que foi gasto de verdade —
quantidade estimada, valor de orçamento, item trocado na hora da compra. O teto
da área encolhia com número de orçamento e ninguém sabia quais linhas eram
reais. Agora o ADM lança na mão, depois do sábado, olhando a nota. `valor` e
`area` continuam no `Pedido` para o Supply se planejar; só não atravessam.

Consequências que vieram junto e não são opcionais:
- **`SUPPLY` saiu de `ORIGENS_AUTOMATICAS`.** Essa tupla trava editar e excluir
  pela tela. Mantê-lo lá deixaria os lançamentos do tempo do espelho
  congelados — a ADM não conseguiria corrigir nem apagar o que ficou errado.
- **`Lancamento.pedido` é `SET_NULL`, não `CASCADE`.** Apagar um pedido antigo
  no Supply apagaria dinheiro do Financeiro, e o teto da área mudaria sozinho.
- **A lista usa `lan.e_automatico`, não `origem == 'MANUAL'`.** Os lançamentos
  antigos continuam com `origem='SUPPLY'` no banco; comparar com 'MANUAL' os
  deixaria sem botão de editar para sempre.

Se um dia o Supply registrar o custo REAL (nota em mãos, não orçamento),
religar o espelho volta a fazer sentido — mas o gatilho aí é a conferência do
sábado, não o salvamento do pedido.

### De quem é o gasto do reembolso

O formulário PERGUNTA, e a resposta tem três saídas que o modelo já sabia
representar:

| Escolha | Grava | Teto |
|---------|-------|------|
| Da minha área | `area` = a do solicitante | desconta o dela |
| De um evento | `evento` = X, `area` **vazia** | não desconta nenhum |
| Do projeto em geral | os dois vazios | não desconta nenhum |

A área saía automaticamente da área do solicitante, e isso mentia: quem é do
Amarelo e abastece o carro para buscar material não gastou dinheiro do Amarelo.
O teto da salinha encolhia por causa de gasolina.

**Evento deixa a área VAZIA de propósito.** Gasolina da Festa Junina não é
gasto do Amarelo e também não é da equipe de EVENTOS, que é um time e não o
evento. Área vazia não conta em teto nenhum — `_despesa_agrupada_por_area`
ignora. Se a liderança quiser que evento caia no teto de EVENTOS, é a ADM que
marca isso na aprovação; não é automático.

**A ADM escolhe área e evento na APROVAÇÃO**, não só no pagamento, porque é na
aprovação que o lançamento nasce. Enquanto a correção só existia no pagamento,
o teto da área errada ficava encolhido no intervalo — e para sempre, se a ADM
esquecesse, porque o número só parecia um pouco maior.

Em `_aplicar_destino_da_adm`, **chave ausente é "não mexi" e string vazia é
"tirei a área"**. São coisas diferentes: o botão de aprovar sozinho não pode
apagar o que o solicitante escolheu.

## Tetos de área (Financeiro)

Quem mexe no teto é **ADM/FIN** (e superusuário), em QUALQUER área — não só na
própria (`AREAS_ESCRITA` em `adm/views.py`). A Tríade lê o Financeiro inteiro e
ainda assim não escreve teto. Qualquer voluntário logado VÊ `/adm/tetos/`: é a
única tela do Financeiro aberta a todos, porque o pedido era cada um acompanhar
o gasto da área sem depender do ADM. Ver não é editar — teto que o limitado
ajusta sozinho não é teto.

Armadilha que já custou a tela inteira: a migration `0005_teto_por_semestre`
trocou `competencia` por `vigente_desde`, e `form_teto.html` continuou
renderizando `{{ form.competencia }}`. Campo inexistente em template do Django
não dá erro — sai string vazia. Resultado: `vigente_desde` (obrigatório) nunca
era enviado, o formulário recusava e a página voltava SEM mensagem, porque o
erro caía num campo que não aparecia. Ninguém conseguia cadastrar nem alterar
teto nenhum. **Ao remover um campo do model, procure o nome antigo nos
templates** — a suíte não pega isso sozinha.

`situacao_dos_tetos()` devolve `teto_id` porque a tabela precisa dele para
editar e excluir. Sem o id sobrava "Definir teto" para área sem teto e ação
nenhuma para área COM teto — dava para criar e não dava para corrigir.

Excluir não é zerar: teto zero acusa estouro no primeiro centavo gasto; sem
teto a área aparece como "gastou sem teto definido". A confirmação diz isso.

## Conventions

- Language: All UI, models, and code comments are in **Brazilian Portuguese**
- Room system: Attendees and `Semanario` plans belong to one of 7 color-coded rooms (VIOLETA → VERMELHO) plus "Família Feliz"; the room choices (`LISTA_SALAS`) are defined in both `atendido/models.py` and `semanario/models.py`
- Volunteer areas: 7 program rooms + MARKETING, ADM/FIN, CR/RE, EVENTOS, GESTAO_DE_TALENTOS, RECREACAO, SUPPLY, PROJETOS, TRIADE (`LISTA_AREAS` in `voluntario/models.py`)
- Competency framework: Activities map to competencies defined per room in `COMPETENCIAS_SALAS`, which roll up to 7 developmental dimensions in `DIMENSOES_COMPETENCIAS` (`semanario/models.py`)
- Soft delete: `Ocorrencia` records are never hard-deleted; use `soft_delete(deleted_by)` and filter `deleted_at__isnull=True` for active records
- Media uploads: Volunteer/attendee profile photos and activity photos stored in `MEDIA_ROOT` (`BASE_DIR/media/`)
