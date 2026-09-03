from django.contrib import admin

from .models import Aviso, InscricaoPush


@admin.register(InscricaoPush)
class InscricaoPushAdmin(admin.ModelAdmin):
    """Tudo readonly: ninguém edita chave de criptografia na mão — só apaga.

    Diferente do resto do projeto, NÃO usa ImportExportModelAdmin de propósito:
    exportar chave de push para planilha é vazamento de credencial.
    """
    list_display = ("voluntario", "user_agent", "criado_em", "ultimo_ok")
    search_fields = ("voluntario__username", "voluntario__first_name",
                     "voluntario__last_name")
    list_filter = ("criado_em",)
    readonly_fields = ("voluntario", "endpoint", "p256dh", "auth",
                       "user_agent", "criado_em", "ultimo_ok")


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    """Registro histórico — readonly."""
    list_display = ("titulo", "autor", "destino", "alvo", "total_enviado", "criado_em")
    search_fields = ("titulo", "mensagem")
    list_filter = ("destino", "criado_em")
    readonly_fields = ("autor", "titulo", "mensagem", "destino", "alvo",
                       "criado_em", "total_enviado")
