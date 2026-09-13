"""Sinais do Financeiro.

VAZIO DE PROPÓSITO — e a explicação importa mais que o código que havia aqui.

Até setembro/2026 este módulo espelhava cada `supply.Pedido` como despesa no
Financeiro: criava o Lançamento no `post_save` e o apagava no `post_delete`.
A coordenação pediu para desligar. O motivo não é técnico:

    o jeito como o Supply registra pedido nem sempre é o que foi gasto de
    verdade — quantidade estimada, valor de orçamento, item trocado na hora da
    compra, lanche que custou outro preço no mercado.

Espelhar isso automaticamente fazia o teto da área encolher com número de
orçamento, e ninguém tinha como saber quais linhas eram reais. Agora quem
lança gasto de Supply é o ADM, na mão, depois do sábado, olhando a nota. O
`valor` e a `area` continuam no Pedido, para o Supply se planejar — só não
atravessam mais para o Financeiro.

O que continua automático: reembolso (`forms_pcf/views.py`) e contribuição de
parceiro (`parceiros/signals.py`). Nos dois, o valor que entra no Financeiro é
o valor que de fato saiu ou entrou, conferido por quem aprovou.

Se um dia o Supply passar a registrar o custo REAL (nota em mãos, não
orçamento), reativar o espelho volta a fazer sentido — mas aí o gatilho é a
conferência do sábado, não o salvamento do pedido.
"""
