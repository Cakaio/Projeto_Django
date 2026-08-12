import secrets
from django.db import models
from django.urls import reverse
from django.utils import timezone

STATUS_REVISTA = (('RASCUNHO', 'Rascunho'), ('PUBLICADA', 'Publicada'))


class Revista(models.Model):
    """Uma edição da revistinha. O conteúdo nasce montado dos semanários do
    período e depois é editado à mão pelo CR — por isso as seções são gravadas
    (snapshot), e não lidas do semanário na hora de exibir: se alguém editar o
    semanário meses depois, a edição já enviada ao doador não muda."""
    titulo = models.CharField('título', max_length=120)
    subtitulo = models.CharField('subtítulo', max_length=200, blank=True)
    periodo_inicio = models.DateField('início do período')
    periodo_fim = models.DateField('fim do período')
    texto_abertura = models.TextField('carta de abertura', blank=True)
    texto_fechamento = models.TextField('fechamento', blank=True)
    mostrar_numeros = models.BooleanField('mostrar os números do período', default=True)
    mostrar_financeiro = models.BooleanField('mostrar onde o dinheiro foi aplicado', default=True)
    status = models.CharField(max_length=10, choices=STATUS_REVISTA, default='RASCUNHO')
    token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
    link_publico_ativo = models.BooleanField('link público ativo', default=False)
    link_expira_em = models.DateField('link expira em', null=True, blank=True)
    atividades_descartadas = models.JSONField(
        default=list, blank=True,
        help_text='Atividades que o CR tirou desta edição. Guardadas para que '
                  '"remontar do semanário" não traga de volta o que ele já recusou.')
    criado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='revistas')
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-periodo_fim', '-criado_em']
        verbose_name = 'revista'
        verbose_name_plural = 'revistas'

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.token:
            # Link público é para o doador abrir sem login: precisa ser
            # impossível de adivinhar, não sequencial.
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def link_publico_valido(self):
        """O link só vale se estiver ligado E dentro da validade. Quem publica
        pode revogar a qualquer momento — há fotos de crianças aqui dentro."""
        if not self.link_publico_ativo:
            return False
        if self.link_expira_em and self.link_expira_em < timezone.localdate():
            return False
        return True

    def get_absolute_url(self):
        return reverse('revista:ver', args=[self.pk])

    @property
    def secoes_incluidas(self):
        return self.secoes.filter(incluir=True)


class SecaoRevista(models.Model):
    """Um destaque da revista — em geral uma atividade do semanário, já com o
    texto solto para o CR reescrever numa linguagem de doador."""
    revista = models.ForeignKey(Revista, on_delete=models.CASCADE, related_name='secoes')
    atividade = models.ForeignKey('semanario.Atividade', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='secoes_revista')
    sabado = models.ForeignKey('sabado.Sabado', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='secoes_revista')
    sala = models.CharField(max_length=20, blank=True)
    titulo = models.CharField('título', max_length=140)
    texto = models.TextField(blank=True)
    competencia = models.CharField('competência', max_length=120, blank=True)
    foto_propria = models.ImageField('foto', upload_to='revista', blank=True, null=True)
    ordem = models.PositiveIntegerField(default=0)
    incluir = models.BooleanField('incluir na revista', default=True)

    class Meta:
        ordering = ['ordem', 'pk']
        verbose_name = 'seção da revista'
        verbose_name_plural = 'seções da revista'

    def __str__(self):
        return self.titulo

    @property
    def foto(self):
        """Foto própria manda; senão, a da atividade do semanário."""
        if self.foto_propria:
            return self.foto_propria
        if self.atividade and self.atividade.fotos:
            return self.atividade.fotos
        return None
