"""Envio de notificações push.

Interface única consumida pelos quatro gatilhos do sistema. O push SOMA ao
e-mail que já existe — nunca substitui.
"""
import json
import logging
import threading

from django.conf import settings
from django.utils import timezone

from .models import InscricaoPush

# Import protegido de proposito. Este modulo e alcancado pelo URLconf
# (TESTE/urls.py -> notificacoes.urls -> views -> services), entao um
# ImportError aqui derruba TODAS as rotas do site, nao so o push — foi o que
# aconteceu no primeiro deploy, com o pywebpush ainda nao instalado. Faltando a
# dependencia, o push desliga e grava no log; o resto do PCF continua de pe.
try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - so acontece em ambiente mal instalado
    webpush = None

    class WebPushException(Exception):
        """Substituto para quando o pywebpush nao esta instalado."""

logger = logging.getLogger("notificacoes")

# Status que significam "esta inscrição morreu": o aparelho desinstalou o app,
# trocou de dono ou limpou o navegador.
STATUS_INSCRICAO_MORTA = (404, 410)

# O servidor de push segura a mensagem por até 1 dia se o aparelho estiver offline.
TTL_SEGUNDOS = 86400

# Segundos de espera por aparelho. Sem isto, uma conexão pendurada com o servidor
# de push trava o laço inteiro e ninguém depois daquele aparelho recebe.
TIMEOUT_SEGUNDOS = 10


def push_configurado() -> bool:
    """Dá para ENVIAR push agora?

    Só o que o envio usa: a biblioteca, a chave privada que assina, e o e-mail
    de contato que vai no claim. A chave PÚBLICA não entra aqui — ela é usada
    pelo navegador para se inscrever, não pelo servidor para enviar; exigi-la no
    envio inventaria uma falha que não existe.

    VAPID_ADMIN_EMAIL entra porque antes o guard checava só a chave privada: com
    o e-mail vazio o claim vira "mailto:" puro, que o FCM tolera e o Firefox
    recusa com 401. Falha assimétrica — Android recebe, Firefox não — e o único
    sinal é uma linha de log que ninguém lê.
    """
    return bool(
        webpush is not None
        and settings.VAPID_PRIVATE_KEY
        and settings.VAPID_ADMIN_EMAIL
    )


def _motivo_de_estar_desligado() -> str:
    """Frase única dizendo o que falta configurar, para log e para tela."""
    if webpush is None:
        return ("pywebpush não instalado — rode "
                "pip install -r requirements.txt no virtualenv do site")
    faltando = [
        nome for nome in ("VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL")
        if not getattr(settings, nome, "")
    ]
    if faltando:
        return (f"faltando no .env: {', '.join(faltando)} — "
                "rode python manage.py gerar_chaves_vapid")
    return ""


def _entregar(inscricao, payload) -> bool:
    """Entrega um payload já serializado a UM aparelho.

    Devolve True se o servidor de push aceitou. Remove a inscrição se o aparelho
    morreu. Nunca levanta.
    """
    try:
        webpush(
            subscription_info={
                "endpoint": inscricao.endpoint,
                "keys": {"p256dh": inscricao.p256dh, "auth": inscricao.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # Dict NOVO a cada chamada: o pywebpush grava 'exp' dentro dele.
            # Reutilizar um dict de módulo faria o segundo envio falhar com
            # token expirado.
            vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            ttl=TTL_SEGUNDOS,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in STATUS_INSCRICAO_MORTA:
            logger.info("Inscrição morta (%s) removida: %s",
                        status, inscricao.endpoint[:60])
            inscricao.delete()
        else:
            logger.warning("Falha ao enviar push (%s): %s",
                           status, inscricao.endpoint[:60])
        return False
    except Exception:
        # Qualquer outro erro segue o mesmo princípio: registra e continua.
        logger.exception("Erro inesperado ao enviar push para %s",
                         inscricao.endpoint[:60])
        return False
    return True


def enviar_push_individual(mensagens, titulo, url="/inicio/", tag=None) -> int:
    """Envia um push com corpo DIFERENTE para cada pessoa.

    `mensagens` é uma sequência de pares (voluntario, corpo). Existe para a
    ronda, onde cada escalado tem local e horário próprios: chamar enviar_push
    por pessoa custaria uma thread e um SELECT por voluntário — numa ronda de 16
    escalas, 16 de cada. Aqui é um SELECT só, e o corpo é escolhido por
    voluntário na memória.

    Retorna quantos aparelhos receberam.
    """
    if not push_configurado():
        logger.error("Push desligado (%s).", _motivo_de_estar_desligado())
        return 0

    corpo_por_voluntario = {}
    for voluntario, corpo in mensagens:
        if voluntario is not None:
            corpo_por_voluntario[voluntario.pk] = corpo
    if not corpo_por_voluntario:
        return 0

    enviados = 0
    alcancados = []
    for inscricao in InscricaoPush.objects.filter(
            voluntario_id__in=list(corpo_por_voluntario)):
        corpo = corpo_por_voluntario[inscricao.voluntario_id]
        payload = json.dumps(
            {"titulo": titulo, "corpo": corpo, "url": url, "tag": tag})
        if _entregar(inscricao, payload):
            alcancados.append(inscricao.pk)
            enviados += 1

    _marcar_ultimo_ok(alcancados)
    return enviados


def enviar_push_individual_async(mensagens, titulo, url="/inicio/", tag=None) -> None:
    """Igual a enviar_push_individual, numa thread daemon só.

    UMA thread para a ronda inteira — não uma por escalado.
    NÃO usar em management command: a thread morre com o processo.
    """
    threading.Thread(
        target=enviar_push_individual,
        args=(list(mensagens), titulo, url, tag),
        daemon=True,
    ).start()


def _marcar_ultimo_ok(ids_de_inscricao) -> None:
    """Um UPDATE só para todos os aparelhos alcançados.

    Antes era um save() por aparelho dentro do laço, intercalado com as
    requisições HTTP: num aviso para 80 voluntários, ~120 UPDATEs individuais.
    """
    if ids_de_inscricao:
        InscricaoPush.objects.filter(pk__in=ids_de_inscricao).update(
            ultimo_ok=timezone.now())


def enviar_push(voluntarios, titulo, corpo, url="/inicio/", tag=None) -> int:
    """Envia um push para todas as inscrições dos voluntários dados.

    Retorna quantos aparelhos receberam. Nunca levanta exceção: falha de push
    não pode derrubar a request nem o comando que chamou.
    """
    if not push_configurado():
        logger.error("Push desligado (%s).", _motivo_de_estar_desligado())
        return 0

    inscricoes = InscricaoPush.objects.filter(voluntario__in=voluntarios)
    payload = json.dumps({"titulo": titulo, "corpo": corpo, "url": url, "tag": tag})

    enviados = 0
    alcancados = []
    for inscricao in inscricoes:
        if _entregar(inscricao, payload):
            alcancados.append(inscricao.pk)
            enviados += 1

    _marcar_ultimo_ok(alcancados)
    return enviados


def enviar_push_async(voluntarios, titulo, corpo, url="/inicio/", tag=None) -> None:
    """Igual a enviar_push, em thread daemon.

    Usar no caminho de request, para não segurar a resposta HTTP — mesmo padrão
    do envio de e-mail de ocorrências em voluntario/views.py.

    NÃO usar em management command: a thread daemon morre quando o processo
    encerra e a notificação some.
    """
    threading.Thread(
        target=enviar_push,
        args=(list(voluntarios), titulo, corpo, url, tag),
        daemon=True,
    ).start()
