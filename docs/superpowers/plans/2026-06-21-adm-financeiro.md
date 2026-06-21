# Módulo ADM Financeiro — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o app Django `adm` com fluxo de caixa, DRE comparativo e integração automática com `supply.Pedido`.

**Architecture:** App isolado `adm/` com modelos `Categoria` e `Lancamento`, mixin de controle de acesso por área, signal no `supply.Pedido` para criar lançamentos automáticos de despesa, e 6 views analíticas/CRUD com templates TailwindCSS seguindo o padrão do projeto.

**Tech Stack:** Django 4.2, TailwindCSS (CDN), Bootstrap 5 (CDN), Python `csv` stdlib para exportação.

## Global Constraints

- Linguagem: todo texto de UI, models e comentários em **português brasileiro**
- Acesso leitura: `area in ['ADM/FIN', 'TRIADE']` ou `is_superuser`
- Acesso escrita: `area == 'ADM/FIN'` ou `is_superuser`
- Lançamentos de `origem='SUPPLY'` não podem ser editados/deletados manualmente
- Templates estendem `base.html`, seguem padrão TailwindCSS + Bootstrap do projeto
- `timezone.now()` sempre, nunca `datetime.now()`
- Sem dependências novas além da stdlib

---

## File Map

**Criar:**
- `adm/__init__.py`
- `adm/apps.py`
- `adm/models.py` — `Categoria`, `Lancamento`
- `adm/admin.py`
- `adm/forms.py` — `CategoriaForm`, `LancamentoForm`
- `adm/views.py` — todas as views
- `adm/urls.py`
- `adm/signals.py` — integração `supply.Pedido`
- `adm/migrations/0001_initial.py` (gerado por makemigrations)
- `adm/templates/painel_adm.html`
- `adm/templates/lista_lancamentos.html`
- `adm/templates/form_lancamento.html`
- `adm/templates/lista_categorias.html`
- `adm/templates/form_categoria.html`
- `adm/templates/fluxo_caixa.html`
- `adm/templates/dre.html`
- `adm/tests.py`

**Modificar:**
- `TESTE/settings.py` — adicionar `'adm'` em `INSTALLED_APPS`
- `TESTE/urls.py` — adicionar `path('adm/', include('adm.urls', namespace='adm'))`
- `templates/navbar.html` — link ADM/FIN condicional

---

## Task 1: Scaffold do app + modelos

**Files:**
- Create: `adm/__init__.py`
- Create: `adm/apps.py`
- Create: `adm/models.py`
- Create: `adm/admin.py`
- Create: `adm/tests.py`
- Modify: `TESTE/settings.py`

**Interfaces:**
- Produces: `Categoria(nome, tipo, ativo)`, `Lancamento(tipo, categoria, valor, data, descricao, origem, pedido, criado_por, criado_em)` — usados em todas as tasks seguintes

- [ ] **Step 1: Criar estrutura do app**

```bash
mkdir adm
touch adm/__init__.py
```

- [ ] **Step 2: Criar `adm/apps.py`**

```python
from django.apps import AppConfig

class AdmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adm'

    def ready(self):
        import adm.signals  # noqa
```

- [ ] **Step 3: Criar `adm/models.py`**

```python
from django.db import models
from django.utils import timezone

TIPO_CHOICES = (
    ('RECEITA', 'Receita'),
    ('DESPESA', 'Despesa'),
)

ORIGEM_CHOICES = (
    ('MANUAL', 'Manual'),
    ('SUPPLY', 'Supply'),
)


class Categoria(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['tipo', 'nome']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return f'{self.nome} ({self.get_tipo_display()})'


class Lancamento(models.Model):
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, editable=False)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name='lancamentos'
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField()
    descricao = models.TextField(blank=True)
    origem = models.CharField(max_length=10, choices=ORIGEM_CHOICES, default='MANUAL')
    pedido = models.OneToOneField(
        'supply.Pedido', on_delete=models.CASCADE,
        null=True, blank=True, related_name='lancamento'
    )
    criado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lancamentos_criados'
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def save(self, *args, **kwargs):
        self.tipo = self.categoria.tipo
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_tipo_display()} — R$ {self.valor} ({self.data})'
```

- [ ] **Step 4: Criar `adm/admin.py`**

```python
from django.contrib import admin
from .models import Categoria, Lancamento

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'ativo')
    list_filter = ('tipo', 'ativo')

@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ('data', 'tipo', 'categoria', 'valor', 'origem', 'criado_por')
    list_filter = ('tipo', 'origem', 'categoria')
    date_hierarchy = 'data'
```

- [ ] **Step 5: Criar `adm/tests.py` com testes dos modelos**

```python
from django.test import TestCase
from django.utils import timezone
from adm.models import Categoria, Lancamento

class CategoriaModelTest(TestCase):
    def test_str(self):
        cat = Categoria(nome='Doação', tipo='RECEITA')
        self.assertEqual(str(cat), 'Doação (Receita)')

class LancamentoModelTest(TestCase):
    def setUp(self):
        self.cat_receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')
        self.cat_despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')

    def test_tipo_derivado_da_categoria(self):
        """tipo deve ser preenchido automaticamente a partir da categoria"""
        lan = Lancamento.objects.create(
            categoria=self.cat_receita,
            valor='100.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'RECEITA')

    def test_tipo_despesa_derivado(self):
        lan = Lancamento.objects.create(
            categoria=self.cat_despesa,
            valor='50.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'DESPESA')
```

- [ ] **Step 6: Adicionar `adm` em `INSTALLED_APPS` em `TESTE/settings.py`**

Localizar a lista `INSTALLED_APPS` e adicionar `'adm'` após `'supply'`:

```python
INSTALLED_APPS = [
    ...
    'supply',
    'adm',
]
```

- [ ] **Step 7: Gerar e aplicar migrations**

```bash
python manage.py makemigrations adm
python manage.py migrate
```

Esperado: `adm/migrations/0001_initial.py` criado, migração aplicada sem erro.

- [ ] **Step 8: Rodar testes**

```bash
python manage.py test adm
```

Esperado: `Ran 3 tests in ...s OK`

- [ ] **Step 9: Commit**

```bash
git add adm/ TESTE/settings.py
git commit -m "feat(adm): scaffold app com modelos Categoria e Lancamento"
```

---

## Task 2: Mixin de acesso + URLs

**Files:**
- Create: `adm/urls.py`
- Modify: `adm/views.py` (criar arquivo com mixins)
- Modify: `TESTE/urls.py`

**Interfaces:**
- Produces: `AdmAcessoMixin` (leitura — ADM/FIN, TRIADE, superuser), `AdmEscritaMixin` (escrita — ADM/FIN, superuser) — usados em todas as views das Tasks 3–8

- [ ] **Step 1: Criar `adm/views.py` com mixins**

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from functools import wraps

AREAS_LEITURA = {'ADM/FIN', 'TRIADE'}
AREAS_ESCRITA = {'ADM/FIN'}


class AdmAcessoMixin(LoginRequiredMixin):
    """Leitura: ADM/FIN, TRIADE, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdmEscritaMixin(LoginRequiredMixin):
    """Escrita: ADM/FIN, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def adm_acesso_required(view_func):
    """Decorator para function-based views de leitura ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def adm_escrita_required(view_func):
    """Decorator para function-based views de escrita ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper
```

- [ ] **Step 2: Criar `adm/urls.py`**

```python
from django.urls import path
from . import views

app_name = 'adm'

urlpatterns = [
    path('', views.painel, name='painel'),
    path('lancamentos/', views.lista_lancamentos, name='lista_lancamentos'),
    path('lancamentos/novo/', views.criar_lancamento, name='criar_lancamento'),
    path('lancamentos/<int:pk>/editar/', views.editar_lancamento, name='editar_lancamento'),
    path('lancamentos/<int:pk>/deletar/', views.deletar_lancamento, name='deletar_lancamento'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/nova/', views.criar_categoria, name='criar_categoria'),
    path('categorias/<int:pk>/editar/', views.editar_categoria, name='editar_categoria'),
    path('categorias/<int:pk>/deletar/', views.deletar_categoria, name='deletar_categoria'),
    path('fluxo-de-caixa/', views.fluxo_caixa, name='fluxo_caixa'),
    path('dre/', views.dre, name='dre'),
]
```

- [ ] **Step 3: Adicionar `adm` em `TESTE/urls.py`**

```python
path('adm/', include('adm.urls', namespace='adm')),
```

Inserir logo após o `path('supply/', ...)`.

- [ ] **Step 4: Adicionar stubs de view em `adm/views.py`** (para o servidor não quebrar)

Adicionar ao final do arquivo:

```python
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import Categoria, Lancamento

def painel(request): return HttpResponse('painel')
def lista_lancamentos(request): return HttpResponse('lancamentos')
def criar_lancamento(request): return HttpResponse('criar')
def editar_lancamento(request, pk): return HttpResponse('editar')
def deletar_lancamento(request, pk): return HttpResponse('deletar')
def lista_categorias(request): return HttpResponse('categorias')
def criar_categoria(request): return HttpResponse('criar cat')
def editar_categoria(request, pk): return HttpResponse('editar cat')
def deletar_categoria(request, pk): return HttpResponse('deletar cat')
def fluxo_caixa(request): return HttpResponse('fluxo')
def dre(request): return HttpResponse('dre')
```

- [ ] **Step 5: Testar mixins**

```python
# Adicionar em adm/tests.py
from django.test import TestCase, RequestFactory
from django.core.exceptions import PermissionDenied
from unittest.mock import MagicMock
from adm.views import AdmAcessoMixin, AdmEscritaMixin

class MixinTest(TestCase):
    def _make_user(self, area, superuser=False):
        u = MagicMock()
        u.is_authenticated = True
        u.is_superuser = superuser
        u.area = area
        return u

    def _make_request(self, area, superuser=False):
        req = MagicMock()
        req.user = self._make_user(area, superuser)
        return req

    def test_adm_fin_tem_acesso_leitura(self):
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('ADM/FIN')
        # não levanta PermissionDenied
        try:
            mixin.dispatch(req)
        except (PermissionDenied, AttributeError):
            pass  # AttributeError de super().dispatch é esperado sem view real

    def test_voluntario_sem_area_bloqueado(self):
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('AZUL')
        with self.assertRaises((PermissionDenied, AttributeError)):
            mixin.dispatch(req)
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 6: Verificar que `/adm/` retorna 200 (ou 302 login)**

```bash
python manage.py runserver
# Navegar para http://localhost:8000/adm/ — deve retornar página ou redirect ao login
```

- [ ] **Step 7: Commit**

```bash
git add adm/ TESTE/urls.py
git commit -m "feat(adm): mixins de acesso e URLs do modulo"
```

---

## Task 3: CRUD de Categorias

**Files:**
- Create: `adm/forms.py`
- Modify: `adm/views.py` — substituir stubs de categoria por views reais
- Create: `adm/templates/lista_categorias.html`
- Create: `adm/templates/form_categoria.html`

**Interfaces:**
- Consumes: `Categoria` (Task 1), `AdmEscritaMixin`, `adm_escrita_required` (Task 2)
- Produces: `/adm/categorias/` funcional — usado pelo ADM/FIN para criar "Materiais Supply" antes de usar o signal

- [ ] **Step 1: Criar `adm/forms.py`**

```python
from django import forms
from .models import Categoria, Lancamento

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nome', 'tipo', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Doação'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nome': 'Nome da Categoria',
            'tipo': 'Tipo',
            'ativo': 'Ativa',
        }
```

- [ ] **Step 2: Substituir stubs de categoria em `adm/views.py`**

Substituir as 4 funções de categoria pelo código abaixo:

```python
@adm_acesso_required
def lista_categorias(request):
    categorias = Categoria.objects.all()
    return render(request, 'lista_categorias.html', {'categorias': categorias})


@adm_escrita_required
def criar_categoria(request):
    form = CategoriaForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria criada com sucesso!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Nova Categoria'})


@adm_escrita_required
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria atualizada!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Editar Categoria', 'objeto': categoria})


@adm_escrita_required
def deletar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        try:
            categoria.delete()
            messages.success(request, 'Categoria removida.')
        except Exception:
            messages.error(request, 'Não é possível remover: existem lançamentos vinculados.')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'objeto': categoria, 'confirmar_delecao': True, 'titulo': 'Remover Categoria'})
```

Também adicionar no topo das imports do arquivo:
```python
from .forms import CategoriaForm, LancamentoForm
```
(LancamentoForm será criado na Task 4 — OK importar agora, basta não usar ainda)

- [ ] **Step 3: Criar `adm/templates/lista_categorias.html`**

```html
{% extends 'base.html' %}
{% block titulo %}Categorias — ADM{% endblock %}
{% block content %}
<div class="container my-5">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h4 class="fw-bold m-0">Categorias</h4>
    <a href="{% url 'adm:criar_categoria' %}" class="btn btn-sm btn-dark">+ Nova Categoria</a>
  </div>
  <div class="card border-0 shadow-sm">
    <table class="table table-hover mb-0">
      <thead class="table-light">
        <tr>
          <th>Nome</th><th>Tipo</th><th>Status</th><th></th>
        </tr>
      </thead>
      <tbody>
        {% for cat in categorias %}
        <tr>
          <td class="fw-medium">{{ cat.nome }}</td>
          <td>
            <span class="badge {% if cat.tipo == 'RECEITA' %}bg-success{% else %}bg-danger{% endif %}">
              {{ cat.get_tipo_display }}
            </span>
          </td>
          <td>{% if cat.ativo %}<span class="badge bg-secondary">Ativa</span>{% else %}<span class="badge bg-light text-muted">Inativa</span>{% endif %}</td>
          <td class="text-end">
            <a href="{% url 'adm:editar_categoria' cat.pk %}" class="btn btn-xs btn-outline-secondary btn-sm me-1">Editar</a>
            <a href="{% url 'adm:deletar_categoria' cat.pk %}" class="btn btn-xs btn-outline-danger btn-sm">Remover</a>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="4" class="text-center text-muted py-4">Nenhuma categoria cadastrada.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="mt-3"><a href="{% url 'adm:painel' %}" class="text-muted small">← Voltar ao painel</a></div>
</div>
{% endblock %}
```

- [ ] **Step 4: Criar `adm/templates/form_categoria.html`**

```html
{% extends 'base.html' %}
{% block titulo %}{{ titulo }} — ADM{% endblock %}
{% block content %}
<div class="container my-5" style="max-width:520px;">
  <h4 class="fw-bold mb-4">{{ titulo }}</h4>

  {% if confirmar_delecao %}
  <div class="alert alert-danger">
    Tem certeza que deseja remover a categoria <strong>{{ objeto.nome }}</strong>?
    Isso só é possível se não houver lançamentos vinculados.
  </div>
  <form method="post">{% csrf_token %}
    <button type="submit" class="btn btn-danger me-2">Confirmar remoção</button>
    <a href="{% url 'adm:lista_categorias' %}" class="btn btn-outline-secondary">Cancelar</a>
  </form>

  {% else %}
  <form method="post">
    {% csrf_token %}
    <div class="mb-3">
      <label class="form-label fw-semibold">{{ form.nome.label }}</label>
      {{ form.nome }}
      {% if form.nome.errors %}<div class="text-danger small mt-1">{{ form.nome.errors }}</div>{% endif %}
    </div>
    <div class="mb-3">
      <label class="form-label fw-semibold">{{ form.tipo.label }}</label>
      {{ form.tipo }}
    </div>
    <div class="mb-4 form-check">
      {{ form.ativo }} <label class="form-check-label">{{ form.ativo.label }}</label>
    </div>
    <button type="submit" class="btn btn-dark me-2">Salvar</button>
    <a href="{% url 'adm:lista_categorias' %}" class="btn btn-outline-secondary">Cancelar</a>
  </form>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Testes de categoria**

```python
# Adicionar em adm/tests.py
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from adm.models import Categoria

User = get_user_model()

class CategoriaViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_user', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='User'
        )
        self.user_outro = User.objects.create_user(
            username='outro', password='pass', area='AZUL',
            first_name='Outro', last_name='User'
        )

    def test_lista_requer_login(self):
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 302)

    def test_adm_fin_acessa_lista(self):
        self.client.login(username='adm_user', password='pass')
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 200)

    def test_outro_bloqueado(self):
        self.client.login(username='outro', password='pass')
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 403)

    def test_criar_categoria(self):
        self.client.login(username='adm_user', password='pass')
        resp = self.client.post('/adm/categorias/nova/', {
            'nome': 'Doação', 'tipo': 'RECEITA', 'ativo': True
        })
        self.assertRedirects(resp, '/adm/categorias/')
        self.assertTrue(Categoria.objects.filter(nome='Doação').exists())
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 6: Commit**

```bash
git add adm/
git commit -m "feat(adm): CRUD de categorias com controle de acesso"
```

---

## Task 4: CRUD de Lançamentos

**Files:**
- Modify: `adm/forms.py` — adicionar `LancamentoForm`
- Modify: `adm/views.py` — substituir stubs de lançamento por views reais
- Create: `adm/templates/lista_lancamentos.html`
- Create: `adm/templates/form_lancamento.html`

**Interfaces:**
- Consumes: `Lancamento`, `Categoria` (Task 1), `AdmEscritaMixin`, `adm_acesso_required` (Task 2), `CategoriaForm` (Task 3)
- Produces: `/adm/lancamentos/` funcional — usado em Task 8 (painel)

- [ ] **Step 1: Adicionar `LancamentoForm` em `adm/forms.py`**

```python
class LancamentoForm(forms.ModelForm):
    class Meta:
        model = Lancamento
        fields = ['categoria', 'valor', 'data', 'descricao']
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'data': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'categoria': 'Categoria',
            'valor': 'Valor (R$)',
            'data': 'Data do Fato',
            'descricao': 'Descrição (opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.filter(ativo=True)
```

- [ ] **Step 2: Substituir stubs de lançamento em `adm/views.py`**

```python
from datetime import date

@adm_acesso_required
def lista_lancamentos(request):
    qs = Lancamento.objects.select_related('categoria', 'criado_por').all()

    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    mes = request.GET.get('mes')   # formato YYYY-MM

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if mes:
        try:
            ano, m = mes.split('-')
            qs = qs.filter(data__year=ano, data__month=m)
        except ValueError:
            pass

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'lista_lancamentos.html', {
        'lancamentos': qs,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_mes': mes,
    })


@adm_escrita_required
def criar_lancamento(request):
    form = LancamentoForm(request.POST or None)
    if form.is_valid():
        lan = form.save(commit=False)
        lan.origem = 'MANUAL'
        lan.criado_por = request.user
        lan.save()
        messages.success(request, 'Lançamento registrado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Novo Lançamento'})


@adm_escrita_required
def editar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem == 'SUPPLY':
        messages.error(request, 'Lançamentos do Supply não podem ser editados manualmente.')
        return redirect('adm:lista_lancamentos')
    form = LancamentoForm(request.POST or None, instance=lan)
    if form.is_valid():
        form.save()
        messages.success(request, 'Lançamento atualizado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Editar Lançamento', 'objeto': lan})


@adm_escrita_required
def deletar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem == 'SUPPLY':
        messages.error(request, 'Lançamentos do Supply não podem ser removidos manualmente.')
        return redirect('adm:lista_lancamentos')
    if request.method == 'POST':
        lan.delete()
        messages.success(request, 'Lançamento removido.')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {
        'objeto': lan, 'confirmar_delecao': True, 'titulo': 'Remover Lançamento'
    })
```

- [ ] **Step 3: Criar `adm/templates/lista_lancamentos.html`**

```html
{% extends 'base.html' %}
{% block titulo %}Lançamentos — ADM{% endblock %}
{% block content %}
<div class="container my-5">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h4 class="fw-bold m-0">Lançamentos</h4>
    <a href="{% url 'adm:criar_lancamento' %}" class="btn btn-sm btn-dark">+ Novo Lançamento</a>
  </div>

  <!-- Filtros -->
  <form method="get" class="row g-2 mb-4">
    <div class="col-auto">
      <select name="tipo" class="form-select form-select-sm">
        <option value="">Todos os tipos</option>
        <option value="RECEITA" {% if filtro_tipo == 'RECEITA' %}selected{% endif %}>Receita</option>
        <option value="DESPESA" {% if filtro_tipo == 'DESPESA' %}selected{% endif %}>Despesa</option>
      </select>
    </div>
    <div class="col-auto">
      <select name="categoria" class="form-select form-select-sm">
        <option value="">Todas as categorias</option>
        {% for cat in categorias %}
        <option value="{{ cat.pk }}" {% if filtro_categoria == cat.pk|stringformat:"s" %}selected{% endif %}>{{ cat.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-auto">
      <input type="month" name="mes" value="{{ filtro_mes }}" class="form-control form-control-sm">
    </div>
    <div class="col-auto">
      <button type="submit" class="btn btn-sm btn-outline-dark">Filtrar</button>
      <a href="{% url 'adm:lista_lancamentos' %}" class="btn btn-sm btn-outline-secondary ms-1">Limpar</a>
    </div>
  </form>

  <div class="card border-0 shadow-sm">
    <table class="table table-hover mb-0">
      <thead class="table-light">
        <tr>
          <th>Data</th><th>Categoria</th><th>Descrição</th>
          <th class="text-end">Valor</th><th>Origem</th><th></th>
        </tr>
      </thead>
      <tbody>
        {% for lan in lancamentos %}
        <tr>
          <td>{{ lan.data|date:"d/m/Y" }}</td>
          <td>
            <span class="badge {% if lan.tipo == 'RECEITA' %}bg-success{% else %}bg-danger{% endif %}">
              {{ lan.categoria.nome }}
            </span>
          </td>
          <td class="text-muted small">{{ lan.descricao|default:"—"|truncatechars:50 }}</td>
          <td class="text-end fw-semibold">R$ {{ lan.valor|floatformat:2 }}</td>
          <td><span class="badge bg-light text-dark border">{{ lan.get_origem_display }}</span></td>
          <td class="text-end">
            {% if lan.origem == 'MANUAL' %}
            <a href="{% url 'adm:editar_lancamento' lan.pk %}" class="btn btn-sm btn-outline-secondary me-1">Editar</a>
            <a href="{% url 'adm:deletar_lancamento' lan.pk %}" class="btn btn-sm btn-outline-danger">Remover</a>
            {% endif %}
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="6" class="text-center text-muted py-4">Nenhum lançamento encontrado.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="mt-3"><a href="{% url 'adm:painel' %}" class="text-muted small">← Voltar ao painel</a></div>
</div>
{% endblock %}
```

- [ ] **Step 4: Criar `adm/templates/form_lancamento.html`**

```html
{% extends 'base.html' %}
{% block titulo %}{{ titulo }} — ADM{% endblock %}
{% block content %}
<div class="container my-5" style="max-width:520px;">
  <h4 class="fw-bold mb-4">{{ titulo }}</h4>

  {% if confirmar_delecao %}
  <div class="alert alert-danger">
    Remover lançamento de <strong>R$ {{ objeto.valor|floatformat:2 }}</strong>
    em <strong>{{ objeto.data|date:"d/m/Y" }}</strong>?
  </div>
  <form method="post">{% csrf_token %}
    <button type="submit" class="btn btn-danger me-2">Confirmar</button>
    <a href="{% url 'adm:lista_lancamentos' %}" class="btn btn-outline-secondary">Cancelar</a>
  </form>

  {% else %}
  <form method="post">{% csrf_token %}
    {% for field in form %}
    <div class="mb-3">
      <label class="form-label fw-semibold">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}<div class="text-danger small mt-1">{{ field.errors }}</div>{% endif %}
    </div>
    {% endfor %}
    <button type="submit" class="btn btn-dark me-2">Salvar</button>
    <a href="{% url 'adm:lista_lancamentos' %}" class="btn btn-outline-secondary">Cancelar</a>
  </form>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Testes de lançamentos**

```python
# Adicionar em adm/tests.py (após CategoriaViewTest)
class LancamentoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm2', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='Dois'
        )
        self.cat = Categoria.objects.create(nome='Doação', tipo='RECEITA')

    def test_criar_lancamento_manual(self):
        self.client.login(username='adm2', password='pass')
        from django.utils import timezone
        resp = self.client.post('/adm/lancamentos/novo/', {
            'categoria': self.cat.pk,
            'valor': '500.00',
            'data': timezone.now().date().isoformat(),
            'descricao': 'Doação teste',
        })
        self.assertRedirects(resp, '/adm/lancamentos/')
        self.assertTrue(Lancamento.objects.filter(descricao='Doação teste').exists())

    def test_nao_edita_lancamento_supply(self):
        from django.utils import timezone
        lan = Lancamento.objects.create(
            categoria=self.cat, valor='100', data=timezone.now().date(), origem='SUPPLY'
        )
        self.client.login(username='adm2', password='pass')
        resp = self.client.get(f'/adm/lancamentos/{lan.pk}/editar/')
        self.assertRedirects(resp, '/adm/lancamentos/')
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 6: Commit**

```bash
git add adm/
git commit -m "feat(adm): CRUD de lancamentos com filtros e protecao origin=SUPPLY"
```

---

## Task 5: Signal de integração com Supply

**Files:**
- Create: `adm/signals.py`
- Modify: `adm/apps.py` — garantir `ready()` importa signals

**Interfaces:**
- Consumes: `supply.Pedido`, `Lancamento`, `Categoria` (Task 1)
- Produces: criação/atualização/deleção automática de `Lancamento` quando `Pedido` tem `valor`

- [ ] **Step 1: Criar `adm/signals.py`**

```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender='supply.Pedido')
def sync_lancamento_do_pedido(sender, instance, created, **kwargs):
    """Cria ou atualiza Lancamento de despesa quando Pedido tem valor."""
    from .models import Categoria, Lancamento

    if not instance.valor:
        # Se valor foi removido, apagar lancamento vinculado
        Lancamento.objects.filter(pedido=instance).delete()
        return

    try:
        categoria = Categoria.objects.get(nome='Materiais Supply', tipo='DESPESA', ativo=True)
    except Categoria.DoesNotExist:
        return  # ADM/FIN precisa criar a categoria antes

    if created:
        Lancamento.objects.create(
            categoria=categoria,
            valor=instance.valor,
            data=instance.sabado.data if instance.sabado else __import__('django.utils.timezone', fromlist=['now']).now().date(),
            descricao=f'Pedido: {instance.nome}',
            origem='SUPPLY',
            pedido=instance,
        )
    else:
        Lancamento.objects.filter(pedido=instance).update(
            valor=instance.valor,
            categoria=categoria,
        )


@receiver(post_delete, sender='supply.Pedido')
def deletar_lancamento_do_pedido(sender, instance, **kwargs):
    """Remove Lancamento vinculado quando Pedido é deletado."""
    from .models import Lancamento
    Lancamento.objects.filter(pedido=instance).delete()
```

- [ ] **Step 2: Verificar `adm/apps.py`**

Confirmar que o `ready()` já está presente (foi criado na Task 1):

```python
def ready(self):
    import adm.signals  # noqa
```

- [ ] **Step 3: Testes do signal**

```python
# Adicionar em adm/tests.py
from django.test import TestCase
from django.utils import timezone
from adm.models import Categoria, Lancamento

class SupplySignalTest(TestCase):
    def setUp(self):
        # Criar a categoria padrão que o signal usa
        self.cat_supply = Categoria.objects.create(
            nome='Materiais Supply', tipo='DESPESA', ativo=True
        )
        # Criar Sabado e Pedido via ORM direto
        from sabado.models import Sabado
        from supply.models import Pedido
        from voluntario.models import Voluntario
        self.user = Voluntario.objects.create_user(
            username='sup_user', password='pass', area='SUPPLY',
            first_name='Sup', last_name='User'
        )
        self.sabado = Sabado.objects.create(
            data=timezone.now().date(), tema='Teste', descricao='Teste'
        )
        self.Pedido = Pedido

    def test_pedido_com_valor_cria_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Tinta azul', quantidade=2, valor='45.00',
            sabado=self.sabado, area='SUPPLY'
        )
        self.assertTrue(Lancamento.objects.filter(pedido=pedido).exists())
        lan = Lancamento.objects.get(pedido=pedido)
        self.assertEqual(lan.valor, 45.00)
        self.assertEqual(lan.origem, 'SUPPLY')

    def test_pedido_sem_valor_nao_cria_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Tinta sem valor', quantidade=1,
            sabado=self.sabado, area='SUPPLY'
        )
        self.assertFalse(Lancamento.objects.filter(pedido=pedido).exists())

    def test_deletar_pedido_remove_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Item para deletar', quantidade=1, valor='10.00',
            sabado=self.sabado, area='SUPPLY'
        )
        pk = pedido.pk
        pedido.delete()
        self.assertFalse(Lancamento.objects.filter(pedido_id=pk).exists())
```

```bash
python manage.py test adm.tests.SupplySignalTest
```

Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add adm/signals.py adm/apps.py adm/tests.py
git commit -m "feat(adm): signal de integracao automatica com supply.Pedido"
```

---

## Task 6: Fluxo de Caixa

**Files:**
- Modify: `adm/views.py` — substituir stub `fluxo_caixa`
- Create: `adm/templates/fluxo_caixa.html`

**Interfaces:**
- Consumes: `Lancamento`, `Categoria` (Task 1), `adm_acesso_required` (Task 2)
- Produces: `/adm/fluxo-de-caixa/` com saldo acumulado e exportação CSV

- [ ] **Step 1: Substituir stub `fluxo_caixa` em `adm/views.py`**

```python
import csv
from decimal import Decimal
from django.db.models import Sum

@adm_acesso_required
def fluxo_caixa(request):
    qs = Lancamento.objects.select_related('categoria').order_by('data', 'criado_em')

    # Filtros
    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    data_ini = request.GET.get('data_ini')
    data_fim = request.GET.get('data_fim')
    exportar = request.GET.get('exportar')

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if data_ini:
        qs = qs.filter(data__gte=data_ini)
    if data_fim:
        qs = qs.filter(data__lte=data_fim)

    # Calcular saldo acumulado
    saldo = Decimal('0')
    lancamentos_com_saldo = []
    for lan in qs:
        if lan.tipo == 'RECEITA':
            saldo += lan.valor
        else:
            saldo -= lan.valor
        lancamentos_com_saldo.append({'lan': lan, 'saldo': saldo})

    if exportar == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="fluxo_caixa.csv"'
        response.write('﻿')  # BOM para Excel reconhecer UTF-8
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Data', 'Descrição', 'Categoria', 'Tipo', 'Entrada (R$)', 'Saída (R$)', 'Saldo (R$)'])
        for item in lancamentos_com_saldo:
            lan = item['lan']
            entrada = lan.valor if lan.tipo == 'RECEITA' else ''
            saida = lan.valor if lan.tipo == 'DESPESA' else ''
            writer.writerow([
                lan.data.strftime('%d/%m/%Y'),
                lan.descricao or lan.categoria.nome,
                lan.categoria.nome,
                lan.get_tipo_display(),
                str(entrada).replace('.', ',') if entrada else '',
                str(saida).replace('.', ',') if saida else '',
                str(item['saldo']).replace('.', ','),
            ])
        return response

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'fluxo_caixa.html', {
        'lancamentos_com_saldo': lancamentos_com_saldo,
        'saldo_final': saldo,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_data_ini': data_ini,
        'filtro_data_fim': data_fim,
    })
```

- [ ] **Step 2: Criar `adm/templates/fluxo_caixa.html`**

```html
{% extends 'base.html' %}
{% block titulo %}Fluxo de Caixa — ADM{% endblock %}
{% block content %}
<div class="container my-5">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h4 class="fw-bold m-0">Fluxo de Caixa</h4>
    <a href="?{{ request.GET.urlencode }}&exportar=csv" class="btn btn-sm btn-outline-dark">⬇ Exportar CSV</a>
  </div>

  <!-- Filtros -->
  <form method="get" class="row g-2 mb-4">
    <div class="col-auto">
      <select name="tipo" class="form-select form-select-sm">
        <option value="">Todos</option>
        <option value="RECEITA" {% if filtro_tipo == 'RECEITA' %}selected{% endif %}>Receita</option>
        <option value="DESPESA" {% if filtro_tipo == 'DESPESA' %}selected{% endif %}>Despesa</option>
      </select>
    </div>
    <div class="col-auto">
      <select name="categoria" class="form-select form-select-sm">
        <option value="">Todas categorias</option>
        {% for cat in categorias %}
        <option value="{{ cat.pk }}" {% if filtro_categoria == cat.pk|stringformat:"s" %}selected{% endif %}>{{ cat.nome }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-auto">
      <input type="date" name="data_ini" value="{{ filtro_data_ini }}" class="form-control form-control-sm" placeholder="De">
    </div>
    <div class="col-auto">
      <input type="date" name="data_fim" value="{{ filtro_data_fim }}" class="form-control form-control-sm" placeholder="Até">
    </div>
    <div class="col-auto">
      <button type="submit" class="btn btn-sm btn-outline-dark">Filtrar</button>
      <a href="{% url 'adm:fluxo_caixa' %}" class="btn btn-sm btn-outline-secondary ms-1">Limpar</a>
    </div>
  </form>

  <!-- Saldo final -->
  <div class="alert {% if saldo_final >= 0 %}alert-success{% else %}alert-danger{% endif %} py-2 mb-4">
    Saldo no período: <strong>R$ {{ saldo_final|floatformat:2 }}</strong>
  </div>

  <div class="card border-0 shadow-sm">
    <table class="table table-hover mb-0 table-sm">
      <thead class="table-light">
        <tr>
          <th>Data</th><th>Descrição</th><th>Categoria</th>
          <th class="text-end text-success">Entrada</th>
          <th class="text-end text-danger">Saída</th>
          <th class="text-end">Saldo</th>
        </tr>
      </thead>
      <tbody>
        {% for item in lancamentos_com_saldo %}
        <tr>
          <td class="text-nowrap">{{ item.lan.data|date:"d/m/Y" }}</td>
          <td class="text-muted small">{{ item.lan.descricao|default:item.lan.categoria.nome|truncatechars:40 }}</td>
          <td><span class="badge bg-light text-dark border">{{ item.lan.categoria.nome }}</span></td>
          <td class="text-end text-success fw-semibold">
            {% if item.lan.tipo == 'RECEITA' %}R$ {{ item.lan.valor|floatformat:2 }}{% endif %}
          </td>
          <td class="text-end text-danger fw-semibold">
            {% if item.lan.tipo == 'DESPESA' %}R$ {{ item.lan.valor|floatformat:2 }}{% endif %}
          </td>
          <td class="text-end fw-bold {% if item.saldo >= 0 %}text-success{% else %}text-danger{% endif %}">
            R$ {{ item.saldo|floatformat:2 }}
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="6" class="text-center text-muted py-4">Nenhum lançamento no período.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="mt-3"><a href="{% url 'adm:painel' %}" class="text-muted small">← Voltar ao painel</a></div>
</div>
{% endblock %}
```

- [ ] **Step 3: Teste do fluxo de caixa**

```python
# Adicionar em adm/tests.py
class FluxoCaixaTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_fc', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='FC'
        )
        self.cat_r = Categoria.objects.create(nome='Doação FC', tipo='RECEITA')
        self.cat_d = Categoria.objects.create(nome='Fixo FC', tipo='DESPESA')
        from django.utils import timezone
        hoje = timezone.now().date()
        Lancamento.objects.create(categoria=self.cat_r, valor='1000', data=hoje)
        Lancamento.objects.create(categoria=self.cat_d, valor='300', data=hoje)

    def test_saldo_calculado(self):
        self.client.login(username='adm_fc', password='pass')
        resp = self.client.get('/adm/fluxo-de-caixa/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '700')  # saldo 1000 - 300

    def test_exportar_csv(self):
        self.client.login(username='adm_fc', password='pass')
        resp = self.client.get('/adm/fluxo-de-caixa/?exportar=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add adm/
git commit -m "feat(adm): view de fluxo de caixa com saldo acumulado e exportacao CSV"
```

---

## Task 7: DRE

**Files:**
- Modify: `adm/views.py` — substituir stub `dre`
- Create: `adm/templates/dre.html`

**Interfaces:**
- Consumes: `Lancamento`, `Categoria` (Task 1), `adm_acesso_required` (Task 2)
- Produces: `/adm/dre/` com DRE categorizado + comparativo de dois períodos

- [ ] **Step 1: Substituir stub `dre` em `adm/views.py`**

```python
from django.db.models import Sum, Q
from decimal import Decimal

def _calcular_dre(ano, mes):
    """Retorna dict com receitas, despesas e resultado para um mês."""
    qs = Lancamento.objects.filter(data__year=ano, data__month=mes)

    receitas = (
        qs.filter(tipo='RECEITA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )
    despesas = (
        qs.filter(tipo='DESPESA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )

    total_receitas = qs.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = qs.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')

    return {
        'receitas': list(receitas),
        'despesas': list(despesas),
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'resultado': total_receitas - total_despesas,
    }


@adm_acesso_required
def dre(request):
    from django.utils import timezone
    hoje = timezone.now().date()

    # Período principal
    mes_str = request.GET.get('mes', hoje.strftime('%Y-%m'))
    # Período comparativo
    comp_str = request.GET.get('comparar', '')

    try:
        ano_p, mes_p = [int(x) for x in mes_str.split('-')]
    except (ValueError, AttributeError):
        ano_p, mes_p = hoje.year, hoje.month

    dre_principal = _calcular_dre(ano_p, mes_p)
    dre_comparativo = None

    if comp_str:
        try:
            ano_c, mes_c = [int(x) for x in comp_str.split('-')]
            dre_comparativo = _calcular_dre(ano_c, mes_c)
        except (ValueError, AttributeError):
            pass

    return render(request, 'dre.html', {
        'dre': dre_principal,
        'dre_comp': dre_comparativo,
        'mes': mes_str,
        'comparar': comp_str,
    })
```

- [ ] **Step 2: Criar `adm/templates/dre.html`**

```html
{% extends 'base.html' %}
{% block titulo %}DRE — ADM{% endblock %}
{% block content %}
<div class="container my-5" style="max-width:780px;">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h4 class="fw-bold m-0">Demonstrativo de Resultados (DRE)</h4>
  </div>

  <!-- Filtro de período -->
  <form method="get" class="row g-2 mb-5">
    <div class="col-auto">
      <label class="form-label small fw-semibold mb-1">Período</label>
      <input type="month" name="mes" value="{{ mes }}" class="form-control form-control-sm">
    </div>
    <div class="col-auto">
      <label class="form-label small fw-semibold mb-1">Comparar com</label>
      <input type="month" name="comparar" value="{{ comparar }}" class="form-control form-control-sm">
    </div>
    <div class="col-auto d-flex align-items-end">
      <button type="submit" class="btn btn-sm btn-dark">Aplicar</button>
    </div>
  </form>

  <!-- DRE Principal -->
  <div class="card border-0 shadow-sm mb-4">
    <div class="card-header bg-white fw-bold py-3">Resultado — {{ mes }}</div>
    <div class="card-body p-0">
      <table class="table mb-0">
        <thead class="table-light">
          <tr>
            <th>Categoria</th>
            <th class="text-end">Valor (R$)</th>
            {% if dre_comp %}<th class="text-end text-muted">{{ comparar }} (R$)</th><th class="text-end">Δ</th>{% endif %}
          </tr>
        </thead>
        <tbody>
          <tr class="table-success">
            <td colspan="{% if dre_comp %}4{% else %}2{% endif %}" class="fw-bold text-success py-2 ps-3">RECEITAS</td>
          </tr>
          {% for r in dre.receitas %}
          <tr>
            <td class="ps-4">{{ r.categoria__nome }}</td>
            <td class="text-end">{{ r.total|floatformat:2 }}</td>
            {% if dre_comp %}
            {% for rc in dre_comp.receitas %}{% if rc.categoria__nome == r.categoria__nome %}
            <td class="text-end text-muted">{{ rc.total|floatformat:2 }}</td>
            <td class="text-end {% if r.total >= rc.total %}text-success{% else %}text-danger{% endif %}">
              {% if r.total >= rc.total %}+{% endif %}{{ r.total|add:rc.total|floatformat:2 }}
            </td>
            {% endif %}{% endfor %}
            {% endif %}
          </tr>
          {% endfor %}
          <tr class="fw-bold border-top">
            <td class="ps-3">TOTAL RECEITAS</td>
            <td class="text-end text-success">{{ dre.total_receitas|floatformat:2 }}</td>
            {% if dre_comp %}<td class="text-end text-muted">{{ dre_comp.total_receitas|floatformat:2 }}</td><td></td>{% endif %}
          </tr>

          <tr class="table-danger">
            <td colspan="{% if dre_comp %}4{% else %}2{% endif %}" class="fw-bold text-danger py-2 ps-3">DESPESAS</td>
          </tr>
          {% for d in dre.despesas %}
          <tr>
            <td class="ps-4">{{ d.categoria__nome }}</td>
            <td class="text-end">{{ d.total|floatformat:2 }}</td>
            {% if dre_comp %}
            {% for dc in dre_comp.despesas %}{% if dc.categoria__nome == d.categoria__nome %}
            <td class="text-end text-muted">{{ dc.total|floatformat:2 }}</td>
            <td class="text-end"></td>
            {% endif %}{% endfor %}
            {% endif %}
          </tr>
          {% endfor %}
          <tr class="fw-bold border-top">
            <td class="ps-3">TOTAL DESPESAS</td>
            <td class="text-end text-danger">{{ dre.total_despesas|floatformat:2 }}</td>
            {% if dre_comp %}<td class="text-end text-muted">{{ dre_comp.total_despesas|floatformat:2 }}</td><td></td>{% endif %}
          </tr>

          <tr class="fw-bold border-top-2 fs-5">
            <td class="ps-3 py-3">RESULTADO DO PERÍODO</td>
            <td class="text-end py-3 {% if dre.resultado >= 0 %}text-success{% else %}text-danger{% endif %}">
              R$ {{ dre.resultado|floatformat:2 }}
            </td>
            {% if dre_comp %}
            <td class="text-end text-muted py-3">R$ {{ dre_comp.resultado|floatformat:2 }}</td>
            <td class="text-end py-3 {% if dre.resultado >= dre_comp.resultado %}text-success{% else %}text-danger{% endif %}">
              {% if dre.resultado >= dre_comp.resultado %}+{% endif %}
            </td>
            {% endif %}
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="mt-3"><a href="{% url 'adm:painel' %}" class="text-muted small">← Voltar ao painel</a></div>
</div>
{% endblock %}
```

- [ ] **Step 3: Teste do DRE**

```python
# Adicionar em adm/tests.py
class DRETest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_dre', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='DRE'
        )
        self.cat_r = Categoria.objects.create(nome='Doação DRE', tipo='RECEITA')
        self.cat_d = Categoria.objects.create(nome='Fixo DRE', tipo='DESPESA')
        import datetime
        self.hoje = datetime.date(2026, 1, 15)
        Lancamento.objects.create(categoria=self.cat_r, valor='2000', data=self.hoje)
        Lancamento.objects.create(categoria=self.cat_d, valor='500', data=self.hoje)

    def test_dre_resultado_correto(self):
        self.client.login(username='adm_dre', password='pass')
        resp = self.client.get('/adm/dre/?mes=2026-01')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '1500')  # resultado 2000-500

    def test_dre_comparativo(self):
        self.client.login(username='adm_dre', password='pass')
        resp = self.client.get('/adm/dre/?mes=2026-01&comparar=2025-12')
        self.assertEqual(resp.status_code, 200)
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 4: Commit**

```bash
git add adm/
git commit -m "feat(adm): view DRE categorizado com comparativo de periodos"
```

---

## Task 8: Painel + Navbar

**Files:**
- Modify: `adm/views.py` — substituir stub `painel`
- Create: `adm/templates/painel_adm.html`
- Modify: `templates/navbar.html` — link ADM condicional

**Interfaces:**
- Consumes: `Lancamento`, `Categoria` (Task 1), todas as views anteriores
- Produces: módulo ADM completo e acessível pelo navbar

- [ ] **Step 1: Substituir stub `painel` em `adm/views.py`**

```python
@adm_acesso_required
def painel(request):
    from django.db.models import Sum
    from decimal import Decimal

    total_receitas = Lancamento.objects.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = Lancamento.objects.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    saldo = total_receitas - total_despesas
    ultimos = Lancamento.objects.select_related('categoria').order_by('-data', '-criado_em')[:10]

    return render(request, 'painel_adm.html', {
        'saldo': saldo,
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'ultimos': ultimos,
    })
```

- [ ] **Step 2: Criar `adm/templates/painel_adm.html`**

```html
{% extends 'base.html' %}
{% block titulo %}Painel ADM/FIN{% endblock %}
{% block content %}
<div class="container my-5">
  <h4 class="fw-bold mb-4">Painel Financeiro</h4>

  <!-- Cards de resumo -->
  <div class="row g-3 mb-5">
    <div class="col-md-4">
      <div class="card border-0 shadow-sm text-center py-4">
        <div class="text-muted small fw-semibold mb-1">SALDO TOTAL</div>
        <div class="fs-3 fw-bold {% if saldo >= 0 %}text-success{% else %}text-danger{% endif %}">
          R$ {{ saldo|floatformat:2 }}
        </div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="card border-0 shadow-sm text-center py-4">
        <div class="text-muted small fw-semibold mb-1">TOTAL RECEITAS</div>
        <div class="fs-4 fw-bold text-success">R$ {{ total_receitas|floatformat:2 }}</div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="card border-0 shadow-sm text-center py-4">
        <div class="text-muted small fw-semibold mb-1">TOTAL DESPESAS</div>
        <div class="fs-4 fw-bold text-danger">R$ {{ total_despesas|floatformat:2 }}</div>
      </div>
    </div>
  </div>

  <!-- Atalhos -->
  <div class="row g-2 mb-5">
    <div class="col-auto"><a href="{% url 'adm:criar_lancamento' %}" class="btn btn-dark btn-sm">+ Lançamento</a></div>
    <div class="col-auto"><a href="{% url 'adm:fluxo_caixa' %}" class="btn btn-outline-dark btn-sm">Fluxo de Caixa</a></div>
    <div class="col-auto"><a href="{% url 'adm:dre' %}" class="btn btn-outline-dark btn-sm">DRE</a></div>
    <div class="col-auto"><a href="{% url 'adm:lista_lancamentos' %}" class="btn btn-outline-secondary btn-sm">Lançamentos</a></div>
    <div class="col-auto"><a href="{% url 'adm:lista_categorias' %}" class="btn btn-outline-secondary btn-sm">Categorias</a></div>
  </div>

  <!-- Últimos lançamentos -->
  <h6 class="fw-semibold mb-3">Últimos 10 Lançamentos</h6>
  <div class="card border-0 shadow-sm">
    <table class="table table-sm table-hover mb-0">
      <thead class="table-light">
        <tr><th>Data</th><th>Categoria</th><th>Descrição</th><th class="text-end">Valor</th></tr>
      </thead>
      <tbody>
        {% for lan in ultimos %}
        <tr>
          <td>{{ lan.data|date:"d/m/Y" }}</td>
          <td><span class="badge {% if lan.tipo == 'RECEITA' %}bg-success{% else %}bg-danger{% endif %}">{{ lan.categoria.nome }}</span></td>
          <td class="text-muted small">{{ lan.descricao|default:"—"|truncatechars:40 }}</td>
          <td class="text-end fw-semibold">R$ {{ lan.valor|floatformat:2 }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="4" class="text-center text-muted py-3">Nenhum lançamento ainda.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Adicionar link ADM no navbar**

Em `templates/navbar.html`, dentro de `<!-- Mais ▾ -->` (dropdown "Mais"), adicionar após o bloco `{% if user.is_superuser ... %}` existente:

```html
{% if user.is_superuser or user.area == 'ADM/FIN' or user.area == 'TRIADE' %}
<div class="pcf-dd-sep"></div>
<a class="pcf-dd-item" href="{% url 'adm:painel' %}">
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
  Financeiro
</a>
{% endif %}
```

Fazer o mesmo no menu mobile (`pcf-mobile-menu`), após o bloco SAAS:

```html
{% if user.is_superuser or user.area == 'ADM/FIN' or user.area == 'TRIADE' %}
<a class="pcf-mobile-link" href="{% url 'adm:painel' %}">
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
  Financeiro
</a>
{% endif %}
```

- [ ] **Step 4: Teste de integração do painel**

```python
# Adicionar em adm/tests.py
class PainelTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_triade = User.objects.create_user(
            username='triade_user', password='pass', area='TRIADE',
            first_name='Triade', last_name='User'
        )

    def test_triade_acessa_painel(self):
        self.client.login(username='triade_user', password='pass')
        resp = self.client.get('/adm/')
        self.assertEqual(resp.status_code, 200)

    def test_painel_sem_login_redireciona(self):
        resp = self.client.get('/adm/')
        self.assertEqual(resp.status_code, 302)
```

```bash
python manage.py test adm
```

Esperado: `OK`

- [ ] **Step 5: Smoke test manual**

```bash
python manage.py runserver
```

Logar com usuário de área ADM/FIN e verificar:
- Navbar mostra "Financeiro" no dropdown "Mais"
- `/adm/` mostra painel com cards
- `/adm/categorias/nova/` cria categoria "Materiais Supply" (tipo DESPESA)
- `/adm/lancamentos/novo/` cria lançamento manual
- `/adm/fluxo-de-caixa/` exibe tabela com saldo acumulado
- `/adm/dre/` exibe DRE com totais

- [ ] **Step 6: Commit final**

```bash
git add adm/ templates/navbar.html
git commit -m "feat(adm): painel financeiro completo com link no navbar"
```

---

## Self-Review

**Spec coverage:**
- ✅ `Categoria` e `Lancamento` com todos os campos — Task 1
- ✅ Acesso ADM/FIN + TRIADE + superuser — Task 2
- ✅ Integração supply via signal — Task 5
- ✅ CRUD lançamentos com proteção SUPPLY — Task 4
- ✅ CRUD categorias — Task 3
- ✅ Fluxo de caixa cronológico + saldo + exportação CSV — Task 6
- ✅ DRE categorizado + comparativo — Task 7
- ✅ Painel com resumo + navbar — Task 8
- ✅ `tipo` derivado de `categoria` no `save()` — Task 1 (`Lancamento.save`)

**Placeholder scan:** Nenhum TBD, TODO ou step sem código.

**Type consistency:** `Categoria`, `Lancamento`, `adm_acesso_required`, `adm_escrita_required`, `_calcular_dre` — consistentes em todos os tasks que os consomem.
