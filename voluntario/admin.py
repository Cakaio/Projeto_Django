from django.contrib import admin
from .models import Talento, Voluntario, PresencaVoluntario
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
    )
    filter_horizontal = ['talentos']
    list_filter = ['area', 'is_active']

    def get_export_queryset(self, request):
        # Obtém a queryset base
        queryset = super().get_export_queryset(request)
        
        # Aplica o filtro atual do admin
        # O 'changelist' contém os filtros aplicados no GET
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)