import random
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

from atendido.models import Atendido, Familia, PresencaAtendido
from sabado.models import Sabado

LISTA_SALAS = [
    "VIOLETA", "ANIL", "AZUL", "VERDE",
    "AMARELO", "LARANJA", "VERMELHO", "FAMILIA_FELIZ",
]

NOMES_ATENDIDOS = [
    "Ana Clara Silva", "Bruno Henrique Santos", "Carla Oliveira Lima",
    "Diego Ferreira Costa", "Elisa Ramos Souza", "Felipe Alves Pereira",
    "Gabriela Nunes Martins", "Henrique Barbosa Gomes", "Isabela Rocha Almeida",
    "João Pedro Nascimento", "Karen Freitas Correia", "Lucas Teixeira Ribeiro",
    "Mariana Cardoso Araújo", "Nicolas Lima Dias", "Olivia Mendes Carvalho",
    "Pedro Moreira Rodrigues", "Renata Vieira Bastos", "Samuel Castro Pinto",
    "Tatiana Figueiredo Lopes", "Victor Andrade Cunha", "Yasmin Borges Macedo",
    "Arthur Cavalcante Pires", "Beatriz Monteiro Leite", "Carlos Eduardo Azevedo",
    "Daniela Melo Guimarães", "Eduardo Fonseca Tavares", "Fernanda Queiroz Amorim",
    "Guilherme Rezende Campos", "Helena Cardoso Braga", "Igor Santana Rocha",
    "Juliana Paiva Vasconcelos", "Kevin Ribeiro Moraes", "Larissa Correia Sousa",
    "Matheus Nogueira Brito", "Natalia Soares Faria", "Otto Fernandes Queirós",
]


class Command(BaseCommand):
    help = "Cria atendidos, famílias e presenças de exemplo para testar a chamada"

    def handle(self, *args, **options):
        familias = self._criar_familias()
        atendidos = self._criar_atendidos(familias)
        self._criar_presencas(atendidos)
        self.stdout.write(self.style.SUCCESS(
            "Seed concluído! Acesse /atendido/visualizar-presencas/ ou /atendido/presencas/"
        ))

    def _criar_familias(self):
        familias = []
        sobrenomes = ["Silva", "Santos", "Oliveira", "Ferreira", "Costa", "Souza", "Alves", "Pereira"]
        for sobrenome in sobrenomes:
            f, _ = Familia.objects.get_or_create(nome=f"Família {sobrenome}")
            familias.append(f)
        self.stdout.write(f"  OK {len(familias)} familias garantidas")
        return familias

    def _criar_atendidos(self, familias):
        salas_cycle = LISTA_SALAS * 5  # garante distribuição
        criados = 0
        atendidos = []

        for i, nome in enumerate(NOMES_ATENDIDOS):
            sala = salas_cycle[i % len(LISTA_SALAS)]
            anos = random.randint(6, 16)
            nascimento = datetime.date.today().replace(year=datetime.date.today().year - anos)

            a, created = Atendido.objects.get_or_create(
                nome=nome,
                defaults={
                    "familia": random.choice(familias),
                    "data_nascimento": nascimento,
                    "sala": sala,
                }
            )
            if created:
                criados += 1
            atendidos.append(a)

        self.stdout.write(f"  OK {criados} atendidos criados ({len(atendidos)} no total)")
        return atendidos

    def _criar_presencas(self, atendidos):
        sabados = list(Sabado.objects.order_by("data"))
        if not sabados:
            self.stdout.write(self.style.WARNING("  AVISO Nenhum sabado encontrado. Rode seed_sabado primeiro."))
            return

        opcoes = ["PRESENTE", "PRESENTE", "PRESENTE", "AUSENTE", "JUSTIFICADA"]
        criadas = 0

        for sabado in sabados:
            for atendido in atendidos:
                exists = PresencaAtendido.objects.filter(atendido=atendido, data=sabado).exists()
                if not exists:
                    PresencaAtendido.objects.create(
                        atendido=atendido,
                        data=sabado,
                        presenca=random.choice(opcoes),
                    )
                    criadas += 1

        self.stdout.write(f"  OK {criadas} presencas criadas em {len(sabados)} sabados")
        self.stdout.write(f"  INFO Para testar chamada ao vivo crie um Sabado com data de HOJE no admin ou shell.")
