from .models import Atendido

# Sala -> nome da variável no template. A contagem que aparece na navbar sai
# daqui, então uma criança desativada inflava o número de todas as telas.
SALAS = (
    ("VIOLETA", "atendidos_violeta"),
    ("ANIL", "atendidos_anil"),
    ("AZUL", "atendidos_azul"),
    ("VERDE", "atendidos_verde"),
    ("AMARELO", "atendidos_amarelo"),
    ("LARANJA", "atendidos_laranja"),
    ("VERMELHO", "atendidos_vermelho"),
    ("FAMILIA_FELIZ", "atendidos_ff"),
)


def atendidos_filtrados(request):
    ativos = Atendido.objects.ativos()
    return {chave: ativos.filter(sala=sala) for sala, chave in SALAS}
