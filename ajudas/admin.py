from django.contrib import admin
from django.db import transaction
from django.db.models import Count, F
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from sabado.models import Sabado
from .forms import AjudaAdminForm
from .models import Ajuda, EscalaAjuda, NecessidadeAjuda


class TriadeAdmin(admin.ModelAdmin):
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

    @admin.display(description="Quadro")
    def abrir_quadro(self, obj):
        escala = obj if isinstance(obj, EscalaAjuda) else obj.escala
        rotulo = "Abrir quadro / reabrir escala" if escala.status == "PUBLICADA" else "Organizar ajudas"
        return format_html('<a href="{}">{}</a>', reverse("ajudas:organizar", args=[escala.sabado_id]), rotulo)


@admin.register(EscalaAjuda)
class EscalaAjudaAdmin(TriadeAdmin):
    list_display = ["sabado", "status", "ver_ajudas", "publicada_em", "atualizado_em", "abrir_quadro"]
    list_filter = ["status", "sabado"]
    search_fields = ["sabado__tema"]
    list_select_related = ["sabado"]
    readonly_fields = ["sabado", "status", "revisao", "publicada_em", "atualizado_em", "ver_ajudas", "abrir_quadro"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_ajudas=Count("ajudas"))

    @admin.display(description="Ajudas alocadas", ordering="total_ajudas")
    def ver_ajudas(self, obj):
        return format_html('<a href="{}?escala__id__exact={}">{} ajudas</a>',
                           reverse("admin:ajudas_ajuda_changelist"), obj.pk, obj.total_ajudas)


@admin.register(NecessidadeAjuda)
class NecessidadeAjudaAdmin(TriadeAdmin):
    list_display = ["escala", "area", "hora_inicio", "hora_fim", "quantidade", "abrir_quadro"]
    list_filter = ["escala__sabado", "area", "escala__status"]
    search_fields = ["escala__sabado__tema", "area"]
    list_select_related = ["escala__sabado"]
    ordering = ["-escala__sabado__data", "hora_inicio", "area"]
    readonly_fields = ["escala", "area", "hora_inicio", "hora_fim", "quantidade", "abrir_quadro"]


@admin.register(Ajuda)
class AjudaAdmin(TriadeAdmin):
    form = AjudaAdminForm
    list_display = ["dia", "voluntario", "area_original", "area_destino", "hora_inicio", "hora_fim", "status_escala", "abrir_quadro"]
    list_display_links = ["voluntario"]
    list_filter = ["escala__sabado", "voluntario__area", "area_destino", "escala__status"]
    search_fields = ["voluntario__first_name", "voluntario__last_name", "voluntario__username", "escala__sabado__tema"]
    list_select_related = ["escala__sabado", "voluntario"]
    ordering = ["-escala__sabado__data", "hora_inicio", "voluntario__first_name"]
    fields = ["escala", "status_escala", "voluntario", "area_original", "area_destino", "hora_inicio", "hora_fim", "revisao_escala", "abrir_quadro"]
    readonly_fields = ["escala", "status_escala", "area_original", "abrir_quadro"]

    @admin.display(description="Sábado", ordering="escala__sabado__data")
    def dia(self, obj):
        return obj.sabado

    @admin.display(description="Área original", ordering="voluntario__area")
    def area_original(self, obj):
        return obj.voluntario.get_area_display()

    @admin.display(description="Status", ordering="escala__status")
    def status_escala(self, obj):
        return obj.escala.get_status_display()

    def get_fields(self, request, obj=None):
        campos = super().get_fields(request, obj)
        return [c for c in campos if c != "revisao_escala"] if obj and obj.escala.status == "PUBLICADA" else campos

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request) and (obj is None or obj.escala.status == "RASCUNHO")

    @transaction.atomic
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # Bloqueia antes da validação, na mesma ordem do serviço do quadro.
        # O admin relê o objeto depois da trava, inclusive o status da escala.
        if request.method == "POST" and object_id:
            objeto = self.get_object(request, object_id)
            if objeto:
                Sabado.objects.select_for_update().filter(pk=objeto.escala.sabado_id).first()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        EscalaAjuda.objects.filter(pk=obj.escala_id).update(revisao=F("revisao") + 1, atualizado_em=timezone.now())
