"""Gera os ícones da PWA a partir do logo do projeto.

Roda uma vez (e de novo se o logo mudar). Os arquivos gerados entram no git:
são estáticos servidos pelo WhiteNoise, não artefato de build.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

# Laranja da marca, o mesmo do theme-color do base.html.
COR_FUNDO = (232, 86, 15, 255)


class Command(BaseCommand):
    help = "Gera os ícones da PWA em static/images/icons/ a partir do Logo_PCF.png"

    def handle(self, *args, **options):
        origem = Path(settings.BASE_DIR) / "static" / "images" / "Logo_PCF.png"
        if not origem.exists():
            raise CommandError(f"Logo não encontrado em {origem}")

        destino = Path(settings.BASE_DIR) / "static" / "images" / "icons"
        destino.mkdir(parents=True, exist_ok=True)

        logo = Image.open(origem).convert("RGBA")
        if max(logo.size) < 512:
            self.stdout.write(self.style.WARNING(
                f"Logo tem {logo.size[0]}x{logo.size[1]}px — os ícones de 512 são "
                f"ampliados e podem sair levemente borrados. Se houver um logo "
                f"maior, substitua {origem.name} e rode este comando de novo."
            ))

        self._quadrado_transparente(logo, 192, destino / "icon-192.png")
        self._quadrado_transparente(logo, 512, destino / "icon-512.png")
        self._maskable(logo, 512, destino / "icon-512-maskable.png")
        self._fundo_opaco(logo, 180, destino / "apple-touch-icon-180.png")
        self._badge(logo, 72, destino / "badge-72.png")

        self.stdout.write(self.style.SUCCESS(f"5 ícones gerados em {destino}"))

    # ── helpers ──

    def _ajustar(self, logo, lado):
        """Redimensiona o logo cabendo num quadrado de `lado`, preservando proporção."""
        copia = logo.copy()
        copia.thumbnail((lado, lado), Image.LANCZOS)
        return copia

    def _colar_centralizado(self, base, arte):
        x = (base.width - arte.width) // 2
        y = (base.height - arte.height) // 2
        base.paste(arte, (x, y), arte)
        return base

    def _quadrado_transparente(self, logo, lado, caminho):
        base = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        self._colar_centralizado(base, self._ajustar(logo, lado)).save(caminho, "PNG")

    def _maskable(self, logo, lado, caminho):
        """Android recorta em círculo/squircle conforme o fabricante.

        A arte fica em 80% do canvas para o recorte não decapitar o logo.
        """
        base = Image.new("RGBA", (lado, lado), COR_FUNDO)
        self._colar_centralizado(base, self._ajustar(logo, int(lado * 0.8))).save(caminho, "PNG")

    def _fundo_opaco(self, logo, lado, caminho):
        """iOS ignora transparência e renderiza o vazio como preto."""
        base = Image.new("RGBA", (lado, lado), (255, 255, 255, 255))
        self._colar_centralizado(base, self._ajustar(logo, int(lado * 0.85)))
        base.convert("RGB").save(caminho, "PNG")

    def _badge(self, logo, lado, caminho):
        """Ícone monocromático da status bar do Android: silhueta branca."""
        arte = self._ajustar(logo, lado)
        branco = Image.new("RGBA", arte.size, (255, 255, 255, 255))
        branco.putalpha(arte.getchannel("A"))
        base = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        self._colar_centralizado(base, branco).save(caminho, "PNG")
