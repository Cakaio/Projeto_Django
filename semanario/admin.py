from django.contrib import admin
from .models import Semanario, Atividade, Material


# ─────────────────────────────
# 1️⃣ INLINE DE MATERIAIS (dentro de Atividade)
# ─────────────────────────────
class MaterialInline(admin.TabularInline):
    """
    Exibe os materiais diretamente dentro do formulário da Atividade.
    """
    model = Material
    extra = 1  # uma linha vazia extra para facilitar adicionar novos


# ─────────────────────────────
# 2️⃣ INLINE DE ATIVIDADES (dentro de Semanário)
# ─────────────────────────────
class AtividadeInline(admin.TabularInline):
    """
    Mostra as atividades associadas ao Semanário.
    Cada linha tem um link que abre a Atividade completa (com os Materiais).
    """
    model = Atividade
    fields = ("atividade", "competencia", "responsavel")  # campos exibidos no inline
    show_change_link = True  # ✅ cria link direto para editar a atividade
    extra = 1


# ─────────────────────────────
# 3️⃣ ADMIN DE SEMANÁRIO
# ─────────────────────────────
@admin.register(Semanario)
class SemanarioAdmin(admin.ModelAdmin):
    """
    Exibe o Semanário com suas Atividades inline.
    """
    list_display = ("sala", "tema")
    list_filter = ("sala", "data")
    search_fields = ("tema","sala")
    filter_horizontal = ['talentos_necessarios']
    inlines = [AtividadeInline]


# ─────────────────────────────
# 4️⃣ ADMIN DE ATIVIDADE
# ─────────────────────────────
@admin.register(Atividade)
class AtividadeAdmin(admin.ModelAdmin):
    """
    Exibe as Atividades com os Materiais inline.
    """
    list_display = ("atividade", "semanario", "competencia", "responsavel")
    list_filter = ("semanario__sala", "competencia")
    search_fields = ("atividade", "descricao")
    inlines = [MaterialInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Material) and not instance.requisitado_por_id:
                instance.requisitado_por = request.user
            instance.save()
        for instance in formset.deleted_objects:
            instance.delete()
        formset.save_m2m()


# ─────────────────────────────
# 5️⃣ ADMIN DE MATERIAL
# ─────────────────────────────
@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    """
    Exibe os Materiais individualmente (caso queira ver todos juntos).
    """
    list_display = ("nome", "especificar", "link", "atividade", "quantidade", "unidade", "valor", "valor_total", "local", "requisitado_por")
    list_filter = ("unidade", "local__tipo")
    search_fields = ("nome", "especificar", "link", "local__nome", "requisitado_por__username")
    autocomplete_fields = ("item", "local")

    def save_model(self, request, obj, form, change):
        if not obj.requisitado_por_id:
            obj.requisitado_por = request.user
        super().save_model(request, obj, form, change)
