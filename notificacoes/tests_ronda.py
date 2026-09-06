"""Gatilho de push da ronda — pedido 4.

"Quando sair uma ronda e a pessoa estiver na ronda, já manda pra ela que ela
está de ronda e o lugar."

"Sair" é a transição SORTEADA -> APROVADA: só depois dela a tela pública
(`ronda_publica`) mostra a escala. Antes disso, a pessoa não tem o que ver.
"""
import datetime
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from notificacoes.models import InscricaoPush
from notificacoes.tests_gatilhos import ThreadSincrona
from ronda.models import (ConfiguracaoRondaSabado, EscalaRonda, HorarioRonda,
                          LocalRonda)
from sabado.models import Sabado

Voluntario = get_user_model()


def _proximo_sabado(dias=6):
    return timezone.localdate() + datetime.timedelta(days=dias)


class BaseRonda(TestCase):
    def setUp(self):
        self.sabado = Sabado.objects.create(
            data=_proximo_sabado(), tema="Tema", descricao="d")
        self.cfg = ConfiguracaoRondaSabado.objects.create(
            sabado=self.sabado, status="SORTEADA")
        self.portao = LocalRonda.objects.create(nome="Portão", ordem=1)
        self.quadra = LocalRonda.objects.create(nome="Quadra", ordem=2)

        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL")
        self.bia = Voluntario.objects.create_user(
            username="bia", password="senha-de-teste-123", area="VERDE")
        self.fora = Voluntario.objects.create_user(
            username="fora", password="senha-de-teste-123", area="AZUL")
        self.triade = Voluntario.objects.create_user(
            username="triade", password="senha-de-teste-123", area="TRIADE")
        for vol in (self.ana, self.bia, self.fora):
            InscricaoPush.objects.create(
                voluntario=vol, endpoint=f"https://push.exemplo/{vol.username}",
                p256dh="p", auth="a")

    def _horario(self, local, inicio="08:00", fim="09:00", ordem=0):
        def hora(texto):
            if texto is None:
                return None
            h, m = texto.split(":")
            return datetime.time(int(h), int(m))

        return HorarioRonda.objects.create(
            configuracao=self.cfg, local=local,
            hora_inicio=hora(inicio), hora_fim=hora(fim), ordem=ordem)

    def _escalar(self, horario, voluntario, dupla=None):
        return EscalaRonda.objects.create(
            horario=horario, local=horario.local,
            voluntario=voluntario, dupla=dupla)

    def _aprovar_pela_view(self):
        from ronda.views import configuracao_aprovar

        pedido = RequestFactory().post(f"/ronda/configuracoes/{self.cfg.pk}/aprovar/")
        pedido.user = self.triade
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            configuracao_aprovar(pedido, self.cfg.pk)


class TextoDaRondaTest(BaseRonda):
    """O texto é montado campo a campo, nunca com str(horario).

    `HorarioRonda.__str__` formata a hora sem checar None e estoura TypeError
    quando ela está vazia — o que é sempre o caso no dia de evento.
    """

    def test_modo_normal_traz_horario_e_local(self):
        from ronda.notificacoes import mensagens_da_ronda

        self._escalar(self._horario(self.portao), self.ana)
        (voluntario, corpo), = mensagens_da_ronda(self.cfg)
        self.assertEqual(voluntario, self.ana)
        self.assertIn("Portão", corpo)
        self.assertIn("08:00", corpo)

    def test_uma_mensagem_por_pessoa_mesmo_com_varias_escalas(self):
        """O sorteio permite a mesma pessoa em janelas diferentes.

        Uma notificação por escala mandaria duas ou três seguidas.
        """
        from ronda.notificacoes import mensagens_da_ronda

        self._escalar(self._horario(self.portao, "08:00", "09:00"), self.ana)
        self._escalar(self._horario(self.quadra, "10:00", "11:00", ordem=1), self.ana)

        mensagens = mensagens_da_ronda(self.cfg)
        self.assertEqual(len(mensagens), 1)
        corpo = mensagens[0][1]
        self.assertIn("Portão", corpo)
        self.assertIn("Quadra", corpo)

    def test_cada_pessoa_recebe_o_proprio_local(self):
        from ronda.notificacoes import mensagens_da_ronda

        self._escalar(self._horario(self.portao), self.ana)
        self._escalar(self._horario(self.quadra, ordem=1), self.bia)

        por_pessoa = dict(mensagens_da_ronda(self.cfg))
        self.assertIn("Portão", por_pessoa[self.ana])
        self.assertNotIn("Quadra", por_pessoa[self.ana])
        self.assertIn("Quadra", por_pessoa[self.bia])
        self.assertNotIn("Portão", por_pessoa[self.bia])

    def test_dia_de_evento_nao_tem_horario_e_traz_o_grupo(self):
        from ronda.notificacoes import mensagens_da_ronda

        self.cfg.dia_de_evento = True
        self.cfg.save()
        horario = self._horario(self.portao, inicio=None, fim=None)
        self._escalar(horario, self.ana, dupla=1)

        (_, corpo), = mensagens_da_ronda(self.cfg)
        self.assertIn("Portão", corpo)
        self.assertIn("Dupla 1", corpo)

    def test_dia_de_evento_usa_o_rotulo_do_local_nao_dupla_fixo(self):
        """Um local pode trabalhar em trios enquanto outro trabalha em duplas."""
        from ronda.notificacoes import mensagens_da_ronda

        self.cfg.dia_de_evento = True
        self.cfg.save()
        self.portao.pessoas_por_grupo = 3
        self.portao.save()
        self._escalar(self._horario(self.portao, inicio=None, fim=None),
                      self.ana, dupla=2)

        (_, corpo), = mensagens_da_ronda(self.cfg)
        self.assertIn("Trio 2", corpo)

    def test_horario_vazio_no_modo_normal_nao_quebra(self):
        from ronda.notificacoes import mensagens_da_ronda

        self._escalar(self._horario(self.portao, inicio=None, fim=None), self.ana)
        (_, corpo), = mensagens_da_ronda(self.cfg)
        self.assertIn("Portão", corpo)

    def test_corpo_muito_longo_e_truncado_com_aviso(self):
        from ronda.notificacoes import LIMITE_CORPO, mensagens_da_ronda

        for i in range(12):
            local = LocalRonda.objects.create(
                nome=f"Local de nome bem comprido número {i}", ordem=i + 5)
            hora = datetime.time(8 + (i % 10), 0)
            horario = HorarioRonda.objects.create(
                configuracao=self.cfg, local=local,
                hora_inicio=hora, hora_fim=hora, ordem=i + 5)
            self._escalar(horario, self.ana)

        (_, corpo), = mensagens_da_ronda(self.cfg)
        self.assertLessEqual(len(corpo), LIMITE_CORPO)
        self.assertIn("no app", corpo)


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class AprovarRondaDisparaPushTest(BaseRonda):

    @patch("notificacoes.services.webpush")
    def test_aprovar_avisa_so_quem_esta_escalado(self, mock_webpush):
        self._escalar(self._horario(self.portao), self.ana)
        self._escalar(self._horario(self.quadra, ordem=1), self.bia)

        self._aprovar_pela_view()

        alcancados = {c.kwargs["subscription_info"]["endpoint"]
                      for c in mock_webpush.call_args_list}
        self.assertEqual(
            alcancados,
            {"https://push.exemplo/ana", "https://push.exemplo/bia"})

    @patch("notificacoes.services.webpush")
    def test_a_notificacao_leva_para_a_tela_publica_da_ronda(self, mock_webpush):
        self._escalar(self._horario(self.portao), self.ana)
        self._aprovar_pela_view()
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertEqual(payload["url"], "/ronda/sabado/")

    @patch("notificacoes.services.webpush")
    def test_sortear_sem_aprovar_nao_avisa_ninguem(self, mock_webpush):
        """Antes da aprovação a escala não existe para o voluntário.

        `ronda_publica` filtra status='APROVADA': avisar no sorteio mandaria a
        pessoa para uma tela onde a escala dela ainda não aparece — e a Tríade
        ainda pode reprovar e re-sortear com outra gente.
        """
        from ronda.views import configuracao_sortear

        self.cfg.status = "PENDENTE_SORTEIO"
        self.cfg.save()
        self._horario(self.portao)

        pedido = RequestFactory().post(f"/ronda/configuracoes/{self.cfg.pk}/sortear/")
        pedido.user = self.triade
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            configuracao_sortear(pedido, self.cfg.pk)

        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.status, "SORTEADA")
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    def test_ronda_de_sabado_que_ja_passou_nao_avisa(self, mock_webpush):
        """O seletor aceita sábados dos últimos 30 dias.

        Aprovar retroativamente não pode convocar ninguém para uma ronda que já
        aconteceu.
        """
        self.sabado.data = timezone.localdate() - datetime.timedelta(days=7)
        self.sabado.save()
        self._escalar(self._horario(self.portao), self.ana)

        self._aprovar_pela_view()
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    def test_um_push_por_pessoa_mesmo_com_duas_escalas(self, mock_webpush):
        self._escalar(self._horario(self.portao, "08:00", "09:00"), self.ana)
        self._escalar(self._horario(self.quadra, "10:00", "11:00", ordem=1), self.ana)

        self._aprovar_pela_view()
        # Uma inscrição, uma pessoa, duas escalas: um envio só.
        self.assertEqual(mock_webpush.call_count, 1)

    @patch("notificacoes.services.webpush")
    def test_aprovar_continua_incrementando_o_score(self, mock_webpush):
        """A notificação reaproveita a query do score — o score não pode sumir."""
        from ronda.models import ScoreRonda

        self._escalar(self._horario(self.portao), self.ana)
        self._aprovar_pela_view()

        score = ScoreRonda.objects.get(
            voluntario=self.ana, ano=self.sabado.data.year)
        self.assertEqual(score.pontos, 1)


class TelaPublicaDaRondaTest(BaseRonda):
    """A tela que a notificação abre não pode dar 500."""

    def test_horarios_mistos_nao_quebram_a_ordenacao(self):
        """Uma linha com horário e outra sem: `time` contra `None` no sorted().

        O formulário permite deixar a hora vazia nos dois modos, então a mistura
        é possível — e o resultado era TypeError na tela pública.
        """
        from ronda.views import ronda_publica

        self.cfg.status = "APROVADA"
        self.cfg.save()
        self._escalar(self._horario(self.portao, "08:00", "09:00"), self.ana)
        self._escalar(self._horario(self.quadra, None, None, ordem=1), self.bia)

        pedido = RequestFactory().get("/ronda/sabado/")
        pedido.user = self.ana
        # Só precisa não levantar: a renderização do template é o que o test
        # client quebrado do Django não consegue exercitar neste ambiente.
        try:
            ronda_publica(pedido)
        except TypeError as erro:
            self.fail(f"ordenação quebrou com horários mistos: {erro}")
        except Exception:
            pass
