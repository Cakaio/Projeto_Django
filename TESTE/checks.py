"""Checagens de sistema do projeto.

Rodam junto de `manage.py migrate`, `runserver` e `check` — ou seja, no meio do
deploy, que é exatamente quando o erro que elas pegam é cometido.
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning, register

from TESTE.versao_estatica import ARQUIVOS_OBSERVADOS


def _fonte_de(relativo):
    """Onde o arquivo mora no repositório, ou None se não existir."""
    for raiz in getattr(settings, 'STATICFILES_DIRS', []):
        caminho = Path(raiz) / relativo
        if caminho.exists():
            return caminho
    return None


@register()
def coleta_de_estaticos_esta_atualizada(app_configs, static_root=None, **kwargs):
    """Avisa quando o `collectstatic` ficou para trás do código.

    Em produção quem serve `/static/` é o WhiteNoise, a partir de STATIC_ROOT —
    não do código-fonte. E ele casa pelo CAMINHO do arquivo, ignorando o `?v=`
    que o projeto acrescenta. Um deploy que faz `git pull` e `migrate` mas
    esquece o `collectstatic` entrega, portanto, **template novo com JavaScript
    velho**, sem erro nenhum em lugar nenhum.

    Isso não é hipótese: foi o que aconteceu com a tela do Bazar em 09/2026. O
    HTML já era o novo e o JS era o antigo, que procurava um elemento que tinha
    deixado de existir — clicar num nome não fazia absolutamente nada, e o
    console não dizia por quê.

    A checagem só reclama quando STATIC_ROOT **existe**: pasta ausente é
    máquina de desenvolvimento que nunca coletou, e avisar ali seria barulho em
    todo comando do dia.
    """
    raiz = Path(static_root or getattr(settings, 'STATIC_ROOT', '') or '')
    if not raiz or not raiz.is_dir():
        return []

    desatualizados = []
    for relativo in ARQUIVOS_OBSERVADOS:
        fonte = _fonte_de(relativo)
        if fonte is None:
            continue
        copia = raiz / relativo
        if not copia.exists():
            desatualizados.append(f'{relativo} (nunca coletado)')
        elif os.path.getmtime(copia) < os.path.getmtime(fonte):
            desatualizados.append(relativo)

    if not desatualizados:
        return []

    return [Warning(
        'A pasta de estáticos coletados está atrás do código: '
        + ', '.join(desatualizados),
        hint=('Rode `python manage.py collectstatic --noinput` e faça o Reload. '
              'Em produção o WhiteNoise serve o que está em STATIC_ROOT e '
              'ignora o `?v=` do endereço, então sem isso o navegador recebe o '
              'arquivo velho — sem erro e sem aviso.'),
        id='pcf.W001',
    )]


@register()
def entrada_pelo_google_tem_dominio(app_configs, **kwargs):
    """Avisa quando o Client ID do Google está posto e o domínio não.

    Essa combinação é a única forma de a entrada pelo Google virar um buraco: a
    conferência do claim `hd` fica sem com o que comparar, e qualquer conta
    Google do planeta passaria. O código FALHA FECHADO — `configurado()` devolve
    False e o botão nem aparece — mas aí a tela de login some um botão sem dizer
    nada, e quem configurou vai procurar erro no Google Cloud Console.

    Este aviso existe para o deploy dizer a verdade: não é o Google, é a linha
    em branco no `.env`.
    """
    from django.conf import settings as cfg

    if not getattr(cfg, 'GOOGLE_LOGIN_CLIENT_ID', ''):
        return []
    if getattr(cfg, 'GOOGLE_LOGIN_DOMINIO', ''):
        return []

    return [Warning(
        'GOOGLE_LOGIN_CLIENT_ID está configurado, mas GOOGLE_LOGIN_DOMINIO '
        'está vazio — o botão "Entrar com o Google" NÃO vai aparecer.',
        hint=('Ponha `GOOGLE_LOGIN_DOMINIO=projetocriancafeliz.org` no `.env` '
              'e recarregue o site. Sem o domínio não há como conferir se a '
              'conta é da organização, e deixar entrar qualquer conta Google '
              'seria pior do que não ter o botão.'),
        id='pcf.W002',
    )]
