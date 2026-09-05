"""Gera o par de chaves VAPID usado para assinar as notificações push.

RODAR UMA VEZ SÓ. Trocar a chave pública invalida todas as inscrições já feitas
e obriga cada voluntário a reativar as notificações no aparelho dele.
"""
import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid02


def _b64(dados: bytes) -> str:
    """base64url sem padding — o formato que o navegador e o pywebpush esperam."""
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


class Command(BaseCommand):
    help = "Gera o par de chaves VAPID para colar no .env"

    def handle(self, *args, **options):
        vapid = Vapid02()
        vapid.generate_keys()

        privada = _b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
        publica = _b64(vapid.public_key.public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        ))

        self.stdout.write(self.style.SUCCESS("Chaves geradas. Cole no .env:\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={publica}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={privada}")
        self.stdout.write("VAPID_ADMIN_EMAIL=<e-mail de contato do projeto>\n")
        self.stdout.write(self.style.WARNING(
            "ATENÇÃO: guarde estas chaves. Gerar de novo invalida todas as "
            "inscrições e todo mundo precisa reativar as notificações."
        ))
