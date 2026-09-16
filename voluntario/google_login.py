"""Entrar com a conta Google da organização.

Sem `django-allauth`: o `google-auth` já está no projeto por causa da
sincronização do Acervo, e verificar um token de identidade é o que ele faz.
Trazer o allauth só para isto significaria tabelas novas, templates próprios e
um fluxo de login diferente para todo mundo — muito preço por pouca coisa.

O login por usuário e senha continua existindo ao lado. É de propósito: se o
Google cair, se alguém perder acesso à conta, ou se a pessoa simplesmente não
tiver conta da organização, ninguém fica trancado para fora num sábado de
manhã.

A REGRA que este módulo existe para garantir: só entra quem tem conta do
Workspace da organização, e quem decide o acesso continua sendo o cadastro de
voluntário — não o Google.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from google.auth.transport import requests as transporte_google
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


class LoginGoogleInvalido(Exception):
    """A entrada foi recusada, e a mensagem explica por quê para a tela."""


def configurado() -> bool:
    """Dá para oferecer o botão do Google agora?

    Vazio na máquina de desenvolvimento é o normal: o botão simplesmente não
    aparece, e o formulário de usuário e senha continua lá. Mesmo padrão do
    VAPID e das credenciais do Drive — configuração faltando não pode derrubar
    o site.

    **Exige o domínio também**, e isso é a diferença entre uma porta e um
    buraco: sem `GOOGLE_LOGIN_DOMINIO`, a conferência do `hd` não tem com o que
    comparar e QUALQUER conta Google do planeta viraria voluntário ativo — com
    a linha em branco no `.env` parecendo inofensiva. A falha aqui é fechada:
    o botão não aparece, e `pcf.W002` diz por quê no meio do deploy.
    """
    return bool(getattr(settings, 'GOOGLE_LOGIN_CLIENT_ID', '')) and bool(dominio())


def dominio() -> str:
    return getattr(settings, 'GOOGLE_LOGIN_DOMINIO', '') or ''


def verificar_credencial(credencial):
    """Confere o token com o Google e devolve o que ele afirma.

    `verify_oauth2_token` checa assinatura, emissor, validade e se o token foi
    emitido para ESTE aplicativo (`aud`). Nada do que o navegador manda é
    aceito sem essa volta.
    """
    if not configurado():
        raise LoginGoogleInvalido(
            'A entrada pelo Google não está configurada neste servidor.')

    try:
        dados = id_token.verify_oauth2_token(
            credencial,
            transporte_google.Request(),
            settings.GOOGLE_LOGIN_CLIENT_ID,
        )
    except ValueError as erro:
        # Assinatura errada, token vencido, ou emitido para outro aplicativo.
        # O voluntário não pode ver um 500 por causa disso.
        logger.warning('Token do Google recusado: %s', erro)
        raise LoginGoogleInvalido(
            'Não consegui confirmar sua conta Google. Tente de novo.')

    if not dados.get('email_verified'):
        raise LoginGoogleInvalido(
            'Este e-mail ainda não foi verificado pelo Google.')

    esperado = dominio()
    if not esperado:
        # `configurado()` já barra isto antes de o botão aparecer. A repetição
        # é de propósito: esta é a última linha antes de alguém entrar, e ela
        # não pode depender de outra função ter sido chamada.
        raise LoginGoogleInvalido(
            'A entrada pelo Google não está configurada neste servidor.')

    # `hd` (hosted domain) só existe em conta do Google Workspace. Conferir o
    # FINAL DO E-MAIL em vez disto deixaria passar um Gmail comum com apelido
    # parecido com o domínio — que é exatamente o ataque que esta linha barra.
    if dados.get('hd') != esperado:
        raise LoginGoogleInvalido(
            f'A entrada pelo Google é só para contas @{esperado}. '
            'Use seu usuário e senha, ou fale com a Gestão de Talentos.')

    return dados


def _username_livre(base):
    """Um nome de usuário que ainda não existe, a partir do e-mail.

    Colisão acontece: "ana@" da organização e uma "ana" cadastrada à mão anos
    atrás são pessoas diferentes.
    """
    Voluntario = get_user_model()
    base = (base or 'voluntario')[:140]
    if not Voluntario.objects.filter(username=base).exists():
        return base
    numero = 2
    while Voluntario.objects.filter(username=f'{base}{numero}').exists():
        numero += 1
    return f'{base}{numero}'


def voluntario_para(dados):
    """Acha o voluntário daquele e-mail, ou cria um.

    Devolve (voluntario, criado). Quem nasce aqui entra ATIVO e SEM ÁREA, por
    decisão da coordenação: usa o sistema no mesmo dia, mas sem permissão de
    área nenhuma até a Gestão de Talentos completar o cadastro.
    """
    Voluntario = get_user_model()
    email = (dados.get('email') or '').strip()
    if not email:
        raise LoginGoogleInvalido('O Google não informou o e-mail da conta.')

    encontrados = list(Voluntario.objects.filter(email__iexact=email)[:2])

    if len(encontrados) > 1:
        # Login ambíguo é pior que login negado: entrar na conta errada dá
        # acesso ao que aquela pessoa podia ver.
        logger.error('Dois cadastros com o e-mail %s — login recusado.', email)
        raise LoginGoogleInvalido(
            'Há mais de um cadastro com este e-mail. Fale com a Gestão de '
            'Talentos para resolver antes de entrar.')

    if encontrados:
        voluntario = encontrados[0]
        if not voluntario.is_active:
            raise LoginGoogleInvalido(
                'Seu acesso está bloqueado. Fale com a Gestão de Talentos.')
        if voluntario.data_saida:
            # O Google continua autenticando a pessoa; quem decide o acesso é
            # o cadastro do projeto.
            raise LoginGoogleInvalido(
                'Seu cadastro consta como desligado do projeto. Se isso está '
                'errado, fale com a Gestão de Talentos.')
        return voluntario, False

    voluntario = Voluntario(
        username=_username_livre(email.split('@')[0].lower()),
        email=email,
        first_name=(dados.get('given_name') or '')[:150],
        last_name=(dados.get('family_name') or '')[:150],
        area='',            # a Gestão de Talentos preenche
        is_active=True,
    )
    # Sem senha utilizável: a conta não vira porta de força bruta enquanto a
    # GT não definir uma.
    voluntario.set_unusable_password()
    voluntario.save()

    logger.info('Voluntário criado pela entrada com Google: %s', email)
    return voluntario, True
