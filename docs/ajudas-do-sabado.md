# Ajudas do Sábado

O app `ajudas` organiza deslocamentos de voluntários entre áreas. Reutiliza a
autenticação Django, `Voluntario.area`, `LISTA_AREAS`, `Voluntario.objects.ativos()`,
`DisponibilidadeVoluntario`, `Semanario`, `base.html` e o design system `pcf-*`.

## Uso

1. Cadastre o sábado no admin como já era feito. Início e término passam a ser
   configuráveis, com defaults de **06:00–12:30**.
2. Na sidebar, abra **Gestão de Ajudas**, disponível exclusivamente à TRIADE.
3. Abra o sábado. A primeira configuração sugere as necessidades, sem gravar no GET.
4. Revise quantidades e horários. Arraste pessoas ou use **Alocar**, que também
   funciona em celular e por teclado. **Editar** permite uma ajuda mais curta que
   o período da necessidade. Arrastar uma ajuda existente muda sua alocação;
   arrastar da equipe cria outra ajuda, se não houver conflito.
5. **Salvar rascunho** persiste o conjunto. Movimentos, inclusões e exclusões
   anteriores ao salvamento ficam somente no navegador. Sair com alterações
   pendentes aciona o aviso do navegador; não há recuperação após fechar/descartar.
6. **Publicar escala** valida novamente e torna a escala acessível aos voluntários.
   Falta/excesso de pessoas gera indicação para revisão, sem impedir publicação.
7. **Reabrir para editar** conserva as alocações e retira a escala da consulta e
   do card do início até a próxima publicação. Não há cópia pública paralela.

## Models e dados existentes

- `Sabado`: dois `TimeField`, `hora_inicio` e `hora_fim`, com defaults para os
  registros antigos e constraint de ordem. O formulário do admin impede encurtar
  o dia deixando necessidades/ajudas salvas fora dele. O quadro permite ajustar
  período e alocações juntos, na mesma transação.
- `EscalaAjuda`: uma por sábado, com status `RASCUNHO`/`PUBLICADA`, revisão para
  detectar edições concorrentes, data de publicação e última atualização.
- `NecessidadeAjuda`: escala, área, início/fim absolutos e quantidade **total**
  necessária. Faixas não sobrepostas da mesma área já são suportadas, sem impor
  uma chave única que impeça essa evolução.
- `Ajuda`: escala, voluntário, área destino e início/fim. O sábado vem da escala
  (`ajuda.sabado`); não há duas relações independentes que possam discordar.
  Permanência na própria área nunca gera registro.

`Semanario.vagas` representa **pessoas extras**, conforme confirmado pelo usuário.
A sugestão para uma sala é `presentes da própria área + vagas do semanário daquele
sábado`. A TRIADE pode sobrescrever o total; alterações futuras no semanário não
reescrevem uma necessidade salva. Sem semanário, sugere-se a equipe confirmada,
ou uma pessoa se não houver ninguém, deixando a quantidade para revisão.

Defaults de horários:

| Área | Horário |
| --- | --- |
| Supply | 06:00–07:00 |
| Salas e Marketing | 09:00–11:00 |
| Recreação | 11:00–12:30 |

O horário específico de Recreação prevalece sobre o padrão geral das áreas
operacionais. Em sábados mais curtos, sugestões são recortadas ao período do dia;
uma sugestão completamente fora do período é omitida. Qualquer área de
`LISTA_AREAS`, inclusive ADM/Fin e TRIADE, pode ser acrescentada manualmente.
Necessidades removidas não são recriadas ao recarregar.

`FaixaHorarioAjuda`/`pode_ajudar` contêm preferências descritivas da enquete,
sem horários estruturados. São exibidas como contexto; não constituem uma
restrição adicional. Elegibilidade exige presença confirmada naquele sábado,
`is_active=True` e `data_saida` vazia, como no manager existente.

## Validações e contagem

`services.py` concentra salvamento, publicação e reabertura. Os forms validam
o payload JSON; os validadores são reutilizados pelos models e pelo serviço.
O servidor exige áreas válidas, pessoas existentes/ativas/confirmadas, períodos
ordenados dentro do sábado, destino diferente da área própria e ajuda contida
na necessidade de destino. Ajudas de um mesmo voluntário não podem se sobrepor.
Intervalos são semiabertos: terminar às 10:00 permite começar outra ajuda às 10:00.

A contagem divide cada necessidade nos instantes em que as alocações mudam.
Cada pessoa conta uma vez em sua área original, exceto no trecho em que está
ajudando fora. Um contador `4–5 / 5` explicita variação; os trechos detalham os
totais. Pessoas inativas ou com presença revogada deixam de contar. Suas ajudas
salvas continuam visíveis à TRIADE com erro para correção, e bloqueiam uma nova
publicação enquanto não forem corrigidas/removidas.

O salvamento é atômico e substitui as linhas da escala após validar todo o novo
conjunto. A revisão rejeita abas desatualizadas com HTTP 409; a trava do sábado
serializa gravações também na criação da primeira escala em bancos com suporte
a `SELECT FOR UPDATE`. As relações não são expostas para edição direta no admin:
há somente consulta da escala e link para o quadro. Escritas programáticas em
lote devem passar pelos serviços; `bulk_create`/`update` não executam `clean()`.

O histórico consulta os próprios registros de ajuda de escalas publicadas,
anteriores ao sábado editado e ao dia atual, limitado às cinco mais recentes
por pessoa. A tela pública mostra equipe e horários, sem carro ou histórico.

## URLs e autorização

| Método | URL | View | Acesso |
| --- | --- | --- | --- |
| GET | `/ajudas/` | `escala_publicada` | Login |
| GET | `/ajudas/<sabado_id>/` | `escala_publicada` | Login, somente publicada |
| GET | `/ajudas/painel/` | `painel` | TRIADE |
| GET | `/ajudas/<sabado_id>/organizar/` | `organizar` | TRIADE |
| POST | `/ajudas/<sabado_id>/salvar/` | `salvar` | TRIADE + CSRF |
| POST | `/ajudas/<sabado_id>/publicar/` | `publicar` | TRIADE + CSRF |
| POST | `/ajudas/<sabado_id>/reabrir/` | `reabrir` | TRIADE + CSRF |

Não há novos grupos ou permissões paralelas. `request.user.area == "TRIADE"`
é obrigatório para administrar, inclusive para superusuários de outras áreas.
Essa escolha segue o requisito específico das ajudas. Rascunhos retornam 404
na consulta por sábado. As telas de escala e organização não são cacheáveis.

O único card novo em `/inicio/` consulta o **próximo sábado com escala publicada**
(incluindo hoje), depois busca as ajudas do usuário autenticado. Não pula para uma
escala posterior caso a mais próxima não tenha ajuda para ele. Mostra a primeira
área em destaque e seu horário; as demais ficam em `+N ajudas`, expansível.
Sem ajuda externa, mantém um estado compacto com link para consulta.

## Arquivos

Criados: `ajudas/{apps,models,forms,permissions,validators,services,selectors,views,urls,admin,tests}.py`,
`ajudas/tests_frontend.cjs`, os inicializadores do app e das migrations,
`ajudas/migrations/0001_initial.py`, os templates
`ajudas/templates/ajudas/{painel,organizar,escala,_card_inicio}.html`,
`static/css/ajudas.css`, `static/js/ajudas.js`, a migration de horários abaixo e este documento.

Alterados: `sabado/models.py`, `sabado/admin.py`, `TESTE/settings.py`,
`TESTE/urls.py`, `TESTE/views.py`, `TESTE/versao_estatica.py`,
`templates/sidebar.html` e `templates/inicio.html`.

## Migrations e verificação

- `sabado/0003_sabado_hora_fim_sabado_hora_inicio_and_more`: acrescenta horários
  com defaults e constraint, sem apagar dados existentes.
- `ajudas/0001_initial`: cria as três tabelas, relações, índice e constraints.

Na implantação, com o ambiente do projeto ativo:

```console
python manage.py migrate
python manage.py collectstatic --noinput
```

Os assets usam os tokens existentes e CSS próprio; não exigem nova dependência
de frontend nem recompilação do Tailwind. A versão dos estáticos observa os dois
novos arquivos, seguindo o mecanismo atual de invalidação de cache.

Verificações automatizadas:

```console
python manage.py test ajudas sabado semanario ronda TESTE --settings=TESTE.settings_test --noinput
python manage.py makemigrations --check --dry-run --settings=TESTE.settings_test
node --test ajudas/tests_frontend.cjs
```

Os testes usam SQLite isolado. A revisão de navegador utiliza dados fictícios,
sem alterar o banco configurado no `.env`. Concorrência com bloqueio real de
linhas depende do banco de implantação; SQLite não implementa `SELECT FOR UPDATE`.
