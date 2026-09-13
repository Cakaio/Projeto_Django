# Bazar — a tela vira caixa — Design Spec

**Data:** 2026-09-13
**App tocado:** `bazar` (mais duas linhas de configuração em `tailwindcss/` e `TESTE/`)
**Autor:** PCF

## Objetivo

A tela de atendimento do Bazar existe e funciona, mas não é operável por quem
nunca a viu — que é exatamente quem vai operá-la, num sábado de manhã, no
próprio celular, com fila na frente.

Este documento registra o redesenho e as decisões que o sustentam. O produto é
uma tela que **se comporta como um caixa de loja**: passos numerados, o saldo
sempre à vista descendo, todo toque com volta, e nenhuma gravação sem uma
conferência explícita com o nome da criança na frente.

**O próximo Bazar é em semanas.** Isso ordena as fatias: primeiro a tela, e logo
em seguida o plano B em papel — que vale mais que qualquer recurso novo, porque
é o que funciona quando nada mais funciona.

## O que motivou: três defeitos verificados, não questão de gosto

Antes de qualquer discussão de layout, três coisas na tela atual estão quebradas.
Foram lidas no código, não inferidas.

**1. Toda mensagem de erro é apagada no instante em que aparece.**
`static/js/bazar-atendimento.js:261` e `:283` escrevem a mensagem e revelam a
faixa. O `.finally` logo abaixo (`:286-290`) chama `redesenharCarrinho()`, que em
`:224-226` faz `elErro.hidden = true` — e `enviando` já foi posto como `false` na
linha anterior, então a condição passa. Consequência: **"João já finalizou a
retirada desta etapa" e "Falha de conexão" nunca são vistos.** O voluntário
aperta Finalizar, a tela não responde, ele aperta de novo. Uma tela que não
responde é, para quem está de fora, uma tela quebrada.

**2. Os pontos não zeram.** `elSaldoNumero` é escrito uma única vez em
`desenharPessoa()` (`:113`) e nunca mais. `redesenharCarrinho()`, que roda a cada
peça, atualiza botões, total e o botão de finalizar — e não toca no saldo. O que
se move é o total da sacola *subindo*, em outro bloco. São dois números grandes
competindo, e o leigo olha para o errado.

**3. Escolher a criança pode não fazer nada.** `escolher()` (`:86-100`) não tem
`.catch`. Se o `fetch` falhar, a função morre em silêncio: nenhum estado muda,
nenhuma faixa aparece.

E o pior alvo de toque da tela: o `−` é um `<span>` de 32px **dentro** do
`<button>` que soma (`atendimento.html:141`). Errar o alvo não é neutro —
**adiciona** peça. Também é `<span>`, então não é focável: dá para somar peça
pelo teclado e não dá para tirar.

## Duas armadilhas de configuração

Pequenas, invisíveis, e as duas quebram o redesenho em silêncio.

**`js/bazar-atendimento.js` não está em `ARQUIVOS_OBSERVADOS`**
(`TESTE/versao_estatica.py:30`). O carimbo `?v=` que quebra cache olha quatro
arquivos, e esse não é um deles. Reescrever o JS e publicar **não entrega o
arquivo novo** a quem já abriu o site. O docstring do próprio arquivo registra
que esse bug já custou três rodadas de confusão.

**`bazar/**/*.html` não está no `content` do Tailwind**
(`tailwindcss/tailwind.config.js:13-29`) — nem `acervo`, `estudio`,
`notificacoes`. O comentário no próprio arquivo avisa: *"Faltando aqui, classe
usada SÓ neles é purgada em silêncio e a tela quebra sem erro nenhum."* Hoje não
quebra por acaso (as classes que o Bazar usa aparecem em outras telas também),
mas qualquer classe nova do redesenho some.

As duas entram na **primeira** tarefa da implementação, não na última.

## Decisões do cliente

Tomadas em 2026-09-13, registradas para não serem re-litigadas.

### 1. Criança não cadastrada pode ser atendida, como VISITANTE

Registro separado, com nome escrito à mão e motivo de uma linha. **Não vira
`Atendido`** — a regra de não existir segunda verdade sobre a mesma criança
continua valendo. Permite contar quantas exceções houve, que é uma estatística
de fechamento por si só.

Consequência no modelo: `Retirada.atendido` deixa de ser obrigatório. E como a
trava por etapa é feita em cima do atendido, **visitante precisa da própria
trava** — senão a mesma pessoa passa quantas vezes quiser.

### 2. Na 2ª etapa a mesma criança pode passar mais de uma vez

O objetivo declarado da 2ª etapa é esvaziar o estoque; ali a trava não protege
ninguém e só produz mensagem de erro para quem está certo. A `UniqueConstraint`
passa a valer **só na 1ª etapa**. O fechamento conta passagens e crianças
distintas separadamente.

### 3. "Veio e não levou nada" entra, em contagem separada

Hoje `conferir_pedido` recusa sacola vazia, então "quantos atendidos vieram"
responde na verdade "quantos levaram peça" — e a criança que não achou nada do
tamanho dela, que é a evidência mais direta de que faltou tamanho, é invisível.
Passa a caber num toque, e o fechamento mostra as duas contagens lado a lado.

Duas contagens separadas não quebram a comparação com edições passadas.

### 4. Offline: meio-termo

A tela abre e a busca funciona sem rede — a lista de elegíveis fica no aparelho
e é apagada no encerramento do Bazar e no logout. **Mas a retirada só vale
quando o servidor confirma**; se falhar, é papel.

Fila de envio local com reenvio automático fica **fora** desta entrega: o modo
de falha é silencioso demais para um evento que acontece uma vez por ano e não
tem ensaio. Só volta à mesa se houver ensaio em modo avião, com voluntários que
não escreveram o código.

## O desenho da tela

Três passos, sempre nomeados: **quem é o próximo** → **marque as peças** →
**confira e entregue**.

```
┌──────────────────────────────────────┐
│ 1ª ETAPA · cota 5      CAIXA: Sala 2 │
├──────────────────────────────────────┤
│ ANA CLARA SOUZA             9 anos   │
│ Salinha Amarelo         [ trocar ]   │
│ camisa 10 · calça 8 · calçado 32     │
├──────────────────────────────────────┤
│ PASSO 2 de 3 — MARQUE AS PEÇAS       │
│ ┌────────────────┐ ┌───────────────┐ │
│ │▌−│ CAMISETA  ×2│ │ CALÇA         │ │
│ │▌ │ 1 pt·restam38│ │ 2 pts · rest 9│ │
│ │▌ │ toque p/ mais│ │ toque p/ somar│ │
│ └────────────────┘ └───────────────┘ │
│        role para ver mais peças      │
╞══════════════════════════════════════╡  ← fixo daqui pra baixo
│ RESTAM  3  de 5 pontos               │
│ ▓▓▓▓▓▓▓▓░░░░░░░░░░░░  2 usados       │
│ último: + Camiseta            [ ↶ ]  │
│ SACOLA: 2 peças · 2 pontos           │
│ ┌──────────────────────────────────┐ │
│ │    CONFERIR E ENTREGAR        >  │ │
│ └──────────────────────────────────┘ │
│ Levou: o próprio atendido  [ trocar ]│
└──────────────────────────────────────┘
```

`▌` é a faixa de 44px com a altura inteira do bloco que serve de `−`. Ela só
aparece depois que há peça marcada; antes disso o bloco inteiro é um alvo só.

### Por que assim

**O rodapé é fixo; só as peças rolam.** Hoje o saldo mora num cartão no topo que
sai da tela exatamente enquanto se marca peça — é por isso que ele parece não
existir.

**Um número grande só, e ele desce.** "RESTAM 3 de 5" cai a cada toque, com uma
barra enchendo ao lado. Ponto é o troco da ficha de papel que ele substituiu:
acaba, e dá para ver acabando.

**O `−` ganha faixa própria de 44px com a altura inteira do bloco**, e só aparece
quando já há peça marcada. O `+` continua sendo o bloco inteiro, que é onde o
leigo toca. Nada de dividir o alvo em dois no meio do gesto.

**Impossibilidade vira frase, nunca botão cinza mudo.** "Não cabe: falta 1 ponto"
escrito dentro do próprio botão. Botão desligado em silêncio é tela quebrada
para quem nunca usou o sistema.

**Criança que já passou não tem grade apagada — tem grade não desenhada**, e uma
frase inteira no lugar: "Ana já levou a sacola desta etapa às 09:12, na Sala 2,
com o Lucas."

**O verde não grava.** Abre a folha de conferência com o nome da criança, as
peças e o que vai sobrar. Dois botões: voltar e corrigir, ou confirmar.

**Depois de gravado, 2 minutos para desfazer.** Cancelar devolve a retirada ao
estado de rascunho (`finalizada_em` nulo) — que não consome nada e reabre a
trava sozinho, porque a `UniqueConstraint` já tem `condition`. Não é preciso
inventar campo de status.

**A sala do caixa é escolhida uma vez por aparelho**, não redigitada a cada
criança. Hoje é um campo de texto livre que é preenchido nas cinco primeiras e
fica vazio no resto da manhã.

**"Quem levou" volta ao padrão a cada criança.** Hoje não é limpo: uma vez
marcado "Outra pessoa autorizada — Maria Souza", a manhã inteira sai com a Maria
colada em crianças que vieram sozinhas.

**A busca mostra idade junto do nome.** Hoje `buscar_atendido` devolve só id,
nome e sala — duas "Maria Eduarda" do Amarelo são duas linhas idênticas, e a
retirada vai para a criança errada. Esse é o único erro do sistema sem conserto
fácil, porque a trava depois barra a criança certa.

**A tela escuta a etapa.** Hoje `descontaPontos` e a lista de categorias são
congelados no carregamento: a tela que ficou aberta continua barrando sacola por
falta de pontos que já não existem.

## Contingência, em três camadas

**1. Kit de papel, impresso antes.** Rota nova, aberta a **qualquer voluntário
logado** — hoje o único CSV está atrás da coordenação, o que é inútil: quem está
no caixa não consegue baixar. No molde de `ronda/templates/imprimir_ronda.html`
(HTML autônomo, sem `base.html`, botão que some no `@media print`). Duas folhas:

- **Ficha do caixa**, uma por sala: cabeçalho com nome, data, etapa e a cota em
  destaque, a tabela de pontos por categoria (quem soma à mão precisa da tabela
  na frente), e 12 linhas em branco — uma por criança, não por peça.
- **Lista de elegíveis por salinha**: nome, idade, numerações e um quadradinho.
  Resolve homônimo no papel do mesmo jeito que na tela.

Também em `.xlsx` (`openpyxl==3.1.5` já é dependência direta, `requirements.txt:6`).

**2. A tela sobrevive sem rede** (decisão 4 acima).

**3. Lançar o papel depois.** Tela onde se escolhe a edição e a etapa na mão e se
digita a hora escrita na ficha. Hoje isso é **impossível**: `finalizada_em` é
`timezone.now()` fixo no corpo de `finalizar_retirada`, a etapa vem de
`bazar.etapa`, `conferir_pedido` exige bazar aberto — e o admin cria retirada mas
o inline de itens é readonly com `extra=0`, ou seja, a saída de emergência que
parece existir só produz retiradas vazias que já queimam a trava da etapa.

Cada linha lançada fica marcada como `origem=PAPEL`, e o fechamento diz quantas
foram. Um relatório que não avisa que 40 das 190 linhas foram digitadas na
segunda-feira apresenta como medição o que foi reconstrução.

## Fechamento

Quem operou o caixa para de cair em "Nenhum Bazar aberto", que parece defeito, e
passa a ver os três números que interessam a quem estava lá.

A coordenação abre o fechamento completo:

- **Passaram X de Y**, com Y **congelado no encerramento** — hoje elegíveis é
  `Atendido.objects.ativos().count()` no instante da consulta, então abrir o
  relatório no ano seguinte dá um número diferente do que foi lido no dia.
- **Uso da cota na 1ª etapa**: média, quantos zeraram, quantos usaram 1 ou menos.
  É a única evidência de se 5 pontos é o número certo. Só da 1ª etapa: somar as
  duas mede coisas opostas.
- **Peças por categoria, separadas por etapa** — vira o pedido de doação do ano
  seguinte.
- **Quem não veio, por salinha, com nome** — "104/230" não diz o que fazer; com
  nome, a salinha liga ou guarda a sacola.
- **Ritmo por faixa de 15 minutos**, com o pico e a hora em que a etapa virou. A
  troca é manual de propósito; manual sem dado é palpite.
- **Sobra por categoria**, com um campo de contagem física digitado no
  encerramento. O domínio já assume que contagem de bazar é aproximada — sem a
  contagem real, "sobrou 40" é uma conta, não um fato.
- **Vieram e não levaram nada** (decisão 3).
- **Quantas linhas vieram de papel.**

## Mudanças no modelo

Nenhuma altera regra existente.

| Onde | O quê | Por quê |
|------|-------|---------|
| `Retirada.atendido` | passa a aceitar nulo | visitante |
| `Retirada` | `visitante_nome`, `visitante_motivo` | visitante |
| `Retirada` | `origem` (TELA/PAPEL), `lancado_por` | lançamento retroativo |
| `Retirada` | `conferido_por_nome` | o universitário do dia pode não ter login |
| `Retirada` | `token` (idempotência) | reenvio não vira "já finalizou" |
| `Retirada` | `cancelada_em`, `cancelada_por`, `motivo_cancelamento` | desfazer visível |
| `Retirada` | `sem_retirada` (booleano) | "veio e não levou nada" |
| `Retirada` | numerações **copiadas** | hoje são lidas ao vivo da ficha; atualizar a ficha em março reescreve a estatística de outubro |
| `UniqueConstraint` | passa a valer só na 1ª etapa | decisão 2 |
| `Bazar` | `aberto_em`, `encerrado_em`, `elegiveis_no_encerramento` | ritmo e número congelado |
| `Categoria` | `contagem_final` | sobra real |
| `SalaDoBazar` (novo) | nome, ordem, ativo | hoje é `CharField` livre |

E em `regras.py`, cirurgia e não reescrita: `finalizar_retirada` ganha `quando`,
`etapa`, `lancado_por` e `token`, e passa a **promover um rascunho existente** em
vez de sempre criar.

`ItemRetirada.save()` calcula `pontos_total`, mas o único caminho de gravação usa
`bulk_create`, que **pula `save()`**. Hoje não quebra porque `conferir_pedido` já
devolve os valores calculados. Qualquer caminho novo de gravação (o lançamento de
papel, por exemplo) precisa saber disso.

## O que sobrevive inteiro

`bazar/models.py` continua valendo — e três decisões dele passam a ser **usadas
pela primeira vez**: `finalizada_em` nulo já *é* o rascunho que a docstring
promete e que ninguém cria; a `UniqueConstraint` ignorar rascunho é o que permite
o carrinho viver no servidor; e cancelar é devolver ao rascunho.

`bazar/regras.py` quase intacto: `saldo_de`, `pontos_usados_na_etapa`,
`ja_retirou_nesta_etapa`, `situacao_do_atendido`, `conferir_pedido` e
`estoque_estourado` continuam sendo a única autoridade. A tela nova só pergunta
mais vezes.

Reescrito do zero: `atendimento.html`, `bazar-atendimento.js` e `painel.html` —
que hoje quase não usa `.pcf-*` e reinventa borda, raio e sombra próprios, e é
parte do "não parece do mesmo sistema".

## Fatias

O cliente escolheu entrega em fatias, e o Bazar é em semanas.

**Fatia 1 — a tela do caixa.** As duas linhas de configuração; os três defeitos
verificados; a tela nova de atendimento e o JS; mobile de verdade. Tem valor
sozinha.

**Fatia 2 — o kit de papel.** Ficha e lista imprimíveis, abertas a qualquer
voluntário logado, mais o `.xlsx`.

> **Recomendação:** dado o prazo, a Fatia 2 é pequena e é o plano B do evento.
> Se sobrar qualquer dúvida sobre o cronograma, ela deve vir **antes** de
> qualquer outra coisa — papel impresso funciona sem servidor, sem rede e sem
> bateria.

**Fatia 3 — lançar o papel depois**, com os campos de modelo que ela exige.

**Fatia 4 — fechamento e estatísticas.**

**Fatia 5 — a tela sobreviver sem rede.**

## Riscos assumidos

- **Reescrever `atendimento.html` quebra `bazar/tests_telas.py` de propósito** —
  ele faz asserção sobre o conteúdo renderizado. Esse retrabalho está no plano.
- **O test client do Django quebra ao renderizar template neste ambiente**
  (Python 3.14). Os testes de tela usam `RequestFactory`, como no resto do
  projeto.
- **Nada prova a frase "uma pessoa leiga consegue" a não ser uma pessoa leiga.**
  Antes do evento, alguém que não escreveu o código deve registrar três crianças
  com outra pessoa cronometrando e calada.

## O que este documento deliberadamente NÃO resolve

Levantado e adiado, para não voltar como surpresa:

- **Tela de configuração do Bazar.** Cota, categorias e estoque continuam no
  admin do Django, que exige `is_staff` — ou seja, o coordenador de EVENTOS não
  abre. O cliente disse que configuração "pode ser mais completa"; fica para
  depois das cinco fatias.
- **Duplicar a edição do ano passado** (hoje se redigita tudo na véspera).
- **Irmãos na mesma passagem** — `Familia` e responsáveis já existem no modelo e
  ninguém usa; é a maior economia de tempo disponível na fila.
- **Troca e devolução de peça** — a criança prova, não serve, volta na fila.
- **Colisão com a roupa já na mão**: quando a Sala 3 ouve "já foi registrada às
  9h12", a sacola já saiu. O que fazer com ela é decisão de processo, não de
  software.
- **Login dos voluntários do dia** — `conferido_por` é FK obrigatória a usuário;
  `conferido_por_nome` alivia, mas criar e entregar contas antes continua sendo
  trabalho de gente.
