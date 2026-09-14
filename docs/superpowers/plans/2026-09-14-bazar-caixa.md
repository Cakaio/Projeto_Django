# Bazar — a tela vira caixa — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar a tela de atendimento do Bazar operável por quem nunca a viu, num celular, com fila na frente — e garantir um plano B em papel que funciona sem servidor.

**Architecture:** O domínio (`bazar/regras.py`) continua sendo a única autoridade e sofre cirurgia, não reescrita: `finalizar_retirada` ganha `quando`, `etapa`, `token` e passa a promover rascunho. A camada de tela (`atendimento.html` + `bazar-atendimento.js`) é reescrita do zero, porque é onde mora todo defeito. O kit de papel é uma rota de impressão independente, sem `base.html`.

**Tech Stack:** Django 4.2.27, templates server-side, JS vanilla sem build, Tailwind compilado à parte (`tailwindcss/`), `openpyxl==3.1.5` para `.xlsx`.

**Spec:** `docs/superpowers/specs/2026-09-13-bazar-caixa-design.md`

## Global Constraints

- **Idioma:** toda UI, model, comentário e mensagem em **português do Brasil**.
- **O test client do Django quebra ao renderizar template neste ambiente** (Python 3.14, `AttributeError: 'super' object has no attribute 'dicts'`). Testes de tela usam `RequestFactory` chamando a view direto. POST que redireciona (302) pode usar `Client`.
- **Rodar testes:** `PYTHONPATH="$SP" python manage.py test <app> --settings=settings_sqlite`, com `$SP` = diretório de scratchpad da sessão.
- **Baseline antes de julgar regressão:** medir com `git stash` na mesma sessão. Baseline atual: `bazar` 0 erros; `supply` 6; `adm` 10; `forms_pcf` 11.
- **Regras de negócio que não podem ser quebradas:** 2ª etapa sem limite de pontos (`saldo_de` devolve `None`); estoque **avisa, não bloqueia**; alerta de estoque medido **antes** do `bulk_create`; `pontos_unitarios` é cópia; rascunho (`finalizada_em` nulo) não consome nada; um Bazar aberto por vez; troca de etapa manual.
- **`ItemRetirada.save()` calcula `pontos_total`, mas `bulk_create` NÃO chama `save()`.** Todo caminho novo de gravação precisa calcular explicitamente.
- **`timezone.localdate()` para datas, `timezone.now()` para datetimes.**
- **Commits:** mensagem em português, terminando com `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `tailwindcss/tailwind.config.js` | *modificar* — incluir os apps novos no `content` |
| `TESTE/versao_estatica.py` | *modificar* — observar o JS do Bazar |
| `bazar/models.py` | *modificar* — `SalaDoBazar`, campos de visitante/token/cancelamento/`sem_retirada`, numerações copiadas, constraint por etapa |
| `bazar/migrations/0002_caixa.py` | *criar* — schema + dados das salas existentes |
| `bazar/regras.py` | *modificar* — `finalizar_retirada` com `quando`/`etapa`/`token`; `conferir_pedido` aceita sacola vazia marcada; `cancelar_retirada` |
| `bazar/views.py` | *modificar* — busca com idade/numerações, `finalizar` com `IntegrityError` e token, `cancelar` |
| `bazar/templates/bazar/atendimento.html` | *reescrever* |
| `static/js/bazar-atendimento.js` | *reescrever* |
| `bazar/templates/bazar/painel.html` | *reescrever em `.pcf-*`* |
| `bazar/papelaria.py` | *criar* — montagem das folhas do kit de papel, longe de HTTP |
| `bazar/templates/bazar/kit_papel.html` | *criar* — HTML autônomo de impressão |
| `bazar/tests_regras.py` | *modificar* — regras novas |
| `bazar/tests_telas.py` | *reescrever as partes que afirmam sobre o HTML antigo* |
| `bazar/tests_papel.py` | *criar* |

---

## Task 1: As duas linhas de configuração

Primeiro de tudo. As duas quebram o resto em silêncio, e nenhum teste do projeto as pega hoje.

**Files:**
- Modify: `tailwindcss/tailwind.config.js:26-29`
- Modify: `TESTE/versao_estatica.py:30-31`
- Test: `TESTE/tests_estaticos.py` (criar)

**Interfaces:**
- Consumes: nada.
- Produces: `ARQUIVOS_OBSERVADOS` passa a conter `js/bazar-atendimento.js`; o `content` do Tailwind passa a conter `../bazar/**/*.html`, `../acervo/**/*.html`, `../estudio/**/*.html`, `../notificacoes/**/*.html`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `TESTE/tests_estaticos.py`:

```python
"""Duas linhas de configuração que quebram telas em silêncio.

Nenhuma delas dá erro quando está errada: o Tailwind purga a classe e a tela
fica sem estilo; o carimbo de versão não muda e o navegador serve o JS velho.
Só um teste pega.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from TESTE.versao_estatica import ARQUIVOS_OBSERVADOS

APPS_COM_TEMPLATE = [
    'templates', 'atendido', 'voluntario', 'semanario', 'sabado', 'supply',
    'adm', 'forms_pcf', 'ronda', 'gerenciamento', 'parceiros', 'editais',
    'revista', 'projetos', 'acervo', 'bazar', 'estudio', 'notificacoes',
]


class ConteudoDoTailwindTest(SimpleTestCase):
    """Classe usada SÓ num app fora do `content` é purgada sem erro nenhum."""

    def test_todo_app_com_template_esta_no_content(self):
        config = (Path(settings.BASE_DIR) / 'tailwindcss' / 'tailwind.config.js'
                  ).read_text(encoding='utf-8')
        bloco = config[config.index('content:'):config.index(']', config.index('content:'))]
        faltando = [app for app in APPS_COM_TEMPLATE if f'/{app}/' not in bloco]
        self.assertEqual(faltando, [], f'apps fora do content do Tailwind: {faltando}')


class CarimboDeVersaoTest(SimpleTestCase):
    """JS fora de ARQUIVOS_OBSERVADOS não muda o `?v=`: o navegador serve o velho."""

    def test_todo_js_referenciado_em_template_e_observado(self):
        raiz = Path(settings.BASE_DIR)
        referenciados = set()
        for caminho in raiz.rglob('*.html'):
            if any(parte in ('venv', 'node_modules', 'staticfiles')
                   for parte in caminho.parts):
                continue
            texto = caminho.read_text(encoding='utf-8', errors='replace')
            for achado in re.findall(r"static\s+'(js/[^']+\.js)'", texto):
                referenciados.add(achado)

        faltando = sorted(referenciados - set(ARQUIVOS_OBSERVADOS))
        self.assertEqual(
            faltando, [],
            f'JS referenciado em template e fora de ARQUIVOS_OBSERVADOS: {faltando}')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test TESTE.tests_estaticos --settings=settings_sqlite`
Expected: FAIL nos dois — `apps fora do content: ['acervo', 'bazar', 'estudio', 'notificacoes']` e `JS referenciado e fora: ['js/bazar-atendimento.js']`.

> Se o segundo teste acusar OUTROS arquivos além do `bazar-atendimento.js`, acrescente todos: são a mesma armadilha e o teste está certo.

- [ ] **Step 3: Corrigir o Tailwind**

Em `tailwindcss/tailwind.config.js`, dentro de `content`, depois de `"../projetos/**/*.html",`:

```js
    "../acervo/**/*.html",
    "../bazar/**/*.html",
    "../estudio/**/*.html",
    "../notificacoes/**/*.html",
```

- [ ] **Step 4: Corrigir o carimbo de versão**

Em `TESTE/versao_estatica.py`, trocar a tupla:

```python
# Só o que é compartilhado por todas as telas, MAIS o JS de tela que muda e
# precisa chegar ao aparelho: sem estar aqui, publicar um JS corrigido não
# entrega nada a quem já abriu o site — foi o que aconteceu com o Bazar.
ARQUIVOS_OBSERVADOS = ('css/pcf.css', 'js/pcf-fx.js', 'js/pcf-estudio.js',
                       'js/pcf-combo.js', 'js/bazar-atendimento.js')
```

- [ ] **Step 5: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test TESTE.tests_estaticos --settings=settings_sqlite`
Expected: OK (2 testes)

- [ ] **Step 6: Recompilar o CSS**

Run: `npx tailwindcss -c tailwindcss/tailwind.config.js -i tailwindcss/input.css -o static/css/pcf.css --minify`
Expected: escreve `static/css/pcf.css`. Se o `npx` não estiver disponível na máquina, registrar na mensagem do commit que o CSS precisa ser recompilado no deploy.

- [ ] **Step 7: Commit**

```bash
git add tailwindcss/tailwind.config.js TESTE/versao_estatica.py TESTE/tests_estaticos.py static/css/pcf.css
git commit -m "fix(config): apps novos no Tailwind e JS do Bazar no carimbo de versao"
```

---

## Task 2: Salas do Bazar

Hoje `sala_do_bazar` é texto livre redigitado a cada criança — preenchido nas cinco primeiras e vazio no resto da manhã. Vira lista fixa, escolhida uma vez por aparelho.

**Files:**
- Modify: `bazar/models.py`
- Create: `bazar/migrations/0002_salas_do_bazar.py` (gerada)
- Modify: `bazar/admin.py`
- Test: `bazar/tests_regras.py`

**Interfaces:**
- Consumes: nada.
- Produces: `bazar.models.SalaDoBazar` com campos `bazar` (FK), `nome` (CharField 30), `ordem` (PositiveSmallIntegerField), `ativo` (Boolean). `Retirada.sala` (FK nullable a `SalaDoBazar`, `on_delete=PROTECT`, `related_name="retiradas"`). O CharField `Retirada.sala_do_bazar` **permanece** e passa a ser histórico.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `bazar/tests_regras.py`:

```python
class SalaDoBazarTest(TestCase):
    """A sala vira lista fixa: o voluntário toca uma vez, não digita 80 vezes."""

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="Bazar 2026", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)

    def test_salas_sao_por_bazar_e_ordenadas(self):
        from bazar.models import SalaDoBazar
        SalaDoBazar.objects.create(bazar=self.bazar, nome="Recepção", ordem=2)
        SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 1", ordem=1)
        self.assertEqual(
            [s.nome for s in SalaDoBazar.objects.filter(bazar=self.bazar)],
            ["Sala 1", "Recepção"])

    def test_duas_salas_com_o_mesmo_nome_no_mesmo_bazar_nao_entram(self):
        from django.db import IntegrityError
        from bazar.models import SalaDoBazar
        SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 1", ordem=1)
        with self.assertRaises(IntegrityError):
            SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 1", ordem=2)

    def test_o_texto_livre_antigo_continua_existindo(self):
        """Migração não apaga histórico: o CharField vira registro do que foi
        digitado antes de existir lista."""
        campo = Retirada._meta.get_field("sala_do_bazar")
        self.assertTrue(campo.blank)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_regras.SalaDoBazarTest --settings=settings_sqlite`
Expected: FAIL — `ImportError: cannot import name 'SalaDoBazar'`

- [ ] **Step 3: Criar o modelo**

Em `bazar/models.py`, depois de `Categoria`:

```python
class SalaDoBazar(models.Model):
    """As salas físicas onde se confere, no dia.

    Existe para o voluntário TOCAR em vez de digitar. O campo de texto livre que
    isto substitui era redigitado a cada criança: na prática era preenchido nas
    cinco primeiras e ficava vazio no resto da manhã, e a coluna do relatório
    que serve para achar a origem de uma divergência vinha vazia justamente
    quando era necessária.
    """
    bazar = models.ForeignKey(Bazar, on_delete=models.CASCADE,
                              related_name="salas")
    nome = models.CharField(max_length=30, help_text="Ex.: Sala 1, Recepção.")
    ordem = models.PositiveSmallIntegerField(
        default=0, help_text="Ordem dos botões na tela.")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["bazar", "nome"],
                                    name="uma_sala_por_nome_no_bazar"),
        ]
        verbose_name = "Sala do Bazar"
        verbose_name_plural = "Salas do Bazar"

    def __str__(self):
        return self.nome
```

E em `Retirada`, junto do `sala_do_bazar` existente:

```python
    # A sala escolhida na lista. O CharField acima fica como histórico do tempo
    # em que era texto livre — apagá-lo reescreveria relatório já lido.
    sala = models.ForeignKey(
        SalaDoBazar, on_delete=models.PROTECT, null=True, blank=True,
        related_name="retiradas")
```

- [ ] **Step 4: Gerar a migração**

Run: `python manage.py makemigrations bazar --name salas_do_bazar`
Expected: `Create model SalaDoBazar` + `Add field sala to retirada`

- [ ] **Step 5: Registrar no admin**

Em `bazar/admin.py`, dentro de `BazarAdmin`, acrescentar o inline:

```python
class SalaDoBazarInline(admin.TabularInline):
    """As salas físicas, configuradas junto do Bazar. `extra=3` porque três é o
    número que a coordenação usa na prática."""
    model = SalaDoBazar
    extra = 3
```

e incluir `SalaDoBazarInline` na lista `inlines` de `BazarAdmin` (junto do `CategoriaInline` que já existe).

- [ ] **Step 6: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK, sem regressão

- [ ] **Step 7: Commit**

```bash
git add bazar/models.py bazar/migrations/ bazar/admin.py bazar/tests_regras.py
git commit -m "feat(bazar): salas fisicas viram lista, em vez de texto redigitado"
```

---

## Task 3: Visitante, 2ª etapa livre, e "veio e não levou nada"

As três decisões do cliente, juntas porque todas mexem na mesma constraint e na mesma função de gravação — um revisor não consegue aprovar uma e rejeitar a outra.

**Files:**
- Modify: `bazar/models.py`
- Create: `bazar/migrations/0003_visitante_e_sem_retirada.py` (gerada)
- Modify: `bazar/regras.py`
- Test: `bazar/tests_regras.py`

**Interfaces:**
- Consumes: `SalaDoBazar` da Task 2.
- Produces:
  - `Retirada.atendido` passa a `null=True, blank=True`.
  - `Retirada.visitante_nome` (CharField 120, blank), `Retirada.visitante_motivo` (CharField 200, blank).
  - `Retirada.sem_retirada` (Boolean, default False).
  - `Retirada.e_visitante` (property) → `bool(self.visitante_nome)`.
  - `Retirada.nome_de_quem_levou` (property) → nome do atendido ou do visitante.
  - `UniqueConstraint` `uma_retirada_finalizada_por_etapa` passa a ter `condition=Q(finalizada_em__isnull=False, etapa=Etapa.PRIMEIRA, atendido__isnull=False)`.
  - `conferir_pedido(bazar, atendido, pedido, sem_retirada=False)` aceita sacola vazia quando `sem_retirada=True`.
  - `finalizar_retirada(..., sem_retirada=False, visitante_nome="", visitante_motivo="")`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar em `bazar/tests_regras.py`:

```python
class VisitanteTest(TestCase):
    """Criança não cadastrada pode levar sacola, em registro SEPARADO.

    Não vira Atendido: a regra de não existir segunda verdade sobre a mesma
    criança continua valendo. O registro existe para o caso sair do escuro e
    para dar para contar quantas exceções houve.
    """

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="B", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)
        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1)
        self.voluntario = Voluntario.objects.create_user(
            username="vol_vis", password="pw", area="EVENTOS")

    def test_visitante_grava_sem_atendido(self):
        retirada, total, _ = finalizar_retirada(
            bazar=self.bazar, atendido=None,
            pedido={self.camiseta.pk: 2}, conferido_por=self.voluntario,
            visitante_nome="Irmão do João",
            visitante_motivo="chegou com a mãe, não é matriculado")
        self.assertIsNone(retirada.atendido)
        self.assertTrue(retirada.e_visitante)
        self.assertEqual(retirada.nome_de_quem_levou, "Irmão do João")
        self.assertEqual(total, 2)

    def test_visitante_sem_nome_e_recusado(self):
        """Sem nome não há registro: seria uma linha anônima que ninguém
        consegue conferir depois."""
        with self.assertRaises(RetiradaInvalida):
            finalizar_retirada(
                bazar=self.bazar, atendido=None,
                pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario,
                visitante_nome="  ")

    def test_visitante_respeita_a_cota(self):
        with self.assertRaises(RetiradaInvalida):
            finalizar_retirada(
                bazar=self.bazar, atendido=None,
                pedido={self.camiseta.pk: 99}, conferido_por=self.voluntario,
                visitante_nome="Irmão do João")


class SegundaEtapaSemTravaTest(TestCase):
    """Na 2ª etapa o objetivo é esvaziar o estoque: a trava de passagem única
    não protege ninguém e só produz erro para quem está certo."""

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="B", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.SEGUNDA, cota_inicial=5)
        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1)
        self.joao = Atendido.objects.create(
            nome="João", sala="VIOLETA", data_nascimento=date(2015, 1, 1))
        self.voluntario = Voluntario.objects.create_user(
            username="vol_2a", password="pw", area="EVENTOS")

    def _retirar(self):
        return finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario)

    def test_mesma_crianca_passa_duas_vezes_na_segunda_etapa(self):
        self._retirar()
        self._retirar()
        self.assertEqual(
            Retirada.objects.filter(bazar=self.bazar, atendido=self.joao,
                                    finalizada_em__isnull=False).count(), 2)

    def test_na_primeira_etapa_a_trava_continua(self):
        self.bazar.etapa = Bazar.Etapa.PRIMEIRA
        self.bazar.save()
        self._retirar()
        with self.assertRaises(RetiradaInvalida):
            self._retirar()


class VeioENaoLevouNadaTest(TestCase):
    """Quem chegou e não achou nada do tamanho dela é a evidência mais direta
    de que faltou tamanho — e hoje é invisível, porque sacola vazia é recusada."""

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="B", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)
        Categoria.objects.create(bazar=self.bazar, nome="Camiseta", pontos=1)
        self.joao = Atendido.objects.create(
            nome="João", sala="VIOLETA", data_nascimento=date(2015, 1, 1))
        self.voluntario = Voluntario.objects.create_user(
            username="vol_nada", password="pw", area="EVENTOS")

    def test_registra_comparecimento_sem_peca(self):
        retirada, total, _ = finalizar_retirada(
            bazar=self.bazar, atendido=self.joao, pedido={},
            conferido_por=self.voluntario, sem_retirada=True)
        self.assertTrue(retirada.sem_retirada)
        self.assertEqual(total, 0)
        self.assertEqual(retirada.total_pecas, 0)

    def test_sacola_vazia_sem_marcar_continua_recusada(self):
        """Vazio por engano e vazio de propósito são coisas diferentes."""
        with self.assertRaises(RetiradaInvalida):
            finalizar_retirada(
                bazar=self.bazar, atendido=self.joao, pedido={},
                conferido_por=self.voluntario)

    def test_comparecimento_sem_peca_nao_gasta_ponto(self):
        finalizar_retirada(
            bazar=self.bazar, atendido=self.joao, pedido={},
            conferido_por=self.voluntario, sem_retirada=True)
        self.assertEqual(saldo_de(self.bazar, self.joao), 5)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_regras --settings=settings_sqlite`
Expected: FAIL nos três novos — `IntegrityError: NOT NULL constraint failed: bazar_retirada.atendido_id`, `RetiradaInvalida` na segunda passagem, e `TypeError: unexpected keyword argument 'sem_retirada'`.

- [ ] **Step 3: Mexer no modelo**

Em `bazar/models.py`, `Retirada`:

```python
    atendido = models.ForeignKey("atendido.Atendido", on_delete=models.PROTECT,
                                 null=True, blank=True,
                                 related_name="retiradas_no_bazar")

    # Criança que apareceu e não é Atendido ativo. Registro SEPARADO de
    # propósito: não vira ficha, para não criar segunda verdade sobre a mesma
    # criança. Existe para o caso sair do escuro e para dar para contar.
    visitante_nome = models.CharField(max_length=120, blank=True)
    visitante_motivo = models.CharField(
        max_length=200, blank=True,
        help_text="Por que foi atendida fora do cadastro.")

    # Veio, foi conferida e não achou nada do tamanho dela. Conta como
    # comparecimento e não como retirada — são perguntas diferentes.
    sem_retirada = models.BooleanField(default=False)
```

E a constraint:

```python
            # A trava contra passar duas vezes vale só na 1ª ETAPA: na 2ª o
            # objetivo declarado é esvaziar o estoque, e ali ela só produziria
            # erro para quem está certo (decisão da liderança, 09/2026).
            # `atendido__isnull=False` porque visitante não tem ficha para
            # travar — a trava dele é a conferência humana.
            models.UniqueConstraint(
                fields=["bazar", "atendido", "etapa"],
                condition=models.Q(finalizada_em__isnull=False,
                                   etapa="PRIMEIRA",
                                   atendido__isnull=False),
                name="uma_retirada_finalizada_na_primeira_etapa",
            ),
```

E as propriedades:

```python
    @property
    def e_visitante(self):
        return bool(self.visitante_nome)

    @property
    def nome_de_quem_levou(self):
        """O nome que vale para tela e relatório, venha da ficha ou da mão."""
        if self.atendido_id:
            return self.atendido.nome
        return self.visitante_nome or "—"
```

E `__str__` passa a usar `nome_de_quem_levou` (hoje quebra com `atendido` nulo):

```python
    def __str__(self):
        return f"{self.nome_de_quem_levou} — {self.get_etapa_display()}"
```

- [ ] **Step 4: Gerar a migração**

Run: `python manage.py makemigrations bazar --name visitante_e_sem_retirada`
Expected: altera `atendido`, acrescenta 3 campos, remove a constraint antiga e cria a nova.

- [ ] **Step 5: Mexer nas regras**

Em `bazar/regras.py`:

`ja_retirou_nesta_etapa` passa a respeitar a etapa:

```python
def ja_retirou_nesta_etapa(bazar, atendido):
    """A trava contra passar duas vezes pela mesma fila.

    Só vale na 1ª etapa: na 2ª o objetivo é esvaziar o estoque, e a família que
    volta na arara está certa. Visitante não tem ficha para travar.
    """
    if bazar.etapa != Bazar.Etapa.PRIMEIRA or atendido is None:
        return False
    return Retirada.objects.filter(
        bazar=bazar, atendido=atendido, etapa=bazar.etapa,
        finalizada_em__isnull=False,
    ).exists()
```

`conferir_pedido` ganha `sem_retirada` e trata atendido nulo:

```python
def conferir_pedido(bazar, atendido, pedido, sem_retirada=False):
    if not bazar.esta_aberto:
        raise RetiradaInvalida("O Bazar não está aberto para retirada.")

    if ja_retirou_nesta_etapa(bazar, atendido):
        raise RetiradaInvalida(
            f"{atendido.nome} já finalizou a retirada desta etapa.")

    linhas = []
    categorias = {
        categoria.pk: categoria
        for categoria in Categoria.objects.filter(bazar=bazar, ativo=True)
    }

    for categoria_id, quantidade in pedido.items():
        categoria = categorias.get(int(categoria_id))
        if categoria is None:
            raise RetiradaInvalida("Categoria não encontrada neste Bazar.")
        quantidade = int(quantidade)
        if quantidade <= 0:
            continue
        linhas.append({
            "categoria": categoria,
            "quantidade": quantidade,
            "pontos_unitarios": categoria.pontos,
            "pontos_total": categoria.pontos * quantidade,
        })

    if not linhas:
        # Vazio POR ENGANO e vazio DE PROPÓSITO são coisas diferentes. O
        # segundo é comparecimento sem retirada, e é dado que a coordenação
        # precisa; o primeiro é toque errado e continua recusado.
        if sem_retirada:
            return [], 0
        raise RetiradaInvalida("Nenhuma peça foi registrada.")

    if sem_retirada:
        raise RetiradaInvalida(
            'Marque "não levou nada" OU registre peças — não os dois.')

    total = sum(linha["pontos_total"] for linha in linhas)

    if bazar.desconta_pontos and atendido is not None:
        saldo = saldo_de(bazar, atendido)
        if total > saldo:
            raise RetiradaInvalida(
                f"Pontos insuficientes. {atendido.nome} tem {saldo} "
                f"ponto{'s' if saldo != 1 else ''} e a sacola soma {total}.")

    if bazar.desconta_pontos and atendido is None and total > bazar.cota_inicial:
        # Visitante não tem histórico, então a cota inteira é o limite.
        raise RetiradaInvalida(
            f"A cota é de {bazar.cota_inicial} pontos e a sacola soma {total}.")

    return linhas, total
```

`finalizar_retirada` ganha os parâmetros novos:

```python
@transaction.atomic
def finalizar_retirada(*, bazar, atendido, pedido, conferido_por,
                       sala=None, sala_do_bazar="",
                       retirado_por=Retirada.RetiradoPor.ATENDIDO,
                       retirado_por_nome="", sem_retirada=False,
                       visitante_nome="", visitante_motivo=""):
    """Grava a retirada inteira de uma vez. Ou tudo, ou nada."""
    visitante_nome = (visitante_nome or "").strip()

    if atendido is None and not visitante_nome:
        raise RetiradaInvalida(
            "Diga de quem é a retirada: escolha o atendido ou escreva o nome "
            "de quem veio sem cadastro.")

    linhas, total = conferir_pedido(bazar, atendido, pedido, sem_retirada)

    # Medido ANTES de gravar: depois do bulk_create os itens desta retirada já
    # contam como distribuídos, e quem consumisse exatamente o que restava
    # dispararia alerta indevido.
    alertas = estoque_estourado(linhas)

    retirada = Retirada.objects.create(
        bazar=bazar,
        atendido=atendido,
        etapa=bazar.etapa,
        sala=sala,
        sala_do_bazar=sala_do_bazar,
        conferido_por=conferido_por,
        retirado_por=retirado_por,
        retirado_por_nome=retirado_por_nome.strip(),
        cota_no_momento=bazar.cota_inicial,
        sem_retirada=sem_retirada,
        visitante_nome=visitante_nome,
        visitante_motivo=(visitante_motivo or "").strip(),
        finalizada_em=timezone.now(),
    )

    ItemRetirada.objects.bulk_create([
        ItemRetirada(
            retirada=retirada,
            categoria=linha["categoria"],
            quantidade=linha["quantidade"],
            pontos_unitarios=linha["pontos_unitarios"],
            # bulk_create NÃO chama save(): o total precisa vir calculado.
            pontos_total=linha["pontos_total"],
        )
        for linha in linhas
    ])

    return retirada, total, alertas
```

- [ ] **Step 6: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK. Se `tests_telas.py` quebrar por causa de `atendido` obrigatório, ajustar lá — o contrato mudou de propósito.

- [ ] **Step 7: Commit**

```bash
git add bazar/models.py bazar/migrations/ bazar/regras.py bazar/tests_regras.py bazar/tests_telas.py
git commit -m "feat(bazar): visitante, 2a etapa sem trava e comparecimento sem retirada"
```

---

## Task 4: Token de idempotência e desfazer

O reenvio depois de uma resposta perdida devolve o mesmo recibo, em vez de acusar a criança de ter passado duas vezes. E cancelar devolve a retirada ao rascunho — que o modelo já sabe fazer e ninguém usa.

**Files:**
- Modify: `bazar/models.py`
- Create: `bazar/migrations/0004_token_e_cancelamento.py` (gerada)
- Modify: `bazar/regras.py`
- Test: `bazar/tests_regras.py`

**Interfaces:**
- Consumes: tudo da Task 3.
- Produces:
  - `Retirada.token` (CharField 40, blank, `db_index=True`).
  - `Retirada.cancelada_em` (DateTime null), `Retirada.cancelada_por` (FK user null), `Retirada.motivo_cancelamento` (CharField 200 blank).
  - `finalizar_retirada(..., token="")` — com token repetido, devolve a retirada existente sem gravar de novo.
  - `cancelar_retirada(retirada, por, motivo) -> Retirada`.
  - `MINUTOS_PARA_DESFAZER = 2`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TokenDeIdempotenciaTest(TestCase):
    """Resposta perdida na rede não pode virar acusação contra a criança.

    Sem token, o reenvio bate na trava e devolve "já finalizou a retirada desta
    etapa" — que é mentira: quem repetiu foi o clique, não a criança.
    """

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="B", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)
        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1)
        self.joao = Atendido.objects.create(
            nome="João", sala="VIOLETA", data_nascimento=date(2015, 1, 1))
        self.voluntario = Voluntario.objects.create_user(
            username="vol_tok", password="pw", area="EVENTOS")

    def _retirar(self, token):
        return finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario,
            token=token)

    def test_mesmo_token_devolve_a_mesma_retirada(self):
        primeira, _, _ = self._retirar("abc-123")
        segunda, total, _ = self._retirar("abc-123")
        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(Retirada.objects.count(), 1)
        self.assertEqual(total, 1)

    def test_token_diferente_na_primeira_etapa_ainda_bate_na_trava(self):
        self._retirar("abc-123")
        with self.assertRaises(RetiradaInvalida):
            self._retirar("outro-456")


class CancelarRetiradaTest(TestCase):
    """Cancelar devolve a retirada ao rascunho — o modelo já sabe fazer isso.

    Rascunho não consome saldo nem estoque, e a UniqueConstraint tem
    `condition`, então a trava da etapa reabre sozinha. Não é preciso campo de
    status novo.
    """

    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="B", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)
        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1)
        self.joao = Atendido.objects.create(
            nome="João", sala="VIOLETA", data_nascimento=date(2015, 1, 1))
        self.voluntario = Voluntario.objects.create_user(
            username="vol_can", password="pw", area="EVENTOS")
        self.retirada, _, _ = finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 3}, conferido_por=self.voluntario)

    def test_cancelar_devolve_o_saldo(self):
        self.assertEqual(saldo_de(self.bazar, self.joao), 2)
        cancelar_retirada(self.retirada, self.voluntario, "marquei errado")
        self.assertEqual(saldo_de(self.bazar, self.joao), 5)

    def test_cancelar_reabre_a_trava_da_etapa(self):
        cancelar_retirada(self.retirada, self.voluntario, "marquei errado")
        self.assertFalse(ja_retirou_nesta_etapa(self.bazar, self.joao))
        finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario)

    def test_cancelar_guarda_quem_e_por_que(self):
        cancelar_retirada(self.retirada, self.voluntario, "marquei errado")
        self.retirada.refresh_from_db()
        self.assertIsNone(self.retirada.finalizada_em)
        self.assertIsNotNone(self.retirada.cancelada_em)
        self.assertEqual(self.retirada.cancelada_por, self.voluntario)
        self.assertEqual(self.retirada.motivo_cancelamento, "marquei errado")

    def test_cancelar_sem_motivo_e_recusado(self):
        """Cancelamento sem motivo vira número que ninguém sabe explicar."""
        with self.assertRaises(RetiradaInvalida):
            cancelar_retirada(self.retirada, self.voluntario, "   ")

    def test_cancelar_o_que_ja_foi_cancelado_nao_faz_nada_de_novo(self):
        cancelar_retirada(self.retirada, self.voluntario, "primeiro")
        with self.assertRaises(RetiradaInvalida):
            cancelar_retirada(self.retirada, self.voluntario, "segundo")

    def test_estoque_volta_com_o_cancelamento(self):
        """Peça cancelada não pode continuar contando como distribuída."""
        self.camiseta.estoque_inicial = 10
        self.camiseta.save()
        self.assertEqual(self.camiseta.distribuido, 3)
        cancelar_retirada(self.retirada, self.voluntario, "marquei errado")
        self.assertEqual(self.camiseta.distribuido, 0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_regras --settings=settings_sqlite`
Expected: FAIL — `TypeError: unexpected keyword argument 'token'` e `NameError: name 'cancelar_retirada' is not defined`

- [ ] **Step 3: Campos no modelo**

Em `Retirada`:

```python
    # Chave do atendimento, gerada pela tela. Reenvio com o mesmo token devolve
    # o mesmo recibo em vez de bater na trava da etapa — o que acusaria a
    # criança de ter passado duas vezes quando quem repetiu foi o clique.
    token = models.CharField(max_length=40, blank=True, db_index=True)

    cancelada_em = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="retiradas_canceladas")
    motivo_cancelamento = models.CharField(max_length=200, blank=True)
```

- [ ] **Step 4: Gerar a migração**

Run: `python manage.py makemigrations bazar --name token_e_cancelamento`

- [ ] **Step 5: Regras**

Em `bazar/regras.py`, no topo:

```python
# Quanto tempo quem acabou de gravar pode desfazer sozinho. Depois disso é a
# coordenação que corrige — pela tela do Bazar, não pelo admin num celular.
MINUTOS_PARA_DESFAZER = 2
```

Em `finalizar_retirada`, acrescentar `token=""` à assinatura (depois de
`visitante_motivo=""`), e logo depois da validação de visitante:

```python
    token = (token or "").strip()
    if token:
        # Reenvio depois de resposta perdida: devolve o mesmo recibo.
        ja_gravada = Retirada.objects.filter(
            bazar=bazar, token=token, finalizada_em__isnull=False).first()
        if ja_gravada is not None:
            return ja_gravada, ja_gravada.pontos_usados, []
```

e `token=token` no `Retirada.objects.create(...)`.

E a função nova, no fim do arquivo:

```python
def cancelar_retirada(retirada, por, motivo):
    """Devolve a retirada ao estado de rascunho.

    Não existe campo de status: `finalizada_em` nulo JÁ é o rascunho que o
    modelo prevê, e a UniqueConstraint tem `condition`, então a trava da etapa
    reabre sozinha. Os itens ficam — `Categoria.distribuido` só conta retirada
    finalizada, então o estoque volta sem ninguém apagar nada.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise RetiradaInvalida(
            "Escreva o motivo do cancelamento. Sem ele, o número do fim do dia "
            "não tem explicação.")
    if retirada.finalizada_em is None:
        raise RetiradaInvalida("Esta retirada já estava cancelada.")

    retirada.finalizada_em = None
    retirada.cancelada_em = timezone.now()
    retirada.cancelada_por = por
    retirada.motivo_cancelamento = motivo
    retirada.save(update_fields=["finalizada_em", "cancelada_em",
                                 "cancelada_por", "motivo_cancelamento"])
    return retirada
```

- [ ] **Step 6: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK

- [ ] **Step 7: Commit**

```bash
git add bazar/models.py bazar/migrations/ bazar/regras.py bazar/tests_regras.py
git commit -m "feat(bazar): token de idempotencia e desfazer que volta ao rascunho"
```

---

## Task 5: As rotas que a tela nova precisa

**Files:**
- Modify: `bazar/views.py`
- Modify: `bazar/urls.py`
- Test: `bazar/tests_telas.py`

**Interfaces:**
- Consumes: tudo das tasks 2-4.
- Produces:
  - `buscar_atendido` devolve por resultado: `id`, `nome`, `sala`, `idade`, `numeracoes` (dict com `camisa`/`calca`/`calcado`).
  - `finalizar` aceita `token`, `sem_retirada`, `visitante_nome`, `visitante_motivo`, `sala` (pk); captura `IntegrityError` e responde 409 com `erro` e `quando`/`onde`/`quem` quando souber.
  - `cancelar` — POST em `/bazar/cancelar/<pk>/`, nome `bazar:cancelar`.
  - `atendimento` passa `salas` ao contexto.

- [ ] **Step 1: Escrever os testes que falham**

```python
class BuscaComIdadeTest(BaseTela):
    """Duas 'Maria Eduarda' do Amarelo são hoje duas linhas idênticas, e a
    retirada vai para a criança errada — erro que a trava depois torna caro."""

    def test_busca_devolve_idade_e_numeracoes(self):
        import json
        self.joao.numeracao_camisa = "10"
        self.joao.save()
        resposta = views.buscar_atendido(
            self.pedido("/bazar/buscar/?q=Jo", self.voluntario))
        linha = json.loads(resposta.content)["resultados"][0]
        self.assertIn("idade", linha)
        self.assertEqual(linha["numeracoes"]["camisa"], "10")


class CorridaEntreDuasSalasTest(BaseTela):
    """Duas salas conferindo a mesma criança viram 500 no celular hoje: a view
    só captura RetiradaInvalida e o IntegrityError da constraint sobe cru."""

    def test_colisao_responde_409_e_nao_500(self):
        """Só na 1ª etapa: a trava passou a valer só lá (Task 3)."""
        import json
        from bazar.regras import finalizar_retirada
        self.bazar.etapa = self.bazar.Etapa.PRIMEIRA
        self.bazar.save()
        finalizar_retirada(bazar=self.bazar, atendido=self.joao,
                           pedido={self.camiseta.pk: 1},
                           conferido_por=self.voluntario)
        resposta = views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1}))
        self.assertEqual(resposta.status_code, 409)
        self.assertIn("erro", json.loads(resposta.content))


class CancelarPelaTelaTest(BaseTela):
    def test_quem_conferiu_cancela_e_a_trava_reabre(self):
        from bazar.regras import finalizar_retirada, ja_retirou_nesta_etapa
        retirada, _, _ = finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario)
        resposta = views.cancelar(
            self.pedido("/bazar/cancelar/", self.voluntario, metodo="post",
                        dados={"motivo": "marquei errado"}),
            pk=retirada.pk)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(ja_retirou_nesta_etapa(self.bazar, self.joao))

    def test_cancelar_sem_motivo_responde_409(self):
        from bazar.regras import finalizar_retirada
        retirada, _, _ = finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario)
        resposta = views.cancelar(
            self.pedido("/bazar/cancelar/", self.voluntario, metodo="post",
                        dados={"motivo": ""}),
            pk=retirada.pk)
        self.assertEqual(resposta.status_code, 409)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_telas --settings=settings_sqlite`
Expected: FAIL — `KeyError: 'idade'`, `IntegrityError` não capturado, `AttributeError: module 'bazar.views' has no attribute 'cancelar'`

- [ ] **Step 3: Implementar**

Em `bazar/views.py`, acrescentar no topo `from django.db import IntegrityError` e `from .regras import cancelar_retirada, MINUTOS_PARA_DESFAZER`.

Helper de idade, junto de `LIMITE_DA_BUSCA`:

```python
def _idade(atendido):
    """Idade em anos, ou None quando a ficha não tem nascimento.

    Existe porque a busca precisa separar homônimos: duas "Maria Eduarda" do
    Amarelo são duas linhas idênticas sem isto, e a retirada vai para a criança
    errada — erro que a trava da etapa depois torna caro de desfazer.
    """
    nascimento = getattr(atendido, "data_nascimento", None)
    if not nascimento:
        return None
    hoje = timezone.localdate()
    return hoje.year - nascimento.year - (
        (hoje.month, hoje.day) < (nascimento.month, nascimento.day))
```

`buscar_atendido` devolve o dicionário completo; `finalizar` passa os campos novos e envolve a chamada em `try/except (RetiradaInvalida, IntegrityError)`; `cancelar` é view nova com `@require_POST`.

A resposta de colisão explica quem registrou, quando e onde:

```python
    except IntegrityError:
        # Duas salas conferindo a mesma criança ao mesmo tempo. A checagem
        # acontece antes da gravação, então a corrida existe — e hoje ela vira
        # 500 no celular do voluntário, com a sacola já na mão.
        anterior = (Retirada.objects
                    .filter(bazar=bazar, atendido=atendido, etapa=bazar.etapa,
                            finalizada_em__isnull=False)
                    .select_related("conferido_por", "sala").first())
        recado = f"A sacola de {atendido.nome} já foi registrada"
        if anterior:
            recado += f" às {timezone.localtime(anterior.finalizada_em):%H:%M}"
            if anterior.sala:
                recado += f", na {anterior.sala.nome}"
            quem = (anterior.conferido_por.get_full_name()
                    or anterior.conferido_por.username)
            recado += f", por {quem}"
        return JsonResponse({"erro": recado + ". Nada foi gravado duas vezes."},
                            status=409)
```

- [ ] **Step 4: Rota**

Em `bazar/urls.py`, depois de `finalizar`:

```python
    path("cancelar/<int:pk>/", views.cancelar, name="cancelar"),
```

- [ ] **Step 5: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add bazar/views.py bazar/urls.py bazar/tests_telas.py
git commit -m "feat(bazar): busca com idade, colisao com recado humano e cancelamento"
```

---

## Task 6: A tela do caixa

O coração. Reescreve `atendimento.html` e `bazar-atendimento.js` inteiros.

**Files:**
- Rewrite: `bazar/templates/bazar/atendimento.html`
- Rewrite: `static/js/bazar-atendimento.js`
- Test: `bazar/tests_telas.py`

**Interfaces:**
- Consumes: as rotas da Task 5; `salas` no contexto.
- Produces: nada que outra task consuma.

**Requisitos não negociáveis desta tela** (cada um tem teste):

1. O saldo **desce** a cada peça marcada, e vive no rodapé fixo.
2. Mensagem de erro **permanece** até alguém agir — nenhum caminho a apaga.
3. Falha ao escolher a criança mostra faixa e botão de tentar de novo.
4. O `−` é `<button>` próprio de 44px, fora do alvo que soma.
5. Nenhum `input`/`select` abaixo de 16px (iOS dá zoom e desalinha).
6. O botão verde abre conferência; não grava.
7. "Quem levou" e o nome voltam ao padrão a cada criança.
8. Criança que já passou: grade **não desenhada**, frase inteira no lugar.
9. Impossibilidade escrita no botão, nunca cinza mudo.
10. Rodapé usa `dvh` e `env(safe-area-inset-bottom)`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class TelaDoCaixaTest(BaseTela):
    """A tela renderizada de verdade. RequestFactory: o test client quebra ao
    copiar o contexto do template neste ambiente."""

    def _html(self):
        return views.atendimento(self.pedido("/bazar/", self.voluntario)).content.decode()

    def test_diz_o_que_fazer_antes_de_escolher_alguem(self):
        """A tela abria com um campo solto e nada mais: o leigo não tem como
        saber que o primeiro passo é digitar o nome."""
        html = self._html()
        self.assertIn("PASSO 1", html.upper())

    def test_o_menos_e_botao_proprio_e_nao_span_dentro_do_botao(self):
        """Errar o alvo de 32px dentro do botão que soma ADICIONA peça."""
        html = self._html()
        self.assertNotIn('<span class="bz-menos"', html)
        self.assertIn('data-menos', html)

    def test_nenhum_campo_de_digitacao_abaixo_de_16px(self):
        """Abaixo de 16px o iOS dá zoom sozinho ao focar e desalinha a tela no
        meio do atendimento.

        A regra vale para CAMPO (input/select/textarea), não para texto: legenda
        de estoque a 0.7rem está certa e não pode ser arrastada junto.
        """
        import re
        html = self._html()
        bloco = html[html.index("<style>"):html.index("</style>")]

        # Cada regra CSS: seletor { corpo }
        for seletor, corpo in re.findall(r'([^{}]+)\{([^{}]*)\}', bloco):
            if not re.search(r'(input|select|textarea)', seletor):
                continue
            for tamanho in re.findall(r'font-size:\s*([\d.]+)rem', corpo):
                with self.subTest(seletor=seletor.strip()):
                    self.assertGreaterEqual(
                        float(tamanho) * 16, 15.99,
                        f"{seletor.strip()} tem font-size {tamanho}rem — "
                        "abaixo de 16px o iOS dá zoom ao focar")

    def test_o_rodape_traz_saldo_sacola_e_o_botao(self):
        html = self._html()
        self.assertIn("data-saldo-numero", html)
        self.assertIn("data-total", html)
        self.assertIn("data-conferir", html)

    def test_oferece_o_caminho_de_quem_nao_esta_cadastrado(self):
        self.assertIn("data-visitante", self._html())

    def test_oferece_veio_e_nao_levou_nada(self):
        self.assertIn("data-sem-retirada", self._html())

    def test_lista_as_salas_do_bazar(self):
        from bazar.models import SalaDoBazar
        SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 1", ordem=1)
        self.assertIn("Sala 1", self._html())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_telas.TelaDoCaixaTest --settings=settings_sqlite`
Expected: FAIL em todos.

- [ ] **Step 3: Reescrever o template e o JS**

Seguir o desenho da spec (seção "O desenho da tela"), os 10 requisitos acima e as classes `.pcf-*` do projeto. O JS é IIFE em ES5, sem build, como o atual.

Regra de ouro do JS novo, que o antigo violava: **nenhuma função que redesenha o carrinho pode esconder faixa de recado.** Mostrar e esconder recado é responsabilidade de quem sabe o que aconteceu, não de quem desenha.

- [ ] **Step 4: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK

- [ ] **Step 5: Conferir no navegador**

Run: `python manage.py runserver` e abrir `/bazar/` com o DevTools em 390px.
Verificar à mão: o saldo desce, o rodapé não sai da tela com o teclado aberto, e o `−` só aparece com peça marcada.

- [ ] **Step 6: Commit**

```bash
git add bazar/templates/bazar/atendimento.html static/js/bazar-atendimento.js bazar/tests_telas.py
git commit -m "feat(bazar): a tela de atendimento vira caixa"
```

---

## Task 7: O kit de papel

O plano B do evento. Pequeno e independente — e o único que funciona sem servidor.

**Files:**
- Create: `bazar/papelaria.py`
- Create: `bazar/templates/bazar/kit_papel.html`
- Modify: `bazar/views.py`, `bazar/urls.py`
- Create: `bazar/tests_papel.py`

**Interfaces:**
- Consumes: `Bazar`, `Categoria`, `SalaDoBazar`, `Atendido.objects.ativos()`.
- Produces:
  - `bazar.papelaria.folhas_do_kit(bazar) -> dict` com `categorias`, `salas`, `por_salinha` (lista de `{sala, rotulo, atendidos}`), `linhas_em_branco` (range 12).
  - `bazar.papelaria.planilha_do_kit(bazar) -> bytes` (.xlsx).
  - View `kit_papel` em `/bazar/<pk>/kit/`, nome `bazar:kit_papel`, **aberta a qualquer voluntário logado**.
  - View `kit_planilha` em `/bazar/<pk>/kit.xlsx`, nome `bazar:kit_planilha`.

- [ ] **Step 1: Escrever os testes que falham**

```python
class KitDePapelTest(TestCase):
    """O plano B. Aberto a QUALQUER voluntário logado: hoje o único CSV está
    atrás da coordenação, e quem está no caixa não consegue baixar."""

    def setUp(self):
        self.fabrica = RequestFactory()
        self.bazar = Bazar.objects.create(
            nome="Bazar 2026", data=date(2026, 10, 3),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=5)
        Categoria.objects.create(bazar=self.bazar, nome="Camiseta", pontos=1)
        Atendido.objects.create(nome="João Silva", sala="VIOLETA",
                                data_nascimento=date(2015, 1, 1))
        self.voluntario = Voluntario.objects.create_user(
            username="vol_kit", password="pw", area="AMARELO")

    def _pedir(self, view, url, **kwargs):
        requisicao = self.fabrica.get(url)
        requisicao.user = self.voluntario
        return view(requisicao, **kwargs)

    def test_qualquer_voluntario_logado_imprime(self):
        resposta = self._pedir(views.kit_papel, "/bazar/1/kit/", pk=self.bazar.pk)
        self.assertEqual(resposta.status_code, 200)

    def test_a_ficha_traz_a_tabela_de_pontos_e_a_cota(self):
        """Quem soma à mão precisa da tabela de preços na frente."""
        html = self._pedir(views.kit_papel, "/bazar/1/kit/",
                           pk=self.bazar.pk).content.decode()
        self.assertIn("Camiseta", html)
        self.assertIn("5", html)

    def test_a_lista_de_elegiveis_traz_nome_e_salinha(self):
        html = self._pedir(views.kit_papel, "/bazar/1/kit/",
                           pk=self.bazar.pk).content.decode()
        self.assertIn("João Silva", html)

    def test_nao_estende_base_html(self):
        """Folha de impressão não carrega navbar, sidebar nem JS do site."""
        html = self._pedir(views.kit_papel, "/bazar/1/kit/",
                           pk=self.bazar.pk).content.decode()
        self.assertNotIn("pcf-navitem", html)

    def test_a_planilha_sai_em_xlsx(self):
        resposta = self._pedir(views.kit_planilha, "/bazar/1/kit.xlsx",
                               pk=self.bazar.pk)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("spreadsheetml", resposta["Content-Type"])
        self.assertTrue(resposta.content.startswith(b"PK"))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH="$SP" python manage.py test bazar.tests_papel --settings=settings_sqlite`
Expected: FAIL — `module 'bazar.views' has no attribute 'kit_papel'`

- [ ] **Step 3: Implementar `papelaria.py`, o template e as views**

`kit_papel.html` segue o molde de `ronda/templates/imprimir_ronda.html`: HTML autônomo, sem `base.html`, com `@media print` escondendo o botão e `print-color-adjust: exact`.

- [ ] **Step 4: Rodar e ver passar**

Run: `PYTHONPATH="$SP" python manage.py test bazar --settings=settings_sqlite`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add bazar/papelaria.py bazar/templates/bazar/kit_papel.html bazar/views.py bazar/urls.py bazar/tests_papel.py
git commit -m "feat(bazar): kit de papel imprimivel, aberto a quem esta no caixa"
```

---

## Task 8: Painel em `.pcf-*` e o CLAUDE.md

**Files:**
- Rewrite: `bazar/templates/bazar/painel.html`
- Modify: `CLAUDE.md`
- Test: `bazar/tests_telas.py`

- [ ] **Step 1: Teste**

```python
class PainelUsaODesignDoProjetoTest(BaseTela):
    """O painel reinventava borda, raio e sombra próprios — é parte do 'não
    parece do mesmo sistema'."""

    def test_usa_as_classes_do_projeto(self):
        html = views.painel(self.pedido("/bazar/painel/", self.coordenacao)).content.decode()
        for classe in ("pcf-page-head", "pcf-kpi", "pcf-table"):
            self.assertIn(classe, html)

    def test_o_link_do_kit_de_papel_aparece(self):
        html = views.painel(self.pedido("/bazar/painel/", self.coordenacao)).content.decode()
        self.assertIn("kit", html.lower())
```

- [ ] **Step 2: Rodar, ver falhar, reescrever, ver passar**

- [ ] **Step 3: CLAUDE.md**

Acrescentar na seção do Bazar: que a tela é um caixa; que o `−` é botão próprio; que erro não pode ser apagado por quem redesenha; que a trava vale só na 1ª etapa; visitante; `sem_retirada`; token; cancelar = voltar ao rascunho; kit de papel aberto a todos; e as duas linhas de configuração.

- [ ] **Step 4: Commit**

```bash
git add bazar/templates/bazar/painel.html CLAUDE.md bazar/tests_telas.py
git commit -m "chore(bazar): painel no design do projeto e decisoes no CLAUDE.md"
```

---

## Ordem e critério de parada

Tasks 1→8 na ordem. A Task 1 é pré-requisito real das outras (o CSS purgado quebraria a tela nova em silêncio).

**Se o prazo apertar, a ordem de corte é:** Task 8 primeiro, depois a Task 6 pode entregar sem o modo visitante na tela (as regras já estarão prontas e o caminho fica pelo admin). **A Task 7 não se corta** — é o plano B do evento.
