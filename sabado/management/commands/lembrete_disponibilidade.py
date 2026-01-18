from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from sabado.models import Sabado, DisponibilidadeVoluntario
from voluntario.models import Voluntario
from django.conf import settings
from datetime import timedelta

class Command(BaseCommand):
    help = 'Envia email para voluntários que não responderam o formulário de disponibilidade, 1 dia antes de fechar a enquete.'

    def handle(self, *args, **options):
        hoje = timezone.now().date()
        sabados = Sabado.objects.all()
        for sabado in sabados:
            data_fechamento = sabado.data - timedelta(days=3)
            if data_fechamento - hoje == timedelta(days=1) and sabado.enquete_aberta:
                voluntarios_que_responderam = DisponibilidadeVoluntario.objects.filter(sabado=sabado).values_list('voluntario_id', flat=True)
                voluntarios = Voluntario.objects.exclude(id__in=voluntarios_que_responderam)
                for voluntario in voluntarios:
                    if voluntario.email:
                        send_mail(
                            subject=f"Lembrete: Responda sua disponibilidade para o sábado {sabado.data.strftime('%d/%m/%Y')}",
                            message=f"Olá {voluntario.get_full_name() or voluntario.username},\n\nPor favor, responda o formulário de disponibilidade para o sábado {sabado.data.strftime('%d/%m/%Y')} antes do fechamento da enquete.\nAcesse o sistema para responder!",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[voluntario.email],
                            fail_silently=False,
                        )
                        self.stdout.write(self.style.SUCCESS(f"Email enviado para {voluntario.email}"))
