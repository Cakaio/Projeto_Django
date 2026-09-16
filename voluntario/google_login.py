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

## Por que REDIRECIONAMENTO e não o botão do Google

A primeira versão usava o widget do Google (`accounts.google.com/gsi/client`).
Em produção ele travava: o clique abria `/gsi/transform` e parava ali, sem erro
e sem prosseguir, e o botão saía escrito em inglês apesar de `data-locale`.

O widget depende de iframe, cookie de terceiro e FedCM — três coisas que o
navegador do voluntário controla e nós não, e que falham CALADAS. No navegador
de dentro do WhatsApp, por onde boa parte da equipe abre link, isso é comum.

O redirecionamento não tem nada disso: é uma navegação de página inteira para o
Google e outra de volta. Some a classe inteira de falha. De quebra, o texto do
botão passa a ser nosso — o widget só aceitava quatro frases fixas, e nenhuma
era a que a coordenação pediu.

## Por que CÓDIGO e não `id_token` direto

`SESSION_COOKIE_SAMESITE = 'Lax'`. Com Lax o cookie de sessão NÃO acompanha um
POST vindo de outro site — só navegação de topo por GET. O modo `form_post` do
Google, que devolveria o token direto, chegaria aqui SEM SESSÃO: sem `state` e
sem `nonce` para conferir, ou seja, sem como saber se aquela volta é da pessoa
que começou o fluxo.

O fluxo de código volta por GET (a sessão vem junto) e o token é buscado pelo
SERVIDOR, direto do Google. O token de identidade nunca passa pelo navegador.
"""
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

URL_DE_AUTORIZACAO = 'https://accounts.google.com/o/oauth2/v2/auth'
URL_DO_TOKEN = 'https://oauth2.googleapis.com/token'

# Onde `state` e `nonce` ficam guardados entre a ida e a volta.
CHAVE_STATE = 'google_login_state'
CHAVE_NONCE = 'google_login_nonce'

# ESTE MODULO E IMPORTADO PELA TELA DE LOGIN, e a tela de login e a unica que
# precisa abrir mesmo quando todo o resto esta quebrado — sem ela ninguem entra
# para consertar nada. Um `from google... import` solto aqui em cima ja derrubou
# `/login/` com 500 em producao, porque o venv do servidor nao tinha a
# biblioteca. `acervo/drive.py` importa dentro da funcao pelo mesmo motivo, e o
# CLAUDE.md ja registrava a regra para `notificacoes.services`.
#
# `except ImportError` e o ponto todo: falta de dependencia vira recurso
# desligado, nunca tela fora do ar. Quem avisa que falta instalar e `pcf.W003`,
# no meio do deploy.
try:
    import requests as http
    from google.auth.transport import requests as transporte_google
    from google.oauth2 import id_token
except ImportError:                                  # pragma: no cover
    http = transporte_google = id_token = None


class LoginGoogleInvalido(Exception):
    """A entrada foi recusada, e a mensagem explica por quê para a tela."""


def biblioteca_instalada() -> bool:
    """A biblioteca do Google está disponível neste servidor?"""
    return id_token is not None and http is not None


def dominio() -> str:
    return getattr(settings, 'GOOGLE_LOGIN_DOMINIO', '') or ''


def configurado() -> bool:
    """Dá para oferecer o botão do Google agora?

    Vazio na máquina de desenvolvimento é o normal: o botão simplesmente não
    aparece, e o formulário de usuário e senha continua lá. Mesmo padrão do
    VAPID e das credenciais do Drive — configuração faltando não pode derrubar
    o site.

    **Exige o domínio também**, e isso é a diferença entre uma porta e um
    buraco: sem `GOOGLE_LOGIN_DOMINIO`, a conferência do `hd` não tem com o que
    comparar e QUALQUER conta Google do planeta viraria voluntário ativo — com
    a linha em branco no `.env` parecendo inofensiva.

    **Exige o segredo também**: sem ele a troca do código pelo token falha, e o
    voluntário só descobriria isso depois de ir ao Google e voltar.

    **E exige a biblioteca**: pior que não ter o botão é ter um botão que
    estoura quando alguém toca nele.

    A falha aqui é sempre FECHADA — o botão não aparece — e `pcf.W002` e
    `pcf.W003` dizem no meio do deploy qual das peças está faltando.
    """
    return (bool(getattr(settings, 'GOOGLE_LOGIN_CLIENT_ID', ''))
            and bool(getattr(settings, 'GOOGLE_LOGIN_CLIENT_SECRET', ''))
            and bool(dominio())
            and biblioteca_instalada())


def endereco_de_ida(request, redirect_uri):
    """Monta o endereço do Google e guarda o que vai ser conferido na volta.

    `state` e `nonce` são sorteados agora e ficam na SESSÃO. Na volta, os dois
    precisam bater:

    - **`state`** prova que esta volta pertence a quem começou a ida. Sem ele,
      alguém poderia mandar para o voluntário um link de volta já pronto e
      fazê-lo entrar na conta Google do atacante sem perceber — o cadastro do
      PCF que ele usaria a partir dali seria de outra pessoa. É o que substitui
      o CSRF do Django, que não vale numa volta vinda de outro site.
    - **`nonce`** amarra o token a ESTE pedido. Um token de identidade válido,
      capturado de outro lugar, não serve para entrar aqui.
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    request.session[CHAVE_STATE] = state
    request.session[CHAVE_NONCE] = nonce

    parametros = {
        'client_id': settings.GOOGLE_LOGIN_CLIENT_ID,
        'response_type': 'code',
        'scope': 'openid email profile',
        'redirect_uri': redirect_uri,
        'state': state,
        'nonce': nonce,
        # Dica para o Google já filtrar a lista de contas. É conforto, não
        # segurança: quem barra de verdade é a conferência do `hd` no servidor.
        'hd': dominio(),
        # Sem isto, quem já tem uma sessão Google entra direto com ela e não
        # tem como trocar de conta — problema real em computador compartilhado,
        # que é o caso do computador do projeto.
        'prompt': 'select_account',
    }
    return f'{URL_DE_AUTORIZACAO}?{urlencode(parametros)}'


def conferir_state(request, state_recebido):
    """A volta pertence a quem começou a ida?

    O valor é CONSUMIDO: uma volta só vale uma vez. Reenviar o mesmo endereço
    depois não entra de novo.
    """
    esperado = request.session.pop(CHAVE_STATE, None)
    if not esperado or not state_recebido:
        raise LoginGoogleInvalido(
            'A entrada pelo Google expirou. Tente de novo.')
    if not secrets.compare_digest(str(esperado), str(state_recebido)):
        logger.warning('State do Google não confere — entrada recusada.')
        raise LoginGoogleInvalido(
            'Não consegui confirmar que esta entrada começou aqui. '
            'Tente de novo.')


def trocar_codigo_por_token(codigo, redirect_uri):
    """Busca o token de identidade no Google, SERVIDOR A SERVIDOR.

    É aqui que o segredo do cliente é usado, e é por isso que ele nunca chega
    ao navegador: quem conversa com o Google é o Django.
    """
    if not biblioteca_instalada():
        raise LoginGoogleInvalido(
            'A entrada pelo Google não está disponível neste servidor. '
            'Use seu usuário e senha.')

    try:
        resposta = http.post(URL_DO_TOKEN, timeout=10, data={
            'code': codigo,
            'client_id': settings.GOOGLE_LOGIN_CLIENT_ID,
            'client_secret': settings.GOOGLE_LOGIN_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        })
    except Exception as erro:                        # pragma: no cover
        # Rede caindo no meio do login não pode virar 500 na cara de quem
        # está tentando entrar.
        logger.error('Falha de rede ao falar com o Google: %s', erro)
        raise LoginGoogleInvalido(
            'Não consegui falar com o Google agora. '
            'Tente de novo ou use seu usuário e senha.')

    if resposta.status_code != 200:
        # O corpo traz `error` e `error_description` e é o que diz, por
        # exemplo, que o `redirect_uri` não bate com o cadastrado no Console.
        logger.error('Google recusou a troca do código (%s): %s',
                     resposta.status_code, resposta.text[:500])
        raise LoginGoogleInvalido(
            'O Google recusou esta entrada. Tente de novo ou fale com a '
            'Gestão de Talentos.')

    token = (resposta.json() or {}).get('id_token')
    if not token:
        logger.error('Resposta do Google veio sem id_token.')
        raise LoginGoogleInvalido(
            'A resposta do Google veio incompleta. Tente de novo.')
    return token


def verificar_credencial(credencial, nonce_esperado=None):
    """Confere o token com o Google e devolve o que ele afirma.

    `verify_oauth2_token` checa assinatura, emissor, validade e se o token foi
    emitido para ESTE aplicativo (`aud`). Nada do que chega de fora é aceito
    sem essa volta.
    """
    if not biblioteca_instalada():
        logger.error('google-auth ausente no venv — entrada pelo Google desligada.')
        raise LoginGoogleInvalido(
            'A entrada pelo Google não está disponível neste servidor. '
            'Use seu usuário e senha.')

    if not getattr(settings, 'GOOGLE_LOGIN_CLIENT_ID', ''):
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

    # `verify_oauth2_token` NÃO confere o nonce — isso é por nossa conta. Sem
    # esta linha, um token de identidade válido obtido em outro lugar entraria.
    if nonce_esperado is not None:
        if not secrets.compare_digest(str(dados.get('nonce') or ''),
                                      str(nonce_esperado)):
            logger.warning('Nonce do Google não confere — entrada recusada.')
            raise LoginGoogleInvalido(
                'Esta entrada não corresponde ao pedido feito aqui. '
                'Tente de novo.')

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
