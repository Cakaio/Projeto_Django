"""Contas do backlog que não são de uma tela só.

Ficam fora das views porque são exatamente a parte que precisa de teste: a
leitura por área é a resposta para "quem está me deixando no vácuo", e resposta
errada aqui vira cobrança errada lá na reunião.
"""
from django.db.models import Max, Q
from django.utils import timezone

from voluntario.models import LISTA_AREAS

from .models import Demanda, RegistroDemanda

# Mesma régua de `Demanda.travada`. Fica nomeada aqui porque o panorama recalcula
# a situação em Python (a propriedade do model consulta o banco uma vez por
# demanda, e no laço das áreas isso seria uma consulta por linha da tabela).
DIAS_TRAVADA = 14

# Retornos que significam "a bola está com a área": é neles que o relógio da
# demanda travada corre.
RETORNOS_ESPERANDO = ('AGUARDANDO', 'NAO_RESPONDE')

# Anotação é conversa nossa, não contato com a área — por isso não conta como
# "último contato". Se contasse, bastaria alguém escrever um lembrete interno
# para a área sumir da lista de quem está sem resposta.
TIPO_SEM_CONTATO = 'NOTA'


def _dias_parada(demanda, ultimo_registro, hoje):
    """Mesma conta de `Demanda.dias_parada`, mas com o último registro vindo de
    fora (já buscado em lote)."""
    referencia = ultimo_registro or timezone.localdate(demanda.criado_em)
    return (hoje - referencia).days


def _travada(demanda, dias_parada):
    """Mesma regra de `Demanda.travada`, com os dias já calculados."""
    return (demanda.aberta
            and demanda.retorno in RETORNOS_ESPERANDO
            and dias_parada > DIAS_TRAVADA)


def anotar_situacao(demandas):
    """Lista de demandas com `dias_sem_movimento` e `esta_travada` prontos.

    Os nomes são outros de propósito: `dias_parada` e `travada` são propriedades
    do model e não podem ser sobrescritas na instância. Quem monta tela deve usar
    estes atributos — dão o mesmo número sem uma consulta por item na lista.
    """
    hoje = timezone.localdate()
    lista = list(demandas.annotate(ultimo_registro=Max('registros__data')))
    for demanda in lista:
        demanda.dias_sem_movimento = _dias_parada(demanda, demanda.ultimo_registro, hoje)
        demanda.esta_travada = _travada(demanda, demanda.dias_sem_movimento)
    return lista


def panorama_por_area():
    """Uma linha por área do PCF, respondendo "como está a relação com ela".

    Devolve lista de dicts, ordenada da área mais parada para a mais ativa:
      area, nome, total, abertas, entregues, travadas,
      sem_contato (bool: nunca procuramos), ultimo_contato (date|None),
      dias_sem_contato (int|None)

    Áreas SEM demanda nenhuma também entram, com total 0 e sem_contato=True —
    são exatamente as que ninguém lembrou de procurar, e sumir com elas da
    tabela esconderia o problema que a tela existe para mostrar.
    """
    hoje = timezone.localdate()

    # Duas consultas no total, as duas ANTES do laço: uma traz as demandas e a
    # outra o resumo do histórico de cada uma. Dentro do laço não pode haver
    # acesso ao banco — são 17 áreas hoje, mas o custo cresceria com o backlog.
    resumo_historico = {
        linha['demanda']: linha
        for linha in RegistroDemanda.objects.values('demanda').annotate(
            ultimo=Max('data'),
            ultimo_contato=Max('data', filter=~Q(tipo=TIPO_SEM_CONTATO)),
        )
    }

    # Toda área nasce zerada: é assim que quem nunca foi procurado aparece.
    acumulado = {
        valor: {'area': valor, 'nome': rotulo, 'total': 0, 'abertas': 0,
                'entregues': 0, 'travadas': 0, 'ultimo_contato': None,
                'so_sem_contato': True}
        for valor, rotulo in LISTA_AREAS
    }

    for demanda in Demanda.objects.all():
        linha = acumulado.get(demanda.area)
        if linha is None:
            # Área que saiu de LISTA_AREAS depois que a demanda foi criada: não
            # dá para descartar a demanda em silêncio.
            linha = acumulado.setdefault(demanda.area, {
                'area': demanda.area, 'nome': demanda.area, 'total': 0,
                'abertas': 0, 'entregues': 0, 'travadas': 0,
                'ultimo_contato': None, 'so_sem_contato': True})

        historico = resumo_historico.get(demanda.pk, {})
        dias = _dias_parada(demanda, historico.get('ultimo'), hoje)

        linha['total'] += 1
        linha['abertas'] += 1 if demanda.aberta else 0
        linha['entregues'] += 1 if demanda.status == 'ENTREGUE' else 0
        linha['travadas'] += 1 if _travada(demanda, dias) else 0
        if demanda.retorno != 'SEM_CONTATO':
            linha['so_sem_contato'] = False

        contato = historico.get('ultimo_contato')
        if contato and (linha['ultimo_contato'] is None or contato > linha['ultimo_contato']):
            linha['ultimo_contato'] = contato

    panorama = []
    for linha in acumulado.values():
        contato = linha.pop('ultimo_contato')
        so_sem_contato = linha.pop('so_sem_contato')
        panorama.append({
            **linha,
            'ultimo_contato': contato,
            'dias_sem_contato': (hoje - contato).days if contato else None,
            # Sem histórico de contato e sem nenhuma demanda que já tenha saído
            # do "ainda não procuramos": é área virgem, com ou sem demanda.
            'sem_contato': contato is None and so_sem_contato,
        })

    panorama.sort(key=_ordem_do_vacuo)
    return panorama


def _ordem_do_vacuo(linha):
    """Do pior para o melhor: primeiro quem tem demanda travada, depois quem
    nunca foi procurado, e só então quem está em dia.

    Dentro de cada grupo manda o tempo sem contato — nunca contatado conta como
    tempo infinito, senão a área que ninguém procurou apareceria como a mais
    recente.
    """
    if linha['travadas']:
        grupo = 0
    elif linha['sem_contato']:
        grupo = 1
    else:
        grupo = 2
    dias = linha['dias_sem_contato']
    return (grupo,
            -linha['travadas'],
            -(dias if dias is not None else 10 ** 6),
            -linha['abertas'],
            linha['nome'])


def sincronizar_retorno(demanda, registro):
    """Faz o status de retorno concordar com o que o histórico acabou de dizer.

    Sem isto a tela mente: alguém registra que a área respondeu e o painel segue
    mostrando a demanda como "aguardando resposta" — e é justamente esse número
    que vira cobrança. Devolve True se mexeu na demanda.
    """
    novo = None
    if registro.tipo == 'RETORNO':
        novo = 'RESPONDEU'
    elif registro.tipo in ('CONVERSA', 'COBRANCA') and demanda.retorno == 'SEM_CONTATO':
        # Procurar a área é o que tira do "ainda não procuramos". Só sai daí quem
        # estava aí: quem já tinha sido marcado como "não responde" continua
        # assim, porque cobrar de novo não é resposta.
        novo = 'AGUARDANDO'

    if novo and novo != demanda.retorno:
        demanda.retorno = novo
        demanda.save(update_fields=['retorno', 'atualizado_em'])
        return True
    return False
