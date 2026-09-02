import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db.models import Q

from sabado.models import Sabado

LISTA_AREAS = (
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
    ("MARKETING", "Marketing"),
    ("ADM/FIN", "ADM/Fin"),
    ("CR/RE", "Captação de Recursos & Relações Externas"),
    ("EVENTOS", "Eventos"),
    ("GESTAO_DE_TALENTOS", "Gestão de Talentos"),
    ("RECREACAO", "Recreação"),
    ("SUPPLY", "Supply"),
    ("PROJETOS", "Projetos"),
    ("TRIADE", "Tríade"),
)

# O nome por extenso é o correto em formulários, organograma e crachá, mas não
# cabe em lugar apertado (o cargo embaixo do nome na navbar, um chip de tabela).
# Só as áreas de nome comprido precisam de forma curta; o resto usa o próprio
# rótulo.
AREAS_ABREVIADAS = {
    "CR/RE": "CR/RE",
}

FACULDADES = (
    ("EEL-USP", "EEL-USP"),
    ("SERRA DOURADA", "Serra Dourada"),
    ("UNISAL", "Unisal"),
    ("UNIFATEA", "Unifatea"),
    ("OUTRA", "Outra"),
    ("NAO_ESTUDANTE", "Não Estudante")
)

CURSOS = (
    ("ENGENHARIA_QUÍMICA", "Engenharia Química"),
    ("ENGENHARIA_DE_PRODUÇÃO", "Engenharia de Produção"),
    ("ENGENHARIA_FÍSICA", "Engenharia Física"),
    ("ENGENHARIA_AMBIENTAL", "Engenharia Ambiental"),
    ("ENGENHARIA_DE_MATERIAIS", "Engenharia de Materiais"),
    ("ENGENHARIA_BIOQUÍMICA", "Engenharia Bioquímica"),
    ("PSICOLOGIA", "Psicologia"),
    ("OUTRO", "Outro"),
    ("NAO_ESTUDANTE", "Não Estudante")
)
TIPO_ALIMENTACAO = (
    ("ONIVORO", "Onívoro"),
    ("VEGETARIANO", "Vegetariano"),
    ("VEGANO", "Vegano")
)

CARGOS = (
    ('LIDER', 'Líder'),
    ('LEG', 'Líder Educacional Geral'),
    ('VICE', 'Vice-Presidente'),
    ('PRESIDENTE', 'Presidente'),
)


class VoluntarioManager(UserManager):
    """Herda de UserManager para não perder `create_user` / `createsuperuser`."""

    def ativos(self):
        """Quem está no projeto HOJE.

        Duas condições, e as duas importam: `data_saida` vazia é quem não saiu
        do projeto, e `is_active` é quem ainda consegue entrar no sistema.
        Contar um desligado ou um login desativado como "pendente" numa enquete
        inflava o número de quem falta responder com gente que não tem como
        responder — e é esse número que a liderança usa para cobrar.
        """
        return self.filter(data_saida__isnull=True, is_active=True)


class Voluntario(AbstractUser):
    objects = VoluntarioManager()

    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    apelido = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    celular = models.CharField(max_length=15, blank=True, null=True, help_text="Formato: DDD + número, apenas números")
    instagram = models.CharField(max_length=50, blank=True, null=True)
    email_alternativo = models.EmailField(blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True, help_text="Endereço de Lorena de preferência")
    republica = models.CharField(max_length=100, blank=True, null=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_voluntarios', blank=True, null=True)
    restricao_alimentar = models.CharField(max_length=100, blank=True, null=True)
    alimentacao = models.CharField(max_length=20,choices=TIPO_ALIMENTACAO,blank=True,null=True)
    comida_favorita = models.CharField(max_length=100, blank=True, null=True)
    alergia = models.CharField(max_length=100, blank=True, null=True)
    medicacao_continua = models.CharField(max_length=100, blank=True, null=True)
    faculdade = models.CharField(max_length=100, choices=FACULDADES, blank=True, null=True)
    n_usp = models.CharField(max_length=20, blank=True, null=True)
    email_usp = models.EmailField(blank=True, null=True)
    curso = models.CharField(max_length=100, choices=CURSOS, blank=True, null=True)
    ano_faculdade = models.IntegerField(blank=True, null=True)
    trabalha = models.BooleanField(default=False)
    empresa = models.CharField(max_length=100, blank=True, null=True)
    talentos = models.ManyToManyField("Talento", blank=True)
    data_entrada = models.DateField(default=timezone.now)
    data_saida = models.DateField(blank=True, null=True)
    is_matricula = models.BooleanField(default=False, help_text="Se marcado, o voluntário pode acessar e usar a tela de Matrícula de Atendidos.")
    lider = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='liderados',
        help_text="Líder direto deste voluntário (monta o organograma; deixe vazio para o topo, ex.: Presidente)."
    )
    cargo = models.CharField(
        max_length=100, choices=CARGOS, blank=True, null=True,
        help_text="Cargo/posição na hierarquia."
    )


    @property
    def area_curta(self):
        """Rótulo da área para espaço apertado (navbar, chips de tabela).
        Onde houver espaço, use `get_area_display` — é o nome por extenso."""
        if not self.area:
            return ""
        return AREAS_ABREVIADAS.get(self.area, self.get_area_display())

    def __str__(self):
        return self.get_full_name() or self.username


class Grupo(models.Model):
    """
    Agrupamento dinâmico de voluntários.

    Cada item de ``regras`` é uma alternativa (OU). Dentro de um item, as áreas
    e os cargos são cumulativos (E). Não existe relação persistida com
    Voluntario: os integrantes são consultados sempre com os dados atuais.
    """
    nome = models.CharField(max_length=100, unique=True)
    regras = models.JSONField(default=list)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if not isinstance(self.regras, list) or not self.regras:
            raise ValidationError({"regras": "Adicione ao menos uma regra ao grupo."})

        areas_validas = {valor for valor, _ in LISTA_AREAS}
        cargos_validos = {valor for valor, _ in CARGOS}
        for indice, regra in enumerate(self.regras, start=1):
            if not isinstance(regra, dict):
                raise ValidationError({"regras": f"A regra {indice} é inválida."})
            areas = regra.get("areas", [])
            cargos = regra.get("cargos", [])
            if not areas and not cargos:
                raise ValidationError({"regras": f"A regra {indice} precisa de uma área ou cargo."})
            if not set(areas).issubset(areas_validas) or not set(cargos).issubset(cargos_validos):
                raise ValidationError({"regras": f"A regra {indice} contém uma opção inválida."})

    def voluntarios(self):
        consulta = Q()
        for regra in self.regras:
            parte = Q()
            if regra.get("areas"):
                parte &= Q(area__in=regra["areas"])
            if regra.get("cargos"):
                parte &= Q(cargo__in=regra["cargos"])
            consulta |= parte
        return Voluntario.objects.ativos().filter(
            consulta
        ).distinct().order_by("first_name", "last_name", "username")

class PresencaVoluntario(models.Model):
    OPCOES_PRESENCA = [
        ("PRESENTE", "Presente"),
        ("AUSENTE", "Ausente"),
        ("JUSTIFICADA", "Falta Justificada"),
    ]

    voluntario = models.ForeignKey("Voluntario",on_delete=models.CASCADE,related_name="presencas")
    presenca = models.CharField(max_length=15,choices=OPCOES_PRESENCA,default="PRESENTE")
    data = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="presencas_voluntarios")
    registrado_por = models.ForeignKey("Voluntario",on_delete=models.SET_NULL,blank=True,null=True,related_name="presencas_registradas_voluntarios")

    def __str__(self):
        return f"{self.voluntario.username} - {self.data} ({self.get_presenca_display()})"
    
class Talento(models.Model):
    talento = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['talento']

    def __str__(self):
        return self.talento


class HistoricoLideranca(models.Model):
    """Registro de quem já foi líder de uma área/cargo e por qual período.

    A pessoa pode NÃO ter ficha no sistema. Boa parte de quem liderou o projeto
    saiu antes de existir site, e não faz sentido criar login para alguém que
    nunca vai entrar — exigir ficha deixaria essas gestões fora da história, que
    é justamente o que esta tela existe para contar. Por isso há duas formas de
    dizer de quem é o registro, e a ficha só tem prioridade quando existe.
    """
    voluntario = models.ForeignKey(
        'Voluntario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='historico_lideranca',
        help_text="Quem liderou, se tiver ficha no sistema.",
    )
    nome_avulso = models.CharField(
        'nome ou apelido', max_length=120, blank=True,
        help_text="Use quando a pessoa não tem ficha — é como ela vai aparecer na história.",
    )
    foto = models.ImageField(
        'foto', upload_to='lideres_historico', blank=True, null=True,
        help_text="Só é necessária para quem não tem ficha; com ficha, usamos a foto do perfil.",
    )
    cargo = models.CharField(max_length=100, help_text="Cargo/posição liderada (ex.: Líder de Sala Violeta, LEG, Presidente).")
    area = models.CharField(max_length=30, choices=LISTA_AREAS, blank=True, null=True, help_text="Área liderada (opcional).")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True, help_text="Deixe vazio se ainda está no cargo.")
    descricao = models.TextField(
        'como foi a passagem', blank=True,
        help_text="Opcional: o que marcou essa gestão, o que foi deixado para a próxima. "
                  "Aparece na linha de sucessão do histórico de líderes.",
    )

    class Meta:
        # Sucessão se lê do mais antigo para o mais novo: é isso que a seta do
        # histórico liga. Ordenar decrescente inverteria a passagem de liderança.
        ordering = ['area', 'data_inicio']
        verbose_name = 'Histórico de Liderança'
        verbose_name_plural = 'Históricos de Liderança'

    @property
    def atual(self):
        return self.data_fim is None

    @property
    def mesmo_ano(self):
        """Gestão que começou e acabou no mesmo ano mostra '2024', não '2024–2024'."""
        return bool(self.data_fim) and self.data_fim.year == self.data_inicio.year

    @property
    def de_quem(self):
        """Nome a mostrar. Ficha primeiro; nome digitado como reserva."""
        if self.voluntario_id:
            return self.voluntario.get_full_name() or self.voluntario.username
        return self.nome_avulso or 'Sem nome'

    @property
    def retrato(self):
        """A foto a exibir, ou None. Perfil primeiro, foto solta depois.

        Devolve o campo de arquivo, não a URL: a URL de campo vazio estoura, e
        o template precisa poder testar antes de chamar `.url`.
        """
        if self.voluntario_id and self.voluntario.foto:
            return self.voluntario.foto
        return self.foto or None

    @property
    def tem_ficha(self):
        """Só quem tem ficha vira link para a trajetória por pessoa."""
        return self.voluntario_id is not None

    def clean(self):
        super().clean()
        if not self.voluntario_id and not self.nome_avulso.strip():
            raise ValidationError({
                'nome_avulso': 'Diga quem liderou: escolha a ficha ou digite o nome.',
            })

    def __str__(self):
        fim = 'atual' if self.atual else self.data_fim.strftime('%m/%Y')
        return f'{self.de_quem} — {self.cargo} ({self.data_inicio:%m/%Y}–{fim})'


class Regra(models.Model):
    TIPOS = (
        ('ALERTA', 'Alerta'),
        ('ADVERTENCIA', 'Advertência'),
        ('SUSPENSAO', 'Suspensão'),
    )
    codigo    = models.CharField(max_length=10, unique=True, help_text='Código curto, ex: AL1, AD2, PO1')
    descricao = models.TextField(help_text='Descrição completa exibida no painel e nos emails')
    tipo      = models.CharField(max_length=20, choices=TIPOS)
    ativo     = models.BooleanField(default=True, help_text='Disponível para aplicação no painel')
    ordem     = models.PositiveSmallIntegerField(default=0, help_text='Ordem de exibição dentro do grupo')

    class Meta:
        ordering  = ['tipo', 'ordem', 'codigo']
        verbose_name = 'Regra'
        verbose_name_plural = 'Regras'

    def __str__(self):
        return f'{self.codigo} – {self.descricao}'


# ─────────────────────────────────────────────────────────────────────────────
# Escala de disciplina (acúmulo de ocorrências)
# Alterar a régua disciplinar aqui reflete em todo o sistema (views, comandos,
# templates via contexto). Não espalhar esses números pelo código.
# ─────────────────────────────────────────────────────────────────────────────
FALTAS_POR_ALERTA = 3          # faltas consecutivas necessárias para 1 alerta automático

# A ÚNICA regra que o alerta automático de faltas pode usar. Antes cada gerador
# escolhia uma: o registro de presença gravava AL13 ("faltou a um sábado sem
# avisar e o líder julgou pertinente") e o comando retroativo gravava AL2
# ("confirmou presença e não compareceu") — duas regras que descrevem
# julgamento humano, não contagem. O voluntário recebia um alerta cujo texto não
# tinha nada a ver com o motivo real.
REGRA_FALTAS_CONSECUTIVAS = 'AL18'
ALERTAS_POR_ADVERTENCIA = 3    # alertas ativos acumulados que geram 1 advertência automática
ADVERTENCIAS_PARA_OBSERVACAO = 3   # advertências ativas que disparam Período de Observação
# Teto visual de alertas: ao atingir, há 3 advertências → Período de Observação
MAX_ALERTAS_DISPLAY = ALERTAS_POR_ADVERTENCIA * ADVERTENCIAS_PARA_OBSERVACAO  # 9


class Ocorrencia(models.Model):
    TIPOS = (
        ('ALERTA', 'Alerta'),
        ('ADVERTENCIA', 'Advertência'),
        ('SUSPENSAO', 'Suspensão'),
    )

    REGRAS = (
        ('Alertas', (
            ('AL1',  'AL1 – Não respondeu o formulário de presença até quarta-feira às 23h59'),
            ('AL2',  'AL2 – Confirmou presença e não compareceu no sábado'),
            ('AL3',  'AL3 – Quórum mínimo: presença inferior a 50% nos sábados do semestre'),
            ('AL4',  'AL4 – Atraso após 8h30 no DEMAR sem justificativa prévia'),
            ('AL5',  'AL5 – Saiu antes do encerramento ou não participou da reunião final'),
            ('AL6',  'AL6 – Atitudes inadequadas reincidentes após aviso da GT'),
            ('AL7',  'AL7 – Não cumpriu turno de ronda durante o sábado'),
            ('AL8',  'AL8 – Demonstrações excessivas de carinho/afeto próximo aos atendidos'),
            ('AL9',  'AL9 – Atraso superior a 20 minutos sem justificativa'),
            ('AL10', 'AL10 – Não respondeu formulários/enquetes disponibilizados nos Informativos'),
            ('AL11', 'AL11 – Falta em turno de pré-evento após confirmação e sem aviso prévio'),
            ('AL12', 'AL12 – Duas faltas seguidas em reunião de área sem justificativa'),
            ('AL13', 'AL13 – Faltou a um sábado sem avisar e o líder julgou pertinente'),
            ('AL14', 'AL14 – Não realizou tarefa da área'),
            ('AL15', 'AL15 – Não respondeu o grupo da área por uma semana ou mais'),
            ('AL16', 'AL16 – Líder não cumpriu prazos estabelecidos pela gestão'),
            ('AL17', 'AL17 – Líder não compareceu às reuniões da Gestão sem justificar'),
            ('AL18', 'AL18 – Faltou a três sábados seguidos sem justificativa'),
        )),
        ('Advertências', (
            ('AD1', 'AD1 – Estava sob influência de álcool ou substância psicoativa durante o projeto'),
            ('AD2', 'AD2 – Dormiu durante o projeto'),
            ('AD3', 'AD3 – Faltou à RG ou Postulação sem justificativa'),
            ('AD4', 'AD4 – Não cumpriu turno em evento externo sem justificativa ao membro de Eventos'),
            ('AD5', 'AD5 – Três faltas seguidas em reunião de área sem justificativa'),
            ('AD6', 'AD6 – Não cumpriu tarefa que afetou o funcionamento do sábado ou prejudicou a área'),
            ('AD7', 'AD7 – Somatório de 2 alertas do mesmo motivo'),
            ('AD8', 'AD8 – Somatório de 3 alertas de diferentes motivos'),
        )),
        ('Períodos de Observação', (
            ('PO1', 'PO1 – Quórum mínimo igual ou inferior a 30% no semestre'),
            ('PO2', 'PO2 – Líder ausente e sem cumprir funções por uma semana ou mais'),
            ('PO3', 'PO3 – Somatório de 2 advertências do mesmo motivo'),
            ('PO4', 'PO4 – Somatório de 3 advertências de diferentes motivos'),
        )),
    )

    # Mapa plano código → descrição para lookup rápido
    REGRAS_DICT = {
        code: label
        for group, items in REGRAS
        for code, label in items
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertido = models.ForeignKey(
        'Voluntario', on_delete=models.CASCADE,
        related_name='ocorrencias_recebidas'
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    regra = models.CharField(max_length=5, blank=True, null=True)
    razao = models.TextField(blank=True, null=True)
    aplicado_por = models.ForeignKey(
        'Voluntario', on_delete=models.SET_NULL,
        null=True, related_name='ocorrencias_aplicadas'
    )
    automatico = models.BooleanField(
        default=False,
        help_text='True se gerada automaticamente por acúmulo'
    )
    criado_em = models.DateTimeField(default=timezone.now)

    # Soft delete — nunca remove do banco
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ocorrencias_deletadas'
    )

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.advertido}"

    @property
    def ativa(self):
        return self.deleted_at is None

    def soft_delete(self, deleted_by):
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=['deleted_at', 'deleted_by'])
