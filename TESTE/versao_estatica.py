"""Carimbo de versão para as URLs de CSS e JS.

Por que existe: o CSS e o JS são pedidos por um endereço fixo
(`/static/css/pcf.css`), e o servidor os entrega sem `Cache-Control` nem
`ETag` — só com `Last-Modified`. Nessas condições o navegador guarda o arquivo
por conta própria, e uma correção publicada NÃO chega em quem já visitou o
site: a pessoa continua vendo a versão antiga, sem nenhum sinal de que está
desatualizada.

Isso não é hipótese. Uma correção de JavaScript ficou três rodadas parecendo
que não tinha funcionado — o arquivo certo estava no servidor o tempo todo, e
o navegador servindo o velho.

A solução é acrescentar `?v=<carimbo>` ao endereço. Quando o arquivo muda, o
endereço muda junto, e o navegador é obrigado a buscar de novo. Escolhemos o
maior `mtime` entre os arquivos que importam: muda sozinho a cada deploy, sem
ninguém precisar lembrar de girar um número à mão — e lembrar é justamente o
que falha.
"""
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

# Só o que é compartilhado por todas as telas. Não vale varrer a pasta inteira:
# seria I/O à toa e mudaria o carimbo por causa de uma imagem qualquer,
# derrubando o cache de tudo sem motivo.
ARQUIVOS_OBSERVADOS = ('css/pcf.css', 'js/pcf-fx.js')

_carimbo = None


def _calcular():
    """Maior data de modificação entre os arquivos observados, como inteiro."""
    marcas = []
    raizes = [str(caminho) for caminho in getattr(settings, 'STATICFILES_DIRS', [])]
    if getattr(settings, 'STATIC_ROOT', None):
        raizes.append(str(settings.STATIC_ROOT))

    for relativo in ARQUIVOS_OBSERVADOS:
        for raiz in raizes:
            caminho = os.path.join(raiz, *relativo.split('/'))
            try:
                marcas.append(int(os.path.getmtime(caminho)))
            except OSError:
                continue

    if marcas:
        return str(max(marcas))
    # Sem os arquivos (coleta ainda não rodou, caminho diferente), um valor fixo
    # é melhor do que estourar: pior caso, voltamos ao comportamento de antes.
    logger.warning('Não achei os arquivos estáticos para carimbar a versão: %s',
                   ARQUIVOS_OBSERVADOS)
    return '0'


def versao_estatica(request=None):
    """Context processor: expõe `ESTATICO_V` para o `base.html`.

    Calculado uma vez por processo. O processo reinicia no Reload, que é
    exatamente quando o arquivo pode ter mudado.
    """
    global _carimbo
    if _carimbo is None:
        _carimbo = _calcular()
    return {'ESTATICO_V': _carimbo}
