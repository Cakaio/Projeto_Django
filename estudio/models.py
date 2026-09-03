"""Estúdio: editor de página com posicionamento livre.

Existe porque a revistinha não é texto formatado. Olhando a edição de março:
painéis coloridos de recorte irregular, nome da sala em arco rotacionado, foto
com moldura da cor da salinha, faixa de mãozinhas sangrando na borda, capa em
full-bleed. Editor de texto rico não chega nesse layout — posicionamento livre
não é luxo aqui, é requisito.

É um app à parte, e não um pedaço da revista, porque a mesma ferramenta serve
Ata, cartaz e o que mais aparecer. Uma revista PODE apontar para um documento
daqui, mas o documento existe sozinho.

DECISÃO DE SEGURANÇA: elemento de texto guarda TEXTO PURO, nunca HTML. A
formatação mora em `estilo`, um dicionário de propriedades conhecidas que o
template aplica uma a uma. Guardar HTML de editor rico e devolvê-lo na página
seria XSS clássico — e a alternativa (sanitizar) é uma dependência nova e uma
lista de permissões para manter errando. Como cada bloco desta revista tem
formatação uniforme, texto puro + estilo por bloco cobre o caso sem abrir a
porta.
"""
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

TIPOS_DE_DOCUMENTO = (
    ('REVISTA', 'Revistinha'),
    ('ATA', 'Ata'),
    ('CARTAZ', 'Cartaz'),
    ('OUTRO', 'Outro'),
)

TIPOS_DE_ELEMENTO = (
    ('TEXTO', 'Texto'),
    ('IMAGEM', 'Imagem'),
    ('FORMA', 'Forma'),
)

FORMAS = (
    ('retangulo', 'Retângulo'),
    ('elipse', 'Elipse'),
    ('linha', 'Linha'),
)

# A4 a 96 dpi. A página é uma tela de tamanho FIXO e as coordenadas são px
# dentro dela; a tela do editor e a impressão só aplicam escala. Guardar
# porcentagem pareceria mais responsivo, mas texto não escala junto com a
# caixa e o layout quebraria justamente no que importa: o PDF.
LARGURA_A4 = 794
ALTURA_A4 = 1123

# Chaves que o template sabe aplicar. Estilo que chega com chave fora desta
# lista é descartado no clean() — é o que impede alguém de injetar CSS
# arbitrário (`background: url(javascript:...)`) por dentro do JSON.
ESTILOS_ACEITOS = {
    'cor', 'fundo', 'fonte', 'tamanho', 'peso', 'alinhamento', 'entrelinha',
    'borda_cor', 'borda_largura', 'raio', 'sombra', 'opacidade', 'forma',
    'ajuste', 'letra_espaco', 'maiusculas', 'contorno_cor', 'contorno_largura',
}


# ── Estilo -> CSS ────────────────────────────────────────────────────────────
# Cada valor é conferido antes de virar CSS. Estilo chega de requisição, e
# `color: {valor}` com valor "red;background:url(...)" é injeção de CSS na
# página publicada: dá para desenhar botão falso em cima do conteúdo. Por isso
# cor casa com padrão, número é número e opção vem de lista fechada.
_COR = re.compile(r'^#[0-9a-fA-F]{3,8}$|^rgba?\([\d\s.,%]+\)$|^transparent$')

FONTES = {
    # A display imita o título da revista impressa; a de corpo é a do sistema.
    'display': "'Trebuchet MS', 'Segoe UI', Verdana, sans-serif",
    'corpo': "'Segoe UI', system-ui, -apple-system, sans-serif",
    'serif': "Georgia, 'Times New Roman', serif",
    'mono': "'Consolas', 'Courier New', monospace",
}
ALINHAMENTOS = {'left', 'center', 'right', 'justify'}
AJUSTES = {'cover', 'contain', 'fill', 'none'}


def _cor(valor):
    valor = str(valor).strip()
    return valor if _COR.match(valor) else None


def _numero(valor, minimo, maximo):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if numero != numero:          # NaN não compara e passaria pelos limites
        return None
    return max(minimo, min(maximo, numero))


class Documento(models.Model):
    titulo = models.CharField('título', max_length=140)
    tipo = models.CharField(max_length=10, choices=TIPOS_DE_DOCUMENTO, default='OUTRO')
    largura = models.PositiveIntegerField(default=LARGURA_A4)
    altura = models.PositiveIntegerField(default=ALTURA_A4)
    revista = models.OneToOneField('revista.Revista', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='documento',
                                   help_text='Preenchido quando o documento é o layout de uma revista.')
    criado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='documentos_estudio')
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-atualizado_em']
        verbose_name = 'documento'
        verbose_name_plural = 'documentos'

    def __str__(self):
        return self.titulo

    @property
    def total_paginas(self):
        return self.paginas.count()


class Pagina(models.Model):
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name='paginas')
    ordem = models.PositiveSmallIntegerField(default=0)
    cor_de_fundo = models.CharField(max_length=20, default='#ffffff')
    # De qual preset a página nasceu. Guardado só para a tela saber dizer
    # "página de salinha" — o preset não amarra nada depois de aplicado.
    preset = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ['ordem', 'pk']
        verbose_name = 'página'
        verbose_name_plural = 'páginas'

    def __str__(self):
        return f'{self.documento.titulo} — página {self.ordem + 1}'

    @property
    def css_de_fundo(self):
        """Cor da folha, conferida antes de virar CSS.

        O valor chega do editor por requisição. Solto num atributo `style`,
        "#fff;background:url(...)" viraria CSS arbitrário na página publicada.
        Cor que não casa com o padrão vira branco.
        """
        return _cor(self.cor_de_fundo) or '#ffffff'


class Elemento(models.Model):
    pagina = models.ForeignKey(Pagina, on_delete=models.CASCADE, related_name='elementos')
    tipo = models.CharField(max_length=8, choices=TIPOS_DE_ELEMENTO)

    # Coordenadas em px dentro da página. Podem ser negativas de propósito: é
    # assim que a faixa de mãozinhas e a foto de capa sangram para fora da
    # borda, como no PDF.
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    largura = models.PositiveIntegerField(default=200)
    altura = models.PositiveIntegerField(default=80)
    rotacao = models.SmallIntegerField('rotação', default=0)
    z = models.SmallIntegerField('camada', default=0)

    texto = models.TextField(blank=True)
    imagem = models.ForeignKey('Asset', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='usos')
    estilo = models.JSONField(default=dict, blank=True)
    travado = models.BooleanField('travado', default=False,
                                  help_text='Elemento travado não se arrasta por acidente.')

    class Meta:
        ordering = ['z', 'pk']
        verbose_name = 'elemento'
        verbose_name_plural = 'elementos'

    def __str__(self):
        return f'{self.get_tipo_display()} em {self.pagina}'

    def clean(self):
        super().clean()
        if not isinstance(self.estilo, dict):
            raise ValidationError({'estilo': 'O estilo precisa ser um objeto.'})
        # Chave desconhecida sai em silêncio: o editor manda o que sabe, e
        # deixar passar seria a porta para CSS arbitrário na página publicada.
        self.estilo = {k: v for k, v in self.estilo.items() if k in ESTILOS_ACEITOS}
        if self.tipo == 'IMAGEM' and not self.imagem_id:
            raise ValidationError({'imagem': 'Elemento de imagem precisa de um arquivo.'})

    @property
    def css_de_estilo(self):
        """Estilo do elemento em CSS, com todo valor já conferido.

        Chave que o `clean()` não conhece nunca chega aqui; valor que não passa
        na conferência é ignorado em silêncio, e o elemento sai com a
        aparência padrão em vez de quebrar a página.
        """
        e = self.estilo if isinstance(self.estilo, dict) else {}
        partes = []

        def cor(chave, propriedade):
            valor = _cor(e.get(chave, ''))
            if valor:
                partes.append(f'{propriedade}:{valor}')

        def numero(chave, propriedade, minimo, maximo, sufixo='px'):
            valor = _numero(e.get(chave), minimo, maximo)
            if valor is not None:
                texto = f'{valor:g}'
                partes.append(f'{propriedade}:{texto}{sufixo}')

        cor('cor', 'color')
        cor('fundo', 'background')
        cor('borda_cor', '--borda-cor')

        fonte = FONTES.get(str(e.get('fonte', '')))
        if fonte:
            partes.append(f'font-family:{fonte}')

        numero('tamanho', 'font-size', 4, 400)
        numero('raio', 'border-radius', 0, 999)
        numero('letra_espaco', 'letter-spacing', -10, 40)
        numero('entrelinha', 'line-height', 0.6, 4, sufixo='')
        numero('opacidade', 'opacity', 0, 1, sufixo='')

        peso = _numero(e.get('peso'), 100, 900)
        if peso is not None:
            partes.append(f'font-weight:{int(peso // 100) * 100}')

        if e.get('alinhamento') in ALINHAMENTOS:
            partes.append(f"text-align:{e['alinhamento']}")
        if e.get('ajuste') in AJUSTES:
            partes.append(f"object-fit:{e['ajuste']}")
        if e.get('maiusculas'):
            partes.append('text-transform:uppercase')

        largura_borda = _numero(e.get('borda_largura'), 0, 40)
        cor_borda = _cor(e.get('borda_cor', ''))
        if largura_borda and cor_borda:
            partes.append(f'border:{largura_borda:g}px solid {cor_borda}')

        # Contorno de texto: é o que dá o título laranja com borda branca da
        # revista impressa. `paint-order` põe o traço atrás do preenchimento,
        # senão o contorno come o miolo da letra.
        largura_contorno = _numero(e.get('contorno_largura'), 0, 12)
        cor_contorno = _cor(e.get('contorno_cor', ''))
        if largura_contorno and cor_contorno:
            partes.append(f'-webkit-text-stroke:{largura_contorno:g}px {cor_contorno}')
            partes.append('paint-order:stroke fill')

        if e.get('forma') == 'elipse':
            partes.append('border-radius:50%')

        if e.get('sombra'):
            partes.append('box-shadow:0 2px 10px rgba(0,0,0,.18)')

        return ';'.join(partes)

    @property
    def css_de_caixa(self):
        """Posição e tamanho. Só números — nada daqui vem de texto do usuário."""
        partes = [
            f'left:{self.x}px', f'top:{self.y}px',
            f'width:{self.largura}px', f'height:{self.altura}px',
            f'z-index:{self.z}',
        ]
        if self.rotacao:
            partes.append(f'transform:rotate({self.rotacao}deg)')
        return ';'.join(partes)


class Asset(models.Model):
    """Imagem reutilizável: foto, faixa de mãozinhas, nome de sala em arco.

    Vive separado do elemento porque a mesma arte entra em toda página e em
    toda edição. Subir a faixa de mãozinhas dez vezes seria dez arquivos no
    disco e dez lugares para trocar quando a arte mudar.
    """
    CATEGORIAS = (
        ('FOTO', 'Foto'),
        ('DECORACAO', 'Decoração'),
        ('LOGO', 'Logo'),
    )

    nome = models.CharField(max_length=120)
    categoria = models.CharField(max_length=10, choices=CATEGORIAS, default='FOTO')
    arquivo = models.ImageField(upload_to='estudio/assets')
    # Slug opcional: é assim que um preset acha a arte certa sem depender de
    # PK ("a faixa de mãozinhas" em vez de "o asset 47").
    apelido = models.SlugField(max_length=60, blank=True, unique=True, null=True,
                               help_text='Para os presets acharem esta arte. Ex.: maozinhas-topo.')
    enviado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assets_enviados')
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['categoria', 'nome']
        verbose_name = 'asset'
        verbose_name_plural = 'assets'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # SlugField unique com string vazia colidiria no segundo asset sem
        # apelido; None não colide.
        if not self.apelido:
            self.apelido = None
        super().save(*args, **kwargs)
