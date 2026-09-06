"""Todo comando de gerência tem que pelo menos IMPORTAR.

Existe por causa de um erro real: um `sincronizar_acervo_drive.py` com f-string
quebrada foi para o servidor e só estourou quando alguém rodou o comando. A
suíte inteira passou verde antes disso porque o Django carrega comando de
gerência SOB DEMANDA — nenhum teste importava aquele arquivo, e `manage.py
check` também não o carrega.

É o teste mais barato que existe e cobre a classe inteira de erro: sintaxe,
import quebrado, nome trocado num `from ... import`.
"""
import pkgutil
from importlib import import_module

from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.test import SimpleTestCase


def _comandos_do_projeto():
    """(app, nome_do_comando) de cada comando escrito NESTE projeto.

    Comando do próprio Django e de biblioteca de terceiro fica de fora: não é
    nosso, e uma falha ali não é coisa que a gente conserte aqui.
    """
    nossos = {config.name for config in apps.get_app_configs()
              if not config.name.startswith('django.')
              and 'site-packages' not in (config.path or '')}

    encontrados = []
    for config in apps.get_app_configs():
        if config.name not in nossos:
            continue
        try:
            pasta = import_module(f'{config.name}.management.commands')
        except ModuleNotFoundError:
            continue
        for modulo in pkgutil.iter_modules(pasta.__path__):
            encontrados.append((config.name, modulo.name))
    return encontrados


class ComandosImportamTest(SimpleTestCase):

    def test_existe_comando_para_conferir(self):
        """Guarda contra a descoberta parar de funcionar e o teste virar vazio."""
        self.assertGreater(len(_comandos_do_projeto()), 5)

    def test_todo_comando_do_projeto_importa(self):
        falhas = []
        for app, nome in _comandos_do_projeto():
            try:
                load_command_class(app, nome)
            except Exception as erro:
                falhas.append(f'{app}.{nome}: {type(erro).__name__}: {erro}')

        self.assertEqual(falhas, [], 'Comando(s) que não importam:\n' +
                         '\n'.join(falhas))

    def test_todo_comando_do_projeto_aceita_ser_descrito(self):
        """`--help` monta os argumentos: pega erro em add_arguments também.

        Um `parser.add_argument` com dest repetido ou default incoerente só
        aparece nessa hora.
        """
        falhas = []
        for app, nome in _comandos_do_projeto():
            try:
                comando = load_command_class(app, nome)
                comando.create_parser('manage.py', nome)
            except Exception as erro:
                falhas.append(f'{app}.{nome}: {type(erro).__name__}: {erro}')

        self.assertEqual(falhas, [], 'Comando(s) com parser quebrado:\n' +
                         '\n'.join(falhas))

    def test_o_registro_de_comandos_do_django_enxerga_os_nossos(self):
        registrados = get_commands()
        for app, nome in _comandos_do_projeto():
            self.assertIn(nome, registrados,
                          f'{app}.{nome} não aparece em manage.py help')
