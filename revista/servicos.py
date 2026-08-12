"""Regras de negócio da revista.

Ficam fora das views porque são o que os testes precisam exercitar de verdade:
montar as seções a partir do semanário e apurar os números do período.
"""
from django.db.models import Max

from atendido.models import PresencaAtendido
from sabado.models import Sabado
from semanario.models import Atividade, Semanario
from voluntario.models import PresencaVoluntario

from .models import SecaoRevista


def _atividades_do_periodo(inicio, fim):
    """Atividades com descrição preenchida no período, na ordem em que serão
    lidas na revista: por sábado, depois por sala."""
    return (Atividade.objects
            .filter(semanario__data__data__range=(inicio, fim))
            .exclude(descricao='')
            .select_related('semanario', 'semanario__data')
            .order_by('semanario__data__data', 'semanario__sala', 'pk'))


def montar_secoes(revista, substituir=False):
    """Cria as seções a partir das atividades dos semanários do período.

    Só entram atividades COM descrição — é a descrição que vira o texto da
    revista. Por padrão não substitui o que já existe, para não apagar o que o
    CR já reescreveu; `substituir=True` recomeça do zero.
    Devolve quantas seções foram criadas."""
    if substituir:
        revista.secoes.all().delete()
        # "Recomeçar do zero" recomeça mesmo, inclusive os descartes: senão o
        # CR não teria como trazer de volta uma atividade que apagou por engano.
        revista.atividades_descartadas = []
        revista.save(update_fields=['atividades_descartadas'])
        ja_usadas = set()
    else:
        # Remontar é operação corriqueira (o CR fecha o período aos poucos):
        # sem isso, cada clique duplicaria os destaques já revisados.
        ja_usadas = set(revista.secoes
                        .exclude(atividade__isnull=True)
                        .values_list('atividade_id', flat=True))
        # Apagar a seção é como o CR diz "esta atividade não entra". Sem
        # lembrar do descarte, o próximo "remontar" ressuscitaria justamente o
        # que ele tirou — e ele teria de tirar de novo, toda vez.
        ja_usadas |= set(revista.atividades_descartadas or [])

    # A ordem continua de onde a revista parou. Usa o MAIOR valor, não a
    # contagem: basta o CR apagar uma seção do meio, ou criar uma manual (que
    # nasce com ordem=0), para a contagem colidir com uma ordem existente e a
    # revista sair numa sequência que ninguém escolheu.
    maior = revista.secoes.aggregate(maior=Max('ordem'))['maior']
    ultima_ordem = (maior + 1) if maior is not None else 0

    novas = []
    for atividade in _atividades_do_periodo(revista.periodo_inicio, revista.periodo_fim):
        if atividade.pk in ja_usadas:
            continue
        semanario = atividade.semanario
        novas.append(SecaoRevista(
            revista=revista,
            atividade=atividade,
            sabado=semanario.data,
            sala=semanario.sala,
            titulo=atividade.atividade,
            texto=atividade.descricao,
            competencia=atividade.competencia or '',
            ordem=ultima_ordem + len(novas),
        ))

    SecaoRevista.objects.bulk_create(novas)
    return len(novas)


# O semanário carimba isto quando a competência da atividade não bate com
# nenhuma dimensão do mapa. É um recado interno, para o time arrumar o
# cadastro — não é uma dimensão de desenvolvimento, e mostrar isso ao doador
# só faz o projeto parecer desorganizado.
DIMENSOES_INTERNAS = {'não classificada', 'nao classificada', 'não classificado'}


def _dimensoes_do_periodo(inicio, fim):
    """Dimensões trabalhadas no período, sem repetição.

    NÃO separe por vírgula. `Atividade` grava sempre UMA dimensão inteira, e
    3 dos 7 nomes têm vírgula dentro ("Autoconhecimento, Identidade e Projeto
    de Vida", "Autonomia, Responsabilidade e Protagonismo", "Criatividade,
    Expressão e Comunicação"). Fatiar transformava cada uma em duas dimensões
    inventadas — bem na capa que vai para o doador.
    """
    brutos = (Atividade.objects
              .filter(semanario__data__data__range=(inicio, fim))
              .exclude(dimensao_competencia__isnull=True)
              .exclude(dimensao_competencia='')
              .values_list('dimensao_competencia', flat=True)
              .distinct())

    return sorted({
        bruto.strip() for bruto in brutos
        if bruto and bruto.strip() and bruto.strip().lower() not in DIMENSOES_INTERNAS
    })


def numeros_do_periodo(inicio, fim):
    """Números para a capa: quantos sábados, quantas atividades, quantas
    crianças estiveram presentes, quantos voluntários, quais dimensões foram
    trabalhadas. Devolve um dict."""
    sabados = Sabado.objects.filter(data__range=(inicio, fim)).count()

    atividades = Atividade.objects.filter(
        semanario__data__data__range=(inicio, fim)).count()

    # Distinct no atendido, não na linha de presença: senão a mesma criança
    # seria contada uma vez por sábado e o número iria para o doador inflado.
    criancas = (PresencaAtendido.objects
                .filter(data__data__range=(inicio, fim), presenca='PRESENTE')
                .values('atendido').distinct().count())

    voluntarios = (PresencaVoluntario.objects
                   .filter(data__data__range=(inicio, fim), presenca='PRESENTE')
                   .values('voluntario').distinct().count())

    salas = (Semanario.objects
             .filter(data__data__range=(inicio, fim))
             .values('sala').distinct().count())

    return {
        'sabados': sabados,
        'atividades': atividades,
        'criancas': criancas,
        'voluntarios': voluntarios,
        'salas': salas,
        'dimensoes': _dimensoes_do_periodo(inicio, fim),
    }


def financeiro_do_periodo(inicio, fim):
    """Onde o dinheiro foi aplicado, vindo do Financeiro (app `adm`).

    Import tardio e tolerante de propósito: `adm.servicos` é entrega de outra
    parte do projeto e a revista não pode deixar de abrir se ele ainda não
    existir. Devolve None quando não há de onde ler."""
    try:
        from adm.servicos import despesas_por_categoria
    except ImportError:
        return None

    linhas, total = despesas_por_categoria(inicio, fim)
    return {'linhas': linhas, 'total': total}
