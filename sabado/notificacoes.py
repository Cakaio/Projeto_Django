"""Textos e públicos das notificações da enquete de sábado.

Separado das views e do comando pelo mesmo motivo de `ronda/sorteio.py`: o texto
e a escolha de quem recebe são a parte que erra, e precisam de teste direto. O
test client do Django quebra ao renderizar template neste ambiente (Python 3.14
com Django 4.2), então testar por HTTP não é opção — estas funções são puras e
se testam chamando.
"""
from django.utils import timezone

from voluntario.models import Voluntario

from .models import DisponibilidadeVoluntario, Sabado

# Título curto: o Android trunca, e o que importa é a pessoa reconhecer o assunto
# antes de decidir se abre.
TITULO_ABERTURA = "Enquete do sábado aberta"
TITULO_LEMBRETE = "Falta a sua resposta"


def sabado_da_vez():
    """O sábado que está valendo agora: o mais próximo com enquete aberta.

    `data__gte` de hoje mata o caso do sábado passado; `first()` mata o caso de a
    liderança cadastrar o semestre inteiro de uma vez. Sem isso, um lembrete
    diário que varresse todos os sábados abertos mandaria uma notificação POR
    SÁBADO, POR DIA, para cada pessoa — dez sábados cadastrados, dez pushes
    diários. O seed do projeto cria dez de uma vez, então não é hipótese.
    """
    hoje = timezone.localdate()
    for sabado in Sabado.objects.filter(data__gte=hoje).order_by("data"):
        if sabado.enquete_aberta:
            return sabado
    return None


def quem_nao_respondeu(sabado):
    """Voluntários ativos sem resposta registrada para este sábado.

    `ativos()` filtra data_saida E is_active: quem saiu do projeto não pode
    continuar recebendo cobrança de uma enquete que não é mais dele.
    """
    respondentes = DisponibilidadeVoluntario.objects.filter(
        sabado=sabado).values_list("voluntario_id", flat=True)
    return Voluntario.objects.ativos().exclude(id__in=respondentes)


def corpo_da_abertura(sabado):
    """Texto de quando a enquete abre.

    Cita o tema porque é o que faz a pessoa querer responder — mas com fallback,
    seguindo o que `inicio.html` já faz: `{{ sabado.tema|default:... }}`.
    """
    data = sabado.data.strftime("%d/%m")
    tema = (sabado.tema or "").strip()
    if tema:
        return f"Sábado {data} — {tema}. Diga se você vai."
    return f"Sábado {data}. Diga se você vai."


def corpo_do_lembrete(sabado):
    """Texto do lembrete diário.

    NÃO pode dizer "fecha amanhã" todo dia — era o que o comando fazia, e era
    mentira em todos os dias menos um. O número de dias restantes vem de
    `Sabado.dias_para_fechar`, que usa a mesma regra de fechamento da view.
    """
    data = sabado.data.strftime("%d/%m")
    dias = sabado.dias_para_fechar
    if dias <= 1:
        return f"A enquete do sábado {data} fecha hoje. Responda agora."
    if dias == 2:
        return f"A enquete do sábado {data} fecha amanhã."
    return f"Sábado {data}: você ainda não respondeu. Faltam {dias} dias."


def tag_da_enquete(sabado):
    """Tag por sábado, para o lembrete de hoje SUBSTITUIR o de ontem.

    É o uso correto da colapsagem do Web Push: sem tag, sete dias de lembrete
    viram sete notificações empilhadas na bandeja da pessoa.
    """
    return f"enquete-{sabado.pk}"


def url_da_enquete(sabado):
    return f"/sabado/responder/{sabado.pk}/"
