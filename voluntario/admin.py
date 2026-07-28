from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Talento, Voluntario, PresencaVoluntario, Ocorrencia, Regra, HistoricoLideranca
from django.contrib.auth.admin import UserAdmin
from import_export.admin import ImportExportModelAdmin
from import_export.formats import base_formats
from import_export import resources, fields
from django.contrib.auth.hashers import make_password

# Register your models here.

# =====================
# RESOURCES
# =====================

import re

class VoluntarioResource(resources.ModelResource):
    def before_import_row(self, row, **kwargs):
        # Verifica se a senha existe na linha do arquivo (CSV/Excel)
        if 'password' in row and row['password']:
            # Só faz hash se não estiver no formato hash do Django
            # Hash do Django começa com 'pbkdf2_' ou 'argon2' ou 'bcrypt' ou 'sha1$'
            if not re.match(r'^(pbkdf2_|argon2|bcrypt|sha1\$)', row['password']):
                row['password'] = make_password(row['password'])

    class Meta:
        model = Voluntario
        fields = (
            'id', 'username', 'first_name','password', 'last_name', 'email', 'apelido', 'area', 'data_nascimento', 'celular',
            'rg', 'foto', 'talentos', 'is_staff', 'is_active', 'date_joined'
        )

class PresencaVoluntarioResource(resources.ModelResource):
    voluntario = fields.Field(column_name='voluntario')
    registrado_por = fields.Field(column_name='registrado_por')

    def dehydrate_voluntario(self, obj):
        return obj.voluntario.get_full_name() or obj.voluntario.username

    def dehydrate_registrado_por(self, obj):
        if obj.registrado_por:
            return obj.registrado_por.get_full_name() or obj.registrado_por.username
        return ''

    class Meta:
        model = PresencaVoluntario
        fields = (
            'id', 'voluntario', 'presenca', 'data', 'registrado_por'
        )

# =====================
# ADMINS
# =====================

@admin.register(PresencaVoluntario)
class PresencaVoluntarioAdmin(ImportExportModelAdmin):
    resource_class = PresencaVoluntarioResource
    formats = [base_formats.XLSX, base_formats.CSV]

    list_display = ['voluntario', 'data', 'registrado_por']
    list_filter = ['data']

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)

@admin.register(Talento)
class TalentoAdmin(admin.ModelAdmin):
    list_display = ['talento']
    search_fields = ['talento']

@admin.register(Voluntario)
class VoluntarioAdmin(UserAdmin, ImportExportModelAdmin):
    resource_class = VoluntarioResource
    formats = [base_formats.XLSX, base_formats.CSV]

    fieldsets = UserAdmin.fieldsets + (
        ("Informações Adicionais", {'fields': ('apelido', 'area', 'data_nascimento', 'celular', 'rg', 'foto', 'talentos')}),
        ("Hierarquia", {'fields': ('cargo', 'lider')}),
        ("Permissões do PCF", {'fields': ('is_matricula',)}),
    )
    filter_horizontal = ['talentos']
    autocomplete_fields = ['lider']
    list_filter = ['area', 'is_active', 'is_matricula']

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)


# =====================
# REGRA
# =====================

@admin.register(Regra)
class RegraAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'tipo_badge', 'descricao_curta', 'ordem', 'ativo']
    list_filter   = ['tipo', 'ativo']
    search_fields = ['codigo', 'descricao']
    list_editable = ['ativo', 'ordem']
    ordering      = ['tipo', 'ordem', 'codigo']

    fieldsets = (
        (None, {'fields': ('codigo', 'tipo', 'ativo', 'ordem')}),
        ('Descrição', {'fields': ('descricao',)}),
    )

    TIPO_COLORS = {
        'ALERTA':      ('#854d0e', '#fef9c3'),
        'ADVERTENCIA': ('#c2410c', '#ffedd5'),
        'SUSPENSAO':   ('#be123c', '#ffe4e6'),
    }

    def tipo_badge(self, obj):
        color, bg = self.TIPO_COLORS.get(obj.tipo, ('#374151', '#f3f4f6'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:9999px;'
            'font-size:.75rem;font-weight:700;">{}</span>', bg, color, obj.get_tipo_display()
        )
    tipo_badge.short_description = 'Tipo'
    tipo_badge.admin_order_field = 'tipo'

    def descricao_curta(self, obj):
        return obj.descricao[:80] + ('…' if len(obj.descricao) > 80 else '')
    descricao_curta.short_description = 'Descrição'


# =====================
# OCORRENCIA
# =====================

class SoftDeletedFilter(admin.SimpleListFilter):
    title = 'Status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):  # noqa: ARG002
        return (
            ('ativas',    'Ativas'),
            ('removidas', 'Removidas (soft-delete)'),
        )

    def queryset(self, request, queryset):  # noqa: ARG002
        if self.value() == 'ativas':
            return queryset.filter(deleted_at__isnull=True)
        if self.value() == 'removidas':
            return queryset.filter(deleted_at__isnull=False)
        return queryset


@admin.register(Ocorrencia)
class OcorrenciaAdmin(admin.ModelAdmin):
    list_display    = ['advertido', 'tipo_badge', 'regra', 'aplicado_por', 'automatico',
                       'criado_em_fmt', 'status_badge']
    list_filter     = ['tipo', 'automatico', SoftDeletedFilter]
    search_fields   = ['advertido__first_name', 'advertido__last_name', 'advertido__username',
                       'regra', 'razao']
    readonly_fields = ['id', 'criado_em', 'deleted_at', 'deleted_by']
    ordering        = ['-criado_em']
    date_hierarchy  = 'criado_em'

    fieldsets = (
        ('Ocorrência', {
            'fields': ('advertido', 'tipo', 'regra', 'razao', 'aplicado_por', 'automatico', 'criado_em')
        }),
        ('Soft Delete', {
            'fields': ('deleted_at', 'deleted_by'),
            'classes': ('collapse',),
            'description': 'Preenchido automaticamente ao remover pelo painel SAAS.',
        }),
    )

    actions = ['restaurar_ocorrencias', 'remover_permanentemente']

    TIPO_COLORS = {
        'ALERTA':      ('#854d0e', '#fef9c3'),
        'ADVERTENCIA': ('#c2410c', '#ffedd5'),
        'SUSPENSAO':   ('#be123c', '#ffe4e6'),
    }

    def tipo_badge(self, obj):
        color, bg = self.TIPO_COLORS.get(obj.tipo, ('#374151', '#f3f4f6'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:9999px;'
            'font-size:.75rem;font-weight:700;">{}</span>', bg, color, obj.get_tipo_display()
        )
    tipo_badge.short_description = 'Tipo'
    tipo_badge.admin_order_field = 'tipo'

    def status_badge(self, obj):
        if obj.deleted_at:
            return format_html(
                '<span style="background:#fee2e2;color:#dc2626;padding:2px 8px;border-radius:9999px;'
                'font-size:.75rem;font-weight:700;">Removida</span>'
            )
        return format_html(
            '<span style="background:#dcfce7;color:#16a34a;padding:2px 8px;border-radius:9999px;'
            'font-size:.75rem;font-weight:700;">Ativa</span>'
        )
    status_badge.short_description = 'Status'

    def criado_em_fmt(self, obj):
        return obj.criado_em.strftime('%d/%m/%Y %H:%M')
    criado_em_fmt.short_description = 'Criado em'
    criado_em_fmt.admin_order_field = 'criado_em'

    @admin.action(description='Restaurar ocorrências selecionadas (desfazer soft-delete)')
    def restaurar_ocorrencias(self, request, queryset):
        n = queryset.filter(deleted_at__isnull=False).update(deleted_at=None, deleted_by=None)
        self.message_user(request, f'{n} ocorrência(s) restaurada(s).')

    @admin.action(description='⚠️ Remover PERMANENTEMENTE do banco (irreversível)')
    def remover_permanentemente(self, request, queryset):
        n, _ = queryset.delete()
        self.message_user(request, f'{n} ocorrência(s) excluída(s) permanentemente.')


@admin.register(HistoricoLideranca)
class HistoricoLiderancaAdmin(admin.ModelAdmin):
    list_display = ['voluntario', 'cargo', 'area', 'data_inicio', 'data_fim', 'atual']
    list_filter = ['area']
    search_fields = ['voluntario__first_name', 'voluntario__last_name', 'cargo']
    autocomplete_fields = ['voluntario']

    @admin.display(boolean=True, description='Atual')
    def atual(self, obj):
        return obj.atual