from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.db import models
from voluntario.models import Voluntario
from django.utils import timezone
from django.db.models import Count, Value, IntegerField, F, Q
from django.urls import reverse

from sabado.models import Sabado
from ronda.models import ConfiguracaoRondaSabado


class LandingView(TemplateView):
    """Landing page pública do projeto (rota '/'). Não exige login."""
    template_name = "landing.html"


# ─────────────────────────── Uploads (/media/) ───────────────────────────
# Só estas pastas podem ser abertas sem login, e por um motivo concreto: são
# as fotos que aparecem na revista do doador, que é uma página pública por
# design (link secreto, sem conta no sistema).
#
# Todo o resto exige sessão. Ali dentro estão documentos de atendidos
# (documentos_atendidos), fotos das crianças (fotos_atendidos), comprovantes de
# reembolso com dado pessoal (reembolsos) e fotos dos voluntários — nada disso
# pode ficar acessível a quem descobrir ou adivinhar um endereço.
PASTAS_DE_MIDIA_PUBLICA = ("revista/", "fotos_atividades/")


def midia(request, path):
    """Entrega um arquivo de /media/, exigindo login no que é sensível.

    Existe porque o WhiteNoise só serve /static/, e servir /media/ inteiro sem
    autenticação (como estava) publicava documento de criança para qualquer um.

    Em produção o ideal é o PythonAnywhere entregar /media/ pelo mapeamento da
    aba "Web" — mas o mapeamento não sabe checar sessão, então as pastas
    privadas devem continuar passando por aqui.
    """
    import posixpath

    from django.views.static import serve as servir_arquivo

    # Normalizar ANTES de olhar o prefixo é o ponto todo: sem isto,
    # "fotos_atividades/../documentos_atendidos/rg.pdf" começa com uma pasta
    # pública, passa na checagem, e o `serve` — que normaliza por conta
    # própria — entrega o documento da criança. A pasta pública viraria porta
    # dos fundos para o resto do /media/.
    caminho = posixpath.normpath((path or "").replace("\\", "/")).lstrip("/")
    if caminho.startswith("..") or caminho == ".":
        raise Http404("Arquivo não disponível.")

    publico = caminho.startswith(PASTAS_DE_MIDIA_PUBLICA)

    if not publico and not request.user.is_authenticated:
        # 404, e não 403: para quem não tem sessão o arquivo simplesmente não
        # existe — assim não confirmamos que aquele caminho é válido.
        raise Http404("Arquivo não disponível.")

    resposta = servir_arquivo(request, caminho, document_root=settings.MEDIA_ROOT)
    if publico:
        # São fotos de crianças: podem ser abertas por quem tem o link da
        # revista, mas não podem cair em buscador.
        resposta["X-Robots-Tag"] = "noindex, nofollow, noimageindex"
    return resposta


# ─────────────────────────── Busca global ───────────────────────────
def _paginas_do_usuario(user):
    """Telas navegáveis, já filtradas pelo que o usuário pode acessar.
    Espelha as regras da sidebar (mesma fonte de verdade de permissão)."""
    area = getattr(user, "area", None)
    is_su = user.is_superuser
    paginas = [
        ("Início", "inicio", "Painel principal", True),
        ("Painel do Sábado", "sabado:resumo_sabado", "Disponibilidade dos voluntários", True),
        ("Semanários", "semanario:semanario_view", "Planejamento por sala", True),
        ("Rondas do Sábado", "ronda:ronda_publica", "Escala de rondas", True),
        ("Relatório Pedagógico", "semanario:relatorio_pedagogico", "Competências e dimensões", True),
        ("Atendidos", "atendido:atendido_view", "Visão geral dos atendidos", True),
        ("Atendidos matriculados", "atendido:lista_atendidos", "Lista completa", True),
        ("Presenças dos atendidos", "atendido:visualizar_presencas_atendidos", "Histórico e gráficos", True),
        ("Nova Matrícula", "atendido:matricula", "Cadastrar criança", is_su or getattr(user, "is_matricula", False)),
        ("Lista de Espera", "atendido:visualizar_lista_espera", "Fila de espera", is_su or getattr(user, "is_matricula", False)),
        ("Voluntários", "voluntario:voluntario_view", "Visão geral da equipe", True),
        ("Lista de voluntários", "voluntario:lista_voluntarios", "Equipe por área", True),
        ("Presenças dos voluntários", "voluntario:visualizar_presencas_voluntarios", "Histórico e gráficos", True),
        ("Organograma", "voluntario:organograma", "Hierarquia de liderança", True),
        ("Histórico de Líderes", "voluntario:historico_lideres", "Quem liderou cada área", True),
        ("Grupos", "voluntario:grupos", "Grupos de pautas", True),
        ("Pautas Recebidas", "gerenciamento:pautas", "Pautas dos seus grupos", True),
        ("Minhas Pautas", "gerenciamento:minhas_pautas", "Pautas que você criou", True),
        ("Nova Pauta", "gerenciamento:criar_pauta", "Criar pauta", True),
        ("Supply", "supply:supply_view", "Estoque e materiais", True),
        ("Meus Pedidos", "supply:meus_pedidos", "Seus pedidos de material", True),
        ("Novo Pedido", "supply:adicionar_pedidos", "Solicitar material", True),
        ("Painel de Materiais", "supply:painel_materiais", "Edição em lote",
         is_su or area in ("SUPPLY", "TRIADE")),
        ("Pedido de Reembolso", "forms_pcf:reembolso", "Solicitar reembolso", True),
        ("Dores & Sugestões", "forms_pcf:feedback", "Enviar feedback", True),
        ("Financeiro", "adm:painel", "Lançamentos, fluxo e DRE",
         is_su or area in ("ADM/FIN", "TRIADE")),
        ("SAAS", "voluntario:saas", "Ocorrências disciplinares",
         is_su or area in ("GESTAO_DE_TALENTOS", "TRIADE")),
        ("Gestão de Rondas", "ronda:painel", "Sortear e aprovar escalas",
         is_su or area == "TRIADE"),
        ("Caixa de Dores & Sugestões", "forms_pcf:feedback_inbox", "Feedbacks recebidos",
         is_su or area in ("PROJETOS", "TRIADE")),
        ("Backlog de Projetos", "projetos:backlog", "O que estamos fazendo para cada área",
         is_su or area in ("PROJETOS", "TRIADE")),
        ("Relação com as Áreas", "projetos:por_area", "Quais áreas responderam e quais sumiram",
         is_su or area in ("PROJETOS", "TRIADE")),
        ("Parceiros", "parceiros:painel", "CRM de doadores e arrecadação",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Grade de Parceiros", "parceiros:grade", "Arrecadação mês a mês",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Lista de Parceiros", "parceiros:lista", "Doadores e carteiras",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Revistinha", "revista:lista", "Revista dos semanários para os doadores",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Editais", "editais:lista", "Editais que o robô encontrou",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Fontes de Editais", "editais:fontes", "De onde o robô lê",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Buscas de Editais", "editais:consultas", "O que o robô pergunta à web",
         is_su or area in ("CR/RE", "TRIADE")),
        ("Onde Investimos", "adm:onde_investimos", "Em que o dinheiro foi aplicado",
         is_su or area in ("CR/RE", "ADM/FIN", "TRIADE")),
        ("Meu Perfil", "voluntario:meu_perfil", "Seus dados e talentos", True),
    ]
    return [(nome, url, desc) for nome, url, desc, pode in paginas if pode]


@login_required(login_url="/login/")
def busca(request):
    """Busca global da topbar: páginas, atendidos, voluntários e semanários."""
    from atendido.models import Atendido
    from semanario.models import Semanario

    q = (request.GET.get("q") or "").strip()
    paginas, atendidos, voluntarios, semanarios = [], [], [], []

    if len(q) >= 2:
        termo = q.lower()
        for nome, url_name, desc in _paginas_do_usuario(request.user):
            if termo in nome.lower() or termo in desc.lower():
                try:
                    paginas.append({"nome": nome, "url": reverse(url_name), "descricao": desc})
                except Exception:
                    continue

        atendidos = list(
            Atendido.objects.filter(nome__icontains=q).order_by("nome")[:12]
        )
        voluntarios = list(
            Voluntario.objects
            .filter(data_saida__isnull=True)
            .filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                    Q(username__icontains=q) | Q(apelido__icontains=q))
            .order_by("first_name")[:12]
        )
        semanarios = list(
            Semanario.objects
            .filter(Q(tema__icontains=q) | Q(sala__icontains=q))
            .select_related("data").order_by("-data__data")[:12]
        )

    total = len(paginas) + len(atendidos) + len(voluntarios) + len(semanarios)
    return render(request, "busca.html", {
        "q": q, "paginas": paginas, "atendidos": atendidos,
        "voluntarios": voluntarios, "semanarios": semanarios, "total": total,
    })


class inicio(TemplateView):
    template_name = "inicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # A mesma regra usada no restante do projeto: o voluntário ainda faz
        # parte da equipe e a checkbox "Ativo" do usuário está marcada.
        total_ativos = Voluntario.objects.ativos().count()

        sabados_qs = (
            Sabado.objects
            .filter(data__gte=timezone.now().date())
            .order_by("data")
            .annotate(
                respostas_count=Count(
                    "disponibilidades",
                    filter=Q(
                        disponibilidades__voluntario__data_saida__isnull=True,
                        disponibilidades__voluntario__is_active=True,
                    ),
                    distinct=True,
                )
            )
        )

        sabados_abertos = []
        for s in sabados_qs:
            if not s.enquete_aberta:
                continue

            s.total_voluntarios_ativos = total_ativos
            s.total_respostas_view = s.respostas_count
            s.total_nao_responderam = max(0, total_ativos - s.total_respostas_view)

            if total_ativos == 0:
                s.percentual_respostas_int = 0
            else:
                pct = (s.total_respostas_view / total_ativos) * 100
                s.percentual_respostas_int = int(round(max(0, min(100, pct))))

            sabados_abertos.append(s)

        context["sabados_abertos"] = sabados_abertos
        context["total_voluntarios_ativos"] = total_ativos

        context["proxima_ronda"] = (
            ConfiguracaoRondaSabado.objects
            .filter(status='APROVADA', sabado__data__gte=timezone.now().date())
            .select_related('sabado')
            .order_by('sabado__data')
            .first()
        )

        return context
