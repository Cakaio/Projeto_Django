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
