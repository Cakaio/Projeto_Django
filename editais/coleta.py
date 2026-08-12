"""O robô: lê as fontes e dá nota ao que encontra.

Sem IA de propósito. A relevância sai de palavras-chave com peso, cadastradas
pelo CR na tela: a regra fica auditável (dá para olhar a nota e entender de
onde ela veio) e muda sem deploy. Um modelo de linguagem aqui custaria dinheiro
e tiraria do CR o controle sobre o que o projeto considera relevante.
"""
import hashlib
import logging
import re
import unicodedata
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from django.utils import timezone

from .models import PalavraChave

logger = logging.getLogger(__name__)

# Nenhuma chamada de rede sem prazo: a coleta roda em tarefa agendada no
# PythonAnywhere e uma fonte pendurada seguraria o processo indefinidamente.
TEMPO_LIMITE = 20
CABECALHOS = {'User-Agent': 'PCF-Bot/1.0 (projeto social)'}

# Quem escreve edital põe o assunto no título; o corpo é enrolação jurídica.
PESO_TITULO = 2

# Teto do texto guardado por item. A descrição é só insumo da pontuação e da
# leitura rápida na lista — não vale carregar um edital inteiro para o banco.
LIMITE_DESCRICAO = 2000


# ────────────────────────────── Pontuação ──────────────────────────────
def normalizar(texto):
    """Minúsculas, sem acento e sem espaço repetido.

    Os dois lados da comparação passam por aqui: é o que faz 'Criança' casar
    com 'crianca' e 'CRIANÇAS  EM' com 'criancas em'.
    """
    if not texto:
        return ''
    decomposto = unicodedata.normalize('NFKD', str(texto))
    sem_acento = ''.join(c for c in decomposto if not unicodedata.combining(c))
    return ' '.join(sem_acento.lower().split())


def _plural_da_ultima_palavra(palavra):
    """Sufixo de regex que aceita a palavra no singular e no plural.

    Existe porque `(s|es)?` sozinho erra justamente as palavras que mais
    aparecem em edital. Como o texto já vem normalizado (sem acento), 'doação'
    chega como 'doacao' e o plural 'doações' como 'doacoes' — não 'doacaos'.
    Sem tratar isso, 'doação' e 'educação', que estão no dicionário inicial,
    simplesmente não achavam nada e os editais bons ficavam abaixo da nota.
    Mesma história com 'edital' → 'editais'.
    """
    escapada = re.escape(palavra)
    if palavra.endswith('ao'):                       # doacao → doacoes/doacaos/doacaes
        return re.escape(palavra[:-2]) + r'(?:ao|oes|aos|aes)'
    if palavra.endswith(('al', 'el', 'ol', 'ul')):   # edital → editais
        return re.escape(palavra[:-1]) + r'(?:l|is)'
    if palavra.endswith(('r', 'z', 's')):            # mulher → mulheres
        return escapada + r'(?:es)?'
    if palavra.endswith('m'):                        # jovem → jovens
        return re.escape(palavra[:-1]) + r'(?:m|ns)'
    return escapada + r'(?:s)?'


def _padrao_do_termo(termo):
    """Regex do termo já normalizado, tolerando plural.

    Casar por 'está contido em' seria mais fácil, mas 'OSC' acharia
    'oscilação' e 'FIA' acharia 'confiança' — e o CR perderia a confiança na
    nota. Daí as âncoras de fronteira de palavra.

    Em termo composto, só a ÚLTIMA palavra flexiona: 'assistência social' vira
    'assistências sociais' na prática raramente, e flexionar as duas geraria
    falso positivo à toa.
    """
    palavras = termo.split()
    if not palavras:
        return re.compile(r'(?!)')                   # nunca casa
    miolo = [re.escape(p) for p in palavras[:-1]]
    miolo.append(_plural_da_ultima_palavra(palavras[-1]))
    return re.compile(r'(?<!\w)' + r'\s+'.join(miolo) + r'(?!\w)')


def pontuar(texto_titulo, texto_descricao, palavras=None):
    """Nota de relevância sem IA: soma os pesos das palavras-chave achadas.
    O título pesa o dobro do corpo — quem escreve edital põe o assunto no
    título. Devolve (nota, [termos encontrados])."""
    if palavras is None:
        palavras = PalavraChave.objects.filter(ativo=True)

    titulo = normalizar(texto_titulo)
    descricao = normalizar(texto_descricao)

    nota = 0
    encontrados = []
    for palavra in palavras:
        if not palavra.ativo:
            continue
        termo = normalizar(palavra.termo)
        if not termo:
            continue
        padrao = _padrao_do_termo(termo)
        # Cada termo conta uma vez só: repetir a palavra no texto é estilo de
        # quem escreve, não sinal de que o edital serve mais para o projeto.
        if padrao.search(titulo):
            nota += palavra.peso * PESO_TITULO
        elif padrao.search(descricao):
            nota += palavra.peso
        else:
            continue
        encontrados.append(palavra.termo)
    return nota, encontrados


def chave_do_link(link):
    """A mesma conta que `Edital.save()` faz.

    O robô precisa da chave ANTES de ter o objeto, para procurar o que já
    existe em vez de criar duplicata.
    """
    return hashlib.sha256((link or '').strip().lower().encode()).hexdigest()


# ────────────────────────────── Coleta ──────────────────────────────
def _baixar(url):
    """Uma única porta de saída para a rede — sempre com timeout."""
    resposta = requests.get(url, timeout=TEMPO_LIMITE, headers=CABECALHOS)
    resposta.raise_for_status()
    return resposta


def _limpar(bruto):
    """Tira marcação e espaço sobrando: a descrição de RSS vem cheia de HTML."""
    if not bruto:
        return ''
    texto = BeautifulSoup(str(bruto), 'html.parser').get_text(' ')
    return ' '.join(texto.split())


def _texto_do_seletor(bloco, seletor):
    if not seletor:
        return ''
    alvo = bloco.select_one(seletor)
    return _limpar(alvo.get_text(' ')) if alvo else ''


def _href_do_bloco(bloco, seletor):
    """Acha o link do item: pelo seletor, ou pelo primeiro <a> do bloco."""
    alvo = bloco.select_one(seletor) if seletor else None
    if alvo is None:
        alvo = bloco if bloco.name == 'a' else bloco.find('a')
    if alvo is None:
        return ''
    return (alvo.get('href') or '').strip()


def _montar_item(titulo, descricao, link, url_base):
    """Normaliza um item lido para o formato que o comando espera.

    Devolve None quando falta título ou link — item sem link não dá para
    consultar depois, e sem título não dá para o CR reconhecer na lista.
    """
    titulo = _limpar(titulo)
    link = urljoin(url_base, (link or '').strip())
    if not titulo or not link:
        return None
    return {
        'titulo': titulo[:250],                     # max_length do model
        'descricao': _limpar(descricao)[:LIMITE_DESCRICAO],
        'link': link[:500],
    }


def _ler_rss(fonte, limite):
    # O feedparser sabe baixar sozinho, mas por urllib e sem timeout. Baixamos
    # com requests (com prazo) e entregamos os bytes só para ele interpretar.
    resposta = _baixar(fonte.url)
    feed = feedparser.parse(resposta.content)
    itens = []
    for entrada in feed.entries[:limite]:
        item = _montar_item(
            entrada.get('title'),
            entrada.get('summary') or entrada.get('description'),
            entrada.get('link'),
            fonte.url,
        )
        if item:
            itens.append(item)
    return itens


def _ler_html(fonte, limite):
    resposta = _baixar(fonte.url)
    sopa = BeautifulSoup(resposta.text, 'html.parser')
    # Sem seletor cadastrado, tenta o desenho mais comum de listagem.
    blocos = sopa.select(fonte.seletor_item or 'article')
    itens = []
    for bloco in blocos[:limite]:
        titulo = _texto_do_seletor(bloco, fonte.seletor_titulo) or _limpar(bloco.get_text(' '))
        item = _montar_item(
            titulo,
            _texto_do_seletor(bloco, fonte.seletor_descricao),
            _href_do_bloco(bloco, fonte.seletor_link),
            fonte.url,
        )
        if item:
            itens.append(item)
    return itens


def _registrar_coleta(fonte, quantidade, erro):
    """Guarda o resultado da tentativa para a tela de fontes mostrar."""
    fonte.ultima_coleta = timezone.now()
    fonte.ultimo_erro = erro
    fonte.itens_ultima_coleta = quantidade
    if not fonte.pk:
        return
    try:
        fonte.save(update_fields=['ultima_coleta', 'ultimo_erro', 'itens_ultima_coleta'])
    except Exception:
        # Nem gravar o diagnóstico pode derrubar a coleta das outras fontes.
        logger.exception('Não consegui gravar o resultado da coleta da fonte %s', fonte.pk)


def coletar_fonte(fonte, limite=60):
    """Lê UMA fonte e devolve lista de dicts {titulo, descricao, link}.
    Nunca levanta exceção para fora: grava o problema em fonte.ultimo_erro e
    devolve lista vazia — uma fonte quebrada não pode derrubar a coleta toda."""
    itens, erro = [], ''
    try:
        if fonte.tipo == 'RSS':
            itens = _ler_rss(fonte, limite)
        else:
            itens = _ler_html(fonte, limite)
    except Exception as falha:
        # `except Exception` é intencional: rede, HTML torto, encoding, seletor
        # inválido — tudo vira o mesmo recado na tela, para o CR consertar a
        # fonte sozinho. O robô segue para a próxima.
        erro = f'{type(falha).__name__}: {falha}'.strip()[:1000]
        itens = []
    _registrar_coleta(fonte, len(itens), erro)
    return itens


# ────────────────────────────── Gravação ──────────────────────────────
def registrar_item(item, palavras, minimo, fonte=None, consulta=None,
                   origem='ROBO', simular=False):
    """Pontua um item e guarda se valer a pena. Devolve o que aconteceu:
    'ignorado' (nota baixa), 'novo', 'renotado' ou 'existente'.

    Fica aqui, e não dentro do comando, porque as duas entradas do robô — ler
    fonte fixa e varrer a web — precisam obedecer exatamente à mesma regra:
    mesma nota de corte, mesmo dedupe e, principalmente, o mesmo cuidado de
    NUNCA sobrescrever o que o time escreveu (status, requisitos, observações,
    responsável). O robô só mexe na nota que ele mesmo deu, porque as
    palavras-chave podem ter mudado desde a última rodada.
    """
    nota, termos = pontuar(item['titulo'], item['descricao'], palavras)
    if nota < minimo:
        return 'ignorado', None

    chave = chave_do_link(item['link'])
    encontrados = ', '.join(termos)[:250]

    if simular:
        from .models import Edital
        existe = Edital.objects.filter(chave=chave).exists()
        return ('existente' if existe else 'novo'), None

    from .models import Edital
    edital, criado = Edital.objects.get_or_create(
        chave=chave,
        defaults={
            'titulo': item['titulo'],
            'descricao': item['descricao'],
            'link': item['link'],
            'fonte': fonte,
            'consulta': consulta,
            'origem': origem,
            'relevancia': nota,
            'termos_encontrados': encontrados,
        },
    )
    if criado:
        return 'novo', edital
    if (edital.relevancia, edital.termos_encontrados) != (nota, encontrados):
        edital.relevancia = nota
        edital.termos_encontrados = encontrados
        edital.save(update_fields=['relevancia', 'termos_encontrados'])
        return 'renotado', edital
    return 'existente', edital
