from django.contrib import admin
from .models import Atendido, Familia, PresencaAtendido, ResponsavelAtendido

# Register your models here.
@admin.register(PresencaAtendido)
class PresencaAtendidoAdmin(admin.ModelAdmin):
    list_display = ['atendido', 'data', 'registrado_por']
    list_filter = ['data', 'atendido__sala']

@admin.register(Atendido)
class AtendidoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Identificação do Atendido", {'fields': ('nome', 'data_nascimento', 'rg', 'cpf', 'foto', 'documento')}),
        ("Sala de Matricula", {'fields': ('sala',)}),
        ("Vínculos Familiares e Responsáveis", {'fields': ('familia', 'responsavel')}),
        ("Informaçoes Educacionais", {'fields': ('escolaridade', 'ano_escolar', 'escola','tipo_escola')}),
        ("Contato", {'fields': ('contato',)}),
        ("Situação Social e Atividades", {'fields': ('trabalho', 'projeto_social',)}),
        ("Saúde e Bem-Estar", {'fields': ('convenio_medico', 'vacina_covid', 'restricao_alimentar', 'restricao_medica', 'medicacao_continua', 'deficiencia', 'comissao_inclusiva')}),
        ("Identidade e Perfil", {'fields': ('identidade_etnica',)}),
        ("Informações Vestuário", {'fields': ('numeracao_camisa','numeracao_calca','numeracao_calcado')}),
        ("Termos e Autorizações", {'fields': ('termos_assinado',)}),
        ("Observações", {'fields': ('observacoes',)}),
        ("Controle e Auditoria do Sistema", {'fields': ('registrado_por','data_criacao','ativo')}),
    )
    list_display = ['nome', 'sala']
    list_filter = ['sala']

@admin.register(Familia)
class FamiliaAdmin(admin.ModelAdmin):
    list_display = ['nome']

@admin.register(ResponsavelAtendido)
class ResponsavelAtendidoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'parentesco']
