# Tela de Matrícula de Atendido — Design

**Data:** 2026-07-22
**App:** `atendido`
**Autor:** PCF

## Objetivo

Criar uma tela de **Matrícula** na área de Atendidos que reúne praticamente todos
os campos hoje disponíveis apenas no `/admin` (modelos `Atendido`, `Familia`,
`ResponsavelAtendido`, `AtendidoInclusivo`, mais o M2M `Mudanca`), com UX muito
melhor: página única em seções, campos obrigatórios, descrição por campo,
selects/date/checkbox/textarea adequados, máscaras leves e validações amigáveis.

## Contexto atual

- App `atendido` tem `app_name = 'atendido'`. Views existentes: `AtendidoView`
  (`atendido:atendido_view`), `ListaAtendido` (`lista_atendidos`),
  `DetalheAtendido` (`detalhe_atendido`), `RegistrarPresencasAtendidos`,
  `visualizar_presencas_atendidos`. **Não existe** `atendido/forms.py` nem view
  de cadastro — o cadastro só acontece no `/admin`.
- O `AtendidoAdmin` agrupa os campos em 14 fieldsets — usados como blueprint das
  seções desta tela.
- Relações: `Atendido.familia` (FK, SET_NULL), `Atendido.responsavel` (M2M →
  `ResponsavelAtendido`), `Atendido.aspectos_mudancas` (M2M → `Mudanca`),
  `AtendidoInclusivo.atendido` (OneToOne, CASCADE), `Atendido.registrado_por`
  (FK → `voluntario.Voluntario`).
- `Atendido` campos obrigatórios no banco: `nome`, `data_nascimento`, `sala`.
  Uploads: `Atendido.foto` (ImageField), `Atendido.documento` (FileField).
- Design system PCF: Tailwind (CDN) + tokens shadcn no `base.html`
  (`hsl(var(--card))`, `--border`, `--primary`, `--radius`), header navy
  `linear-gradient(135deg,#0f172a 0%,#1e293b 55%,#0f3460 100%)`, primária `#fe8210`.

## Decisões (confirmadas)

1. **Formato:** página única dividida em seções (cards), com menu de âncoras.
2. **Responsáveis:** vários por matrícula — formset dinâmico (adicionar/remover),
   mínimo 1.
3. **Acesso:** qualquer voluntário logado (`@login_required`, sem checagem de área).
4. **Inclusivo:** incluir também o modelo `AtendidoInclusivo` — seção
   "Comissão Inclusiva" que aparece só quando `comissao_inclusiva` é marcado.
5. **Obrigatórios:** nome, data_nascimento, sala, tipo de matrícula, ≥1 responsável
   (nome + parentesco + contato), CPF **ou** RG da criança, e endereço da família
   (CEP, bairro, cidade). `escola` e `ano_escolar` são **encorajados mas opcionais**
   (criança fora da escola não pode travar o cadastro).
6. **Socioeconômico:** todos os campos; contadores de bens num bloco recolhível.
7. **Pós-salvar:** redireciona para o detalhe do atendido.
8. **Criar e Editar na mesma tela** (modo `criar`/`editar`), à la
   `ronda/form_configuracao.html`. Edição pré-preenche todos os forms do atendido
   existente (Atendido, Família, Responsáveis, Inclusivo).
9. **Prioridade de usabilidade para usuários leigos** (ver seção "UX para leigos").

## Arquitetura

### Rotas
`atendido/urls.py`:
- `path('matricula/', views.matricula_atendido, name='matricula')` — criar.
- `path('matricula/<int:pk>/editar/', views.matricula_atendido, name='matricula_editar')` — editar.

### View — `matricula_atendido(request, pk=None)`
- `@login_required(login_url="/")`.
- `atendido = get_object_or_404(Atendido, pk=pk)` quando `pk` (modo editar); senão
  `atendido = None` (modo criar). `modo = 'editar' if pk else 'criar'`.
- **GET:** instancia `AtendidoForm(instance=atendido)`, `FamiliaForm(instance=atendido.familia)`,
  `ResponsavelFormSet` (queryset = responsáveis do atendido, `extra=1`),
  `AtendidoInclusivoForm(instance=getattr(atendido, 'inclusivo', None))`. Em modo
  criar, todos vazios (extra=1 no formset). Renderiza `matricula_atendido.html`.
- **POST:** valida os quatro. Se todos válidos, dentro de `transaction.atomic()`:
  1. `familia = FamiliaForm.save()` (cria ou atualiza).
  2. Para cada form preenchido do `ResponsavelFormSet` (respeitando `DELETE`): se
     `cpf` informado e já existe `ResponsavelAtendido` com esse CPF, **reaproveita**
     o existente; senão cria/atualiza. Coleta a lista de responsáveis.
  3. `atendido = AtendidoForm.save(commit=False)`; `atendido.familia = familia`;
     em modo criar `atendido.registrado_por = request.user`; `atendido.save()`.
  4. `atendido.responsavel.set(responsaveis)`; `AtendidoForm.save_m2m()`
     (para `aspectos_mudancas`).
  5. Se `atendido.comissao_inclusiva`: cria/atualiza `AtendidoInclusivo`
     (`AtendidoInclusivoForm.save(commit=False)`, `inclusivo.atendido = atendido`,
     `save()`). Se desmarcado e existir um `AtendidoInclusivo`, mantê-lo intacto
     (não apagar — histórico), apenas não exibir.
  6. `messages.success(...)`; `redirect('atendido:detalhe_atendido', pk=atendido.pk)`.
- Se algum form inválido: re-renderiza com os erros e um **resumo de pendências no
  topo** (lista amigável dos campos obrigatórios faltando), mantendo o preenchido.
- O template usa `enctype="multipart/form-data"`; a view passa `request.POST, request.FILES`.

### Forms — `atendido/forms.py` (novo)

- **`AtendidoForm(ModelForm)`** — `fields` = todos os campos de `Atendido` **exceto**
  `familia`, `responsavel`, `registrado_por`, `data_criacao`, `ativo` (esses são
  tratados pela view). `help_text` vem do model. Tornar obrigatório via
  `__init__`: `matricula`. `clean()` valida que `cpf` **ou** `rg` foi informado
  (senão `ValidationError`).
- **`FamiliaForm(ModelForm)`** — todos os campos de `Familia` exceto `data_criacao`.
  Obrigatórios via `__init__`: `cep`, `bairro`, `cidade`.
- **`ResponsavelAtendidoForm(ModelForm)`** — `fields` = todos exceto `data_criacao`.
  Obrigatórios: `nome`, `parentesco`, `contato`. `ResponsavelFormSet =
  modelformset_factory(ResponsavelAtendido, form=ResponsavelAtendidoForm, extra=1,
  can_delete=True)`; a view garante ao menos 1 responsável válido (senão erro).
- **`AtendidoInclusivoForm(ModelForm)`** — `fields` = todos exceto `atendido`.
  Todos opcionais (o preenchimento é condicional). Validado só quando
  `comissao_inclusiva` marcado; caso contrário, ignorado.

Widgets estilizados via `<style>` escopado no template (padrão já usado em
`ronda/templates/form_configuracao.html`) — evita poluir os forms com classes.
Selects para campos com choices, `type="date"` para `data_nascimento`,
`type="file"` para foto/documento, checkbox para booleanos, `<textarea>` para
os `TextField`, `CheckboxSelectMultiple` para `aspectos_mudancas`.

### Template — `atendido/templates/matricula_atendido.html`

Página única, header navy PCF com curva `::after`, container central, **menu de
âncoras** (lista lateral fixa em telas grandes) para saltar entre seções e ver o
progresso. Cada seção é um card `bg-card border border-border rounded-lg`. Cada
campo: label com `*` quando obrigatório, descrição (help_text) em texto pequeno,
widget, e erros inline em vermelho. Diretriz de UI: Tailwind + shadcn, sem
dependência de Bootstrap para estilo, qualidade de designer sênior, responsivo
(a Tríade usa celular). Detalhes de interação na seção "UX para leigos".

## UX para usuários leigos

Os operadores da matrícula são pessoas não técnicas; o design prioriza clareza e
baixo atrito:

- **Perguntas Sim/Não como botões segmentados** (não checkbox cru): cada
  `BooleanField` vira um par de botões "Sim / Não" claros, com o rótulo em
  linguagem simples (o `help_text` do model). Estado inicial reflete o default.
- **Revelação condicional:** os campos de "descrição" (`diagnostico_descricao`,
  `sensibilidade_descricao`, `dificuldade_motora_descricao`,
  `dificuldade_emocional_descricao`) só aparecem quando a pergunta Sim/Não
  correspondente está em "Sim". A seção "Comissão Inclusiva" idem
  (`comissao_inclusiva`). Reduz a tela e o medo de "campo vazio".
- **Navegação/progresso por seções:** menu lateral fixo com as seções; ao rolar,
  destaca a atual. Cada seção com pelo menos um obrigatório mostra um indicador de
  pendente/ok.
- **Resumo de pendências ao salvar:** se faltarem obrigatórios, um card no topo
  lista em português claro o que falta e cada campo com erro fica destacado, com
  rolagem até o primeiro erro.
- **Máscaras leves** (só visuais) de CPF, telefone e CEP; placeholders com exemplo.
- **Agrupamento e ordem** seguem o raciocínio de uma ficha de matrícula real:
  primeiro a criança, depois responsáveis, depois família, depois saúde/inclusão.
- **Botão salvar fixo** (sticky) no rodapé, sempre acessível, com rótulo claro
  ("Concluir matrícula" / "Salvar alterações").
- JS vanilla para: formset dinâmico de responsáveis (adicionar/remover, reindexando
  `TOTAL_FORMS`), toggles Sim/Não, revelação condicional, bloco recolhível "Bens e
  infraestrutura", navegação de seções e máscaras.

## Seções e campos

Legenda: `*` = obrigatório nesta tela.

1. **Identificação da Criança** — `nome`*, `data_nascimento`* (date),
   `identidade_etnica` (select), `rg`, `cpf` (CPF **ou** RG obrigatório),
   `foto` (file), `documento` (file).
2. **Matrícula** — `matricula`* (select Matrícula/Rematrícula), `sala`* (select).
3. **Informações Educacionais** — `escolaridade`*, `ano_escolar`*, `escola`*
   (select, opção "Outro"), `tipo_escola` (select Pública/Privada).
4. **Contato** — `contato` (telefone).
5. **Situação Social e Atividades** — `trabalho` (checkbox), `projeto_social`
   (checkbox).
6. **Responsáveis** (formset dinâmico) — `nome`*, `parentesco`* (select),
   `contato`*, `cpf`, `rg`, `outro_contato`, `trabalho`, `email`,
   `escolaridade` (select).
7. **Família · Endereço** — `cep`*, `endereco`, `bairro`* (select),
   `cidade`* (select), `zona_residencial` (select), `situacao_moradia` (select).
8. **Família · Socioeconômico** — `renda_total_familia` (select),
   `pessoas_moram_familia` (int), `pessoas_trabalham_familia` (int),
   `programa_transferencia_renda` (Sim/Não), `agua_encanada`, `esgoto_encanado`,
   `energia_eletrica`, `internet_casa` (Sim/Não), `cesta_natal` (Sim/Não);
   **[recolhível] Bens e infraestrutura** — `comodos_casa`, `tv_casa`,
   `banheiro_casa`, `motos_casa`, `carros_casa`, `geladeira_casa`, `freezer_casa`,
   `celular_casa`, `computador_casa` (todos int).
9. **Saúde e Bem-Estar** — `convenio_medico`, `vacina_covid`, `campanha_vacinacao`
   (checkboxes), `restricao_alimentar`, `restricao_medica`, `medicacao_continua`
   (textareas), `saude_bucal` (checkbox).
10. **PCF Inclusivo** — `diagnostico` (checkbox) + `diagnostico_descricao`
    (textarea), `comportamento_social` (select), `comportamento_regras` (select),
    `concentracao`, `aprendizado`, `sensibilidade` + `sensibilidade_descricao`,
    `dificuldade_motora` + `dificuldade_motora_descricao`, `dificuldade_emocional`
    + `dificuldade_emocional_descricao`, `acompanhamento` (select),
    `recomendacao_acompanhamento` (textarea), `comissao_inclusiva` (checkbox),
    `expectativas_familia` (textarea).
11. **Comissão Inclusiva** *(condicional: só se `comissao_inclusiva` marcado)* —
    campos do `AtendidoInclusivo`: `diagnostico`, `diagnostico_descricao`,
    `acompanhamento`, `recomendacoes`, `comportamento_social`,
    `dificuldades_aprendizado`, `dificuldades_motoras`, `dificuldade_atencao`,
    `dificuldade_emocional`, `servicos_apoio`, `expectativas_familia`,
    `observacoes_adicionais`.
12. **Impacto do Projeto** — `mudancas_positivas` (Sim/Não), `aspectos_mudancas`
    (checkboxes múltiplos de `Mudanca`, aparecem quando "Sim"),
    `impacto_social` (select, campo da Família), `tipo_impacto_social` (select,
    campo da Família).
13. **Vestuário** — `numeracao_camisa`, `numeracao_calca`, `numeracao_calcado`.
14. **Termos e Autorizações** — `termos_assinado` (checkbox).
15. **Observações** — `observacoes` (textarea).

## Regras de validação

- **CPF ou RG da criança:** ao menos um preenchido (`AtendidoForm.clean`).
- **≥1 responsável válido:** a view rejeita o POST se nenhum form do formset tiver
  nome + parentesco + contato.
- **Obrigatórios:** `matricula`, `cep`, `bairro`, `cidade` (além de nome,
  data_nascimento, sala). `escola`/`ano_escolar` ficam opcionais.
- **Unicidade de CPF:** `Atendido.cpf` e `ResponsavelAtendido.cpf` são `unique`.
  Para atendido, erro amigável se CPF já existir. Para responsável, se o CPF já
  existe, **reaproveita** o registro (vincula o existente).
- Máscaras leves apenas visuais (CPF/telefone/CEP); o banco guarda só números
  conforme os `help_text`.

## Casos de borda

- **Uploads:** form multipart; `request.FILES` na view. Campos opcionais.
- **`aspectos_mudancas` vazio:** se não houver registros `Mudanca` cadastrados, a
  seção de checkboxes fica vazia — não bloqueia a matrícula. (Catálogo `Mudanca` é
  gerenciado no admin.)
- **Transação:** todo o salvamento em `transaction.atomic()`; se algo falhar,
  nada é persistido.
- **Booleanos anuláveis do `AtendidoInclusivo`** (`diagnostico`, `acompanhamento`,
  `servicos_apoio`) usam o toggle Sim/Não (Sim = True; Não = False) — abre-se mão
  do terceiro estado (nulo) em favor da clareza para o operador leigo.

## Fora de escopo (YAGNI)

- Reaproveitar `Familia` existente (irmãos) — cada matrícula cria uma família nova.
- Busca de endereço por CEP (ViaCEP): bairro/cidade são selects curados da região,
  então autofill não mapeia bem; fica de fora.

## Testes

Cobrir em `atendido/tests.py`:
- POST válido cria Atendido + Familia + 1 Responsável vinculado, com
  `registrado_por` = usuário logado, e redireciona ao detalhe.
- CPF e RG ambos vazios → erro de validação, nada é criado.
- `comissao_inclusiva` marcado cria `AtendidoInclusivo`; desmarcado não cria.
- Responsável com CPF já existente reaproveita o registro (não duplica).
- Vários responsáveis via formset são todos vinculados.
- Acesso exige login (não logado redireciona).
- **Editar** (`matricula_editar` com pk) pré-preenche e atualiza o atendido,
  a família e os responsáveis existentes sem duplicar registros.
