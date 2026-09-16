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
4. Uma **Scheduled Task** chamando `manage.py lembrete_disponibilidade`.
   Sem ela o lembrete da enquete NUNCA roda — o comando não tem relógio próprio,
   só dispara quando alguém o chama. Use `--dry-run` para conferir antes.

   **Para cobrar de 8 em 8 horas são TRÊS tarefas**, não uma. O comando não tem
   trava de frequência, então rodar três vezes é seguro: o push usa tag por
   sábado (`enquete-{pk}`) e o lembrete de agora SUBSTITUI o de quatro horas
   atrás na bandeja. O e-mail não tem essa colapsagem — três por dia, todo dia,
   ensinam a equipe a ignorar os três. Por isso o arranjo é uma rodada completa
   e duas só com push:

   ```
   11:00 UTC (08:00 SP)  manage.py lembrete_disponibilidade
   19:00 UTC (16:00 SP)  manage.py lembrete_disponibilidade --so-push
   03:00 UTC (00:00 SP)  manage.py lembrete_disponibilidade --so-push
   ```

   Horário de Scheduled Task no PythonAnywhere é **UTC** (São Paulo = UTC−3).

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

## Entrar com a conta Google da organização

Botão na tela de login, **só para contas `@projetocriancafeliz.org`**. O login
por usuário e senha continua ao lado, de propósito: se o Google cair, se alguém
perder acesso à conta, ou se o voluntário não tiver conta da organização,
ninguém fica trancado para fora num sábado de manhã.

**Sem `django-allauth`.** O `google-auth` já estava no projeto por causa do
Acervo, e verificar um token de identidade é o que ele faz. O allauth traria
tabelas, templates e um fluxo de login diferente para todo mundo — muito preço
por pouca coisa.

Configuração no `.env`: `GOOGLE_LOGIN_CLIENT_ID` (de um OAuth client do tipo
**Aplicativo da Web**) e `GOOGLE_LOGIN_DOMINIO`. **Vazio = o botão não
aparece** e o formulário de senha continua inteiro — mesmo padrão do VAPID e do
Drive.

O que decide se isso é segurança ou teatro:

- **A checagem é no claim `hd`, não no final do e-mail.** `hd` (hosted domain)
  só existe em conta Google Workspace de verdade. Conferir
  `email.endswith('@dominio')` deixaria passar um Gmail comum com apelido
  parecido — e há teste para exatamente esse caso.
- **A verificação é no SERVIDOR**, com a chave pública do Google, conferindo
  também `aud` (o token foi emitido para este aplicativo), emissor e validade.
  Nada do que o navegador afirma é aceito. `data-hd` no HTML é só dica para o
  seletor de contas.
- **`email_verified` é exigido.**
- **Quem decide o acesso é o CADASTRO, não o Google.** Conta bloqueada
  (`is_active=False`) ou desligada (`data_saida` preenchido) não entra, mesmo
  com token válido.
- **Dois cadastros com o mesmo e-mail RECUSAM o login.** `email` não é único no
  modelo; login ambíguo é pior que login negado, porque entrar na conta errada
  dá acesso ao que aquela pessoa podia ver.
- **Primeira entrada cria voluntário ATIVO e SEM ÁREA** (decisão da
  coordenação), com senha inutilizável e um recado mandando procurar a Gestão
  de Talentos. Sem área, ele não passa em nenhum gate de permissão. Mas
  **entra em `Voluntario.objects.ativos()`** — ou seja, já aparece na cobrança
  da enquete do sábado e nas listas de presença.
- **`LoginPCF` existe só para levar o Client ID ao template.** `extra_context`
  não serviria: é avaliado uma vez, na importação das rotas.
- **A tela de login passou a renderizar `messages`.** Ela não renderizava, e
  toda recusa da entrada pelo Google seria escrita e nunca vista — o mesmo
  defeito que a tela do Bazar tinha.

## Estáticos: o `collectstatic` esquecido quebra tela em silêncio

Já quebrou. Em 09/2026 a tela do Bazar subiu com o template NOVO e o JavaScript
VELHO: clicar num nome não fazia nada, e o console não dizia por quê.

**Em produção quem serve `/static/` é o WhiteNoise, a partir de `STATIC_ROOT`**
— não do código-fonte — **e ele casa pelo CAMINHO, ignorando o `?v=`**. Um
deploy com `git pull` + `migrate` mas sem `collectstatic` entrega, portanto,
HTML novo com JS velho. Sem erro, sem 404, sem aviso.

Duas defesas, e as duas são necessárias:

1. **`TESTE/checks.py`** (`pcf.W001`) compara o mtime de cada arquivo de
   `ARQUIVOS_OBSERVADOS` no código com a cópia em `STATIC_ROOT`, e reclama por
   nome quando a cópia está atrás. Roda junto de `manage.py check`, `migrate` e
   `runserver` — ou seja, no meio do deploy. Só reclama se `STATIC_ROOT`
   EXISTIR: pasta ausente é máquina de desenvolvimento, e avisar ali seria
   barulho em todo comando do dia. Registrada por `TESTE/apps.py`, que existe
   só para isso (`'TESTE.apps.NucleoConfig'` em INSTALLED_APPS; sem models, sem
   templates, sem migrations).
2. **`TESTE/tests_estaticos.py`** varre os templates atrás de
   `{% static 'js/...' %}` e cobra que todo JS esteja em `ARQUIVOS_OBSERVADOS`.
   Fora dela, o `?v=` não muda quando o arquivo muda e o navegador de quem já
   visitou continua com o velho. Esse teste já pegou cinco arquivos esquecidos
   de uma vez, incluindo os três das pautas e o `js/ajudas.js`.

**Ao criar um JS novo, acrescente-o a `ARQUIVOS_OBSERVADOS` na mesma hora.**

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

O link do Bazar fica fixo na sidebar e na busca global (a pedido).

### A tela de atendimento e um CAIXA (redesenho de 09/2026)

Tres passos numerados, o saldo sempre a vista DESCENDO, todo toque com volta, e
nada grava sem uma conferencia com o nome da crianca na frente. Spec e plano em
`docs/superpowers/specs/2026-09-13-bazar-caixa-design.md`.

**A regra de ouro de `static/js/bazar-atendimento.js`, escrita no topo do
arquivo: NENHUMA FUNCAO QUE REDESENHA ESCONDE UM RECADO.** Na versao anterior
`redesenharCarrinho()` fazia `elErro.hidden = true` e era chamado no `.finally`
do envio — logo depois de a mensagem ser escrita. Efeito: "ja finalizou a
retirada desta etapa" e "falha de conexao" NUNCA eram vistos. O voluntario
apertava, a tela nao respondia, e ele apertava de novo. Mostrar e esconder
recado e de quem SABE o que aconteceu, nunca de quem desenha.

Outras armadilhas da tela, todas com teste:
- **O saldo desce.** Era escrito uma vez e congelava, enquanto o total da sacola
  subia noutro bloco — dois numeros grandes competindo, e o leigo olhando para o
  errado.
- **O `-` e botao proprio**, faixa de 44px com a altura inteira do bloco, e so
  aparece com peca marcada. Era um `<span>` de 32px DENTRO do botao que soma:
  errar o alvo ADICIONAVA peca, e `<span>` nem e focavel.
- **Nenhum campo abaixo de 16px.** Abaixo disso o iOS da zoom ao focar e
  desalinha a tela no meio do atendimento. O teste varre o CSS e so cobra de
  `input`/`select`/`textarea` — legenda a 0.7rem esta certa.
- **O rodape e `fixed` + `dvh` + `env(safe-area-inset-bottom)`.** `sticky
  bottom:0` se ancora no viewport de LAYOUT do iOS, que nao encolhe com o
  teclado: o botao verde ia parar atras dele.
- **Crianca que ja passou tem a grade NAO DESENHADA**, com uma frase inteira no
  lugar (hora, sala e quem conferiu). Antes os botoes ficavam `disabled`,
  identicos aos clicaveis, e o leigo concluia que travou.
- **Impossibilidade vira frase dentro do botao** ("nao cabe: falta 1 ponto"),
  nunca cinza mudo.
- **"Quem levou" volta ao padrao a cada crianca.** Nao era limpo: uma vez
  marcado "Outra pessoa — Maria", a manha inteira saia com a Maria colada em
  quem veio sozinha.

### Regras que mudaram com o redesenho

- **A trava de uma retirada por etapa vale so na 1a ETAPA**, e so para quem tem
  ficha (`atendido__isnull=False` na `condition`). Na 2a o objetivo declarado e
  esvaziar o estoque: ali a familia que volta na arara esta certa.
- **`atendido` aceita NULO**: e o VISITANTE, crianca que apareceu e nao e
  Atendido ativo. Registro separado, com nome a mao e motivo — nao vira ficha,
  para nao criar segunda verdade sobre a mesma crianca. **Todo lugar que lia
  `retirada.atendido.nome` precisa usar `nome_de_quem_levou`**; no CSV do
  relatorio ler direto estourava com AttributeError.
- **`sem_retirada`**: veio, foi conferida e nao achou nada do tamanho dela.
  Conta como comparecimento e nao como retirada. Vazio por engano continua
  recusado, e marcar os dois e recusado tambem.
- **`token` de idempotencia**: reenvio depois de resposta perdida devolve o
  MESMO recibo, em vez de acusar a crianca pela trava. Token diferente continua
  batendo na trava — ele protege contra clique repetido, nao contra passar duas
  vezes.
- **Cancelar = voltar ao RASCUNHO.** `finalizada_em` nulo ja E o rascunho, e a
  UniqueConstraint tem `condition`, entao a trava reabre sozinha e o estoque
  volta sem apagar item nenhum. Nenhum campo de status foi inventado. O motivo e
  obrigatorio.
- **`recado_de_ja_retirou` vive em `regras.py`**, nao na view: os dois caminhos
  que produzem essa recusa — a checagem antes de gravar e a corrida entre duas
  salas — precisam dizer a MESMA coisa.
- **`finalizar` captura `IntegrityError`.** Duas salas conferindo a mesma
  crianca viravam 500 no celular, com a sacola na mao.
- **As salas fisicas sao lista (`SalaDoBazar`)**, escolhida uma vez por
  aparelho. Era `CharField` livre redigitado a cada crianca: preenchido nas
  cinco primeiras e vazio no resto da manha. O CharField antigo fica como
  historico e nada novo escreve nele.

### Kit de papel (`bazar/papelaria.py`)

O plano B, e a unica camada que funciona sem servidor, sem rede e sem bateria.
**Aberto a QUALQUER voluntario logado** — quem esta no caixa e que precisa
imprimir, e o CSV antigo ficava atras de TRIADE/EVENTOS. Alcancavel da tela de
atendimento E do painel.

- Ficha do caixa: **uma linha por CRIANCA, nao por peca**. A mao, com fila,
  linha por peca e lentidao garantida. Traz a tabela de pontos no cabecalho.
- Lista de elegiveis por salinha, com idade e numeracoes ao lado do nome —
  resolve homonimo no papel do mesmo jeito que na tela. Salinha vazia nao vira
  folha.
- `kit_papel.html` NAO estende `base.html`: e a pagina que precisa abrir quando
  tudo o mais estiver fora do ar.
- Tambem sai em `.xlsx` (`openpyxl`, import local).

FALTA: lancar as fichas de papel depois do evento (hoje impossivel —
`finalizada_em` e `timezone.now()` fixo e a etapa vem do bazar), o fechamento
com estatisticas, e a tela abrir sem rede.

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

### Fechamento do sábado no Supply

`supply.FechamentoSabado`, um por sábado, com duas etapas: **materiais** (o que
saiu do estoque) e **pedidos** (o que foi comprado). São dois trabalhos
diferentes, às vezes de pessoas diferentes.

Existe porque o ADM passou a lançar o gasto do Supply na mão, e precisava saber
se os números da tela já eram os reais ou ainda os do planejamento. Era pergunta
no grupo toda semana.

**Abrir o painel e confirmar o fechamento são permissões DIFERENTES**, e são
duas listas em `supply/views.py`:

- `AREAS_DO_PAINEL` = SUPPLY, TRIADE, **ADM/FIN** — quem abre e edita. O
  Financeiro entrou porque lança o gasto do Supply na mão e precisa chegar no
  número, não só ouvir falar dele.
- `AREAS_DO_FECHAMENTO` = SUPPLY, TRIADE — quem confirma. Menor de propósito: o
  check existe para o Supply **avisar** a ADM; se a ADM pudesse marcar,
  confirmaria para si mesma e o aviso deixaria de significar "o Supply
  conferiu".

Superusuário passa nas duas. Na tela, `pode_fechar` esconde os botões de quem
não confirma — e o texto explica por quê, senão parece tela quebrada.

- **Não há campo booleano: a DATA preenchida É o check.** Booleano mais data são
  duas verdades sobre o mesmo fato; na primeira vez que uma for gravada sem a
  outra, ninguém sabe qual vale. Desmarcar limpa os DOIS campos.
- **A tela lê com `filter().first()`, não com `do_sabado()`.** Abrir o painel é
  GET, e GET não grava — senão só navegar pelos 40 sábados do seletor criaria
  40 registros. Fechamento ausente significa "as duas etapas em aberto".
- **`marcar_fechamento` é só POST e responde 403 a quem é de fora.** Isso grava
  o nome de uma pessoa como responsável pelo número: um link colado no grupo
  não pode marcar em nome de quem clicar, e recusar precisa ser recusa, não um
  desvio silencioso.
- **O painel do Financeiro olha o último sábado que JÁ PASSOU.** Sábado futuro
  viraria cobrança falsa toda semana.
- **Materiais não têm valor em R$** (`Movimentacao` controla quantidade). O
  check diz "conferi"; o número que a ADM lança continua vindo da nota. Se um
  dia a ADM precisar ler o valor real na tela, falta um campo de custo ali.

## Revistinha: só os textos, por salinha (set/2026)

A revista mostra **apenas os textos dos semanários agrupados por salinha**, mais
o título e o período. Todo o resto — números do período, dimensões, carta de
abertura, financeiro, fechamento, chamada para apoiar e as fotos — está
**comentado nos templates**, a pedido, para voltar depois.

**O agrupamento acontece na EXIBIÇÃO, não no modelo.** `SecaoRevista` continua
gravada uma por atividade, com sábado, competência e foto; quem junta é
`textos_por_salinha()` em `revista/servicos.py`, chamado de `_contexto_leitura`.
Foi de propósito: mudar o modelo tornaria "descomentar no futuro" impossível
sem remontar todas as edições.

- A ordem é a **oficial das salinhas** (`LISTA_SALAS`: Violeta → Vermelho,
  Família Feliz por último), não alfabética — alfabético põe Amarelo antes de
  Anil e Azul antes de Violeta, que não é como o projeto fala das salas.
- Seção **sem texto não vira bloco**: título de sala com nada embaixo parece
  defeito. Seção **sem sala** cai num bloco "Outros" no fim, em vez de sumir.
- `mostrar_numeros` e `mostrar_financeiro` continuam LIGADOS no modelo. Quem
  desliga é o template, então a preferência do CR sobrevive ao religamento.
- **São QUATRO saídas** — `publica.html`, `pdf.html`, `email.html` e
  `ver.html` — e as quatro leem o mesmo `_contexto_leitura`. Mexer numa só faz
  quem confere na tela aprovar uma coisa e o doador receber outra.
- **`{% comment %}` NÃO aninha.** Cada trecho desligado é um bloco só, e o
  texto da nota dentro dele não pode conter a sequência de fechamento. Há teste
  que renderiza as quatro saídas e falha se o comentário vazar para a página.
- `ver.html` estende `base.html` e lê `request.user`: em teste ele precisa
  passar pela view, não por `render_to_string`.

**PARA RELIGAR:** apagar a abertura e o fechamento de cada `{% comment %}` nos
quatro templates. Nada mais.

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
