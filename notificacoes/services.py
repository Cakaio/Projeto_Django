"""Envio de notificações push.

Interface única consumida pelos quatro gatilhos do sistema. O push SOMA ao
e-mail que já existe — nunca substitui.
"""
import json
import logging
import threading

from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import InscricaoPush

logger = logging.getLogger("notificacoes")

# Status que significam "esta inscrição morreu": o aparelho desinstalou o app,
# trocou de dono ou limpou o navegador.
STATUS_INSCRICAO_MORTA = (404, 410)

# O servidor de push segura a mensagem por até 1 dia se o aparelho estiver offline.
TTL_SEGUNDOS = 86400


def enviar_push(voluntarios, titulo, corpo, url="/inicio/", tag=None) -> int:
    """Envia um push para todas as inscrições dos voluntários dados.

    Retorna quantos aparelhos receberam. Nunca levanta exceção: falha de push
    não pode derrubar a request nem o comando que chamou.
    """
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY não configurada — push não enviado.")
        return 0

    inscricoes = InscricaoPush.objects.filter(voluntario__in=voluntarios)
    payload = json.dumps({"titulo": titulo, "corpo": corpo, "url": url, "tag": tag})

    enviados = 0
    for inscricao in inscricoes:
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
        except Exception:
            # Qualquer outro erro segue o mesmo princípio: registra e continua.
            logger.exception("Erro inesperado ao enviar push para %s",
                             inscricao.endpoint[:60])
        else:
            inscricao.ultimo_ok = timezone.now()
            inscricao.save(update_fields=["ultimo_ok"])
            enviados += 1

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
