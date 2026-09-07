"""Cobra, todo dia, quem ainda não respondeu a enquete do próximo sábado.

Feito para rodar em tarefa agendada no PythonAnywhere, UMA vez por dia — mesmo
padrão de `editais/management/commands/buscar_editais.py`.

Antes este comando disparava em um único dia por sábado (a condição era uma
igualdade exata: `hoje == data - 4 dias`) e o texto dizia "fecha amanhã" —
mentira em qualquer outro dia. Agora ele cobra todos os dias enquanto a enquete
estiver aberta, e o texto diz quantos dias faltam de verdade.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from notificacoes.services import enviar_push
from sabado.notificacoes import (TITULO_LEMBRETE, corpo_do_lembrete,
                                 quem_nao_respondeu, sabado_da_vez,
                                 tag_da_enquete, url_da_enquete)


class Command(BaseCommand):
    help = ('Cobra quem ainda não respondeu a enquete de disponibilidade do '
            'próximo sábado. Roda todo dia enquanto a enquete estiver aberta.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Mostra quem receberia e não envia nada. Use para conferir em '
                 'produção sem cobrar a equipe.',
        )

    def handle(self, *args, **options):
        seco = options['dry_run']

        sabado = sabado_da_vez()
        if sabado is None:
            self.stdout.write('Nenhum sábado com enquete aberta. Nada a fazer.')
            return

        pendentes = list(quem_nao_respondeu(sabado))
        data_fmt = sabado.data.strftime('%d/%m/%Y')
        self.stdout.write(
            f'Sábado {data_fmt} — fecha em {sabado.dias_para_fechar} dia(s). '
            f'{len(pendentes)} pendente(s).'
        )

        if not pendentes:
            return

        if seco:
            for voluntario in pendentes:
                nome = voluntario.get_full_name() or voluntario.username
                canais = []
                if voluntario.email:
                    canais.append('e-mail')
                if voluntario.inscricoes_push.exists():
                    canais.append('push')
                self.stdout.write(
                    f'  {nome} — {", ".join(canais) or "SEM CANAL NENHUM"}')
            self.stdout.write(self.style.WARNING('--dry-run: nada foi enviado.'))
            return

        corpo = corpo_do_lembrete(sabado)

        # O push vem ANTES do laço de e-mail, e não depois como era. O laço usava
        # fail_silently=False: um endereço inválido ou o SMTP fora do ar levantava
        # no meio dele, e ninguém dali para frente recebia e-mail E o push não
        # saía para NINGUÉM. Num comando diário isso vira falha recorrente,
        # visível só no log do servidor.
        #
        # Comando agendado usa enviar_push SÍNCRONO: a thread daemon do
        # enviar_push_async morreria junto com o processo e a notificação sumiria.
        enviados = enviar_push(
            pendentes,
            TITULO_LEMBRETE,
            corpo,
            url=url_da_enquete(sabado),
            tag=tag_da_enquete(sabado),
        )
        self.stdout.write(self.style.SUCCESS(f'{enviados} push enviado(s).'))

        sem_canal = 0
        falhas = 0
        for voluntario in pendentes:
            if not voluntario.email:
                sem_canal += 1
                continue
            nome = voluntario.get_full_name() or voluntario.username
            try:
                send_mail(
                    subject=f'Lembrete: responda sua disponibilidade para {data_fmt}',
                    message=(
                        f'Olá {nome},\n\n{corpo}\n\n'
                        f'Acesse o sistema para responder.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[voluntario.email],
                    fail_silently=True,
                )
            except Exception as erro:
                # fail_silently cobre queda de SMTP, mas não tudo: endereço
                # malformado estoura na montagem da mensagem, antes de o backend
                # ver a flag. Um voluntário com cadastro ruim não pode calar a
                # cobrança de todos os que vêm depois dele na lista — e num
                # comando diário essa lista é percorrida todo dia.
                falhas += 1
                self.stderr.write(f'E-mail falhou para {nome}: {erro}')

        if sem_canal:
            self.stdout.write(self.style.WARNING(
                f'{sem_canal} pendente(s) sem e-mail cadastrado.'))
        if falhas:
            self.stdout.write(self.style.WARNING(
                f'{falhas} e-mail(s) falharam — o push desses já tinha saído.'))
