from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import EscalaAjuda


@admin.register(EscalaAjuda)
class EscalaAjudaAdmin(admin.ModelAdmin):
    """Toda escrita passa pelo quadro, inclusive para quem tem acesso ao admin."""
    list_display = ["sabado", "status", "atualizado_em", "abrir_quadro"]
    list_filter = ["status"]
    readonly_fields = ["sabado", "status", "revisao", "publicada_em", "atualizado_em", "abrir_quadro"]

    @admin.display(description="Organizar")
    def abrir_quadro(self, obj):
        return format_html('<a href="{}">Abrir quadro de ajudas</a>', reverse("ajudas:organizar", args=[obj.sabado_id]))

    def has_module_permission(self, request):
        return request.user.is_active and request.user.area == "TRIADE"

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
