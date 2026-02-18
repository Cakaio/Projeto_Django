from import_export import resources, fields
from django.contrib import admin
from .models import Atendido, Familia, PresencaAtendido, ResponsavelAtendido, AtendidoInclusivo
from import_export.admin import ImportExportModelAdmin
from import_export.formats import base_formats
from django.utils.translation import gettext_lazy as _

# Register your models here.

# =====================
# RESOURCES
# =====================

class AtendidoResource(resources.ModelResource):
    class Meta:
        model = Atendido
        fields = (
            'id', 'familia', 'responsavel', 'nome', 'data_nascimento', 'sala', 'rg', 'cpf', 'contato', 'documento',
            'escolaridade', 'ano_escolar', 'escola', 'tipo_escola', 'trabalho', 'foto', 'projeto_social',
            'convenio_medico', 'vacina_covid', 'restricao_alimentar', 'restricao_medica', 'medicacao_continua',
            'deficiencia', 'identidade_etnica', 'numeracao_camisa', 'numeracao_calca', 'numeracao_calcado',
            'termos_assinado', 'registrado_por', 'comissao_inclusiva', 'observacoes', 'data_criacao', 'ativo'
        )


class FamiliaResource(resources.ModelResource):
    class Meta:
        model = Familia
        fields = (
            'id', 'nome', 'cep', 'endereco', 'bairro', 'cidade', 'zona_residencial', 'situacao_moradia',
            'agua_encanada', 'esgoto_encanado', 'energia_eletrica', 'renda_total_familia', 'pessoas_moram_familia',
            'pessoas_trabalham_familia', 'programa_transferencia_renda', 'internet_casa', 'comodos_casa', 'tv_casa',
            'banheiro_casa', 'motos_casa', 'carros_casa', 'geladeira_casa', 'freezer_casa', 'celular_casa',
            'computador_casa', 'cesta_natal', 'data_criacao'
        )


class ResponsavelAtendidoResource(resources.ModelResource):
    class Meta:
        model = ResponsavelAtendido
        fields = (
            'id', 'nome', 'cpf', 'rg', 'parentesco', 'contato', 'outro_contato', 'trabalho', 'email', 'escolaridade', 'data_criacao'
        )


class AtendidoInclusivoResource(resources.ModelResource):
    class Meta:
        model = AtendidoInclusivo
        fields = (
            'id', 'atendido', 'diagnostico', 'diagnostico_descricao', 'acompanhamento', 'recomendacoes',
            'comportamento_social', 'dificuldades_aprendizado', 'dificuldades_motoras', 'dificuldade_atencao',
            'dificuldade_emocional', 'servicos_apoio', 'expectativas_familia', 'observacoes_adicionais'
        )


class PresencaAtendidoResource(resources.ModelResource):
    class Meta:
        model = PresencaAtendido
        fields = (
            'id', 'atendido', 'presenca', 'data', 'registrado_por'
        )


# =====================
# ADMINS
# =====================

@admin.register(Atendido)
class AtendidoAdmin(ImportExportModelAdmin):
    resource_class = AtendidoResource
    formats = [base_formats.XLSX, base_formats.CSV]

    fieldsets = (
        ("Identificação do Atendido", {'fields': ('nome', 'data_nascimento', 'rg', 'cpf', 'foto', 'documento')}),
        ("Matricula", {'fields': ('sala','matricula')}),
        ("Vínculos Familiares e Responsáveis", {'fields': ('familia', 'responsavel')}),
        ("Informaçoes Educacionais", {'fields': ('escolaridade', 'ano_escolar', 'escola','tipo_escola')}),
        ("Contato", {'fields': ('contato',)}),
        ("Situação Social e Atividades", {'fields': ('trabalho', 'projeto_social',)}),
        ("Saúde e Bem-Estar", {'fields': ('convenio_medico', 'vacina_covid', 'restricao_alimentar', 'restricao_medica', 'medicacao_continua','campanha_vacinacao')}),
        ("PCF INCLUSIVO", {'fields': ('diagnostico', 'diagnostico_descricao', 'comportamento_social', 'comportamento_regras', 'concentracao', 'aprendizado', 'sensibilidade', 'sensibilidade_descricao', 'dificuldade_motora', 'dificuldade_motora_descricao', 'dificuldade_emocional', 'dificuldade_emocional_descricao', 'acompanhamento', 'recomendacao_acompanhamento', 'comissao_inclusiva','expectativas_familia')}),
        ("Impacto Projeto Crianca Feliz", {'fields': ('mudancas_positivas', 'aspectos_mudancas', 'saude_bucal',)}),
        ("Identidade e Perfil", {'fields': ('identidade_etnica',)}),
        ("Informações Vestuário", {'fields': ('numeracao_camisa','numeracao_calca','numeracao_calcado')}),
        ("Termos e Autorizações", {'fields': ('termos_assinado',)}),
        ("Observações e Informações Adicionais", {'fields': ('observacoes',)}),
        ("Controle e Auditoria do Sistema", {'fields': ('registrado_por','data_criacao','ativo')}),
    )
    list_display = ['nome', 'sala']
    list_filter = ['sala', 'ativo']

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)




# Filtro customizado para filtrar famílias por sala dos atendidos
class SalaAtendidoFamiliaListFilter(admin.SimpleListFilter):
    title = _('Sala do Atendido')
    parameter_name = 'sala_atendido'

    def lookups(self, request, model_admin):
        from .models import LISTA_SALAS
        return LISTA_SALAS

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(atendidos__sala=self.value()).distinct()
        return queryset

@admin.register(Familia)
class FamiliaAdmin(ImportExportModelAdmin):
    resource_class = FamiliaResource
    formats = [base_formats.XLSX, base_formats.CSV]
    list_display = ["id", "nome"]
    list_filter = [SalaAtendidoFamiliaListFilter]

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)



class SalaAtendidoListFilter(admin.SimpleListFilter):
    title = _('Sala do Atendido')
    parameter_name = 'sala_atendido'

    def lookups(self, request, model_admin):
        from .models import Atendido, LISTA_SALAS
        return LISTA_SALAS

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(atendidos__sala=self.value()).distinct()
        return queryset

@admin.register(ResponsavelAtendido)
class ResponsavelAtendidoAdmin(ImportExportModelAdmin):
    resource_class = ResponsavelAtendidoResource
    formats = [base_formats.XLSX, base_formats.CSV]
    list_display = ["nome", "contato", "parentesco"]
    list_filter = [SalaAtendidoListFilter]

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)


@admin.register(AtendidoInclusivo)
class AtendidoInclusivoAdmin(ImportExportModelAdmin):
    resource_class = AtendidoInclusivoResource
    formats = [base_formats.XLSX, base_formats.CSV]

    list_display = ['atendido', 'get_sala']
    list_filter = ['atendido__sala']

    def get_sala(self, obj):
        return obj.atendido.sala if obj.atendido else None
    get_sala.short_description = 'Sala'

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)


@admin.register(PresencaAtendido)
class PresencaAtendidoAdmin(ImportExportModelAdmin):
    resource_class = PresencaAtendidoResource
    formats = [base_formats.XLSX, base_formats.CSV]

    list_display = ['atendido', 'data', 'registrado_por']
    list_filter = ['data', 'atendido__sala']

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)
