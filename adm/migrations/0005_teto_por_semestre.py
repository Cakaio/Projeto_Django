"""Teto de área deixa de ser mensal e passa a valer até alguém alterar.

Antes havia uma linha por área POR MÊS. Agora é uma linha por área, e o que
muda de período é só o gasto (medido no semestre). Como `area` vira única, é
obrigatório deduplicar ANTES de aplicar a restrição — senão a migração falha no
banco de quem já cadastrou teto em mais de um mês.

Mantemos o teto de competência mais recente de cada área: é o último valor que
alguém combinou, e portanto o que deve seguir valendo. `vigente_desde` recebe
essa competência, para não perder a memória de quando o valor passou a valer.
"""
from django.db import migrations, models
import django.utils.timezone


def manter_o_teto_mais_recente(apps, schema_editor):
    TetoArea = apps.get_model('adm', 'TetoArea')
    vistos = {}
    apagar = []
    # Mais recente primeiro: o primeiro de cada área é o que fica.
    for teto in TetoArea.objects.order_by('area', '-competencia'):
        if teto.area in vistos:
            apagar.append(teto.pk)
        else:
            vistos[teto.area] = teto
    if apagar:
        TetoArea.objects.filter(pk__in=apagar).delete()


def nada_a_desfazer(apps, schema_editor):
    """Os tetos antigos foram apagados e não há de onde recriá-los.

    Reverter a migração devolve o schema mensal, mas não o histórico — e é
    melhor dizer isso aqui do que fingir que dá para voltar.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('adm', '0004_conta_evento_lancamento_area_tetoarea_recargacartao_and_more'),
    ]

    operations = [
        # Primeiro a limpeza, enquanto `competencia` ainda existe.
        migrations.RunPython(manter_o_teto_mais_recente, nada_a_desfazer),
        migrations.AlterModelOptions(
            name='tetoarea',
            options={'ordering': ['area'], 'verbose_name': 'teto de área',
                     'verbose_name_plural': 'tetos de área'},
        ),
        migrations.RemoveConstraint(
            model_name='tetoarea',
            name='um_teto_por_area_por_mes',
        ),
        migrations.AddField(
            model_name='tetoarea',
            name='vigente_desde',
            field=models.DateField(default=django.utils.timezone.localdate,
                                   verbose_name='vale a partir de'),
        ),
        # `vigente_desde` recebe a competência que sobrou, antes de a coluna sair.
        migrations.RunSQL(
            sql='UPDATE adm_tetoarea SET vigente_desde = competencia WHERE competencia IS NOT NULL',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RemoveField(
            model_name='tetoarea',
            name='competencia',
        ),
        migrations.AlterField(
            model_name='tetoarea',
            name='area',
            field=models.CharField(
                choices=[('VIOLETA', 'Violeta'), ('ANIL', 'Anil'), ('AZUL', 'Azul'),
                         ('VERDE', 'Verde'), ('AMARELO', 'Amarelo'), ('LARANJA', 'Laranja'),
                         ('VERMELHO', 'Vermelho'), ('FAMILIA_FELIZ', 'Família Feliz'),
                         ('MARKETING', 'Marketing'), ('ADM/FIN', 'ADM/Fin'),
                         ('CR/RE', 'Captação de Recursos & Relações Externas'),
                         ('EVENTOS', 'Eventos'), ('GESTAO_DE_TALENTOS', 'Gestão de Talentos'),
                         ('RECREACAO', 'Recreação'), ('SUPPLY', 'Supply'),
                         ('PROJETOS', 'Projetos'), ('TRIADE', 'Tríade')],
                max_length=30, unique=True),
        ),
        migrations.AlterField(
            model_name='tetoarea',
            name='valor',
            field=models.DecimalField(decimal_places=2, max_digits=10,
                                      verbose_name='teto por semestre'),
        ),
    ]
