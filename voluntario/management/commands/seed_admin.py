from django.core.management.base import BaseCommand
from voluntario.models import Voluntario


class Command(BaseCommand):
    help = "Cria o superusuário admin padrão para desenvolvimento"

    def handle(self, *args, **options):
        username = "admin"
        password = "admin123"

        if Voluntario.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'Usuário "{username}" já existe, pulando.'))
            return

        Voluntario.objects.create_superuser(
            username=username,
            password=password,
            email="admin@pcf.local",
            first_name="Admin",
            last_name="PCF",
            area="ADM/FIN",
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superusuário criado — login: {username} / senha: {password}'
        ))
