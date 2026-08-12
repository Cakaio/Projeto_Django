from django.contrib import admin

from .models import Demanda, RegistroDemanda
from .servicos import sincronizar_retorno


class RegistroInline(admin.TabularInline):
    model = RegistroDemanda
    extra = 0
    fields = ('data', 'tipo', 'descricao', 'autor')
    readonly_fields = ('autor',)     # quem escreveu sai de quem está logado


@admin.register(Demanda)
class DemandaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'area', 'status', 'retorno', 'prioridade',
                    'responsavel', 'atualizado_em')
    list_filter = ('area', 'status', 'retorno', 'prioridade')
    search_fields = ('titulo', 'o_que_pediram', 'o_que_fizemos')
    inlines = [RegistroInline]

    def save_formset(self, request, form, formset, change):
        """Registro criado pelo inline precisa passar pelas mesmas regras.

        O Django salva inline por aqui, e NÃO pelo `save_model` do admin do
        filho — então o `RegistroDemandaAdmin.save_model` nunca roda para
        registros digitados dentro da demanda. Sem este método, dava para
        cadastrar um retorno da área pelo inline e a demanda continuar
        marcada como "aguardando resposta": o histórico e o status contando
        histórias diferentes, que é justamente o que a tela existe para evitar.
        """
        if formset.model is not RegistroDemanda:
            return super().save_formset(request, form, formset, change)

        registros = formset.save(commit=False)
        for apagado in formset.deleted_objects:
            apagado.delete()
        for registro in registros:
            if not registro.autor_id:
                registro.autor = request.user
            registro.save()
        formset.save_m2m()
        for registro in registros:
            sincronizar_retorno(registro.demanda, registro)


@admin.register(RegistroDemanda)
class RegistroDemandaAdmin(admin.ModelAdmin):
    list_display = ('demanda', 'data', 'tipo', 'autor')
    list_filter = ('tipo', 'data', 'demanda__area')
    search_fields = ('demanda__titulo', 'descricao')
    date_hierarchy = 'data'
    readonly_fields = ('autor',)     # idem: não se escreve histórico em nome de outro

    def save_model(self, request, obj, form, change):
        if not obj.autor_id:
            obj.autor = request.user
        super().save_model(request, obj, form, change)
        # Mesma coerência da ficha: histórico e status da demanda não podem
        # contar histórias diferentes só porque o registro entrou pelo admin.
        sincronizar_retorno(obj.demanda, obj)
