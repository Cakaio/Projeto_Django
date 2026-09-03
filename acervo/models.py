"""Acervo: a memória documental do projeto.

Nasce com uma coleção — os documentos das postulações passadas, de quem foi
eleito e de quem não foi — mas a estrutura é genérica de propósito. Acervo que
só serve para uma coisa vira gambiarra na primeira vez que alguém quiser
guardar outra.

Sobre acesso: ler é liberado para qualquer voluntário logado (decisão da
liderança). "Logado" não é "público": os arquivos vivem em MEDIA_ROOT e são
entregues pela view `midia` de TESTE/views.py, que exige sessão em tudo que não
está nas duas pastas públicas. Um documento de postulação não abre por link
solto nem cai em buscador.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

RESULTADO_POSTULACAO = (
    ('ELEITO', 'Eleito'),
    ('NAO_ELEITO', 'Não eleito'),
)


def caminho_do_documento(instancia, nome_do_arquivo):
    """Guarda separado por coleção, para o disco não virar uma pasta só.

    O prefixo `acervo/` é o que faz a view `midia` exigir login — ele não está
    entre as pastas públicas. Mudar esse prefixo abre o acervo para a internet.
    """
    pasta = instancia.colecao.slug if instancia.colecao_id else 'sem-colecao'
    return f'acervo/{pasta}/{nome_do_arquivo}'


class Colecao(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True,
                            help_text='Deixe vazio para gerar a partir do nome.')
    descricao = models.TextField('descrição', blank=True,
                                 help_text='O que entra nesta coleção, e o que não entra.')
    ordem = models.PositiveSmallIntegerField(default=0,
                                             help_text='Menor aparece primeiro.')
    ativo = models.BooleanField(default=True,
                                help_text='Desmarque para esconder a coleção sem apagar nada.')
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['ordem', 'nome']
        verbose_name = 'coleção'
        verbose_name_plural = 'coleções'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)[:80]
        super().save(*args, **kwargs)

    @property
    def total_documentos(self):
        return self.documentos.count()


class Documento(models.Model):
    colecao = models.ForeignKey(Colecao, on_delete=models.PROTECT,
                                related_name='documentos', verbose_name='coleção')
    titulo = models.CharField('título', max_length=160)
    arquivo = models.FileField(upload_to=caminho_do_documento)
    ano = models.PositiveSmallIntegerField(
        help_text='Ano a que o documento se refere — o da postulação, não o do upload.')

    # Duas formas de dizer de quem é o documento. A ficha vale mais que o
    # texto: quem está cadastrado vira link para o perfil. Mas postulação de
    # 2019 pode ser de gente que nunca teve login, e exigir ficha deixaria
    # esse documento fora do acervo.
    pessoa = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='documentos_no_acervo',
                               help_text='Quem o documento se refere, se estiver cadastrado.')
    nome_avulso = models.CharField('nome', max_length=120, blank=True,
                                   help_text='Use quando a pessoa não tem ficha no sistema.')

    cargo_pretendido = models.CharField(max_length=100, blank=True,
                                        help_text='Ex.: Presidente, LEG, Líder de Sala Azul.')
    resultado = models.CharField(max_length=12, choices=RESULTADO_POSTULACAO, blank=True,
                                 help_text='Em branco quando não se aplica à coleção.')
    descricao = models.TextField('descrição', blank=True)

    enviado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='documentos_enviados')
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        # Mais recente primeiro: acervo se consulta a partir do que acabou de
        # acontecer, e é a postulação do ano passado que alguém vai querer ver.
        ordering = ['-ano', 'titulo']
        verbose_name = 'documento'
        verbose_name_plural = 'documentos'

    def __str__(self):
        return f'{self.titulo} ({self.ano})'

    def clean(self):
        super().clean()
        if not self.pessoa_id and not self.nome_avulso.strip():
            raise ValidationError({
                'nome_avulso': 'Diga de quem é o documento: escolha a ficha ou digite o nome.',
            })

    @property
    def de_quem(self):
        """Nome a mostrar. Ficha primeiro; nome digitado como reserva."""
        if self.pessoa_id:
            return self.pessoa.get_full_name() or self.pessoa.username
        return self.nome_avulso or '—'

    @property
    def extensao(self):
        """Só o sufixo, em maiúsculas, para o selo do arquivo na lista."""
        nome = (self.arquivo.name or '').rsplit('.', 1)
        return nome[-1].upper() if len(nome) == 2 else 'ARQUIVO'
