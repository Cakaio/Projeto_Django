"""Regras comuns a toda importação para o Acervo.

Dois caminhos trazem documento de fora: o comando `importar_acervo` (pasta local
baixada do Drive) e a sincronização automática (`acervo/sincronizacao.py`, que
fala com o Drive direto). Os dois precisam decidir exatamente a mesma coisa
sobre cada arquivo — que ano é, que título dar, se o formato serve, se o tamanho
cabe. Duplicar essa decisão nos dois lugares é pedir para divergirem, e o
sintoma seria o pior possível: o mesmo arquivo entrando de um jeito pelo botão e
de outro pelo comando.

Tudo aqui é função pura. Nada de banco, nada de rede, nada de Django além das
constantes do form.
"""
import re

from .forms import EXTENSOES_ACEITAS, TAMANHO_MAXIMO_MB

# Anos plausíveis para um documento do projeto. Serve para não confundir um
# "2 vias" ou um telefone no nome do arquivo com o ano do documento.
ANO_MINIMO = 1990
ANO_MAXIMO = 2100
_ANO = re.compile(r'(?<!\d)(199\d|20\d\d)(?!\d)')

LIMITE_BYTES = TAMANHO_MAXIMO_MB * 1024 * 1024


def ano_em(partes):
    """Primeiro ano plausível encontrado, varrendo `partes` na ordem dada.

    Quem chama passa do mais específico para o mais genérico — nome do arquivo,
    depois as pastas de dentro para fora. Assim "ata-2023.pdf" dentro de
    "Postulações 2019/" é de 2023, não de 2019.

    Devolve None quando não há ano em lugar nenhum. Chutar a data de upload
    seria pior: essa data é de quando alguém mexeu no arquivo, não do documento.
    """
    for parte in partes:
        achado = _ANO.search(parte or '')
        if achado:
            ano = int(achado.group(1))
            if ANO_MINIMO <= ano <= ANO_MAXIMO:
                return ano
    return None


def titulo_de(nome_do_arquivo):
    """Nome de arquivo vira título legível.

    "ata_reuniao-geral_2023.pdf" -> "ata reuniao geral 2023". Não tenta ser
    esperto além disso: inventar capitalização em nome próprio erra mais do que
    acerta, e o título é editável na tela depois.
    """
    sem_extensao = nome_do_arquivo.rsplit('.', 1)[0] if '.' in nome_do_arquivo \
        else nome_do_arquivo
    bruto = sem_extensao.replace('_', ' ').replace('-', ' ')
    return re.sub(r'\s+', ' ', bruto).strip()[:160] or nome_do_arquivo[:160]


def extensao_de(nome_do_arquivo):
    return nome_do_arquivo.rsplit('.', 1)[-1].lower() if '.' in nome_do_arquivo else ''


def motivo_para_recusar(nome_do_arquivo, tamanho_em_bytes):
    """Por que este arquivo não entra — ou None se entra.

    O texto devolvido é agregável: aparece igual para todos os arquivos com o
    mesmo problema, para o relatório poder dizer "12x formato .mp4 não aceito"
    em vez de listar doze linhas.
    """
    extensao = extensao_de(nome_do_arquivo)
    if extensao not in EXTENSOES_ACEITAS:
        # Vídeo, planilha e afins caem aqui, e é bom que caiam: importar arquivo
        # que a tela do acervo não sabe abrir só ocupa disco.
        return f'formato .{extensao or "sem extensão"} não aceito'

    if tamanho_em_bytes is not None and tamanho_em_bytes > LIMITE_BYTES:
        return f'acima de {TAMANHO_MAXIMO_MB} MB'

    return None
