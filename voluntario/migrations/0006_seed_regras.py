from django.db import migrations

REGRAS_INICIAIS = [
    # (codigo, descricao, tipo, ordem)
    ('AL1',  'Não respondeu o formulário de presença até quarta-feira às 23h59',              'ALERTA',      1),
    ('AL2',  'Confirmou presença e não compareceu no sábado',                                 'ALERTA',      2),
    ('AL3',  'Quórum mínimo: presença inferior a 50% nos sábados do semestre',                'ALERTA',      3),
    ('AL4',  'Atraso após 8h30 no DEMAR sem justificativa prévia',                            'ALERTA',      4),
    ('AL5',  'Saiu antes do encerramento ou não participou da reunião final',                 'ALERTA',      5),
    ('AL6',  'Atitudes inadequadas reincidentes após aviso da GT',                            'ALERTA',      6),
    ('AL7',  'Não cumpriu turno de ronda durante o sábado',                                   'ALERTA',      7),
    ('AL8',  'Demonstrações excessivas de carinho/afeto próximo aos atendidos',               'ALERTA',      8),
    ('AL9',  'Atraso superior a 20 minutos sem justificativa',                                'ALERTA',      9),
    ('AL10', 'Não respondeu formulários/enquetes disponibilizados nos Informativos',          'ALERTA',     10),
    ('AL11', 'Falta em turno de pré-evento após confirmação e sem aviso prévio',              'ALERTA',     11),
    ('AL12', 'Duas faltas seguidas em reunião de área sem justificativa',                     'ALERTA',     12),
    ('AL13', 'Faltou a um sábado sem avisar e o líder julgou pertinente',                    'ALERTA',     13),
    ('AL14', 'Não realizou tarefa da área',                                                   'ALERTA',     14),
    ('AL15', 'Não respondeu o grupo da área por uma semana ou mais',                          'ALERTA',     15),
    ('AL16', 'Líder não cumpriu prazos estabelecidos pela gestão',                            'ALERTA',     16),
    ('AL17', 'Líder não compareceu às reuniões da Gestão sem justificar',                     'ALERTA',     17),
    ('AD1',  'Estava sob influência de álcool ou substância psicoativa durante o projeto',    'ADVERTENCIA',  1),
    ('AD2',  'Dormiu durante o projeto',                                                      'ADVERTENCIA',  2),
    ('AD3',  'Faltou à RG ou Postulação sem justificativa',                                   'ADVERTENCIA',  3),
    ('AD4',  'Não cumpriu turno em evento externo sem justificativa ao membro de Eventos',    'ADVERTENCIA',  4),
    ('AD5',  'Três faltas seguidas em reunião de área sem justificativa',                     'ADVERTENCIA',  5),
    ('AD6',  'Não cumpriu tarefa que afetou o funcionamento do sábado ou prejudicou a área',  'ADVERTENCIA',  6),
    ('AD7',  'Somatório de 2 alertas do mesmo motivo',                                        'ADVERTENCIA',  7),
    ('AD8',  'Somatório de 3 alertas de diferentes motivos',                                  'ADVERTENCIA',  8),
    ('PO1',  'Quórum mínimo igual ou inferior a 30% no semestre',                             'SUSPENSAO',    1),
    ('PO2',  'Líder ausente e sem cumprir funções por uma semana ou mais',                    'SUSPENSAO',    2),
    ('PO3',  'Somatório de 2 advertências do mesmo motivo',                                   'SUSPENSAO',    3),
    ('PO4',  'Somatório de 3 advertências de diferentes motivos',                             'SUSPENSAO',    4),
]


def seed_regras(apps, schema_editor):
    Regra = apps.get_model('voluntario', 'Regra')
    for codigo, descricao, tipo, ordem in REGRAS_INICIAIS:
        Regra.objects.get_or_create(
            codigo=codigo,
            defaults={'descricao': descricao, 'tipo': tipo, 'ordem': ordem, 'ativo': True},
        )


def delete_regras(apps, schema_editor):
    Regra = apps.get_model('voluntario', 'Regra')
    Regra.objects.filter(codigo__in=[r[0] for r in REGRAS_INICIAIS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0005_regra'),
    ]

    operations = [
        migrations.RunPython(seed_regras, delete_regras),
    ]
