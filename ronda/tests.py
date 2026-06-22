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
