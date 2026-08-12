"""A varredura: o robô pergunta à web em vez de esperar por fontes conhecidas.

Por que existe: ler `FonteEdital` só encontra edital em site que alguém já
mapeou. O projeto não tinha nenhum mapeado — e é justamente descobrir os
desconhecidos que interessa. Aqui o robô faz perguntas a um buscador e colhe o
que voltar de qualquer domínio.

Por que DuckDuckGo: não pede chave nem cartão. Google e Bing cobram ou exigem
cadastro com cota, e o projeto não tem orçamento para isso. Em troca, o
DuckDuckGo limita o ritmo de quem consulta demais — daí a pausa entre as
perguntas e o cuidado de nunca deixar uma falha derrubar a varredura inteira.
"""
import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Resultado de busca cai muito em rede social: é gente comentando o edital, não
# o edital. Some o domínio uma vez aqui em vez de sujar a lista do CR.
DOMINIOS_IGNORADOS = {
    'facebook.com', 'instagram.com', 'youtube.com', 'youtu.be', 'linkedin.com',
    'twitter.com', 'x.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'reddit.com', 'whatsapp.com', 'telegram.org', 'issuu.com', 'scribd.com',
}

# Pausa entre perguntas. O buscador é gratuito e responde a quem se comporta;
# disparar tudo de uma vez é o caminho mais curto para levar bloqueio.
PAUSA_ENTRE_CONSULTAS = 2.5

REGIAO = 'br-pt'


def dominio_de(link):
    """'https://www.abc.org.br/edital/1' -> 'abc.org.br' (sem o www)."""
    try:
        host = (urlparse(link).hostname or '').lower()
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def _ignorado(link):
    dominio = dominio_de(link)
    if not dominio:
        return True
    # Cobre subdomínio também: 'br.pinterest.com' cai em 'pinterest.com'.
    return any(dominio == ruim or dominio.endswith('.' + ruim)
               for ruim in DOMINIOS_IGNORADOS)


def buscar_na_web(termo, limite=20):
    """Faz UMA pergunta ao buscador e devolve [{titulo, descricao, link}].

    Levanta exceção se a busca falhar — quem chama decide o que fazer (o
    comando grava o erro na consulta e segue para a próxima pergunta).
    """
    # Import adiado: assim o app carrega (e os testes rodam) mesmo numa máquina
    # sem a biblioteca, que só é obrigatória na hora de varrer de verdade.
    try:
        from ddgs import DDGS
    except ImportError:
        # Quem lê isto é um voluntário na tela de consultas, não um programador:
        # "No module named 'ddgs'" não diz o que fazer.
        raise RuntimeError(
            'A biblioteca de busca não está instalada no servidor. '
            'Rode "pip install -r requirements.txt" e varra de novo. '
            'As fontes fixas continuam funcionando sem ela.'
        ) from None

    achados = []
    with DDGS() as buscador:
        for bruto in buscador.text(termo, region=REGIAO, max_results=limite):
            link = (bruto.get('href') or '').strip()
            titulo = (bruto.get('title') or '').strip()
            if not link or not titulo or _ignorado(link):
                continue
            achados.append({
                'titulo': titulo[:250],
                'descricao': (bruto.get('body') or '').strip()[:2000],
                'link': link[:500],
            })
    return achados


def varrer(consultas, limite_por_consulta=20, pausar=True):
    """Roda várias perguntas e devolve (itens, erros).

    `itens` já vem com a consulta que o trouxe, para a tela mostrar de onde
    veio. `erros` é {consulta: mensagem} — uma pergunta que falha não pode
    impedir as outras de rodar.
    """
    itens, erros = [], {}
    consultas = list(consultas)
    for indice, consulta in enumerate(consultas):
        try:
            achados = buscar_na_web(consulta.termo, limite=limite_por_consulta)
        except Exception as falha:
            # `except Exception` é proposital: rede, bloqueio do buscador,
            # biblioteca ausente, resposta em formato inesperado — tudo vira o
            # mesmo recado na tela de consultas, e a varredura continua.
            erros[consulta] = f'{type(falha).__name__}: {falha}'.strip()[:1000]
            logger.warning('Consulta "%s" falhou: %s', consulta.termo, falha)
            continue
        for achado in achados:
            achado['consulta'] = consulta
        itens.extend(achados)
        # Não dorme depois da última: seria só atraso sem ninguém para proteger.
        if pausar and indice < len(consultas) - 1:
            time.sleep(PAUSA_ENTRE_CONSULTAS)
    return itens, erros
