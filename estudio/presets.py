"""Modelos de página tirados da edição de março da Revista PCF.

Cada preset devolve uma lista de elementos já posicionados. Quem aplica pode
mexer em tudo depois — o preset é ponto de partida, não amarra.

As artes (faixa de mãozinhas, nome da sala em arco, ondas do Dia da Água) são
desenhos feitos no Canva e não dá para reproduzi-los fielmente em código. Os
presets os procuram no acervo de assets pelo APELIDO; quando a arte ainda não
foi subida, a página nasce sem ela e o resto do layout fica no lugar. É por isso
que `_asset` devolve None em silêncio em vez de estourar: preset meio montado é
melhor que tela de erro.

Apelidos que os presets procuram:
    maozinhas-topo, maozinhas-pe, ondas-agua, faixa-obrigado
    sala-violeta, sala-anil, sala-azul, sala-verde, sala-amarelo,
    sala-laranja, sala-vermelho, sala-familia-feliz
"""
from .models import ALTURA_A4, LARGURA_A4

LARANJA_TITULO = '#f5a623'

# Cores lidas dos painéis da edição de março: o claro é o fundo do painel, o
# escuro é a borda e a moldura da foto.
CORES_DAS_SALAS = {
    'VIOLETA': ('#e8dcf5', '#9b6fc4'),
    'ANIL': ('#d8e4f7', '#4a6fa5'),
    'AZUL': ('#d5f0f7', '#2f9fb8'),
    'VERDE': ('#ddf0d5', '#5aa03c'),
    'AMARELO': ('#fbf3cf', '#c9a20e'),
    'LARANJA': ('#fce3cd', '#e07b28'),
    'VERMELHO': ('#fbd5d3', '#d64545'),
    'FAMILIA_FELIZ': ('#ece0d5', '#8b6f52'),
}

ESTILO_TITULO = {
    'fonte': 'display', 'tamanho': 54, 'peso': 800, 'alinhamento': 'center',
    'cor': LARANJA_TITULO, 'maiusculas': True, 'letra_espaco': 1,
    'contorno_cor': '#ffffff', 'contorno_largura': 2,
}
ESTILO_CORPO = {
    'fonte': 'corpo', 'tamanho': 13, 'alinhamento': 'justify',
    'entrelinha': 1.55, 'cor': '#2b2b2b',
}


def _asset(apelido):
    """Busca a arte pelo apelido. None quando ainda não foi subida."""
    from .models import Asset
    return Asset.objects.filter(apelido=apelido).first()


def _faixas_de_maozinhas():
    """Topo e pé. Sangram para fora da página, como no PDF (x e y negativos)."""
    elementos = []
    topo = _asset('maozinhas-topo')
    if topo:
        elementos.append({
            'tipo': 'IMAGEM', 'imagem': topo, 'x': -20, 'y': -10,
            'largura': LARGURA_A4 + 40, 'altura': 90, 'z': 1,
            'estilo': {'ajuste': 'cover'}, 'travado': True,
        })
    pe = _asset('maozinhas-pe')
    if pe:
        elementos.append({
            'tipo': 'IMAGEM', 'imagem': pe, 'x': -20, 'y': ALTURA_A4 - 80,
            'largura': LARGURA_A4 + 40, 'altura': 90, 'z': 1,
            'estilo': {'ajuste': 'cover'}, 'travado': True,
        })
    return elementos


def _numero_da_pagina(numero):
    """Número no pé, à direita — em toda página miolo da edição de março."""
    return {
        'tipo': 'TEXTO', 'texto': str(numero),
        'x': LARGURA_A4 - 90, 'y': ALTURA_A4 - 78, 'largura': 60, 'altura': 50, 'z': 40,
        'estilo': {'fonte': 'display', 'tamanho': 34, 'peso': 800,
                   'alinhamento': 'right', 'cor': '#1a1a1a'},
    }


def capa(titulo='REVISTA PCF', edicao='', **_):
    """Foto sangrando na página inteira, título artístico e selo da edição."""
    elementos = [{
        'tipo': 'FORMA', 'x': 0, 'y': 0, 'largura': LARGURA_A4, 'altura': ALTURA_A4, 'z': 0,
        'estilo': {'forma': 'retangulo', 'fundo': '#cfe8f5'},
    }]
    elementos += _faixas_de_maozinhas()
    elementos.append({
        'tipo': 'TEXTO', 'texto': titulo,
        'x': 40, 'y': 150, 'largura': LARGURA_A4 - 80, 'altura': 110, 'z': 30,
        'estilo': dict(ESTILO_TITULO, tamanho=78),
    })
    if edicao:
        elementos.append({
            'tipo': 'TEXTO', 'texto': edicao,
            'x': 180, 'y': ALTURA_A4 - 210, 'largura': LARGURA_A4 - 360, 'altura': 80, 'z': 30,
            'estilo': {'fonte': 'display', 'tamanho': 20, 'peso': 700,
                       'alinhamento': 'center', 'cor': '#ffffff',
                       'fundo': LARANJA_TITULO, 'raio': 14, 'maiusculas': True},
        })
    return elementos


def sumario(itens=(), **_):
    """Título e a lista com linha pontilhada até o número da página."""
    elementos = _faixas_de_maozinhas()
    elementos.append({
        'tipo': 'TEXTO', 'texto': 'SUMÁRIO',
        'x': 40, 'y': 130, 'largura': LARGURA_A4 - 80, 'altura': 90, 'z': 30,
        'estilo': dict(ESTILO_TITULO, tamanho=64),
    })
    y = 300
    for rotulo, pagina in (itens or [('Seção', '1')]):
        elementos.append({
            'tipo': 'TEXTO', 'texto': f'{rotulo} {"." * 30} {pagina}',
            'x': 70, 'y': y, 'largura': LARGURA_A4 - 140, 'altura': 46, 'z': 20,
            'estilo': {'fonte': 'display', 'tamanho': 17, 'cor': '#2b2b2b',
                       'alinhamento': 'left'},
        })
        y += 56
    return elementos


def salinha(sala='VIOLETA', texto='', foto_a_esquerda=False, numero=None, **_):
    """Painel colorido, nome da sala em arco, texto e foto com moldura.

    A foto alterna de lado a cada sala na edição de março — é o que dá ritmo à
    página quando três salinhas se empilham.
    """
    claro, escuro = CORES_DAS_SALAS.get(sala, ('#f0f0f0', '#888888'))
    elementos = _faixas_de_maozinhas()

    elementos.append({
        'tipo': 'FORMA', 'x': 36, 'y': 140, 'largura': LARGURA_A4 - 72, 'altura': 300, 'z': 5,
        'estilo': {'forma': 'retangulo', 'fundo': claro, 'raio': 28,
                   'borda_cor': escuro, 'borda_largura': 2},
    })

    arco = _asset(f'sala-{sala.lower().replace("_", "-")}')
    if arco:
        elementos.append({
            'tipo': 'IMAGEM', 'imagem': arco, 'x': 20, 'y': 96,
            'largura': 220, 'altura': 80, 'z': 25, 'estilo': {'ajuste': 'contain'},
        })
    else:
        # Sem a arte do Canva, o nome entra como texto rotacionado — não é
        # igual, mas a página não nasce sem identificação da sala.
        elementos.append({
            'tipo': 'TEXTO', 'texto': sala.replace('_', ' ').title(),
            'x': 26, 'y': 100, 'largura': 240, 'altura': 60, 'z': 25, 'rotacao': -8,
            'estilo': {'fonte': 'display', 'tamanho': 36, 'peso': 800,
                       'cor': escuro, 'contorno_cor': '#ffffff', 'contorno_largura': 2},
        })

    largura_foto = 250
    if foto_a_esquerda:
        x_foto, x_texto = 60, 60 + largura_foto + 24
    else:
        x_foto, x_texto = LARGURA_A4 - 60 - largura_foto, 60

    elementos.append({
        'tipo': 'FORMA', 'x': x_foto, 'y': 175, 'largura': largura_foto, 'altura': 230, 'z': 15,
        'estilo': {'forma': 'retangulo', 'fundo': '#ffffff', 'raio': 16,
                   'borda_cor': escuro, 'borda_largura': 4},
    })
    elementos.append({
        'tipo': 'TEXTO', 'texto': texto or 'Escreva aqui o resumo do mês desta salinha.',
        'x': x_texto, 'y': 175,
        'largura': LARGURA_A4 - 120 - largura_foto - 24, 'altura': 240, 'z': 20,
        'estilo': ESTILO_CORPO,
    })
    if numero:
        elementos.append(_numero_da_pagina(numero))
    return elementos


def texto_centrado(titulo='TÍTULO', texto='', numero=None, **_):
    """Página de Portas Abertas e de Agradecimento: título e um bloco só."""
    elementos = _faixas_de_maozinhas()
    elementos.append({
        'tipo': 'TEXTO', 'texto': titulo,
        'x': 40, 'y': 130, 'largura': LARGURA_A4 - 80, 'altura': 90, 'z': 30,
        'estilo': ESTILO_TITULO,
    })
    elementos.append({
        'tipo': 'TEXTO', 'texto': texto or 'Escreva aqui o texto desta página.',
        'x': 70, 'y': 290, 'largura': LARGURA_A4 - 140, 'altura': 420, 'z': 20,
        'estilo': dict(ESTILO_CORPO, tamanho=17, alinhamento='center', entrelinha=1.7),
    })
    if numero:
        elementos.append(_numero_da_pagina(numero))
    return elementos


def grade_de_fotos(titulo='FOTOS', quantas=6, decoracao='', numero=None, **_):
    """Mosaico de fotos, como as páginas de Portas Abertas e Dia da Água."""
    elementos = _faixas_de_maozinhas()
    elementos.append({
        'tipo': 'TEXTO', 'texto': titulo,
        'x': 40, 'y': 120, 'largura': LARGURA_A4 - 80, 'altura': 90, 'z': 30,
        'estilo': ESTILO_TITULO,
    })

    if decoracao:
        arte = _asset(decoracao)
        if arte:
            elementos.append({
                'tipo': 'IMAGEM', 'imagem': arte, 'x': -10, 'y': 230,
                'largura': LARGURA_A4 + 20, 'altura': ALTURA_A4 - 330, 'z': 2,
                'estilo': {'ajuste': 'contain'}, 'travado': True,
            })

    colunas, margem, vao = 2, 70, 20
    largura = (LARGURA_A4 - 2 * margem - (colunas - 1) * vao) // colunas
    altura = 200
    for indice in range(max(1, quantas)):
        linha, coluna = divmod(indice, colunas)
        elementos.append({
            'tipo': 'FORMA',
            'x': margem + coluna * (largura + vao),
            'y': 250 + linha * (altura + vao),
            'largura': largura, 'altura': altura, 'z': 15,
            'estilo': {'forma': 'retangulo', 'fundo': '#ffffff', 'raio': 14,
                       'borda_cor': '#e2d5c9', 'borda_largura': 3},
        })
    if numero:
        elementos.append(_numero_da_pagina(numero))
    return elementos


def contracapa(mensagem='NOSSO MUITO OBRIGADO!', **_):
    """Foto na página inteira e a faixa curva de agradecimento."""
    elementos = [{
        'tipo': 'FORMA', 'x': 0, 'y': 0, 'largura': LARGURA_A4, 'altura': ALTURA_A4, 'z': 0,
        'estilo': {'forma': 'retangulo', 'fundo': '#d9d4cf'},
    }]
    elementos += _faixas_de_maozinhas()

    faixa = _asset('faixa-obrigado')
    if faixa:
        elementos.append({
            'tipo': 'IMAGEM', 'imagem': faixa, 'x': 60, 'y': 130,
            'largura': LARGURA_A4 - 120, 'altura': 130, 'z': 30,
            'estilo': {'ajuste': 'contain'},
        })
    else:
        elementos.append({
            'tipo': 'TEXTO', 'texto': mensagem,
            'x': 60, 'y': 150, 'largura': LARGURA_A4 - 120, 'altura': 90, 'z': 30, 'rotacao': -4,
            'estilo': {'fonte': 'display', 'tamanho': 40, 'peso': 800,
                       'alinhamento': 'center', 'cor': '#1a1a1a',
                       'fundo': LARANJA_TITULO, 'raio': 40, 'maiusculas': True},
        })
    return elementos


# Nome interno -> (rótulo na tela, função). A ordem é a de uso na revista.
PRESETS = {
    'capa': ('Capa', capa),
    'sumario': ('Sumário', sumario),
    'salinha': ('Salinha', salinha),
    'texto_centrado': ('Título e texto', texto_centrado),
    'grade_de_fotos': ('Grade de fotos', grade_de_fotos),
    'contracapa': ('Contracapa', contracapa),
    'branca': ('Página em branco', lambda **_: []),
}


def aplicar(pagina, nome_do_preset, **argumentos):
    """Cria os elementos do preset na página. Devolve quantos entraram."""
    from .models import Elemento

    rotulo_e_funcao = PRESETS.get(nome_do_preset)
    if not rotulo_e_funcao:
        return 0
    _, funcao = rotulo_e_funcao

    criados = 0
    for dados in funcao(**argumentos):
        Elemento.objects.create(pagina=pagina, **dados)
        criados += 1
    pagina.preset = nome_do_preset
    pagina.save(update_fields=['preset'])
    return criados
