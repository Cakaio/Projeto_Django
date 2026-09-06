# ronda/tests.py
from django.test import TestCase, Client
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


def _vol(username, area='AZUL', **kwargs):
    return User.objects.create_user(
        username=username, password='pw', area=area,
        first_name=username.capitalize(), last_name='Teste', **kwargs
    )


class LocalRondaModelTest(TestCase):
    def test_seed_locais_criados(self):
        from ronda.models import LocalRonda
        self.assertEqual(LocalRonda.objects.count(), 3)
        self.assertTrue(LocalRonda.objects.filter(nome='Brinquedoteca').exists())

    def test_str(self):
        from ronda.models import LocalRonda
        local = LocalRonda(nome='Teste')
        self.assertEqual(str(local), 'Teste')


class ScoreRondaIncrementarTest(TestCase):
    def test_cria_e_incrementa(self):
        from ronda.models import ScoreRonda
        vol = _vol('vol_score')
        ano = timezone.now().year
        ScoreRonda.incrementar(vol, ano)
        ScoreRonda.incrementar(vol, ano)
        score = ScoreRonda.objects.get(voluntario=vol, ano=ano)
        self.assertEqual(score.pontos, 2)

    def test_incrementar_cria_se_nao_existe(self):
        from ronda.models import ScoreRonda
        vol = _vol('vol_novo')
        ano = timezone.now().year
        ScoreRonda.incrementar(vol, ano)
        self.assertEqual(ScoreRonda.objects.get(voluntario=vol, ano=ano).pontos, 1)


class EscalaRondaCleanTest(TestCase):
    def test_max_2_por_local_horario(self):
        from ronda.models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, EscalaRonda
        from sabado.models import Sabado
        import datetime
        sabado = Sabado.objects.create(data=datetime.date(2099, 1, 4), tema='T', descricao='D')
        cfg = ConfiguracaoRondaSabado.objects.create(sabado=sabado)
        horario = HorarioRonda.objects.create(configuracao=cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1)
        local = LocalRonda.objects.get(nome='Campus')
        v1 = _vol('v1')
        v2 = _vol('v2')
        v3 = _vol('v3')
        EscalaRonda.objects.create(horario=horario, local=local, voluntario=v1)
        EscalaRonda.objects.create(horario=horario, local=local, voluntario=v2)
        escala3 = EscalaRonda(horario=horario, local=local, voluntario=v3)
        with self.assertRaises(ValidationError):
            escala3.clean()


class SorteioAlgoritmoTest(TestCase):
    def setUp(self):
        from ronda.models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda
        from sabado.models import Sabado
        import datetime
        self.sabado = Sabado.objects.create(data=datetime.date(2099, 1, 4), tema='T', descricao='D')
        self.cfg = ConfiguracaoRondaSabado.objects.create(sabado=self.sabado)
        self.horario = HorarioRonda.objects.create(
            configuracao=self.cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1
        )
        # 10 voluntários elegíveis (área AZUL)
        self.vols = [_vol(f'sv{i}') for i in range(10)]

    def test_sorteia_2_por_local(self):
        from ronda.models import LocalRonda, EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        locais = LocalRonda.objects.filter(ativo=True)
        for local in locais:
            count = EscalaRonda.objects.filter(horario=self.horario, local=local).count()
            self.assertEqual(count, 2)

    def test_status_muda_para_sorteada(self):
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.status, 'SORTEADA')

    def test_area_isenta_excluida(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        vol_supply = _vol('supply_vol', area='SUPPLY')
        executar_sorteio(self.cfg)
        self.assertFalse(EscalaRonda.objects.filter(voluntario=vol_supply).exists())

    def test_mesmo_voluntario_nao_aparece_duas_vezes_no_horario(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        vols_escalados = list(EscalaRonda.objects.filter(
            horario=self.horario
        ).values_list('voluntario_id', flat=True))
        self.assertEqual(len(vols_escalados), len(set(vols_escalados)))


class SorteioEquidadeTest(TestCase):
    def setUp(self):
        from ronda.models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, ScoreRonda
        from sabado.models import Sabado
        import datetime
        self.ano = timezone.now().year
        self.sabado = Sabado.objects.create(data=datetime.date(2099, 2, 1), tema='T', descricao='D')
        self.cfg = ConfiguracaoRondaSabado.objects.create(sabado=self.sabado)
        HorarioRonda.objects.create(configuracao=self.cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1)
        # 6 voluntários com score 0, 1 com score 5
        self.vol_alto = _vol('vol_alto_score')
        ScoreRonda.objects.create(voluntario=self.vol_alto, ano=self.ano, pontos=5)
        self.vols_zerados = [_vol(f'zerado{i}') for i in range(6)]

    def test_vol_score_alto_nao_e_sorteado_quando_ha_suficientes_com_zero(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        self.assertFalse(EscalaRonda.objects.filter(voluntario=self.vol_alto).exists())


class PainelPermissaoTest(TestCase):
    def test_triade_acessa(self):
        c = Client()
        c.force_login(_vol('triade1', area='TRIADE'))
        resp = c.get(reverse('ronda:painel'))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_acessa(self):
        c = Client()
        su = User.objects.create_superuser(username='su_ronda', password='pw', first_name='Su', last_name='R')
        c.force_login(su)
        resp = c.get(reverse('ronda:painel'))
        self.assertEqual(resp.status_code, 200)

    def test_outra_area_recebe_403(self):
        c = Client()
        c.force_login(_vol('azul_ronda', area='AZUL'))
        resp = c.get(reverse('ronda:painel'))
        self.assertEqual(resp.status_code, 403)

    def test_nao_logado_redireciona(self):
        resp = Client().get(reverse('ronda:painel'))
        self.assertEqual(resp.status_code, 302)


class LocalRondaCRUDTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.triade = _vol('triade_crud', area='TRIADE')
        self.client.force_login(self.triade)

    def test_lista_locais(self):
        resp = self.client.get(reverse('ronda:locais'))
        self.assertEqual(resp.status_code, 200)

    def test_criar_local(self):
        resp = self.client.post(reverse('ronda:local_criar'), {
            'nome': 'Quadra', 'ativo': True, 'ordem': 4, 'pessoas_por_grupo': 2
        })
        self.assertRedirects(resp, reverse('ronda:locais'))
        from ronda.models import LocalRonda
        self.assertTrue(LocalRonda.objects.filter(nome='Quadra').exists())

    def test_criar_local_com_trios(self):
        resp = self.client.post(reverse('ronda:local_criar'), {
            'nome': 'Portaria', 'ativo': True, 'ordem': 5, 'pessoas_por_grupo': 3
        })
        self.assertRedirects(resp, reverse('ronda:locais'))
        from ronda.models import LocalRonda
        local = LocalRonda.objects.get(nome='Portaria')
        self.assertEqual(local.pessoas_por_grupo, 3)
        self.assertEqual(local.total_evento, 6)
        self.assertEqual(local.rotulo_grupo, 'Trio')


class ConfiguracaoCriarTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.triade = _vol('triade_conf', area='TRIADE')
        self.client.force_login(self.triade)
        from sabado.models import Sabado
        import datetime
        self.sabado = Sabado.objects.create(data=datetime.date(2099, 4, 5), tema='T', descricao='D')

    def test_criar_configuracao_com_horario(self):
        from ronda.models import ConfiguracaoRondaSabado, HorarioRonda
        resp = self.client.post(reverse('ronda:configuracao_criar'), {
            'sabado': self.sabado.pk,
            'horarios-TOTAL_FORMS': '1',
            'horarios-INITIAL_FORMS': '0',
            'horarios-MIN_NUM_FORMS': '1',
            'horarios-MAX_NUM_FORMS': '1000',
            'horarios-0-hora_inicio': '08:00',
            'horarios-0-hora_fim': '09:00',
            'horarios-0-ordem': '1',
            'horarios-0-DELETE': '',
        })
        self.assertEqual(ConfiguracaoRondaSabado.objects.count(), 1)
        self.assertEqual(HorarioRonda.objects.count(), 1)


class DetalheConfiguracaoTest(TestCase):
    def setUp(self):
        from ronda.models import ConfiguracaoRondaSabado, HorarioRonda
        from sabado.models import Sabado
        import datetime
        self.client = Client()
        self.triade = _vol('triade_det', area='TRIADE')
        self.client.force_login(self.triade)
        self.sabado = Sabado.objects.create(data=datetime.date(2099, 5, 3), tema='T', descricao='D')
        self.cfg = ConfiguracaoRondaSabado.objects.create(sabado=self.sabado, criado_por=self.triade)
        self.horario = HorarioRonda.objects.create(configuracao=self.cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1)
        # 10 voluntários elegíveis
        self.vols = [_vol(f'det{i}') for i in range(10)]

    def test_detalhe_acessivel(self):
        resp = self.client.get(reverse('ronda:configuracao_detalhe', args=[self.cfg.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_sortear_muda_status(self):
        from ronda.models import EscalaRonda
        resp = self.client.post(reverse('ronda:configuracao_sortear', args=[self.cfg.pk]))
        self.assertRedirects(resp, reverse('ronda:configuracao_detalhe', args=[self.cfg.pk]))
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.status, 'SORTEADA')
        self.assertGreater(EscalaRonda.objects.filter(horario__configuracao=self.cfg).count(), 0)

    def test_aprovar_incrementa_scores(self):
        from ronda.models import EscalaRonda, ScoreRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        self.cfg.refresh_from_db()
        ano = timezone.now().year
        resp = self.client.post(reverse('ronda:configuracao_aprovar', args=[self.cfg.pk]))
        self.assertRedirects(resp, reverse('ronda:configuracao_detalhe', args=[self.cfg.pk]))
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.status, 'APROVADA')
        for escala in EscalaRonda.objects.filter(horario__configuracao=self.cfg):
            score = ScoreRonda.objects.get(voluntario=escala.voluntario, ano=ano)
            self.assertGreaterEqual(score.pontos, 1)

    def test_reprovar_sem_motivo_nao_reprova(self):
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        self.client.post(reverse('ronda:configuracao_reprovar', args=[self.cfg.pk]), {'observacao': ''})
        self.cfg.refresh_from_db()
        self.assertNotEqual(self.cfg.status, 'REPROVADA')

    def test_reprovar_com_motivo(self):
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        self.client.post(reverse('ronda:configuracao_reprovar', args=[self.cfg.pk]), {'observacao': 'Ajuste necessário'})
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.status, 'REPROVADA')

    def test_swap_troca_voluntario(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        escala = EscalaRonda.objects.filter(horario__configuracao=self.cfg).first()
        novo_vol = _vol('swap_novo')
        resp = self.client.post(
            reverse('ronda:escala_swap', args=[escala.pk]),
            {'voluntario_novo_pk': novo_vol.pk}
        )
        self.assertEqual(resp.status_code, 302)
        escala.refresh_from_db()
        self.assertEqual(escala.voluntario, novo_vol)
        self.assertTrue(escala.is_substituto)


class DiaDeEventoTest(TestCase):
    """Dia de evento: 2 grupos por local, tamanho definido no próprio local."""

    def setUp(self):
        from ronda.models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda
        from sabado.models import Sabado, DisponibilidadeVoluntario
        import datetime

        self.sabado = Sabado.objects.create(data=datetime.date(2099, 6, 6), tema='T', descricao='D')
        self.cfg = ConfiguracaoRondaSabado.objects.create(sabado=self.sabado, dia_de_evento=True)

        self.campus = LocalRonda.objects.get(nome='Campus')
        self.brinquedoteca = LocalRonda.objects.get(nome='Brinquedoteca')
        self.h_campus = HorarioRonda.objects.create(configuracao=self.cfg, local=self.campus, ordem=0)
        self.h_brinq = HorarioRonda.objects.create(configuracao=self.cfg, local=self.brinquedoteca, ordem=1)

        self.vols = [_vol(f'ev{i}') for i in range(20)]
        for v in self.vols:
            DisponibilidadeVoluntario.objects.create(sabado=self.sabado, voluntario=v, vai_ao_projeto=True)

        self.client = Client()
        self.client.force_login(_vol('triade_evento', area='TRIADE'))

    def test_campus_vem_em_trios(self):
        self.assertEqual(self.campus.pessoas_por_grupo, 3)
        self.assertEqual(self.campus.total_evento, 6)

    def test_sorteio_respeita_tamanho_do_grupo(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)

        campus = EscalaRonda.objects.filter(horario=self.h_campus)
        self.assertEqual(campus.count(), 6)
        self.assertEqual(campus.filter(dupla=1).count(), 3)
        self.assertEqual(campus.filter(dupla=2).count(), 3)

        brinq = EscalaRonda.objects.filter(horario=self.h_brinq)
        self.assertEqual(brinq.count(), 4)
        self.assertEqual(brinq.filter(dupla=1).count(), 2)
        self.assertEqual(brinq.filter(dupla=2).count(), 2)

    def test_necessarios_soma_tamanhos_por_local(self):
        resp = self.client.get(reverse('ronda:configuracao_detalhe', args=[self.cfg.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['necessarios'], 10)  # 6 (Campus) + 4 (Brinquedoteca)

    def test_clean_permite_ate_o_total_do_local(self):
        from ronda.models import EscalaRonda
        for i, vol in enumerate(self.vols[:6]):
            EscalaRonda.objects.create(
                horario=self.h_campus, local=self.campus, voluntario=vol, dupla=1 if i < 3 else 2,
            )
        excedente = EscalaRonda(horario=self.h_campus, local=self.campus, voluntario=self.vols[6], dupla=2)
        with self.assertRaises(ValidationError):
            excedente.clean()

    def test_swap_permitido_em_dia_de_evento(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        escala = EscalaRonda.objects.filter(horario=self.h_campus).first()
        escalados = set(
            EscalaRonda.objects.filter(horario__configuracao=self.cfg).values_list('voluntario_id', flat=True)
        )
        novo_vol = next(v for v in self.vols if v.pk not in escalados)

        resp = self.client.post(
            reverse('ronda:escala_swap', args=[escala.pk]), {'voluntario_novo_pk': novo_vol.pk}
        )
        self.assertEqual(resp.status_code, 302)
        escala.refresh_from_db()
        self.assertEqual(escala.voluntario, novo_vol)
        self.assertTrue(escala.is_substituto)

    def test_swap_recusa_quem_ja_esta_em_outro_local(self):
        from ronda.models import EscalaRonda
        from ronda.sorteio import executar_sorteio
        executar_sorteio(self.cfg)
        escala = EscalaRonda.objects.filter(horario=self.h_campus).first()
        ja_escalado = EscalaRonda.objects.filter(horario=self.h_brinq).first().voluntario

        self.client.post(
            reverse('ronda:escala_swap', args=[escala.pk]), {'voluntario_novo_pk': ja_escalado.pk}
        )
        escala.refresh_from_db()
        self.assertNotEqual(escala.voluntario, ja_escalado)


class RankingRondaTest(TestCase):
    def test_triade_acessa_ranking(self):
        c = Client()
        c.force_login(_vol('triade_rank', area='TRIADE'))
        resp = c.get(reverse('ronda:ranking'))
        self.assertEqual(resp.status_code, 200)

    def test_ranking_exclui_areas_isentas(self):
        _vol('supply_rank', area='SUPPLY')
        c = Client()
        c.force_login(_vol('triade_rank2', area='TRIADE'))
        resp = c.get(reverse('ronda:ranking'))
        vols = [item['vol'] for item in resp.context['voluntarios']]
        areas = [v.area for v in vols]
        self.assertNotIn('SUPPLY', areas)
        self.assertNotIn('TRIADE', areas)


class ScoreEditarTest(TestCase):
    def test_editar_score(self):
        from ronda.models import ScoreRonda
        ano = timezone.now().year
        vol = _vol('vol_edit_score')
        score = ScoreRonda.objects.create(voluntario=vol, ano=ano, pontos=3)
        c = Client()
        c.force_login(_vol('triade_se', area='TRIADE'))
        resp = c.post(reverse('ronda:score_editar', args=[score.pk]), {'pontos': 7})
        score.refresh_from_db()
        self.assertEqual(score.pontos, 7)


class RondaPublicaTest(TestCase):
    def test_qualquer_logado_ve(self):
        c = Client()
        c.force_login(_vol('qualquer'))
        resp = c.get(reverse('ronda:ronda_publica'))
        self.assertEqual(resp.status_code, 200)

    def test_nao_logado_redireciona(self):
        resp = Client().get(reverse('ronda:ronda_publica'))
        self.assertEqual(resp.status_code, 302)

    def test_exibe_apenas_aprovadas(self):
        from ronda.models import ConfiguracaoRondaSabado
        from sabado.models import Sabado
        import datetime
        s1 = Sabado.objects.create(data=datetime.date(2099, 6, 7), tema='T1', descricao='D')
        s2 = Sabado.objects.create(data=datetime.date(2099, 7, 5), tema='T2', descricao='D')
        cfg1 = ConfiguracaoRondaSabado.objects.create(sabado=s1, status='APROVADA')
        cfg2 = ConfiguracaoRondaSabado.objects.create(sabado=s2, status='SORTEADA')
        c = Client()
        c.force_login(_vol('pub_vol'))
        resp = c.get(reverse('ronda:ronda_publica'))
        cfgs = list(resp.context['configuracoes'])
        self.assertIn(cfg1, cfgs)
        self.assertNotIn(cfg2, cfgs)


class SortearCommandTest(TestCase):
    def test_command_em_sexta_executa_sorteio(self):
        from ronda.models import ConfiguracaoRondaSabado, HorarioRonda, EscalaRonda
        from sabado.models import Sabado
        from django.core.management import call_command
        import datetime
        # 2099-01-02 é sexta-feira, 2099-01-03 é sábado
        sab = Sabado.objects.create(data=datetime.date(2099, 1, 3), tema='T', descricao='D')
        cfg = ConfiguracaoRondaSabado.objects.create(sabado=sab)
        HorarioRonda.objects.create(configuracao=cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1)
        [_vol(f'cmd{i}') for i in range(10)]
        from unittest.mock import patch
        import datetime as dt
        sexta = dt.date(2099, 1, 2)  # sexta-feira real
        # Dubla `localdate`, não `now().date()`: o comando é agendado e usa a
        # data LOCAL. Com now().date() (UTC) uma execução às 22h de sexta já
        # calcularia sábado e o sorteio não rodaria.
        with patch('ronda.management.commands.sortear_rondas.timezone') as mock_tz:
            mock_tz.localdate.return_value = sexta
            call_command('sortear_rondas')
        cfg.refresh_from_db()
        self.assertEqual(cfg.status, 'SORTEADA')


class SorteioSemElegiveisSuficientesTest(TestCase):
    def test_sorteia_quem_tem_sem_quebrar(self):
        from ronda.models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, EscalaRonda
        from sabado.models import Sabado
        import datetime
        sabado = Sabado.objects.create(data=datetime.date(2099, 3, 1), tema='T', descricao='D')
        cfg = ConfiguracaoRondaSabado.objects.create(sabado=sabado)
        HorarioRonda.objects.create(configuracao=cfg, hora_inicio='08:00', hora_fim='09:00', ordem=1)
        # Apenas 2 voluntários elegíveis (menos que 6 necessários)
        _vol('pouco1')
        _vol('pouco2')
        from ronda.sorteio import executar_sorteio
        executar_sorteio(cfg)  # Não deve lançar exceção
        self.assertLessEqual(EscalaRonda.objects.filter(horario__configuracao=cfg).count(), 6)
