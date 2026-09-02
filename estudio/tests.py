"""Testes do estúdio.

As views que renderizam página são chamadas direto pelo RequestFactory, sem
`self.client`: o test client copia o contexto do template e essa cópia quebra
no Python 3.14 (o Django 4.2 só suporta até o 3.12). Chamando a view direto, os
templates DE VERDADE são exercitados.

O bloco que mais importa aqui é o de injeção. O estúdio guarda estilo vindo de
requisição e o devolve dentro de atributo `style` — se o valor não fosse
conferido, qualquer pessoa com acesso ao editor escreveria CSS arbitrário na
página que vai para o doador.
"""
import json
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from revista.models import Revista, SecaoRevista
from voluntario.models import Voluntario

from . import presets, views
from .models import (ALTURA_A4, LARGURA_A4, Asset, Documento, Elemento,
                     Pagina)


def imagem(nome='arte.png'):
    # PNG 1x1 de verdade: ImageField roda o Pillow e recusa bytes falsos.
    dados = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
             b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
             b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
    return SimpleUploadedFile(nome, dados, content_type='image/png')


class EstiloEmCssTests(TestCase):
    """Todo valor de estilo é conferido antes de virar CSS."""

    def setUp(self):
        self.documento = Documento.objects.create(titulo='Doc')
        self.pagina = Pagina.objects.create(documento=self.documento)

    def elemento(self, estilo):
        return Elemento(pagina=self.pagina, tipo='TEXTO', texto='oi', estilo=estilo)

    def test_cor_valida_entra(self):
        self.assertIn('color:#f5a623', self.elemento({'cor': '#f5a623'}).css_de_estilo)

    def test_cor_com_ponto_e_virgula_nao_entra(self):
        """`color: red;background:url(...)` seria CSS arbitrário na página."""
        css = self.elemento({'cor': 'red;background:url(http://x/y.png)'}).css_de_estilo
        self.assertNotIn('url(', css)
        self.assertNotIn('background', css)

    def test_nome_de_cor_solto_nao_entra(self):
        """Só padrão conhecido passa: hex, rgb/rgba e transparent."""
        self.assertEqual(self.elemento({'cor': 'red'}).css_de_estilo, '')

    def test_expressao_em_numero_nao_entra(self):
        css = self.elemento({'tamanho': '16px;position:fixed;top:0'}).css_de_estilo
        self.assertNotIn('position', css)
        self.assertNotIn('fixed', css)

    def test_numero_fora_da_faixa_e_preso(self):
        """Fonte de 9000px cobriria a página inteira de uma letra."""
        self.assertIn('font-size:400px', self.elemento({'tamanho': 9000}).css_de_estilo)

    def test_nan_nao_vira_css(self):
        self.assertEqual(self.elemento({'tamanho': 'NaN'}).css_de_estilo, '')

    def test_alinhamento_fora_da_lista_nao_entra(self):
        self.assertEqual(self.elemento({'alinhamento': 'end;color:red'}).css_de_estilo, '')

    def test_fonte_desconhecida_nao_entra(self):
        self.assertEqual(self.elemento({'fonte': 'Comic Sans'}).css_de_estilo, '')

    def test_contorno_precisa_de_cor_e_espessura(self):
        so_cor = self.elemento({'contorno_cor': '#ffffff'}).css_de_estilo
        self.assertNotIn('text-stroke', so_cor)
        completo = self.elemento({'contorno_cor': '#ffffff',
                                  'contorno_largura': 2}).css_de_estilo
        self.assertIn('-webkit-text-stroke:2px #ffffff', completo)
        # paint-order põe o traço atrás do preenchimento; sem ele o contorno
        # come o miolo da letra e o título fica ilegível.
        self.assertIn('paint-order:stroke fill', completo)

    def test_chave_desconhecida_nao_chega_a_ser_gravada(self):
        el = self.elemento({'cor': '#000000', 'position': 'fixed', 'onload': 'x'})
        el.clean()
        self.assertEqual(set(el.estilo), {'cor'})


class FundoDaPaginaTests(TestCase):
    def test_cor_de_fundo_conferida(self):
        documento = Documento.objects.create(titulo='Doc')
        pagina = Pagina.objects.create(
            documento=documento, cor_de_fundo='#fff;background:url(http://x)')
        self.assertEqual(pagina.css_de_fundo, '#ffffff')

    def test_cor_de_fundo_valida_passa(self):
        documento = Documento.objects.create(titulo='Doc')
        pagina = Pagina.objects.create(documento=documento, cor_de_fundo='#cfe8f5')
        self.assertEqual(pagina.css_de_fundo, '#cfe8f5')


class SalvarPaginaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.usuario = Voluntario.objects.create_user(
            username='ze', password='x', area='MARKETING')
        cls.documento = Documento.objects.create(titulo='Doc')
        cls.pagina = Pagina.objects.create(documento=cls.documento)
        cls.asset = Asset.objects.create(nome='Foto', arquivo=imagem())

    def salvar(self, carga, usuario=None):
        fabrica = RequestFactory()
        rota = reverse('estudio:salvar_pagina',
                       args=[self.documento.pk, self.pagina.pk])
        pedido = fabrica.post(rota, data=json.dumps(carga),
                              content_type='application/json')
        pedido.user = usuario or self.usuario
        return views.salvar_pagina(pedido, pk=self.documento.pk,
                                   pagina_pk=self.pagina.pk)

    def test_grava_elemento_de_texto(self):
        resposta = self.salvar({'elementos': [
            {'tipo': 'TEXTO', 'texto': 'Oi', 'x': 10, 'y': 20,
             'largura': 100, 'altura': 40, 'estilo': {'cor': '#000000'}},
        ]})
        self.assertEqual(resposta.status_code, 200)
        el = self.pagina.elementos.get()
        self.assertEqual((el.texto, el.x, el.y), ('Oi', 10, 20))

    def test_coordenada_absurda_e_presa(self):
        """Sem trava, uma página de 2 milhões de px derrubaria o navegador de
        quem abrisse depois."""
        self.salvar({'elementos': [
            {'tipo': 'TEXTO', 'texto': 'x', 'x': 99999999, 'largura': 99999999},
        ]})
        el = self.pagina.elementos.get()
        self.assertLessEqual(el.x, views.LIMITE_COORDENADA)
        self.assertLessEqual(el.largura, views.LIMITE_TAMANHO)

    def test_coordenada_negativa_e_mantida(self):
        """Negativo não é erro: é assim que a faixa de mãozinhas e a foto de
        capa sangram para fora da borda, como na revista impressa."""
        self.salvar({'elementos': [
            {'tipo': 'IMAGEM', 'imagem': self.asset.pk, 'x': -20, 'y': -10,
             'largura': LARGURA_A4 + 40, 'altura': 90},
        ]})
        el = self.pagina.elementos.get()
        self.assertEqual((el.x, el.y), (-20, -10))

    def test_texto_nao_numerico_em_coordenada_nao_estoura(self):
        resposta = self.salvar({'elementos': [
            {'tipo': 'TEXTO', 'texto': 'x', 'x': 'abc', 'largura': None},
        ]})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.pagina.elementos.get().x, 0)

    def test_tipo_desconhecido_e_ignorado(self):
        self.salvar({'elementos': [{'tipo': 'SCRIPT', 'texto': 'x'}]})
        self.assertEqual(self.pagina.elementos.count(), 0)

    def test_imagem_sem_arquivo_e_ignorada(self):
        """Elemento de imagem sem asset não é elemento, é buraco na página."""
        self.salvar({'elementos': [{'tipo': 'IMAGEM', 'imagem': 999999}]})
        self.assertEqual(self.pagina.elementos.count(), 0)

    def test_json_invalido_devolve_400_e_nao_apaga_nada(self):
        Elemento.objects.create(pagina=self.pagina, tipo='TEXTO', texto='antigo')
        fabrica = RequestFactory()
        pedido = fabrica.post('/x/', data='{isso nao e json',
                              content_type='application/json')
        pedido.user = self.usuario
        resposta = views.salvar_pagina(pedido, pk=self.documento.pk,
                                       pagina_pk=self.pagina.pk)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(self.pagina.elementos.count(), 1)

    def test_salvar_substitui_a_pagina_inteira(self):
        Elemento.objects.create(pagina=self.pagina, tipo='TEXTO', texto='velho')
        self.salvar({'elementos': [{'tipo': 'TEXTO', 'texto': 'novo'}]})
        self.assertEqual([e.texto for e in self.pagina.elementos.all()], ['novo'])

    def test_estilo_com_chave_estranha_e_limpo_ao_gravar(self):
        self.salvar({'elementos': [
            {'tipo': 'TEXTO', 'texto': 'x',
             'estilo': {'cor': '#111111', 'position': 'fixed'}},
        ]})
        self.assertEqual(set(self.pagina.elementos.get().estilo), {'cor'})


class PermissaoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.comum = Voluntario.objects.create_user(
            username='comum', password='x', area='VIOLETA')
        cls.crre = Voluntario.objects.create_user(
            username='crre', password='x', area='CR/RE')
        cls.revista = Revista.objects.create(
            titulo='Edição 25', periodo_inicio=date(2026, 3, 1),
            periodo_fim=date(2026, 3, 31))
        cls.solto = Documento.objects.create(titulo='Ata de reunião', tipo='ATA')
        Pagina.objects.create(documento=cls.solto)
        cls.da_revista = Documento.objects.create(
            titulo='Layout', tipo='REVISTA', revista=cls.revista)
        Pagina.objects.create(documento=cls.da_revista)

    def abrir(self, documento, usuario):
        fabrica = RequestFactory()
        pedido = fabrica.get(reverse('estudio:editor', args=[documento.pk]))
        pedido.user = usuario
        return views.editor(pedido, pk=documento.pk)

    def test_qualquer_voluntario_edita_ata(self):
        """Ata é do projeto inteiro, não de uma área."""
        self.assertEqual(self.abrir(self.solto, self.comum).status_code, 200)

    def test_documento_de_revista_e_do_crre(self):
        """Mexer nele é mexer no que vai para o doador."""
        with self.assertRaises(PermissionDenied):
            self.abrir(self.da_revista, self.comum)

    def test_crre_edita_documento_de_revista(self):
        self.assertEqual(self.abrir(self.da_revista, self.crre).status_code, 200)


class PresetsTests(TestCase):

    def setUp(self):
        self.documento = Documento.objects.create(titulo='Doc')
        self.pagina = Pagina.objects.create(documento=self.documento)

    def test_preset_de_salinha_monta_a_pagina(self):
        criados = presets.aplicar(self.pagina, 'salinha', sala='AZUL',
                                  texto='Foi um mês bom.')
        self.assertGreater(criados, 0)
        self.pagina.refresh_from_db()
        self.assertEqual(self.pagina.preset, 'salinha')
        textos = [e.texto for e in self.pagina.elementos.filter(tipo='TEXTO')]
        self.assertIn('Foi um mês bom.', textos)

    def test_preset_usa_a_cor_da_sala(self):
        presets.aplicar(self.pagina, 'salinha', sala='AZUL')
        claro, _ = presets.CORES_DAS_SALAS['AZUL']
        fundos = [e.estilo.get('fundo') for e in self.pagina.elementos.all()]
        self.assertIn(claro, fundos)

    def test_preset_sem_a_arte_do_canva_nao_quebra(self):
        """As faixas e os nomes em arco são desenhos do Canva. Enquanto não
        forem subidos, a página nasce sem eles e o resto fica no lugar."""
        self.assertEqual(Asset.objects.count(), 0)
        criados = presets.aplicar(self.pagina, 'capa', titulo='REVISTA PCF')
        self.assertGreater(criados, 0)

    def test_preset_usa_a_arte_quando_ela_existe(self):
        Asset.objects.create(nome='Mãozinhas', apelido='maozinhas-topo',
                             categoria='DECORACAO', arquivo=imagem())
        presets.aplicar(self.pagina, 'capa', titulo='REVISTA PCF')
        self.assertTrue(self.pagina.elementos.filter(tipo='IMAGEM').exists())

    def test_faixa_sangra_para_fora_da_folha(self):
        """A faixa tem que ser maior que a página, senão sobra tarja branca."""
        Asset.objects.create(nome='Mãozinhas', apelido='maozinhas-topo',
                             categoria='DECORACAO', arquivo=imagem())
        presets.aplicar(self.pagina, 'capa')
        faixa = self.pagina.elementos.filter(tipo='IMAGEM').first()
        self.assertLess(faixa.x, 0)
        self.assertGreater(faixa.largura, LARGURA_A4)

    def test_preset_inexistente_nao_cria_nada(self):
        self.assertEqual(presets.aplicar(self.pagina, 'nao-existe'), 0)


class GerarDaRevistaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.crre = Voluntario.objects.create_user(
            username='crre', password='x', area='CR/RE')
        cls.comum = Voluntario.objects.create_user(
            username='comum', password='x', area='VIOLETA')
        cls.revista = Revista.objects.create(
            titulo='Edição 25', subtitulo='Março de 2026',
            periodo_inicio=date(2026, 3, 1), periodo_fim=date(2026, 3, 31))
        for indice, sala in enumerate(['VIOLETA', 'ANIL', 'AZUL']):
            SecaoRevista.objects.create(
                revista=cls.revista, sala=sala, titulo=f'Sala {sala}',
                texto=f'Resumo do {sala}.', ordem=indice, incluir=True)

    def gerar(self, usuario):
        fabrica = RequestFactory()
        rota = reverse('estudio:gerar_da_revista', args=[self.revista.pk])
        pedido = fabrica.post(rota)
        pedido.user = usuario
        from django.contrib.messages.storage.fallback import FallbackStorage
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        return views.gerar_da_revista(pedido, revista_pk=self.revista.pk)

    def test_monta_capa_sumario_salinhas_e_contracapa(self):
        self.gerar(self.crre)
        documento = Documento.objects.get(revista=self.revista)
        presets_usados = list(documento.paginas.values_list('preset', flat=True))
        self.assertEqual(presets_usados,
                         ['capa', 'sumario', 'salinha', 'salinha', 'salinha', 'contracapa'])

    def test_o_texto_do_semanario_chega_na_pagina(self):
        """O conteúdo continua nascendo dos semanários — é o ponto da revista."""
        self.gerar(self.crre)
        documento = Documento.objects.get(revista=self.revista)
        todos = [e.texto for p in documento.paginas.all() for e in p.elementos.all()]
        self.assertIn('Resumo do ANIL.', todos)

    def test_a_foto_alterna_de_lado_entre_salinhas(self):
        """É o que dá ritmo à página quando três salinhas se empilham."""
        self.gerar(self.crre)
        documento = Documento.objects.get(revista=self.revista)
        salinhas = documento.paginas.filter(preset='salinha')
        xs = []
        for pagina in salinhas:
            forma = pagina.elementos.filter(tipo='FORMA', z=15).first()
            xs.append(forma.x)
        self.assertNotEqual(xs[0], xs[1])

    def test_nao_gera_duas_vezes(self):
        self.gerar(self.crre)
        self.gerar(self.crre)
        self.assertEqual(Documento.objects.filter(revista=self.revista).count(), 1)

    def test_voluntario_de_fora_nao_gera(self):
        with self.assertRaises(PermissionDenied):
            self.gerar(self.comum)


class TelasTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.usuario = Voluntario.objects.create_superuser(
            username='chefe', password='x', email='c@pcf.org')
        cls.documento = Documento.objects.create(titulo='Ata de agosto', tipo='ATA')
        pagina = Pagina.objects.create(documento=cls.documento)
        Elemento.objects.create(pagina=pagina, tipo='TEXTO', texto='Pauta um',
                                estilo={'cor': '#123456', 'tamanho': 18})

    def abrir(self, nome, **kwargs):
        fabrica = RequestFactory()
        pedido = fabrica.get(reverse(f'estudio:{nome}', kwargs=kwargs))
        pedido.user = self.usuario
        return getattr(views, nome)(pedido, **kwargs).content.decode()

    def test_lista_mostra_o_documento(self):
        self.assertIn('Ata de agosto', self.abrir('lista'))

    def test_editor_entrega_o_estado_em_json_script(self):
        html = self.abrir('editor', pk=self.documento.pk)
        self.assertIn('id="estudio-estado"', html)
        self.assertIn('estudio-estado', html)

    def test_visualizacao_desenha_o_texto_e_o_estilo(self):
        html = self.abrir('ver', pk=self.documento.pk)
        self.assertIn('Pauta um', html)
        self.assertIn('color:#123456', html)

    def test_impressao_nao_traz_a_interface_do_sistema(self):
        """A tela de impressão não estende base.html: a barra lateral do
        sistema no papel arruinaria a revista."""
        html = self.abrir('imprimir', pk=self.documento.pk)
        self.assertIn('Pauta um', html)
        self.assertNotIn('pcf-navitem', html)
        self.assertIn('@page', html)

    def test_texto_do_usuario_sai_escapado(self):
        """Elemento guarda TEXTO PURO. Se um dia entrar HTML, ele aparece como
        texto na página, não como marcação."""
        pagina = self.documento.paginas.first()
        Elemento.objects.create(pagina=pagina, tipo='TEXTO',
                                texto='<script>alert(1)</script>')
        html = self.abrir('ver', pk=self.documento.pk)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)


class ElementoValidacaoTests(TestCase):

    def test_imagem_sem_asset_nao_valida(self):
        documento = Documento.objects.create(titulo='Doc')
        pagina = Pagina.objects.create(documento=documento)
        with self.assertRaises(ValidationError):
            Elemento(pagina=pagina, tipo='IMAGEM').clean()

    def test_estilo_que_nao_e_objeto_nao_valida(self):
        documento = Documento.objects.create(titulo='Doc')
        pagina = Pagina.objects.create(documento=documento)
        with self.assertRaises(ValidationError):
            Elemento(pagina=pagina, tipo='TEXTO', estilo=['nao', 'e', 'dict']).clean()


class AssetTests(TestCase):
    def test_dois_assets_sem_apelido_convivem(self):
        """`SlugField(unique=True, blank=True)` deixa gravar '' e o segundo
        colidiria por unicidade — por isso vazio vira None."""
        Asset.objects.create(nome='A', arquivo=imagem('a.png'))
        Asset.objects.create(nome='B', arquivo=imagem('b.png'))
        self.assertEqual(Asset.objects.filter(apelido__isnull=True).count(), 2)
