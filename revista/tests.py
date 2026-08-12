"""Testes da revista.

Os testes que renderizam página chamam a view por `RequestFactory`, e não pelo
`self.client`: neste ambiente (Python 3.14 + Django 4.2) a instrumentação de
template do test client quebra. `self.client` fica para o que não renderiza.

Os templates de tela são de outra entrega, então aqui usamos stubs em memória
(`locmem`) — o teste valida a view, não o HTML.
"""
import datetime

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from atendido.models import Atendido, PresencaAtendido
from sabado.models import Sabado
from semanario.models import Atividade, Semanario
from voluntario.models import PresencaVoluntario, Voluntario

from .models import Revista, SecaoRevista
from .servicos import financeiro_do_periodo, montar_secoes, numeros_do_periodo
from .views import _contexto_leitura, lista, pdf, publica, publicar

TEMPLATES_STUB = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': False,
    'OPTIONS': {
        'loaders': [('django.template.loaders.locmem.Loader', {
            'revista/lista.html': '<h1>Revistas</h1>{{ total }}',
            'revista/publica.html': (
                '<meta name="robots" content="noindex, nofollow">'
                '<h1>{{ revista.titulo }}</h1>'
            ),
            'revista/pdf.html': (
                '<html><body><h1>{{ revista.titulo }}</h1>'
                '{% for s in secoes %}<p>{{ s.titulo }}</p>{% endfor %}'
                '</body></html>'
            ),
        })],
        'context_processors': [
            'django.template.context_processors.request',
        ],
    },
}]

INICIO = datetime.date(2026, 3, 1)
FIM = datetime.date(2026, 3, 31)


def cria_voluntario(username, area='CR/RE', **extra):
    return Voluntario.objects.create_user(
        username=username, password='x', area=area, **extra)


class BaseRevista(TestCase):
    """Um período com dois sábados, duas salas e atividades de verdade."""

    def setUp(self):
        self.fabio = cria_voluntario('fabio', area='CR/RE')

        self.sabado_1 = Sabado.objects.create(
            data=datetime.date(2026, 3, 7), tema='Amizade', descricao='...')
        self.sabado_2 = Sabado.objects.create(
            data=datetime.date(2026, 3, 14), tema='Respeito', descricao='...')

        self.sem_violeta = Semanario.objects.create(
            sala='VIOLETA', data=self.sabado_1, tema='Amizade')
        self.sem_azul = Semanario.objects.create(
            sala='AZUL', data=self.sabado_2, tema='Respeito')

        self.ativ_a = Atividade.objects.create(
            semanario=self.sem_violeta, atividade='Roda de conversa',
            descricao='As crianças contaram o que é ser amigo.',
            competencia='Respeito')
        self.ativ_b = Atividade.objects.create(
            semanario=self.sem_azul, atividade='Mural da empatia',
            descricao='Cada criança desenhou um colega.',
            competencia='Empatia')
        # Sem descrição: não vira seção, porque é a descrição que vira o texto.
        self.ativ_sem_texto = Atividade.objects.create(
            semanario=self.sem_azul, atividade='Lanche', descricao='',
            competencia='Recreativos')

        self.revista = Revista.objects.create(
            titulo='Março no PCF', periodo_inicio=INICIO, periodo_fim=FIM,
            criado_por=self.fabio)


# ─────────────────────────── Permissão ───────────────────────────
@override_settings(TEMPLATES=TEMPLATES_STUB)
class PermissaoTests(BaseRevista):

    def _get_lista(self, usuario):
        requisicao = RequestFactory().get('/revista/')
        requisicao.user = usuario
        return lista(requisicao)

    def test_voluntario_de_outra_area_nao_entra(self):
        de_sala = cria_voluntario('joana', area='VIOLETA')
        with self.assertRaises(PermissionDenied):
            self._get_lista(de_sala)

    def test_crre_entra(self):
        self.assertEqual(self._get_lista(self.fabio).status_code, 200)

    def test_triade_entra(self):
        chefe = cria_voluntario('bruna', area='TRIADE')
        self.assertEqual(self._get_lista(chefe).status_code, 200)

    def test_superuser_entra_mesmo_fora_da_area(self):
        admin = Voluntario.objects.create_superuser(
            username='admin', password='x', area='SUPPLY')
        self.assertEqual(self._get_lista(admin).status_code, 200)

    def test_anonimo_vai_para_o_login(self):
        # Sem render: o decorator redireciona antes de chegar na view.
        resposta = self._get_lista(AnonymousUser())
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login/', resposta['Location'])


# ─────────────────────── Montagem das seções ───────────────────────
class MontarSecoesTests(BaseRevista):

    def test_monta_uma_secao_por_atividade_com_descricao(self):
        criadas = montar_secoes(self.revista)

        self.assertEqual(criadas, 2)
        self.assertEqual(self.revista.secoes.count(), 2)
        # A atividade sem descrição ficou de fora.
        self.assertNotIn(
            'Lanche',
            list(self.revista.secoes.values_list('titulo', flat=True)),
        )

    def test_copia_os_dados_da_atividade_para_a_secao(self):
        montar_secoes(self.revista)
        secao = self.revista.secoes.get(atividade=self.ativ_a)

        self.assertEqual(secao.titulo, 'Roda de conversa')
        self.assertEqual(secao.texto, 'As crianças contaram o que é ser amigo.')
        self.assertEqual(secao.competencia, 'Respeito')
        self.assertEqual(secao.sala, 'VIOLETA')
        self.assertEqual(secao.sabado, self.sabado_1)
        self.assertTrue(secao.incluir)

    def test_ignora_atividade_fora_do_periodo(self):
        sabado_abril = Sabado.objects.create(
            data=datetime.date(2026, 4, 4), tema='Outro mês', descricao='...')
        semanario_abril = Semanario.objects.create(
            sala='VERDE', data=sabado_abril, tema='Outro mês')
        Atividade.objects.create(
            semanario=semanario_abril, atividade='Fora do período',
            descricao='Não deve entrar.', competencia='Autonomia')

        montar_secoes(self.revista)

        self.assertEqual(self.revista.secoes.count(), 2)
        self.assertFalse(self.revista.secoes.filter(titulo='Fora do período').exists())

    def test_remontar_nao_duplica_o_que_ja_existe(self):
        montar_secoes(self.revista)
        criadas = montar_secoes(self.revista)

        self.assertEqual(criadas, 0)
        self.assertEqual(self.revista.secoes.count(), 2)

    def test_remontar_traz_apenas_a_atividade_nova(self):
        montar_secoes(self.revista)
        Atividade.objects.create(
            semanario=self.sem_violeta, atividade='Pintura',
            descricao='Pintaram o mural da sala.', competencia='Imaginação')

        criadas = montar_secoes(self.revista)

        self.assertEqual(criadas, 1)
        self.assertEqual(self.revista.secoes.count(), 3)

    def test_substituir_recomeca_do_zero(self):
        montar_secoes(self.revista)
        secao = self.revista.secoes.get(atividade=self.ativ_a)
        secao.titulo = 'Texto reescrito pelo CR'
        secao.save()

        criadas = montar_secoes(self.revista, substituir=True)

        self.assertEqual(criadas, 2)
        self.assertEqual(self.revista.secoes.count(), 2)
        # Recomeçar do zero é justamente perder o que foi reescrito.
        self.assertFalse(
            self.revista.secoes.filter(titulo='Texto reescrito pelo CR').exists())


# ─────────────────────────── Snapshot ───────────────────────────
class SnapshotTests(BaseRevista):
    """A revista já montada é um retrato: mexer no semanário depois não pode
    mudar o que o doador recebeu."""

    def test_editar_o_semanario_depois_nao_altera_a_revista(self):
        montar_secoes(self.revista)
        secao = self.revista.secoes.get(atividade=self.ativ_a)

        self.ativ_a.atividade = 'Título trocado meses depois'
        self.ativ_a.descricao = 'Descrição reescrita meses depois'
        self.ativ_a.competencia = 'Autonomia'
        self.ativ_a.save()

        secao.refresh_from_db()
        self.assertEqual(secao.titulo, 'Roda de conversa')
        self.assertEqual(secao.texto, 'As crianças contaram o que é ser amigo.')
        self.assertEqual(secao.competencia, 'Respeito')

    def test_apagar_a_atividade_nao_apaga_a_secao(self):
        montar_secoes(self.revista)
        secao_pk = self.revista.secoes.get(atividade=self.ativ_a).pk

        self.ativ_a.delete()

        secao = SecaoRevista.objects.get(pk=secao_pk)
        self.assertIsNone(secao.atividade)
        self.assertEqual(secao.titulo, 'Roda de conversa')


# ─────────────────────── Números do período ───────────────────────
class NumerosDoPeriodoTests(BaseRevista):

    def _atendido(self, nome):
        return Atendido.objects.create(
            nome=nome, data_nascimento=datetime.date(2016, 5, 10), sala='VIOLETA')

    def test_conta_sabados_atividades_e_salas(self):
        numeros = numeros_do_periodo(INICIO, FIM)

        self.assertEqual(numeros['sabados'], 2)
        self.assertEqual(numeros['atividades'], 3)  # inclui a sem descrição
        self.assertEqual(numeros['salas'], 2)

    def test_conta_cada_crianca_uma_vez_mesmo_com_varias_presencas(self):
        ana = self._atendido('Ana')
        beto = self._atendido('Beto')
        # Ana veio nos dois sábados: ainda assim é uma criança.
        PresencaAtendido.objects.create(atendido=ana, data=self.sabado_1, presenca='PRESENTE')
        PresencaAtendido.objects.create(atendido=ana, data=self.sabado_2, presenca='PRESENTE')
        PresencaAtendido.objects.create(atendido=beto, data=self.sabado_1, presenca='PRESENTE')

        self.assertEqual(numeros_do_periodo(INICIO, FIM)['criancas'], 2)

    def test_nao_conta_falta_como_presenca(self):
        ausente = self._atendido('Carlos')
        PresencaAtendido.objects.create(
            atendido=ausente, data=self.sabado_1, presenca='AUSENTE')
        voluntario_ausente = cria_voluntario('lucas', area='AZUL')
        PresencaVoluntario.objects.create(
            voluntario=voluntario_ausente, data=self.sabado_1, presenca='AUSENTE')

        numeros = numeros_do_periodo(INICIO, FIM)
        self.assertEqual(numeros['criancas'], 0)
        self.assertEqual(numeros['voluntarios'], 0)

    def test_conta_voluntarios_distintos(self):
        PresencaVoluntario.objects.create(
            voluntario=self.fabio, data=self.sabado_1, presenca='PRESENTE')
        PresencaVoluntario.objects.create(
            voluntario=self.fabio, data=self.sabado_2, presenca='PRESENTE')

        self.assertEqual(numeros_do_periodo(INICIO, FIM)['voluntarios'], 1)

    def test_dimensoes_sem_repeticao_e_ordenadas(self):
        # 'Respeito' e 'Empatia' caem na mesma dimensão socioemocional.
        dimensoes = numeros_do_periodo(INICIO, FIM)['dimensoes']

        self.assertEqual(dimensoes, sorted(set(dimensoes)))
        self.assertIn('Desenvolvimento Socioemocional e Relacional', dimensoes)
        self.assertEqual(
            dimensoes.count('Desenvolvimento Socioemocional e Relacional'), 1)

    def test_periodo_vazio_zera_tudo(self):
        numeros = numeros_do_periodo(
            datetime.date(2030, 1, 1), datetime.date(2030, 1, 31))

        self.assertEqual(numeros['sabados'], 0)
        self.assertEqual(numeros['atividades'], 0)
        self.assertEqual(numeros['criancas'], 0)
        self.assertEqual(numeros['voluntarios'], 0)
        self.assertEqual(numeros['dimensoes'], [])


# ─────────────────────── Link público do doador ───────────────────────
@override_settings(TEMPLATES=TEMPLATES_STUB)
class LinkPublicoTests(BaseRevista):

    def _abre(self, revista):
        requisicao = RequestFactory().get(f'/r/{revista.token}/')
        requisicao.user = AnonymousUser()
        return publica(requisicao, token=revista.token)

    def _publica_valida(self):
        self.revista.status = 'PUBLICADA'
        self.revista.link_publico_ativo = True
        self.revista.save()
        return self.revista

    def test_token_e_gerado_sozinho_e_nao_se_repete(self):
        outra = Revista.objects.create(
            titulo='Abril', periodo_inicio=INICIO, periodo_fim=FIM)

        self.assertTrue(self.revista.token)
        self.assertGreater(len(self.revista.token), 20)
        self.assertNotEqual(self.revista.token, outra.token)

    def test_link_ativo_abre_sem_login_e_pede_para_nao_indexar(self):
        revista = self._publica_valida()

        resposta = self._abre(revista)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['X-Robots-Tag'], 'noindex, nofollow, noarchive')
        self.assertIn('noindex', resposta.content.decode())

    def test_link_revogado_da_404(self):
        revista = self._publica_valida()
        revista.link_publico_ativo = False
        revista.save()

        self.assertFalse(revista.link_publico_valido)
        with self.assertRaises(Http404):
            self._abre(revista)

    def test_link_expirado_da_404(self):
        revista = self._publica_valida()
        revista.link_expira_em = datetime.date(2020, 1, 1)
        revista.save()

        self.assertFalse(revista.link_publico_valido)
        with self.assertRaises(Http404):
            self._abre(revista)

    def test_rascunho_nao_abre_mesmo_com_link_ligado(self):
        self.revista.status = 'RASCUNHO'
        self.revista.link_publico_ativo = True
        self.revista.save()

        # O link está válido; o que barra é a revista não estar publicada.
        self.assertTrue(self.revista.link_publico_valido)
        with self.assertRaises(Http404):
            self._abre(self.revista)

    def test_token_inexistente_da_404(self):
        requisicao = RequestFactory().get('/r/naoexiste/')
        requisicao.user = AnonymousUser()
        with self.assertRaises(Http404):
            publica(requisicao, token='naoexiste')

    def test_link_sem_data_de_expiracao_continua_valido(self):
        revista = self._publica_valida()
        self.assertIsNone(revista.link_expira_em)
        self.assertTrue(revista.link_publico_valido)


# ─────────────────────── Publicar, revogar e PDF ───────────────────────
@override_settings(TEMPLATES=TEMPLATES_STUB)
class AcoesTests(BaseRevista):

    def _post(self, acao):
        requisicao = RequestFactory().post(
            f'/revista/{self.revista.pk}/publicar/', {'acao': acao})
        requisicao.user = self.fabio
        # `messages` precisa de sessão; com RequestFactory montamos na mão.
        requisicao.session = {}
        requisicao._messages = FallbackStorage(requisicao)
        return publicar(requisicao, pk=self.revista.pk)

    def test_publicar_liga_o_status_e_o_link(self):
        self._post('publicar')

        self.revista.refresh_from_db()
        self.assertEqual(self.revista.status, 'PUBLICADA')
        self.assertTrue(self.revista.link_publico_ativo)
        self.assertTrue(self.revista.link_publico_valido)

    def test_revogar_mata_o_link_mas_mantem_publicada(self):
        self._post('publicar')

        self._post('revogar')

        self.revista.refresh_from_db()
        self.assertEqual(self.revista.status, 'PUBLICADA')
        self.assertFalse(self.revista.link_publico_valido)

    def test_despublicar_volta_para_rascunho(self):
        self._post('publicar')

        self._post('despublicar')

        self.revista.refresh_from_db()
        self.assertEqual(self.revista.status, 'RASCUNHO')
        self.assertFalse(self.revista.link_publico_ativo)

    def test_publicar_por_get_nao_muda_nada(self):
        requisicao = RequestFactory().get(f'/revista/{self.revista.pk}/publicar/')
        requisicao.user = self.fabio

        resposta = publicar(requisicao, pk=self.revista.pk)

        self.revista.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.revista.status, 'RASCUNHO')

    def test_secao_desmarcada_nao_entra_na_leitura(self):
        montar_secoes(self.revista)
        fora = self.revista.secoes.first()
        fora.incluir = False
        fora.save()

        contexto = _contexto_leitura(self.revista)

        self.assertEqual(contexto['secoes'].count(), 1)
        self.assertNotIn(fora, contexto['secoes'])

    def test_desligar_numeros_e_financeiro_tira_os_blocos(self):
        self.revista.mostrar_numeros = False
        self.revista.mostrar_financeiro = False
        self.revista.save()

        contexto = _contexto_leitura(self.revista)

        self.assertIsNone(contexto['numeros'])
        self.assertIsNone(contexto['financeiro'])

    def test_financeiro_vem_do_adm_no_formato_esperado(self):
        resultado = financeiro_do_periodo(INICIO, FIM)
        if resultado is None:
            self.skipTest('adm.servicos ainda não foi integrado neste ambiente.')

        # O contrato com o Financeiro: (linhas, total) virando estas chaves.
        self.assertEqual(sorted(resultado.keys()), ['linhas', 'total'])
        self.assertIsInstance(resultado['linhas'], list)

    def test_pdf_devolve_um_arquivo_pdf(self):
        montar_secoes(self.revista)
        requisicao = RequestFactory().get(f'/revista/{self.revista.pk}/pdf/')
        requisicao.user = self.fabio

        resposta = pdf(requisicao, pk=self.revista.pk)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename=', resposta['Content-Disposition'])
        # Assinatura de arquivo PDF: não basta responder 200.
        self.assertTrue(resposta.content.startswith(b'%PDF'))


class DimensoesInternasTests(TestCase):
    """'Não classificada' é recado interno do semanário para o time arrumar o
    cadastro. Ir parar na revista do doador faria o projeto parecer
    desorganizado — e o doador não tem como saber que é só um rótulo técnico."""

    def test_nao_classificada_fica_de_fora(self):
        import datetime
        from sabado.models import Sabado
        from semanario.models import Semanario, Atividade
        from revista import servicos

        sabado = Sabado.objects.create(data=datetime.date(2026, 3, 7))
        semanario = Semanario.objects.create(sala='AZUL', data=sabado, tema='Teste')
        # Competência real do mapa da sala AZUL: assim o save() do model
        # carimba uma dimensão de verdade, e o teste prova que ela SOBREVIVE
        # ao filtro — não basta o 'Não classificada' sumir.
        Atividade.objects.create(semanario=semanario, atividade='Boa',
                                 descricao='texto', competencia='Empatia')
        indefinida = Atividade.objects.create(semanario=semanario, atividade='Sem mapa',
                                              descricao='texto', competencia='inexistente')
        # Grava direto: o save() do model recalcula o campo a partir do mapa.
        Atividade.objects.filter(pk=indefinida.pk).update(
            dimensao_competencia='Não classificada')

        numeros = servicos.numeros_do_periodo(datetime.date(2026, 1, 1),
                                              datetime.date(2026, 12, 31))
        self.assertNotIn('Não classificada', numeros['dimensoes'])
        self.assertTrue(numeros['dimensoes'], 'as dimensões válidas devem continuar')


class CorrecoesDaRevisaoTests(TestCase):
    """Regressões encontradas na revisão adversarial. Cada uma quebrava algo
    que o doador veria."""

    def _cenario(self):
        import datetime
        from sabado.models import Sabado
        from semanario.models import Semanario, Atividade
        from revista.models import Revista

        revista = Revista.objects.create(
            titulo='Edição de teste',
            periodo_inicio=datetime.date(2026, 1, 1),
            periodo_fim=datetime.date(2026, 12, 31))
        sabado = Sabado.objects.create(data=datetime.date(2026, 3, 7))
        semanario = Semanario.objects.create(sala='AZUL', data=sabado, tema='Teste')
        atividades = [
            Atividade.objects.create(semanario=semanario, atividade=nome,
                                     descricao='relato', competencia='Empatia')
            for nome in ('Pintura', 'Música', 'Teatro')
        ]
        return revista, atividades

    def test_dimensao_com_virgula_no_nome_nao_e_estilhacada(self):
        """3 das 7 dimensões têm vírgula dentro do nome. Fatiar por vírgula
        inventava duas dimensões inexistentes bem na capa do doador."""
        import datetime
        from sabado.models import Sabado
        from semanario.models import Semanario, Atividade
        from revista import servicos

        sabado = Sabado.objects.create(data=datetime.date(2026, 4, 4))
        semanario = Semanario.objects.create(sala='AZUL', data=sabado, tema='T')
        atividade = Atividade.objects.create(semanario=semanario, atividade='A',
                                             descricao='x', competencia='Empatia')
        Atividade.objects.filter(pk=atividade.pk).update(
            dimensao_competencia='Autoconhecimento, Identidade e Projeto de Vida')

        dimensoes = servicos.numeros_do_periodo(
            datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))['dimensoes']

        self.assertEqual(dimensoes, ['Autoconhecimento, Identidade e Projeto de Vida'])
        self.assertNotIn('Autoconhecimento', dimensoes)   # metade solta: não existe

    def test_secao_apagada_nao_volta_ao_remontar(self):
        """Apagar a seção é como o CR diz 'esta atividade não entra'. Se o
        remontar a trouxesse de volta, ele teria de tirar de novo toda vez."""
        from revista import servicos

        revista, atividades = self._cenario()
        servicos.montar_secoes(revista)
        self.assertEqual(revista.secoes.count(), 3)

        # O CR tira a "Música" e o sistema registra o descarte.
        revista.secoes.filter(atividade=atividades[1]).delete()
        revista.atividades_descartadas = [atividades[1].pk]
        revista.save(update_fields=['atividades_descartadas'])

        criadas = servicos.montar_secoes(revista)

        self.assertEqual(criadas, 0)
        self.assertEqual(revista.secoes.count(), 2)
        self.assertFalse(revista.secoes.filter(atividade=atividades[1]).exists())

    def test_substituir_limpa_os_descartes(self):
        """'Recomeçar do zero' precisa recomeçar mesmo — senão não há como
        trazer de volta uma atividade apagada por engano."""
        from revista import servicos

        revista, atividades = self._cenario()
        revista.atividades_descartadas = [atividades[1].pk]
        revista.save(update_fields=['atividades_descartadas'])

        servicos.montar_secoes(revista, substituir=True)

        revista.refresh_from_db()
        self.assertEqual(revista.atividades_descartadas, [])
        self.assertEqual(revista.secoes.count(), 3)

    def test_ordem_nao_repete_depois_de_apagar_do_meio(self):
        """A ordem vinha da CONTAGEM de seções. Bastava apagar uma do meio para
        a próxima nascer com um número já usado, e a revista saía numa sequência
        que ninguém escolheu."""
        from revista import servicos
        from semanario.models import Atividade

        revista, atividades = self._cenario()
        servicos.montar_secoes(revista)
        revista.secoes.filter(atividade=atividades[0]).delete()   # apaga a de ordem 0

        Atividade.objects.create(semanario=atividades[0].semanario,
                                 atividade='Dança', descricao='relato',
                                 competencia='Empatia')
        servicos.montar_secoes(revista)

        ordens = list(revista.secoes.values_list('ordem', flat=True))
        self.assertEqual(len(ordens), len(set(ordens)), f'ordem repetida: {ordens}')

    def test_link_publico_manda_nao_guardar_em_cache(self):
        """Sem isto, revogar o link não revoga nada para quem já abriu: o cache
        continua entregando a edição."""
        import datetime
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from revista import views
        from revista.models import Revista

        revista = Revista.objects.create(
            titulo='Pública', periodo_inicio=datetime.date(2026, 1, 1),
            periodo_fim=datetime.date(2026, 6, 30),
            status='PUBLICADA', link_publico_ativo=True)

        # RequestFactory e não o test client: o client copia o contexto do
        # template ao renderizar, e essa cópia quebra no Python 3.14 com
        # Django 4.2 (falha do ambiente, não do app).
        pedido = RequestFactory().get('/r/' + revista.token + '/')
        pedido.user = AnonymousUser()
        resposta = views.publica(pedido, revista.token)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('no-store', resposta['Cache-Control'])
        self.assertIn('noindex', resposta['X-Robots-Tag'])
