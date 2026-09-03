from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.html import format_html
from django.utils import timezone
from .models import Grupo, Talento, Voluntario, PresencaVoluntario, Ocorrencia, Regra, HistoricoLideranca
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
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

@admin.register(Grupo)
class GrupoAdmin(admin.ModelAdmin):
    list_display = ["nome", "atualizado_em"]
    search_fields = ["nome"]

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

class VoluntarioAdminForm(UserChangeForm):
    liderados = forms.ModelMultipleChoiceField(
        queryset=Voluntario.objects.all(),
        required=False,
        widget=FilteredSelectMultiple('liderados', is_stacked=False),
        label='Liderados',
        help_text='Selecione as pessoas que este voluntário lidera — o líder delas é definido automaticamente.',
    )

    class Meta(UserChangeForm.Meta):
        model = Voluntario
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ativos = Voluntario.objects.filter(data_saida__isnull=True)
        if self.instance and self.instance.pk:
            ativos = ativos.exclude(pk=self.instance.pk)
            self.fields['liderados'].initial = self.instance.liderados.all()
        self.fields['liderados'].queryset = ativos.order_by('first_name', 'last_name')


@admin.register(Voluntario)
class VoluntarioAdmin(UserAdmin, ImportExportModelAdmin):
    resource_class = VoluntarioResource
    formats = [base_formats.XLSX, base_formats.CSV]
    form = VoluntarioAdminForm

    fieldsets = UserAdmin.fieldsets + (
        ("Informações Adicionais", {'fields': ('apelido', 'area', 'data_nascimento', 'celular', 'rg', 'foto', 'talentos')}),
        ("Hierarquia", {'fields': ('cargo', 'lider', 'liderados')}),
        ("Permissões do PCF", {'fields': ('is_matricula',)}),
    )
    filter_horizontal = ['talentos']
    autocomplete_fields = ['lider']
    list_filter = ['area', 'is_active', 'is_matricula']

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        selecionados = set(form.cleaned_data.get('liderados') or [])
        atuais = set(obj.liderados.all())
        for v in selecionados - atuais:
            if v.pk != obj.pk:
                v.lider = obj
                v.save(update_fields=['lider'])
        for v in atuais - selecionados:
            v.lider = None
            v.save(update_fields=['lider'])

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
    # `de_quem` e não `voluntario`: quem não tem ficha apareceria como "None" na
    # listagem, e é justamente esse o caso que o campo `nome_avulso` atende.
    list_display = ['de_quem', 'cargo', 'area', 'data_inicio', 'data_fim', 'atual']
    list_filter = ['area']
    search_fields = ['voluntario__first_name', 'voluntario__last_name',
                     'nome_avulso', 'cargo']
    autocomplete_fields = ['voluntario']
    fieldsets = (
        ('Quem liderou', {
            'fields': ('voluntario', 'nome_avulso', 'foto'),
            'description': 'Escolha a ficha OU digite o nome. Boa parte de quem '
                           'liderou saiu antes de existir site e não tem login — '
                           'para essas pessoas, use nome e foto.',
        }),
        ('O cargo', {'fields': ('cargo', 'area', 'data_inicio', 'data_fim')}),
        ('A passagem', {'fields': ('descricao',)}),
    )

    @admin.display(boolean=True, description='Atual')
    def atual(self, obj):
        return obj.atual
