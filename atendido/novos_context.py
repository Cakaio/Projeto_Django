from .models import Atendido

def atendidos_filtrados(request):
    try:
        violeta = list(Atendido.objects.filter(sala="VIOLETA"))
        anil = list(Atendido.objects.filter(sala="ANIL"))
        azul = list(Atendido.objects.filter(sala="AZUL"))
        verde = list(Atendido.objects.filter(sala="VERDE"))
        amarelo = list(Atendido.objects.filter(sala="AMARELO"))
        laranja = list(Atendido.objects.filter(sala="LARANJA"))
        vermelho = list(Atendido.objects.filter(sala="VERMELHO"))
        ff = list(Atendido.objects.filter(sala="FAMILIA_FELIZ"))

        context = {
            "atendidos_violeta": violeta,
            "atendidos_anil": anil,
            "atendidos_azul": azul,
            "atendidos_verde": verde,
            "atendidos_amarelo": amarelo,
            "atendidos_laranja": laranja,
            "atendidos_vermelho": vermelho,
            "atendidos_ff": ff,
        }
    except Exception:
        context = {}

    return context