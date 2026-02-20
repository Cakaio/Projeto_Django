from django.db import models
from django.utils import timezone

from sabado.models import Sabado

# Create your models here.
LISTA_SALAS = (
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
)

BAIRROS = (
    ("NOVO HORIZONTE","Novo Horizonte"),
    ("JARDIM NOVO HORIZONTE","Jardim Novo Horizonte"),
    ("CECAP","CECAP"),
    ("CECAP ALTA","CECAP Alta"),
    ("BAIRRO DA CRUZ","Bairro da Cruz"),
    ("CAMPOS DOS IPES","Campos dos Ipes"),
    ("PARQUE DAS RODOVIAS","Parque das Rodovias"),
    ("VILA INDUSTRIAL","Vila Industrial"),
    ("VILA CRISTIANA","Vila Cristiana"),
    ("VILA PASSOS","Vila Passos"),
    ("VILA BRITO","Vila Brito"),
    ("VILA DELI","Vila Deli"),
    ("DONA ANA","Dona Ana"),
    ("SANTA LUCRÉCIA","Santa Lucrécia"),
    ("FAZENDA MONDEZIR","Fazenda Mondezir"),
    ("OUTRO BAIRRO","Outro Bairro")
)

ZONAIS_RESIDENCIAIS = (
    ("ZONA RURAL","Zona Rural"),
    ("ZONA URBANA","Zona Urbana"),
)

SITUACAO_MORADIA = (
    ("PRÓPRIA QUITADA","Própria Quitada"),
    ("PRÓPRIA FINANCIADA","Própria Financiada"),
    ("ALUGADA","Alugada"),
    ("CEDIDA","Cedida"),
    ("ABRIGO INSTITUCIONAL","Abrigo Institucional"),
    ("OUTRA SITUAÇÃO","Outra Situação"),
)

CIDADES = (
    ("LORENA","Lorena"),
    ("PIQUETE","Piquete"),
    ("GUARATINGUETÁ","Guaratinguetá"),
    ("CACHOEIRA PAULISTA","Cachoeira Paulista"),
    ("CANAS","Canas"),
    ("CRUZEIRO","Cruzeiro"),
    ("LAVRINHAS","Lavrinhas"),
    ("SÃO JOSÉ DOS CAMPOS","São José dos Campos"),
    ("TAUBATÉ","Taubaté"),
    ("OUTRA CIDADE","Outra Cidade")
)

RENDA_FAMILIA = (
    ("MENOS DE 1000","menos de 1000"),
    ("ENTRE 1000-1500","Entre 1000 e 1500"),
    ("ENTRE 1500-2000","Entre 1500 e 2000"),
    ("ENTRE 2000-3000","Entre 2000 e 3000"),
    ("ENTRE 3000-4000","Entre 3000 e 4000"),
    ("ENTRE 4000-5000","Entre 4000 e 5000"),
    ("MAIS DE 5000","Mais de 5000"),
)

ESCOLARIDADE = (
    ("SEM ESCOLARIDADE","Sem Escolaridade"),
    ("ENSINO FUNDAMENTAL INCOMPLETO","Ensino Fundamental Incompleto"),
    ("ENSINO FUNDAMENTAL COMPLETO","Ensino Fundamental Completo"),
    ("ENSINO MÉDIO INCOMPLETO","Ensino Médio Incompleto"),
    ("ENSINO MÉDIO COMPLETO","Ensino Médio Completo"),
    ("ENSINO SUPERIOR INCOMPLETO","Ensino Superior Incompleto"),
    ("ENSINO SUPERIOR COMPLETO","Ensino Superior Completo"),
    ("PÓS-GRADUAÇÃO","Pós-Graduação"),
)

ANO_ESCOLAR = (
    ("1º ANO","1º Ano"),
    ("2º ANO","2º Ano"),
    ("3º ANO","3º Ano"),
    ("4º ANO","4º Ano"),
    ("5º ANO","5º Ano"),
    ("6º ANO","6º Ano"),
    ("7º ANO","7º Ano"),
    ("8º ANO","8º Ano"),
    ("9º ANO","9º Ano"),
    ("1ª SÉRIE DO ENSINO MÉDIO","1ª Série do Ensino Médio"),
    ("2ª SÉRIE DO ENSINO MÉDIO","2ª Série do Ensino Médio"),
    ("3ª SÉRIE DO ENSINO MÉDIO","3ª Série do Ensino Médio"),
)

GRAU_PARENTESCO = (
    ("PAI","Pai"),
    ("MÃE","Mãe"),
    ("AVÔ","Avô"),
    ("AVÓ","Avó"),
    ("TIO","Tio"),
    ("TIA","Tia"),
    ("IRMÃO","Irmão"),
    ("IRMÃ","Irmã"),
    ("OUTRO","Outro"),
)

IDENTIDADE_ETNICA = (
    ("BRANCA","Branca"),
    ("PRETA","Preta"),
    ("PARDA","Parda"),
    ("AMARELA","Amarela"),
    ("INDÍGENA","Indígena"),
    ("NÃO DECLARADA","Não Declarada"),
)

ESCOLA = (
("ESCOLA RUI BRASIL", "Escola Rui Brasil"),
("ESCOLA ESTADUAL ARNOLFO AZEVEDO", "Escola Estadual Arnolfo Azevedo"),
("E.M PROFª HERMÍNIA FIGUEIRA DE AZEVEDO ALMEIDA", "E.M Profª Hermínia Figueira de Azevedo Almeida"),
("CEMEI JÂNIO QUADROS", "CEMEI Jânio Quadros"),
("APARECIDA GUEDES", "Aparecida Guedes"),
("ESCOLA GABRIEL PRESTES", "Escola Gabriel Prestes"),
("E.M PROFESSORA LEDA MARIA BILARD DE CARVALHO", "E.M Professora Leda Maria Bilard de Carvalho"),
("E.E PROF. LUIZ DE CASTRO PINTO", "E.E Prof. Luiz de Castro Pinto"),
("E.E PROF. FRANCISCO MARQUES DE OLIVEIRA JUNIOR", "E.E Prof. Francisco Marques de Oliveira Junior"),
("EE PEI PROF.ª MIQUELINA CARTOLANO", "EE PEI Prof.ª Miquelina Cartolano"),
("ETEC PADRE CARLOS LEÔNCIO DA SILVA", "Etec Padre Carlos Leôncio da Silva"),
("ESCOLA MARIA AUXILIADORA", "Escola Maria Auxiliadora"),
("ESCOLA ESTADUAL LEONOR GUIMARÃES", "Escola Estadual Leonor Guimarães"),
("OUTRO", "Outro"),
)

COMPORTAMENTO_SOCIAL = (
    ("INTERAGE BEM COM COLEGAS","Interage bem com colegas"),
    ("DIFICULDADE DE INTERAÇÃO SOCIAL","Dificuldade de interação social"),
    ("ISOLADO","Isolado"),
    ("AGRESSIVO","Agressivo"),
    ("TIMÍDO","Tímido"),
    ("DEPENDE DO AMBIENTE","Depende do ambiente"),
    ("AINDA ESTÁ SE ADAPTANDO","Ainda está se adaptando"),
)

OPÇOES = (
    ("SIM","Sim"),
    ("NÃO","Não"),
    ("ÀS VEZES","Às vezes"),
)

ACOMPANHAMENTO = (
    ("NENHUM","Nenhum"),
    ("PEDIATRIA","Pediatria"),
    ("TERAPIA OCUPACIONAL","Terapia Ocupacional"),
    ("FONOAUDIOLOGIA","Fonoaudiologia"),
    ("PSICOLOGIA","Psicologia"),
    ("PSIQIATRA","Psiquiatria"),
    ("FISIOTERAPIA","Fisioterapia"),
    ("OUTRO ACOMPANHAMENTO","Outro Acompanhamento"),
)

TIPO_MATRICULA = (
    ("MATRÍCULA","Matrícula"),
    ("REMATRÍCULA","Rematrícula"),
)

TIPO_IMPACTO_SOCIAL = (
    ("APOIO NO DESENVOLVIMENTO DO ATENDIDO","Apoio no desenvolvimento do atendido"),
    ("SUPORTE À FAMÍLIA","Suporte à família"),
    ("ORIENTAÇÃO EDUCACIONAL","Orientação educacional"),
    ("CONTRIBUIÇÃO PARA ROTINA FAMILIAR","Contribuição para rotina familiar"),
    ("APOIO EMOCIONAL","Apoio emocional"),
)


class Mudanca(models.Model):
    mudanca = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['mudanca']

    def __str__(self):
        return self.mudanca

class Atendido(models.Model):
    familia = models.ForeignKey("Familia", on_delete=models.SET_NULL, null=True, blank=True, related_name="atendidos", help_text="Família que o atendido pertence, caso não tenha, cadastre uma nova família.")
    responsavel = models.ManyToManyField("ResponsavelAtendido", blank=True, related_name="atendidos", help_text="Responsável(s) pelo atendido, caso não tenha, cadastre um novo responsável.")
    nome = models.CharField(max_length=50, help_text="Nome completo do atendido")
    data_nascimento = models.DateField(help_text="Data de nascimento do atendido")
    sala = models.CharField(max_length=20, choices=LISTA_SALAS,help_text="Sala em que o atendido está sendo matriculado")
    rg = models.CharField(max_length=9, blank=True, null=True,help_text="RG do atendido, somente números")
    cpf = models.CharField(max_length=11, unique=True, blank=True, null=True,help_text="CPF do atendido, somente números")
    contato = models.CharField(max_length=11, blank=True, null=True,help_text="Número de contato do atendido, somente números")
    documento = models.FileField(upload_to='documentos_atendidos', blank=True, null=True,help_text="Documento do atendido (RG ou Certidão de Nascimento)")
    escolaridade = models.CharField(max_length=100, choices=ESCOLARIDADE, blank=True, null=True,help_text="Escolaridade do atendido")
    ano_escolar = models.CharField(max_length=50, choices=ANO_ESCOLAR, blank=True, null=True,help_text="Ano escolar do atendido")
    escola = models.CharField(max_length=100, choices=ESCOLA, blank=True, null=True,help_text="Escola do atendido")
    tipo_escola = models.CharField(max_length=50, choices=(("PÚBLICA","Pública"),("PRIVADA","Privada")), blank=True, null=True,help_text="Tipo de escola do atendido")
    trabalho = models.BooleanField(default=False, help_text="O atendido trabalha?")
    foto = models.ImageField(upload_to='fotos_atendidos', blank=True, null=True,help_text="Foto do atendido")
    projeto_social = models.BooleanField(default=False, help_text="O atendido já participou de algum projeto social?")
    convenio_medico = models.BooleanField(default=False, help_text="O atendido possui convênio médico?")
    vacina_covid = models.BooleanField(default=False, help_text="O atendido tomou as vacinas contra a COVID-19?")
    restricao_alimentar = models.TextField(blank=True, null=True,help_text="Restrições alimentares do atendido")
    restricao_medica = models.TextField(blank=True, null=True,help_text="Restrições médicas do atendido")
    medicacao_continua = models.TextField(blank=True, null=True,help_text="Medicação contínua do atendido")
    diagnostico = models.BooleanField(default=False,help_text="O atendido possui algum diagnóstico, laudo ou acompanhamento relacionado ao desenvolvimento, aprendizagem ou comportamento (como TEA, TDAH, dificuldades de atenção, comunicação ou socialização)? Há condições de saúde que requerem acompanhamento ou suporte especializado?")
    diagnostico_descricao = models.TextField(blank=True, null=True,help_text="Descrição do diagnóstico, laudo ou acompanhamento relacionado ao desenvolvimento, aprendizagem ou comportamento do atendido")
    comportamento_social = models.CharField(max_length=100, choices=COMPORTAMENTO_SOCIAL, blank=True, null=True,help_text="Como o atendido costuma se comportar em atividades em grupo e na socialização com outras pessoas da mesma idade?")
    comportamento_regras = models.CharField(max_length=100, choices=OPÇOES, blank=True, null=True,help_text="O atendido apresenta alguma dificuldade em seguir regras ou combinados?")
    concentracao = models.BooleanField(default=False,help_text="O atendido apresenta dificuldade de concentração em atividades mais longas?")
    aprendizado = models.BooleanField(default=False,help_text="O atendido apresenta alguma dificuldade de aprendizado?")
    sensibilidade = models.BooleanField(default=False,help_text="O atendido apresenta sensibilidade a sons, luzes, cheiros ou toque?")
    sensibilidade_descricao = models.TextField(blank=True, null=True,help_text="Descrição da sensibilidade do atendido a sons, luzes, cheiros ou toque")
    dificuldade_motora = models.BooleanField(default=False,help_text="O atendido apresenta alguma dificuldade motora ou de coordenação?")
    dificuldade_motora_descricao = models.TextField(blank=True, null=True,help_text="Descrição da dificuldade motora ou de coordenação do atendido")
    dificuldade_emocional = models.BooleanField(default=False,help_text="O atendido apresenta alguma dificuldade em controlar suas emoções ou comportamentos?")
    dificuldade_emocional_descricao = models.TextField(blank=True, null=True,help_text="Descrição da dificuldade do atendido em controlar suas emoções ou comportamentos")
    acompanhamento = models.CharField(max_length=100, choices=ACOMPANHAMENTO, blank=True, null=True,help_text="O atendido realiza acompanhamento com algum profissional? Se sim, qual?")
    recomendacao_acompanhamento = models.TextField(blank=True, null=True,help_text="Qual é a recomendação do profissional de saúde ou educacional para melhor atender o atendido?")
    identidade_etnica = models.CharField(max_length=50, choices=IDENTIDADE_ETNICA, blank=True, null=True,help_text="Identidade étnica do atendido")
    numeracao_camisa = models.CharField(max_length=5, blank=True, null=True,help_text="Numeração da camisa do atendido")
    numeracao_calca = models.CharField(max_length=5, blank=True, null=True,help_text="Numeração da calça do atendido")
    numeracao_calcado = models.CharField(max_length=5, blank=True, null=True,help_text="Numeração do calçado do atendido")
    termos_assinado = models.BooleanField(default=False, help_text="Os termos de: Ciencia do EDUC ; Dados/LGPD ; Uso de Imagem ; Saúde Bucal foram assinados?")
    registrado_por = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="atendidos_registrados")
    comissao_inclusiva = models.BooleanField(default=False,help_text="O Atendido tem necessidade de apoio da Comissão Inclusiva?")
    expectativas_familia = models.TextField(blank=True, null=True, help_text="Quais são as expectativas da família em relação ao apoio inclusivo oferecido pelo projeto?")
    matricula = models.CharField(max_length=20, choices=TIPO_MATRICULA, blank=True, null=True, help_text="Indica se é matrícula ou rematrícula do atendido")
    mudancas_positivas = models.BooleanField(default=False, help_text="Desde que a criança participa do Projeto Criança Feliz, você percebeu mudanças positivas no comportamento dela?")
    aspectos_mudancas = models.ManyToManyField("Mudanca", blank=True, help_text="Quais aspectos ou áreas de desenvolvimento você percebeu mudanças positivas na criança? (Marque todas as que se aplicam)")
    saude_bucal = models.BooleanField(default=False, help_text="Antes de participar do Projeto Criança Feliz, o atendido já havia passado por atendimento odontológico?")
    observacoes = models.TextField(blank=True, null=True, help_text="Adicione quaisquer outras informações relevantes sobre o atendido que não foram contempladas nos campos anteriores.")
    campanha_vacinacao = models.BooleanField(default=False, help_text="Você apoiaria a realização de campanhas de vacinação para os atendidos do Projeto Criança Feliz?")
    data_criacao = models.DateTimeField(default=timezone.now)
    ativo = models.BooleanField(default=True, help_text="Indica que o usuário será tratado como ativo. Ao invés de excluir atendidos, desmarque isso.")

    def __str__(self):
        return f"{self.nome}"

class AtendidoInclusivo(models.Model):
    atendido = models.OneToOneField(Atendido, on_delete=models.CASCADE, related_name="inclusivo")
    diagnostico = models.BooleanField(blank=True, null=True, help_text="O Atendido possui algum diagnóstico médico formal (laudo)?")
    diagnostico_descricao = models.TextField(blank=True, null=True, help_text="Descrição do diagnóstico médico formal (laudo) do Atendido")
    acompanhamento = models.BooleanField(blank=True, null=True, help_text="A condições de saúde requer acompanhamento ou suporte especializado? Exemplo: Transtorno do Espectro Autista, TDAH?")
    recomendacoes = models.TextField(blank=True, null=True, help_text="Qual é a recomendação do profissional de saúde ou educacional para melhor atender o Atendido?")
    comportamento_social = models.TextField(blank=True, null=True, help_text="Descreva o comportamento social do Atendido (interação com colegas, comunicação, etc.)")
    dificuldades_aprendizado = models.TextField(blank=True, null=True, help_text="O Atendido apresenta dificuldades específicas de aprendizado? Se sim, descreva.")
    dificuldades_motoras = models.TextField(blank=True, null=True, help_text="O Atendido apresenta dificuldades motoras? Se sim, descreva.")
    dificuldade_atencao = models.TextField(blank=True, null=True, help_text="O Atendido apresenta dificuldades de atenção ou concentração? Se sim, descreva.")
    dificuldade_emocional = models.TextField(blank=True, null=True, help_text="O Atendido apresenta dificuldades em controlar suas emoções ou comportamentais? Se sim, descreva.")
    servicos_apoio = models.BooleanField(blank=True, null=True, help_text="O Atendido recebe algum serviço de apoio externo (terapia ocupacional, fonoaudiologia, psicologia, etc.)?")
    expectativas_familia = models.TextField(blank=True, null=True, help_text="Quais são as expectativas da família em relação ao apoio inclusivo oferecido pelo projeto?")
    observacoes_adicionais = models.TextField(blank=True, null=True, help_text="Adicione quaisquer outras informações relevantes sobre as necessidades inclusivas do Atendido.")

    
class Familia(models.Model):
    nome = models.CharField(max_length=50, blank=True, null=True,help_text="Nome da família")
    cep = models.CharField(max_length=10, blank=True, null=True,help_text="CEP da residência da família, somente números")
    endereco = models.CharField(max_length=200, blank=True, null=True,help_text="Endereço da residência da família")
    bairro = models.CharField(max_length=50, choices=BAIRROS, blank=True, null=True,help_text="Bairro da residência da família")
    cidade = models.CharField(max_length=100, choices=CIDADES, blank=True, null=True,help_text="Cidade da residência da família")
    zona_residencial = models.CharField(max_length=20, choices=ZONAIS_RESIDENCIAIS, blank=True, null=True,help_text="Zona residencial da residência da família")
    situacao_moradia = models.CharField(max_length=100,choices=SITUACAO_MORADIA, blank=True, null=True,help_text="Situação da moradia da família")
    agua_encanada = models.BooleanField(default=False, help_text="A residência da família possui água encanada?")
    esgoto_encanado = models.BooleanField(default=False, help_text="A residência da família possui esgoto encanado?")
    energia_eletrica = models.BooleanField(default=False, help_text="A residência da família possui energia elétrica?")
    renda_total_familia = models.CharField(max_length=20, choices=RENDA_FAMILIA, blank=True, null=True, help_text="Renda total da família")
    pessoas_moram_familia = models.IntegerField(default=1,help_text="Número de pessoas que moram na residência da família")
    pessoas_trabalham_familia = models.IntegerField(default=0,help_text="Número de pessoas que trabalham na residência da família")
    programa_transferencia_renda = models.BooleanField(default=False,help_text="A família participa de algum programa de transferência de renda?")
    internet_casa = models.BooleanField(default=False,help_text="A residência da família possui acesso à internet?")
    comodos_casa = models.IntegerField(default=0,help_text="Número de cômodos na residência da família")
    tv_casa = models.IntegerField(default=0,help_text="Número de televisores na residência da família")
    banheiro_casa = models.IntegerField(default=0,help_text="Número de banheiros na residência da família")
    motos_casa = models.IntegerField(default=0,help_text="Número de motos na residência da família")
    carros_casa = models.IntegerField(default=0,help_text="Número de carros na residência da família")
    geladeira_casa = models.IntegerField(default=0,help_text="Número de geladeiras na residência da família")
    freezer_casa = models.IntegerField(default=0,help_text="Número de freezers na residência da família")
    celular_casa = models.IntegerField(default=0,help_text="Número de celulares na residência da família")
    computador_casa = models.IntegerField(default=0,help_text="Número de computadores na residência da família")
    cesta_natal = models.BooleanField(default=False,help_text="A família tem interesse em receber cesta de Natal?")
    impacto_social = models.CharField(max_length=100, choices=OPÇOES, blank=True, null=True, help_text="O Projeto Criança Feliz contribui positivamente para a rotina da sua família?")
    tipo_impacto_social = models.CharField(max_length=100, choices=TIPO_IMPACTO_SOCIAL, blank=True, null=True, help_text="De que forma o Projeto Criança Feliz contribui positivamente na sua família?")
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.nome}"

class ResponsavelAtendido(models.Model):
    nome = models.CharField(max_length=50, blank=True, null=True, help_text="Nome do responsável pelo atendido")
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True, help_text="CPF do responsável pelo atendido, somente números")
    rg = models.CharField(max_length=15, blank=True, null=True, help_text="RG do responsável pelo atendido, somente números")
    parentesco = models.CharField(max_length=50, choices=GRAU_PARENTESCO, null=True, blank=True, help_text="Grau de parentesco com o atendido")
    contato = models.CharField(max_length=20, blank=True, null=True, help_text="Número de contato do responsável pelo atendido, somente números")
    outro_contato = models.CharField(max_length=20, blank=True, null=True, help_text="Número de contato alternativo do responsável pelo atendido, somente números")
    trabalho = models.CharField(max_length=100, blank=True, null=True, help_text="Local de trabalho do responsável pelo atendido")
    email = models.EmailField(blank=True, null=True, help_text="E-mail do responsável pelo atendido")
    escolaridade = models.CharField(max_length=100, choices=ESCOLARIDADE, blank=True, null=True, help_text="Escolaridade do responsável pelo atendido")
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.nome}"

class PresencaAtendido(models.Model):
    OPCOES_PRESENCA = [
        ("PRESENTE", "Presente"),
        ("AUSENTE", "Ausente"),
        ("JUSTIFICADA", "Falta Justificada"),
    ]
    atendido = models.ForeignKey("Atendido",on_delete=models.CASCADE,related_name="presencas")
    presenca = models.CharField(max_length=15,choices=OPCOES_PRESENCA,default="PRESENTE")
    data = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="presencas_atendidos")
    registrado_por = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="presencas_registradas_atendidos")

    def __str__(self):
        return f"{self.atendido.nome} - {self.data} ({self.get_presenca_display()})"


