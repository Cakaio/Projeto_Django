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
        fields = ('id', 'sabado', 'voluntario', 'vai_ao_projeto', 'saude', 'vai_de_carro', 'respondido_em')


# Register your models here.
@admin.register(Sabado)
class SabadoAdmin(admin.ModelAdmin):
    list_display = ['data', 'tema']
    search_fields = ['tema']

@admin.register(DisponibilidadeVoluntario)
class DisponibilidadeVoluntarioAdmin(ImportExportModelAdmin):
    resource_class = DisponibilidadeVoluntarioResource
    list_display = ['sabado', 'voluntario', 'vai_ao_projeto']
    search_fields = ['voluntario__first_name', 'voluntario__last_name']
    list_filter = ['sabado', 'vai_ao_projeto']
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