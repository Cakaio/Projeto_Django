"""Testes do backlog de Projetos.

Observação sobre RequestFactory: as views que RENDERIZAM página são chamadas
direto, sem `self.client`. O test client do Django copia o contexto do template
(`store_rendered_templates`), e essa cópia quebra no Python 3.14 — o Django 4.2
só suporta até o 3.12. É falha do ambiente, não do app. Para redirect e 404,
que não renderizam nada, `self.client` funciona.

Os templates de verdade são escritos à parte, então as views rodam contra um
jogo de templates de mentira (`TEMPLATES_DE_TESTE`): o que está sob teste aqui é
permissão, contexto e regra de negócio — não o HTML.
"""
from datetime import timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from projetos import servicos, views
from projetos.forms import DemandaForm
from projetos.models import Demanda, RegistroDemanda
from voluntario.models import LISTA_AREAS, Voluntario

TEMPLATES_DE_TESTE = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': False,
    'OPTIONS': {
        'context_processors': [],
        'loaders': [('django.template.loaders.locmem.Loader', {
            'projetos/backlog.html':
                'total={{ total }}|abertas={{ abertas }}|travadas={{ travadas }}|'
                'esperando={{ esperando }}|entregues={{ entregues }}|'
                '{% for d in demandas %}[{{ d.titulo }}]{% endfor %}',
            'projetos/por_area.html':
                'areas={{ total_areas }}|sem_contato={{ areas_sem_contato }}|'
                'travadas={{ areas_travadas }}|'
                '{% for l in panorama %}[{{ l.area }}:{{ l.total }}]{% endfor %}',
            'projetos/ficha.html':
                'ficha={{ demanda.titulo }}|dias={{ dias_parada }}|'
                'travada={{ travada }}|registros={{ registros|length }}',
            'projetos/form.html': 'form|{{ form.errors|length }}',
            'projetos/confirmar_exclusao.html':
                'apagar|demanda={{ demanda.titulo }}|registro={{ registro.pk|default:"" }}',
        })],
    },
}]


def criar_voluntario(username, area='RECREACAO', superuser=False):
    """`area` é obrigatória no model. O padrão RECREACAO é de propósito: uma
    área SEM poder nenhum aqui, para provar que o acesso veio de onde
    esperamos (PROJETOS, TRIADE ou is_superuser) e não da área."""
    return Voluntario.objects.create_user(
        username=username, password='senha-de-teste',
        first_name=username.capitalize(), area=area, is_superuser=superuser,
    )


def requisicao(metodo, rota, usuario, dados=None):
    """Requisição pronta para chamar a view direto, com mensagens ligadas
    (as views usam `messages`, que exige o middleware que o factory não tem)."""
    fabrica = RequestFactory()
    pedido = getattr(fabrica, metodo)(rota, dados or {})
    pedido.user = usuario
    pedido.session = {}
    setattr(pedido, '_messages', FallbackStorage(pedido))
    return pedido


def criar_demanda(**campos):
    campos.setdefault('titulo', 'Tela de presença')
    campos.setdefault('area', 'MARKETING')
    return Demanda.objects.create(**campos)


def envelhecer(demanda, dias):
    """Empurra a criação para trás no tempo.

    `criado_em` tem default, então não adianta passar no create: só um update
    escapa do valor calculado na hora de gravar.
    """
    Demanda.objects.filter(pk=demanda.pk).update(
        criado_em=timezone.now() - timedelta(days=dias))
    demanda.refresh_from_db()
    return demanda


# ────────────────────────────── Permissão ──────────────────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class PermissaoTests(TestCase):
    """O backlog é do time de Projetos, da Tríade e do superusuário — e de mais
    ninguém: ele registra conversa interna com cada área."""

    @classmethod
    def setUpTestData(cls):
        cls.projetos = criar_voluntario('ana', area='PROJETOS')
        cls.triade = criar_voluntario('tri', area='TRIADE')
        cls.admin = criar_voluntario('root', superuser=True)
        cls.comum = criar_voluntario('zeca', area='RECREACAO')
        cls.demanda = criar_demanda()

    def telas(self):
        return [
            (reverse('projetos:backlog'), views.backlog, {}),
            (reverse('projetos:por_area'), views.por_area, {}),
            (reverse('projetos:criar'), views.criar, {}),
            (reverse('projetos:ficha', args=[self.demanda.pk]), views.ficha,
             {'pk': self.demanda.pk}),
            (reverse('projetos:editar', args=[self.demanda.pk]), views.editar,
             {'pk': self.demanda.pk}),
        ]

    def test_projetos_tem_acesso(self):
        for rota, view, kwargs in self.telas():
            resposta = view(requisicao('get', rota, self.projetos), **kwargs)
            self.assertEqual(resposta.status_code, 200, rota)

    def test_triade_e_superuser_tem_acesso(self):
        for usuario in (self.triade, self.admin):
            for rota, view, kwargs in self.telas():
                resposta = view(requisicao('get', rota, usuario), **kwargs)
                self.assertEqual(resposta.status_code, 200, f'{rota} / {usuario}')

    def test_voluntario_de_outra_area_recebe_403(self):
        for rota, view, kwargs in self.telas():
            with self.assertRaises(PermissionDenied, msg=rota):
                view(requisicao('get', rota, self.comum), **kwargs)

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse('projetos:backlog'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)


# ─────────────────────── Dias parada / travada ───────────────────────
class SituacaoDaDemandaTests(TestCase):
    """`dias_parada` é o número que denuncia o que está no vácuo. Errar nele é
    cobrar a área errada."""

    def test_sem_registro_conta_desde_a_criacao(self):
        demanda = envelhecer(criar_demanda(), 10)
        self.assertEqual(demanda.dias_parada, 10)

    def test_com_registro_conta_desde_o_ultimo(self):
        demanda = envelhecer(criar_demanda(), 40)
        RegistroDemanda.objects.create(
            demanda=demanda, tipo='CONVERSA', descricao='Falei com a líder',
            data=timezone.localdate() - timedelta(days=30))
        RegistroDemanda.objects.create(
            demanda=demanda, tipo='COBRANCA', descricao='Cobrei de novo',
            data=timezone.localdate() - timedelta(days=3))
        # Vale o registro mais recente, não o primeiro nem o último inserido.
        self.assertEqual(demanda.dias_parada, 3)

    def test_travada_quando_aberta_esperando_e_parada(self):
        demanda = envelhecer(
            criar_demanda(status='ESPERANDO_AREA', retorno='AGUARDANDO'), 20)
        self.assertTrue(demanda.travada)

    def test_quinze_dias_trava_e_quatorze_nao(self):
        """A régua é "mais de 14 dias" — o limite exato ainda não é vácuo."""
        no_limite = envelhecer(
            criar_demanda(status='FAZENDO', retorno='AGUARDANDO'), 14)
        passou = envelhecer(
            criar_demanda(status='FAZENDO', retorno='AGUARDANDO'), 15)
        self.assertFalse(no_limite.travada)
        self.assertTrue(passou.travada)

    def test_entregue_nunca_esta_travada(self):
        """Demanda fechada parada há meses é normal — é o fim da vida dela."""
        demanda = envelhecer(
            criar_demanda(status='ENTREGUE', retorno='AGUARDANDO'), 90)
        self.assertFalse(demanda.travada)

    def test_quem_respondeu_nao_esta_travada(self):
        demanda = envelhecer(
            criar_demanda(status='FAZENDO', retorno='RESPONDEU'), 90)
        self.assertFalse(demanda.travada)

    def test_nao_responde_tambem_trava(self):
        """Área marcada como "não responde" é o caso mais grave, não o menos."""
        demanda = envelhecer(
            criar_demanda(status='ESPERANDO_AREA', retorno='NAO_RESPONDE'), 60)
        self.assertTrue(demanda.travada)

    def test_registro_novo_zera_o_relogio(self):
        demanda = envelhecer(
            criar_demanda(status='ESPERANDO_AREA', retorno='AGUARDANDO'), 60)
        self.assertTrue(demanda.travada)
        RegistroDemanda.objects.create(demanda=demanda, tipo='COBRANCA',
                                       descricao='Cobrei hoje')
        self.assertEqual(demanda.dias_parada, 0)
        self.assertFalse(demanda.travada)


# ────────────────────────────── Panorama ──────────────────────────────
class PanoramaPorAreaTests(TestCase):
    """A tabela que responde "quem está me deixando no vácuo"."""

    def linha(self, panorama, area):
        return next(l for l in panorama if l['area'] == area)

    def test_area_sem_demanda_nenhuma_aparece(self):
        """São justamente as que ninguém procurou: sumir com elas esconderia o
        problema que a tela existe para mostrar."""
        criar_demanda(area='MARKETING')
        panorama = servicos.panorama_por_area()

        self.assertEqual(len(panorama), len(LISTA_AREAS))
        supply = self.linha(panorama, 'SUPPLY')
        self.assertEqual(supply['total'], 0)
        self.assertTrue(supply['sem_contato'])
        self.assertIsNone(supply['ultimo_contato'])
        self.assertIsNone(supply['dias_sem_contato'])

    def test_conta_abertas_entregues_e_travadas(self):
        criar_demanda(area='EVENTOS', status='FAZENDO')
        criar_demanda(area='EVENTOS', status='ENTREGUE')
        envelhecer(criar_demanda(area='EVENTOS', status='ESPERANDO_AREA',
                                 retorno='AGUARDANDO'), 30)

        eventos = self.linha(servicos.panorama_por_area(), 'EVENTOS')
        self.assertEqual(eventos['total'], 3)
        self.assertEqual(eventos['abertas'], 2)
        self.assertEqual(eventos['entregues'], 1)
        self.assertEqual(eventos['travadas'], 1)
        self.assertEqual(eventos['nome'], dict(LISTA_AREAS)['EVENTOS'])

    def test_ultimo_contato_ignora_anotacao_interna(self):
        """Anotação é conversa nossa. Se contasse como contato, bastaria
        escrever um lembrete para a área sair da lista de quem sumiu."""
        demanda = criar_demanda(area='ADM/FIN', retorno='AGUARDANDO')
        RegistroDemanda.objects.create(
            demanda=demanda, tipo='CONVERSA', descricao='Falei com o líder',
            data=timezone.localdate() - timedelta(days=20))
        RegistroDemanda.objects.create(
            demanda=demanda, tipo='NOTA', descricao='Lembrar de cobrar',
            data=timezone.localdate())

        linha = self.linha(servicos.panorama_por_area(), 'ADM/FIN')
        self.assertEqual(linha['ultimo_contato'],
                         timezone.localdate() - timedelta(days=20))
        self.assertEqual(linha['dias_sem_contato'], 20)
        self.assertFalse(linha['sem_contato'])

    def test_demanda_criada_e_nunca_procurada_continua_sem_contato(self):
        criar_demanda(area='SUPPLY')      # nasce em SEM_CONTATO
        linha = self.linha(servicos.panorama_por_area(), 'SUPPLY')
        self.assertEqual(linha['total'], 1)
        self.assertTrue(linha['sem_contato'])

    def test_ordena_da_mais_parada_para_a_mais_ativa(self):
        envelhecer(criar_demanda(area='EVENTOS', status='ESPERANDO_AREA',
                                 retorno='AGUARDANDO'), 40)          # travada
        ativa = criar_demanda(area='MARKETING', status='FAZENDO', retorno='RESPONDEU')
        RegistroDemanda.objects.create(demanda=ativa, tipo='RETORNO',
                                       descricao='Responderam hoje')

        panorama = servicos.panorama_por_area()
        posicao = {l['area']: i for i, l in enumerate(panorama)}
        # Travada primeiro, quem nunca foi procurado no meio, ativa por último.
        self.assertEqual(panorama[0]['area'], 'EVENTOS')
        self.assertEqual(panorama[-1]['area'], 'MARKETING')
        self.assertLess(posicao['SUPPLY'], posicao['MARKETING'])

    def test_nao_consulta_o_banco_dentro_do_laco(self):
        """São 17 áreas e o backlog só cresce: uma consulta por linha viraria
        dezenas a cada abertura da tela."""
        for i in range(12):
            area = LISTA_AREAS[i % len(LISTA_AREAS)][0]
            demanda = criar_demanda(area=area, titulo=f'Demanda {i}')
            RegistroDemanda.objects.create(demanda=demanda, tipo='CONVERSA',
                                           descricao='Conversamos')

        with self.assertNumQueries(2):    # demandas + resumo do histórico
            servicos.panorama_por_area()


# ─────────────────── Coerência histórico × retorno ───────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class RegistroNaFichaTests(TestCase):
    """O histórico e o status não podem contar histórias diferentes: é o status
    que vira número na tela e cobrança na reunião."""

    @classmethod
    def setUpTestData(cls):
        cls.projetos = criar_voluntario('ana', area='PROJETOS')

    def registrar(self, demanda, tipo, descricao='algo aconteceu'):
        rota = reverse('projetos:ficha', args=[demanda.pk])
        resposta = views.ficha(
            requisicao('post', rota, self.projetos,
                       {'data': timezone.localdate().isoformat(),
                        'tipo': tipo, 'descricao': descricao}),
            pk=demanda.pk)
        demanda.refresh_from_db()
        return resposta

    def test_retorno_marca_a_demanda_como_respondeu(self):
        demanda = criar_demanda(retorno='AGUARDANDO')
        resposta = self.registrar(demanda, 'RETORNO', 'A líder respondeu no grupo')

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(demanda.retorno, 'RESPONDEU')

    def test_retorno_resgata_ate_quem_estava_como_nao_responde(self):
        demanda = criar_demanda(retorno='NAO_RESPONDE')
        self.registrar(demanda, 'RETORNO')
        self.assertEqual(demanda.retorno, 'RESPONDEU')

    def test_conversa_tira_de_sem_contato(self):
        demanda = criar_demanda(retorno='SEM_CONTATO')
        self.registrar(demanda, 'CONVERSA', 'Chamei no grupo da área')
        self.assertEqual(demanda.retorno, 'AGUARDANDO')

    def test_cobranca_tambem_tira_de_sem_contato(self):
        demanda = criar_demanda(retorno='SEM_CONTATO')
        self.registrar(demanda, 'COBRANCA')
        self.assertEqual(demanda.retorno, 'AGUARDANDO')

    def test_cobranca_nao_rebaixa_quem_ja_respondeu(self):
        """Cobrar não desfaz resposta: só quem estava em "ainda não procuramos"
        muda de casa."""
        for atual in ('RESPONDEU', 'NAO_RESPONDE'):
            with self.subTest(retorno=atual):
                demanda = criar_demanda(retorno=atual)
                self.registrar(demanda, 'COBRANCA')
                self.assertEqual(demanda.retorno, atual)

    def test_anotacao_nao_mexe_no_retorno(self):
        demanda = criar_demanda(retorno='SEM_CONTATO')
        self.registrar(demanda, 'NOTA', 'Ideia: reaproveitar a tela do supply')
        self.assertEqual(demanda.retorno, 'SEM_CONTATO')

    def test_autor_sai_do_usuario_logado_e_nao_do_formulario(self):
        demanda = criar_demanda()
        self.registrar(demanda, 'NOTA', 'primeira anotação')
        registro = RegistroDemanda.objects.get()
        self.assertEqual(registro.autor, self.projetos)
        self.assertEqual(registro.demanda, demanda)

    def test_criado_por_sai_do_usuario_logado(self):
        rota = reverse('projetos:criar')
        resposta = views.criar(requisicao('post', rota, self.projetos, {
            'titulo': 'Painel de presença do Marketing', 'area': 'MARKETING',
            'o_que_pediram': '', 'o_que_fizemos': '', 'status': 'IDEIA',
            'retorno': 'SEM_CONTATO', 'prioridade': 'MEDIA',
            'responsavel': '', 'contato_na_area': '', 'entregue_em': '',
        }))

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Demanda.objects.get().criado_por, self.projetos)


# ─────────────────────── Filtros do backlog ───────────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class BacklogTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.projetos = criar_voluntario('ana', area='PROJETOS')
        cls.outra = criar_voluntario('bia', area='PROJETOS')
        cls.entregue = criar_demanda(
            titulo='Revistinha do doador', area='CR/RE', status='ENTREGUE',
            retorno='RESPONDEU', responsavel=cls.projetos,
            o_que_fizemos='Página pública com o token do doador')
        cls.travada = envelhecer(criar_demanda(
            titulo='Enquete do sábado', area='EVENTOS', status='ESPERANDO_AREA',
            retorno='AGUARDANDO', responsavel=cls.outra,
            o_que_pediram='Queriam saber quem não respondeu'), 30)
        cls.nova = criar_demanda(
            titulo='Inventário do supply', area='SUPPLY', status='IDEIA')

    def abrir(self, **filtros):
        pedido = requisicao('get', reverse('projetos:backlog'), self.projetos, filtros)
        return views.backlog(pedido).content.decode()

    def test_sem_filtro_traz_tudo_e_conta_os_kpis(self):
        html = self.abrir()
        self.assertIn('total=3', html)
        self.assertIn('abertas=2', html)
        self.assertIn('travadas=1', html)
        self.assertIn('entregues=1', html)
        self.assertIn('[Enquete do sábado]', html)

    def test_filtra_por_area(self):
        html = self.abrir(area='EVENTOS')
        self.assertIn('[Enquete do sábado]', html)
        self.assertNotIn('[Revistinha do doador]', html)

    def test_filtra_por_status_e_por_retorno(self):
        self.assertIn('[Inventário do supply]', self.abrir(status='IDEIA'))
        self.assertNotIn('[Enquete do sábado]', self.abrir(status='IDEIA'))
        self.assertIn('[Enquete do sábado]', self.abrir(retorno='AGUARDANDO'))
        self.assertNotIn('[Inventário do supply]', self.abrir(retorno='AGUARDANDO'))

    def test_filtra_por_responsavel(self):
        html = self.abrir(responsavel=str(self.outra.pk))
        self.assertIn('[Enquete do sábado]', html)
        self.assertNotIn('[Revistinha do doador]', html)
        self.assertIn('[Inventário do supply]', self.abrir(responsavel='sem'))

    def test_busca_olha_titulo_e_os_dois_textos(self):
        self.assertIn('[Revistinha do doador]', self.abrir(q='revistinha'))
        self.assertIn('[Revistinha do doador]', self.abrir(q='token do doador'))
        self.assertIn('[Enquete do sábado]', self.abrir(q='quem não respondeu'))
        self.assertNotIn('[Revistinha do doador]', self.abrir(q='quem não respondeu'))

    def test_filtro_de_travadas(self):
        html = self.abrir(travadas='1')
        self.assertIn('total=1', html)
        self.assertIn('[Enquete do sábado]', html)
        self.assertNotIn('[Inventário do supply]', html)


# ───────────────────────────── Exclusões ─────────────────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class ExclusaoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.projetos = criar_voluntario('ana', area='PROJETOS')

    def test_get_so_confirma_e_post_apaga_a_demanda_com_o_historico(self):
        demanda = criar_demanda()
        RegistroDemanda.objects.create(demanda=demanda, tipo='NOTA', descricao='x')
        rota = reverse('projetos:deletar', args=[demanda.pk])

        views.deletar(requisicao('get', rota, self.projetos), pk=demanda.pk)
        self.assertTrue(Demanda.objects.filter(pk=demanda.pk).exists())

        resposta = views.deletar(requisicao('post', rota, self.projetos), pk=demanda.pk)
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(Demanda.objects.exists())
        self.assertFalse(RegistroDemanda.objects.exists())   # CASCADE

    def test_apagar_registro_nao_apaga_a_demanda(self):
        demanda = criar_demanda()
        registro = RegistroDemanda.objects.create(
            demanda=demanda, tipo='NOTA', descricao='anotação errada')
        rota = reverse('projetos:registro_deletar', args=[registro.pk])

        resposta = views.registro_deletar(
            requisicao('post', rota, self.projetos), pk=registro.pk)

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(RegistroDemanda.objects.exists())
        self.assertTrue(Demanda.objects.filter(pk=demanda.pk).exists())

    def test_demanda_inexistente_da_404(self):
        """Link velho de demanda apagada não pode virar erro 500.

        Chamado direto e não pelo `self.client`: um 404 passa pelo logger
        `django.request`, que monta a página de traceback — e é justamente essa
        renderização que quebra no Python 3.14.
        """
        rota = reverse('projetos:ficha', args=[9999])
        for view in (views.ficha, views.editar, views.deletar):
            with self.subTest(view=view.__name__), self.assertRaises(Http404):
                view(requisicao('get', rota, self.projetos), pk=9999)


# ───────────────────────── Formulário ─────────────────────────
class FormularioTests(TestCase):
    """Quem já saiu do projeto não pode ser oferecido: não dá para cobrar nem
    procurar alguém que não está mais no PCF."""

    def test_so_voluntario_ativo_entra_nas_escolhas(self):
        from projetos.forms import DemandaForm

        ativo = criar_voluntario('ana', area='PROJETOS')
        saiu = criar_voluntario('ex', area='MARKETING')
        saiu.data_saida = timezone.localdate()
        saiu.save(update_fields=['data_saida'])
        desligado = criar_voluntario('off', area='MARKETING')
        desligado.is_active = False
        desligado.save(update_fields=['is_active'])

        form = DemandaForm()
        for campo in ('responsavel', 'contato_na_area'):
            escolhas = list(form.fields[campo].queryset)
            self.assertIn(ativo, escolhas)
            self.assertNotIn(saiu, escolhas)
            self.assertNotIn(desligado, escolhas)


@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class CorrecoesDaRevisaoTests(TestCase):
    """Regressões encontradas na revisão adversarial."""

    @classmethod
    def setUpTestData(cls):
        cls.pj = criar_voluntario('projetista', area='PROJETOS')

    def _desligar(self, voluntario):
        voluntario.data_saida = timezone.localdate() - timedelta(days=30)
        voluntario.save(update_fields=['data_saida'])
        return voluntario

    def test_registro_com_data_futura_nao_zera_o_relogio(self):
        """`data` é digitada à mão. Um 2027 no lugar de 2026 dava 'parada há
        -300 dias' e tirava a demanda da lista de travadas — justamente o
        lugar onde ela precisa aparecer."""
        demanda = Demanda.objects.create(
            titulo='Tela nova', area='SUPPLY', status='ESPERANDO_AREA',
            retorno='AGUARDANDO')
        Demanda.objects.filter(pk=demanda.pk).update(
            criado_em=timezone.now() - timedelta(days=60))
        demanda.refresh_from_db()

        RegistroDemanda.objects.create(
            demanda=demanda, tipo='COBRANCA', descricao='erro de digitação',
            data=timezone.localdate() + timedelta(days=400))

        self.assertGreater(demanda.dias_parada, 0)
        self.assertTrue(demanda.travada)

        # O mesmo pela lista, que usa a agregação em lote e não a property.
        item = servicos.anotar_situacao(Demanda.objects.all())[0]
        self.assertGreater(item.dias_sem_movimento, 0)
        self.assertTrue(item.esta_travada)

    def test_panorama_ignora_data_futura(self):
        demanda = Demanda.objects.create(titulo='X', area='EVENTOS', retorno='AGUARDANDO')
        RegistroDemanda.objects.create(
            demanda=demanda, tipo='CONVERSA', descricao='digitação errada',
            data=timezone.localdate() + timedelta(days=200))

        linha = next(l for l in servicos.panorama_por_area() if l['area'] == 'EVENTOS')

        if linha['dias_sem_contato'] is not None:
            self.assertGreaterEqual(linha['dias_sem_contato'], 0)

    def test_demanda_com_responsavel_desligado_continua_editavel(self):
        """Antes, qualquer alteração era barrada até alguém esvaziar o campo —
        e esvaziar apagava do registro quem cuidava dela na época."""
        saiu = self._desligar(criar_voluntario('exdono', area='PROJETOS'))
        demanda = Demanda.objects.create(titulo='Antiga', area='SUPPLY', responsavel=saiu)

        form = DemandaForm(instance=demanda, data={
            'titulo': 'Antiga (corrigida)', 'area': 'SUPPLY', 'o_que_pediram': '',
            'o_que_fizemos': '', 'status': 'FAZENDO', 'retorno': 'RESPONDEU',
            'prioridade': 'MEDIA', 'responsavel': saiu.pk,
            'contato_na_area': '', 'entregue_em': ''})

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.save().responsavel, saiu)

    def test_desligado_nao_aparece_em_demanda_nova(self):
        """A regra original continua valendo onde ela faz sentido."""
        saiu = self._desligar(criar_voluntario('outro', area='PROJETOS'))
        escolhas = DemandaForm().fields['responsavel'].queryset
        self.assertNotIn(saiu, escolhas)
        self.assertIn(self.pj, escolhas)

    def test_filtro_de_responsavel_torto_nao_derruba_a_pagina(self):
        """Era 500 servido por GET: bastava um link torto. `isdigit()` aceita
        '²' (que int() rejeita) e numero grande demais para o banco."""
        for valor in ('99999999999999999999', '²', 'abc', '-1', ''):
            with self.subTest(valor=valor):
                requisicao = RequestFactory().get(
                    reverse('projetos:backlog'), {'responsavel': valor})
                requisicao.user = self.pj
                self.assertEqual(views.backlog(requisicao).status_code, 200)

    def test_inline_do_admin_sincroniza_o_retorno(self):
        """O Django salva inline por `save_formset`, nao pelo `save_model` do
        admin do filho. Sem o hook, dava para registrar um retorno da area pelo
        inline e a demanda seguir marcada como 'aguardando resposta'."""
        from django.contrib.admin.sites import AdminSite
        from projetos.admin import DemandaAdmin

        self.assertIn('save_formset', DemandaAdmin.__dict__,
                      'sem save_formset o inline burla a sincronizacao')

        demanda = Demanda.objects.create(titulo='Y', area='SUPPLY', retorno='AGUARDANDO')
        admin_demanda = DemandaAdmin(Demanda, AdminSite())

        requisicao = RequestFactory().post('/admin/')
        # Superusuário de propósito: o formset de inline do admin descarta em
        # silêncio a linha nova quando quem envia não tem permissão de adicionar
        # (`has_changed()` devolve False e o objeto nunca é salvo). Quem mexe no
        # /admin/ é staff — testar com um voluntário sem permissão não exercita
        # o caminho real e faz o teste falhar por um motivo que não é o nosso.
        requisicao.user = criar_voluntario('raiz', area='PROJETOS', superuser=True)

        inline = admin_demanda.inlines[0](Demanda, AdminSite())
        FormSet = inline.get_formset(requisicao, demanda)
        formset = FormSet(instance=demanda, data={
            'registros-TOTAL_FORMS': '1', 'registros-INITIAL_FORMS': '0',
            'registros-MIN_NUM_FORMS': '0', 'registros-MAX_NUM_FORMS': '1000',
            'registros-0-data': timezone.localdate().isoformat(),
            'registros-0-tipo': 'RETORNO',
            'registros-0-descricao': 'a area respondeu no grupo',
        })
        self.assertTrue(formset.is_valid(), formset.errors)
        admin_demanda.save_formset(requisicao, None, formset, change=True)

        demanda.refresh_from_db()
        self.assertEqual(demanda.retorno, 'RESPONDEU')
        self.assertEqual(demanda.registros.get().autor, requisicao.user)
