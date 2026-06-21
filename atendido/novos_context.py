from .models import Atendido

def atendidos_filtrados(request):
    violeta = Atendido.objects.filter(sala="VIOLETA")
    anil = Atendido.objects.filter(sala="ANIL")
    azul = Atendido.objects.filter(sala="AZUL")
    verde = Atendido.objects.filter(sala="VERDE")
    amarelo = Atendido.objects.filter(sala="AMARELO")
    laranja = Atendido.objects.filter(sala="LARANJA")
    vermelho = Atendido.objects.filter(sala="VERMELHO")
    ff = Atendido.objects.filter(sala="FAMILIA_FELIZ")
    
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
    
    return context