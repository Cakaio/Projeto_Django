from django.db import models
from django.utils import timezone

TIPO_CHOICES = (
    ('RECEITA', 'Receita'),
    ('DESPESA', 'Despesa'),
)

ORIGEM_CHOICES = (
    ('MANUAL', 'Manual'),
    ('SUPPLY', 'Supply'),
    ('REEMBOLSO', 'Reembolso'),
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
