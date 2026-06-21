import random
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

from voluntario.models import Voluntario, LISTA_AREAS, TIPO_ALIMENTACAO
from sabado.models import Sabado, FaixaHorarioAjuda, DisponibilidadeVoluntario


FAIXAS = [
    ("ABA", "Abertura (08h–09h)"),
    ("MAT", "Manhã (09h–12h)"),
    ("ALM", "Almoço (12h–13h)"),
    ("TAR", "Tarde (13h–17h)"),
    ("ENC", "Encerramento (17h–18h)"),
]

NOMES = [
    ("Ana", "Lima"), ("Bruno", "Souza"), ("Carla", "Oliveira"), ("Diego", "Ferreira"),
    ("Elisa", "Santos"), ("Felipe", "Costa"), ("Gabriela", "Alves"), ("Henrique", "Pereira"),
    ("Isabela", "Rodrigues"), ("João", "Martins"), ("Karen", "Nascimento"), ("Lucas", "Barbosa"),
    ("Mariana", "Carvalho"), ("Nicolas", "Gomes"), ("Olivia", "Araújo"), ("Pedro", "Ribeiro"),
    ("Renata", "Mendes"), ("Samuel", "Freitas"), ("Tatiana", "Moreira"), ("Victor", "Correia"),
    ("Yasmin", "Dias"), ("Arthur", "Nunes"), ("Beatriz", "Ramos"), ("Carlos", "Teixeira"),
]


class Command(BaseCommand):
    help = "Cria sábados, faixas de horário e voluntários de exemplo para /sabado/resumo_sabado/"

    def handle(self, *args, **options):
        self._criar_faixas()
        self._criar_sabados()
        self._criar_voluntarios()
        self._criar_disponibilidades()
        self.stdout.write(self.style.SUCCESS("Seed concluído! Acesse /sabado/resumo_sabado/?sabado=6"))

    # ------------------------------------------------------------------

    def _criar_faixas(self):
        for codigo, descricao in FAIXAS:
            FaixaHorarioAjuda.objects.get_or_create(codigo=codigo, defaults={"descricao": descricao})
        self.stdout.write(f"  ✔ {len(FAIXAS)} faixas de horário garantidas")

    def _criar_sabados(self):
        base = datetime.date(2025, 1, 4)  # primeiro sábado de 2025
        criados = 0
        for i in range(10):
            data = base + datetime.timedelta(weeks=i)
            tema = f"Tema do Sábado {i + 1}"
            desc = f"Descrição do evento número {i + 1} do projeto."
            _, c = Sabado.objects.get_or_create(data=data, defaults={"tema": tema, "descricao": desc})
            if c:
                criados += 1
        self.stdout.write(f"  ✔ {criados} sábados criados (10 no total, id=6 = {base + datetime.timedelta(weeks=5)})")

    def _criar_voluntarios(self):
        areas = [a[0] for a in LISTA_AREAS]
        alimentacoes = [a[0] for a in TIPO_ALIMENTACAO]
        criados = 0
        for i, (primeiro, ultimo) in enumerate(NOMES):
            username = f"{primeiro.lower()}.{ultimo.lower()}"
            if Voluntario.objects.filter(username=username).exists():
                continue
            Voluntario.objects.create_user(
                username=username,
                password="senha123",
                first_name=primeiro,
                last_name=ultimo,
                email=f"{username}@pcf.local",
                area=areas[i % len(areas)],
                alimentacao=alimentacoes[i % len(alimentacoes)],
            )
            criados += 1
        self.stdout.write(f"  ✔ {criados} voluntários criados")

    def _criar_disponibilidades(self):
        faixas = list(FaixaHorarioAjuda.objects.all())
        voluntarios = list(Voluntario.objects.filter(is_superuser=False))

        try:
            sabado = Sabado.objects.order_by("data")[5]  # o 6º sábado (índice 5)
        except IndexError:
            self.stdout.write(self.style.ERROR("Sábado de índice 5 não encontrado."))
            return

        criados = 0
        for v in voluntarios:
            obj, created = DisponibilidadeVoluntario.objects.get_or_create(
                sabado=sabado,
                voluntario=v,
                defaults={
                    "vai_ao_projeto": random.random() > 0.2,
                    "saude": random.choice([True, True, True, False, None]),
                    "vai_de_carro": random.choice([True, False, None]),
                },
            )
            if created:
                if obj.vai_ao_projeto and faixas:
                    n = random.randint(0, len(faixas))
                    obj.pode_ajudar.set(random.sample(faixas, n))
                criados += 1

        self.stdout.write(f"  ✔ {criados} disponibilidades criadas para sábado id={sabado.pk} ({sabado.data})")
