"""Lê o prazo de inscrição do texto do edital.

Sem isso a regra de prazo não serve para quase nada: o robô nunca preenchia
`prazo`, então todo edital que ele trazia tinha data vazia e passava pelo filtro
como se fosse oportunidade aberta. Quem descobria que a chamada tinha fechado
era a pessoa, clicando.

Aqui não tem IA, igual ao resto do módulo: é data escrita em português achada
por padrão de texto. E é melhor-esforço declarado — quando não dá para afirmar,
devolve None, e o edital segue aparecendo. Errar escondendo um edital vivo custa
mais caro para o projeto do que errar mostrando um vencido.
"""
import re
import unicodedata
from datetime import date

# Uma data só não diz nada: edital tem data de publicação, de resultado, de
# início do projeto. O que marca prazo é a palavra que vem ANTES dela.
GATILHOS = (
    'ate', 'prazo', 'inscric', 'encerra', 'submiss', 'submet', 'limite',
    'termina', 'data final', 'ultimo dia', 'vence',
)

# Quantos caracteres olhar para trás procurando o gatilho. Curto de propósito:
# uma janela larga acha "inscrições" a três frases de distância e cola a
# palavra numa data que não tem nada a ver.
JANELA_GATILHO = 70

MESES = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4, 'maio': 5,
    'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10,
    'novembro': 11, 'dezembro': 12,
}

# Fora dessa faixa é ruído de parser, não prazo: ano digitado errado, data de
# fundação da entidade, número que só parecia data.
ANOS_PARA_TRAS = 2
ANOS_PARA_FRENTE = 3

_NUMERICA = re.compile(r'(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?!\d)')
_ESCRITA = re.compile(
    r'(?<!\d)(\d{1,2})\s*(?:o|º)?\s+de\s+(' + '|'.join(MESES) + r')'
    r'(?:\s+de\s+(\d{4}))?',
)


def normalizar(texto):
    """Minúsculas e sem acento, para o gatilho casar com "inscrições" e "marco"."""
    if not texto:
        return ''
    sem_acento = unicodedata.normalize('NFD', str(texto))
    sem_acento = ''.join(c for c in sem_acento if unicodedata.category(c) != 'Mn')
    return sem_acento.lower()


def _ano_de_quatro_digitos(bruto, hoje):
    ano = int(bruto)
    if ano >= 100:
        return ano
    # "30/11/26" é 2026, não 26 d.C. Ancora no século de hoje.
    return (hoje.year // 100) * 100 + ano


def _dentro_da_faixa(candidata, hoje):
    return (hoje.year - ANOS_PARA_TRAS) <= candidata.year <= (hoje.year + ANOS_PARA_FRENTE)


def _tem_gatilho_antes(texto, posicao):
    trecho = texto[max(0, posicao - JANELA_GATILHO):posicao]
    return any(gatilho in trecho for gatilho in GATILHOS)


def _datas_com_gatilho(texto, hoje):
    achadas = []

    for casamento in _NUMERICA.finditer(texto):
        if not _tem_gatilho_antes(texto, casamento.start()):
            continue
        dia, mes, ano = casamento.groups()
        try:
            candidata = date(_ano_de_quatro_digitos(ano, hoje), int(mes), int(dia))
        except ValueError:
            continue          # 31/02, 45/13 — não é data
        if _dentro_da_faixa(candidata, hoje):
            achadas.append(candidata)

    for casamento in _ESCRITA.finditer(texto):
        if not _tem_gatilho_antes(texto, casamento.start()):
            continue
        dia, mes, ano = casamento.groups()
        # "até 30 de novembro", sem ano: assume o próximo 30/11 que ainda não
        # passou. Assumir o ano corrente venceria o edital sozinho em janeiro.
        try:
            if ano:
                candidata = date(int(ano), MESES[mes], int(dia))
            else:
                candidata = date(hoje.year, MESES[mes], int(dia))
                if candidata < hoje:
                    candidata = date(hoje.year + 1, MESES[mes], int(dia))
        except ValueError:
            continue
        if _dentro_da_faixa(candidata, hoje):
            achadas.append(candidata)

    return achadas


def extrair_prazo(titulo, descricao, hoje=None):
    """Devolve a data de inscrição achada no texto, ou None.

    Quando há mais de uma data com gatilho, fica a MAIS DISTANTE. "inscrições de
    01/10 até 30/11" tem as duas marcadas, e o prazo é a segunda; e na dúvida
    entre duas datas soltas, escolher a mais longe erra para o lado de mostrar o
    edital em vez de esconder.
    """
    hoje = hoje or date.today()
    texto = normalizar(f'{titulo or ""} . {descricao or ""}')
    achadas = _datas_com_gatilho(texto, hoje)
    return max(achadas) if achadas else None
