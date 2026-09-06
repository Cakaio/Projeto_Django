from django.contrib import admin
from .models import DisponibilidadeVoluntario, Sabado, FaixaHorarioAjuda
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields

class DisponibilidadeVoluntarioResource(resources.ModelResource):
    voluntario = fields.Field(column_name='voluntario')

    def dehydrate_voluntario(self, obj):
        return obj.voluntario.get_full_name() or obj.voluntario.username

    class Meta:
        model = DisponibilidadeVoluntario
        fields = ('id', 'sabado', 'voluntario', 'vai_ao_projeto','pode_ajudar', 'saude', 'vai_de_carro', 'respondido_em')


# Register your models here.
@admin.register(Sabado)
class SabadoAdmin(admin.ModelAdmin):
    list_display = ['data', 'tema']
    search_fields = ['tema']

    def save_model(self, request, obj, form, change):
        """Cadastrar o sábado é o que 'abre o formulário' — e agora avisa todo mundo.

        Fica em `save_model` e não num signal `post_save` de propósito: o admin é
        o único caminho de escrita de Sabado em produção (não existe view nem
        ModelForm, e o SabadoAdmin nem é ImportExportModelAdmin), enquanto um
        signal pegaria também as dez criações do `seed_sabado` e as dezenas
        espalhadas pelos testes de ronda, revista e adm — disparando push em
        todas.

        `if not change` porque editar o tema de um sábado já cadastrado não é
        abrir a enquete de novo.
        """
        super().save_model(request, obj, form, change)
        if change or not obj.enquete_aberta:
            return

        # Import local: `notificacoes.services` alcança o pywebpush, e um import
        # no topo do admin colocaria a dependência na cadeia de carregamento dos
        # apps — foi assim que o primeiro deploy derrubou o site inteiro.
        from notificacoes.services import enviar_push_async

        from .notificacoes import (TITULO_ABERTURA, corpo_da_abertura,
                                   quem_nao_respondeu, tag_da_enquete,
                                   url_da_enquete)

        enviar_push_async(
            quem_nao_respondeu(obj),
            TITULO_ABERTURA,
            corpo_da_abertura(obj),
            url=url_da_enquete(obj),
            tag=tag_da_enquete(obj),
        )

@admin.register(DisponibilidadeVoluntario)
class DisponibilidadeVoluntarioAdmin(ImportExportModelAdmin):
    resource_class = DisponibilidadeVoluntarioResource
    list_display = ['sabado', 'voluntario', 'vai_ao_projeto']
    search_fields = ['voluntario__first_name', 'voluntario__last_name']
    list_filter = ['sabado', 'vai_ao_projeto','pode_ajudar','vai_de_carro']
    filter_horizontal = ['pode_ajudar']

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)

@admin.register(FaixaHorarioAjuda)
class FaixaHorarioAjudaAdmin(admin.ModelAdmin):
    list_display = ['descricao']
    search_fields = ['descricao']