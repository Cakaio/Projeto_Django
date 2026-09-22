# Rateio de gasto: descontar o teto sem descontar o caixa

## O problema

O Supply compra com **dois ou mais cartões**, de voluntários diferentes, numa
compra só — não separada por salinha. Depois alguém precisa lançar quanto cada
salinha gastou, para o teto da área descontar.

Essas duas coisas não se encontram:

- O **extrato** sabe quanto saiu de cada cartão, e não sabe de qual salinha foi.
- A **nota** sabe que o Família Feliz gastou R$34, e não sabe de qual cartão
  saiu.

Quem lança o gasto da salinha não tem como responder "de qual cartão?", e hoje
o formulário exige escolher um. O resultado prático é número inventado ou
lançamento que não acontece.

Lançar as duas coisas como despesa resolveria o teto e **quebraria o caixa**: os
R$800 dos cartões mais os R$800 rateados viram R$1.600 de gasto que não
existiu.

## A separação que o sistema já tinha e ninguém tinha explorado

As três contas do Financeiro leem campos DIFERENTES do mesmo lançamento:

| Quem soma | Filtra por | Ignora |
|---|---|---|
| Teto da área (`_despesa_agrupada_por_area`) | `area` | `conta` |
| Saldo do cartão (`saldo_das_contas`) | `conta` | `area` |
| Total gasto / DRE / fluxo | nada — soma tudo | — |

Só a terceira impede lançar as duas coisas. O desenho abaixo tira o rateio de
dentro do `Lancamento` justamente por isso.

## A decisão central: rateio NÃO é lançamento

`RateioDeGasto` e `LinhaDeRateio` são modelos próprios, fora do `Lancamento`.

A alternativa era uma marca (`so_teto`) no próprio `Lancamento`, com `.exclude()`
nas consultas de total. Foi recusada: bastaria UMA consulta futura esquecer o
filtro para dinheiro fantasma aparecer no caixa, e quem escreve essa consulta
daqui a um ano não vai saber que a marca existe.

Como modelo separado, **dinheiro fantasma no caixa é impossível por
construção** — não há filtro para esquecer. O rateio tem um consumidor só: o
teto.

## Os modelos

**`RateioDeGasto`** — o documento de um sábado
- `data` — decide em qual semestre o teto desconta
- `total_a_ratear` — digitado pela ADM (ex.: R$800)
- `descricao` — distingue dois rateios do mesmo dia ("materiais", "lanches")
- `fechado_em` — **nulo significa ABERTO**. Sem booleano ao lado: data e
  booleano são duas verdades sobre o mesmo fato, e na primeira vez que uma for
  gravada sem a outra ninguém sabe qual vale. Mesmo padrão do
  `supply.FechamentoSabado`.
- `criado_por`, `criado_em`

**`LinhaDeRateio`** — uma por salinha
- `rateio` (CASCADE: linha não existe fora do documento)
- `area` (`LISTA_AREAS`), `valor`
- `UniqueConstraint(rateio, area)` — duas linhas "Família Feliz" no mesmo
  rateio deixariam a soma ambígua e a tela mostrando a salinha duas vezes.

### Regras

- Ratear **acima** do total é **recusado**: isso é dedo errado, não trabalho
  pela metade.
- Ratear **abaixo** salva e o rateio fica ABERTO. Melhor um teto parcialmente
  certo que um teto zerado esperando alguém ter tempo.
- `fechado_em` só pode ser preenchido quando a soma bate no centavo.

## O que muda em cada consulta

| Consulta | Muda? |
|---|---|
| `situacao_dos_tetos` | **sim** — soma `Lancamento.area` **+** `LinhaDeRateio.area` |
| `gasto_por_area` ("onde investimos") | **NÃO** |
| `saldo_das_contas` | não — rateio não é `Lancamento` |
| `total_despesas`, DRE, fluxo de caixa | não — idem |

**`gasto_por_area` fica de fora de propósito.** Ela responde "para onde o
dinheiro foi", e o dinheiro já foi contado no lançamento do cartão. Somar o
rateio ali dobraria o total da própria tela. Por isso `_despesa_agrupada_por_area`
NÃO muda: o rateio entra por uma função separada, que só o teto chama.

## O fluxo, na prática

1. A ADM lança **cada cartão** com o valor real do extrato: categoria
   "materiais de Supply", **área vazia**, conta = o cartão. Isso desconta o
   saldo daquele cartão e entra no total do projeto.
2. A ADM cria o **rateio do sábado** com o total e distribui entre as salinhas.
   Isso desconta **só** o teto.
3. Ela nunca precisa saber de qual cartão saiu o gasto de cada salinha.

**O reembolso não muda em nada.** Continua nascendo como `Lancamento` com área
**e** conta: desconta o teto da salinha **e** a despesa do ADM/FIN. A diferença
entre os dois é real — no reembolso o dinheiro sai agora; no rateio ele já saiu
antes, pelo cartão.

## Telas

```
/adm/rateios/                lista, ABERTOS no topo
/adm/rateios/novo/           data, descrição, total a ratear
/adm/rateios/<pk>/           o trabalho: uma linha por salinha
/adm/rateios/<pk>/deletar/
```

Quem escreve: **`ADM/FIN`** e superusuário (o mesmo `AREAS_ESCRITA` do teto).
Não é o Supply que rateia — rateia quem tem a nota na mão.

**Rateio ABERTO precisa incomodar**: aviso no painel do ADM com quanto falta.
Sem isso ele apodrece em silêncio e o teto fica menor que a realidade — que é o
defeito que este trabalho existe para matar.

**Na tela de tetos o número se explica.** Sem isso o líder da salinha vê o teto
encolher e procura um lançamento que não existe:

```
Família Feliz   teto R$ 500   gasto R$ 234
                  ├─ lançamentos (reembolso etc.) ... R$ 200
                  └─ rateio do Supply ............... R$  34
```

## O que este desenho NÃO faz

- **Não confere o rateio contra os cartões.** O total é digitado. Decisão da
  coordenação: parte da compra pode não ser de salinha nenhuma, e travar isso
  emperraria o fechamento.
- **Não junta com o `FechamentoSabado` do Supply.** Aquilo é o Supply avisando
  "conferi os números"; o rateio é da ADM. Juntar faria o Supply responder por
  um número que ele não lança.
