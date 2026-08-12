"""Varredura na web: procura edital em site que ninguém mapeou.

O irmão deste comando, `buscar_editais`, lê fontes já cadastradas — só acha
onde alguém já sabia procurar. Este aqui faz o contrário: pergunta a um
buscador e colhe de qualquer domínio. É a parte que descobre o desconhecido.

Uso:
    python manage.py varrer_editais
    python manage.py varrer_editais --minimo 3 --limite 30
    python manage.py varrer_editais --consulta "FIA CMDCA" --dry-run

Feito para rodar em tarefa agendada no PythonAnywhere (conta paga — a gratuita
só alcança sites de uma lista branca e a busca não funcionaria).

Duas regras mandam aqui, as mesmas do outro comando:

1. Uma consulta que falha não derruba as outras — o motivo fica gravado na
   consulta e aparece na tela.
2. Edital que já existe não é sobrescrito: status, requisitos, observações e
   responsável são trabalho humano.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from editais import busca, coleta
from editais.models import ConsultaBusca, PalavraChave


class Command(BaseCommand):
    help = 'Pergunta à web e guarda os editais que combinam com o perfil do PCF.'

    def add_arguments(self, parser):
        parser.add_argument('--consulta', default='',
                            help='Roda só nas consultas cujo texto contém isto.')
        parser.add_argument('--minimo', type=int, default=3,
                            help='Nota mínima para guardar (padrão: 3, mais exigente '
                                 'que o das fontes fixas porque a web traz mais ruído).')
        parser.add_argument('--limite', type=int, default=20,
                            help='Quantos resultados pedir por consulta (padrão: 20).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Só mostra o que faria, sem gravar edital nenhum.')
        parser.add_argument('--sem-pausa', action='store_true',
                            help='Não espera entre as consultas. Use só em teste: '
                                 'sem a pausa o buscador tende a bloquear.')

    def handle(self, *args, **opcoes):
        texto, minimo = opcoes['consulta'], opcoes['minimo']
        limite, simular, sem_pausa = opcoes['limite'], opcoes['dry_run'], opcoes['sem_pausa']

        consultas = ConsultaBusca.objects.filter(ativo=True)
        if texto:
            consultas = consultas.filter(termo__icontains=texto)
        consultas = list(consultas)
        if not consultas:
            self.stdout.write(self.style.WARNING(
                'Nenhuma consulta ativa. Cadastre em /editais/consultas/ ou rode '
                '"python manage.py seed_editais".'))
            return

        palavras = list(PalavraChave.objects.filter(ativo=True))
        if not palavras:
            self.stdout.write(self.style.WARNING(
                'Nenhuma palavra-chave ativa: sem elas tudo tira nota zero. '
                'Rode "python manage.py seed_editais".'))

        self.stdout.write(f'Perguntando {len(consultas)} coisa(s) à web...')
        itens, erros = busca.varrer(consultas, limite_por_consulta=limite,
                                    pausar=not sem_pausa)

        # Agrupa por consulta só para o relatório sair legível por pergunta.
        por_consulta = {}
        for item in itens:
            por_consulta.setdefault(item['consulta'], []).append(item)

        novos = ignorados = 0
        dominios_novos = {}

        for consulta in consultas:
            achados = por_consulta.get(consulta, [])
            novos_da_consulta = ignorados_da_consulta = 0

            for item in achados:
                resultado, _ = coleta.registrar_item(
                    item, palavras, minimo, consulta=consulta,
                    origem='BUSCA', simular=simular)
                if resultado == 'ignorado':
                    ignorados_da_consulta += 1
                elif resultado == 'novo':
                    novos_da_consulta += 1
                    dominio = busca.dominio_de(item['link'])
                    dominios_novos[dominio] = dominios_novos.get(dominio, 0) + 1

            novos += novos_da_consulta
            ignorados += ignorados_da_consulta

            erro = erros.get(consulta)
            if not simular:
                consulta.ultima_busca = timezone.now()
                consulta.ultimo_erro = erro or ''
                consulta.resultados_ultima_busca = len(achados)
                consulta.save(update_fields=['ultima_busca', 'ultimo_erro',
                                             'resultados_ultima_busca'])

            if erro:
                self.stdout.write(self.style.ERROR(f'  "{consulta.termo}": falhou — {erro}'))
            else:
                linha = (f'  "{consulta.termo}": {len(achados)} resultado(s), '
                         f'{novos_da_consulta} novo(s), '
                         f'{ignorados_da_consulta} fora do perfil')
                self.stdout.write(self.style.SUCCESS(linha) if novos_da_consulta else linha)

        resumo = (f'{"[simulação] " if simular else ""}'
                  f'{len(consultas)} consulta(s), {len(itens)} resultado(s), '
                  f'{novos} edital(is) novo(s), {ignorados} abaixo da nota {minimo}.')
        self.stdout.write(self.style.SUCCESS(resumo) if novos else resumo)

        if erros:
            self.stdout.write(self.style.WARNING(
                f'{len(erros)} consulta(s) com erro — confira em /editais/consultas/.'))

        # O achado mais útil da varredura não é o edital solto: é descobrir QUE
        # SITE publica edital com frequência. Esse vira fonte fixa e passa a ser
        # lido todo dia, de graça.
        if dominios_novos:
            self.stdout.write('\nDomínios que trouxeram edital novo '
                              '(vale cadastrar como fonte fixa em /editais/fontes/):')
            for dominio, quantos in sorted(dominios_novos.items(),
                                           key=lambda par: -par[1]):
                self.stdout.write(f'  {quantos:>3}x  {dominio}')
