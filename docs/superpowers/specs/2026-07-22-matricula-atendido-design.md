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
5. **Obrigatórios (política "mais completo"):** nome, data_nascimento, sala, tipo
   de matrícula, ≥1 responsável (nome + parentesco + contato), CPF **ou** RG da
   criança, escola, ano_escolar, e endereço da família (CEP, bairro, cidade).
6. **Socioeconômico:** todos os campos; contadores de bens num bloco recolhível.
7. **Pós-salvar:** redireciona para o detalhe do atendido criado.

## Arquitetura

### Rota
`atendido/urls.py`: `path('matricula/', views.matricula_atendido, name='matricula')`.

### View — `matricula_atendido(request)`
- `@login_required(login_url="/")`.
- **GET:** instancia `AtendidoForm`, `FamiliaForm`, `ResponsavelFormSet` (extra=1),
  `AtendidoInclusivoForm` (todos vazios) e renderiza `matricula_atendido.html`.
- **POST:** valida os quatro. Se todos válidos, dentro de `transaction.atomic()`:
  1. `familia = FamiliaForm.save()`.
  2. Para cada form preenchido do `ResponsavelFormSet`: se `cpf` informado e já
     existe `ResponsavelAtendido` com esse CPF, **reaproveita** o existente; senão
     cria novo. Coleta a lista de responsáveis.
  3. `atendido = AtendidoForm.save(commit=False)`; `atendido.familia = familia`;
     `atendido.registrado_por = request.user`; `atendido.save()`.
  4. `atendido.responsavel.set(responsaveis)`;
     `AtendidoForm.save_m2m()` (para `aspectos_mudancas`).
  5. Se `atendido.comissao_inclusiva`: `inclusivo = AtendidoInclusivoForm.save(commit=False)`;
     `inclusivo.atendido = atendido`; `inclusivo.save()`.
  6. `messages.success(...)`; `redirect('atendido:detalhe_atendido', pk=atendido.pk)`.
- Se algum form inválido: re-renderiza com os erros (mantendo o que foi digitado).
- O template usa `enctype="multipart/form-data"`; a view passa `request.POST, request.FILES`.

### Forms — `atendido/forms.py` (novo)

- **`AtendidoForm(ModelForm)`** — `fields` = todos os campos de `Atendido` **exceto**
  `familia`, `responsavel`, `registrado_por`, `data_criacao`, `ativo` (esses são
  tratados pela view). `help_text` vem do model. Tornar obrigatórios via
  `__init__`: `matricula`, `escola`, `ano_escolar`. `clean()` valida que `cpf`
  **ou** `rg` foi informado (senão `ValidationError`).
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
âncoras** (lista lateral fixa em telas grandes) para saltar entre seções. Cada
seção é um card `bg-card border border-border rounded-lg`. Cada campo: label com
`*` quando obrigatório, descrição (help_text) em texto pequeno, widget, e erros
inline em vermelho. JS vanilla para: (a) formset dinâmico de responsáveis
(adicionar/remover linha, reindexando `TOTAL_FORMS`); (b) mostrar/ocultar a seção
"Comissão Inclusiva" conforme o checkbox `comissao_inclusiva`; (c) bloco recolhível
"Bens e infraestrutura"; (d) máscaras leves de CPF/telefone/CEP. Diretriz de UI:
Tailwind + shadcn, sem dependência de Bootstrap para estilo, qualidade de
designer sênior, responsivo (a Tríade usa celular).

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
   `programa_transferencia_renda` (checkbox), `agua_encanada`, `esgoto_encanado`,
   `energia_eletrica`, `internet_casa` (checkboxes), `impacto_social` (select),
   `tipo_impacto_social` (select), `cesta_natal` (checkbox);
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
12. **Impacto do PCF** — `mudancas_positivas` (checkbox), `aspectos_mudancas`
    (checkboxes múltiplos de `Mudanca`).
13. **Vestuário** — `numeracao_camisa`, `numeracao_calca`, `numeracao_calcado`.
14. **Termos e Autorizações** — `termos_assinado` (checkbox).
15. **Observações** — `observacoes` (textarea).

## Regras de validação

- **CPF ou RG da criança:** ao menos um preenchido (`AtendidoForm.clean`).
- **≥1 responsável válido:** a view rejeita o POST se nenhum form do formset tiver
  nome + parentesco + contato.
- **Obrigatórios "mais completo":** `matricula`, `escola`, `ano_escolar`, `cep`,
  `bairro`, `cidade`.
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
  `servicos_apoio`) usam checkbox simples (marcado = True; desmarcado = False).

## Fora de escopo (YAGNI)

- Edição/rematrícula reusando esta tela (foco é criar; edição segue no admin por ora).
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
