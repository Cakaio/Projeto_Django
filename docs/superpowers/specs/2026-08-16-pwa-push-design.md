# PWA + Notificações Push — Design Spec

**Data:** 2026-08-16
**App novo:** `notificacoes`
**Apps tocados:** `TESTE` (settings/urls), `sabado`, `voluntario`, `forms_pcf`, `supply`
**Autor:** PCF

## Objetivo

Transformar o PCF em app instalável no celular (Android e iOS) com notificações
push, **sem loja de aplicativos, sem conta de desenvolvedor e sem build nativo** —
tudo dentro do Django que já existe.

O voluntário abre `pcf.pythonanywhere.com` no celular, adiciona à tela de início,
e passa a ter ícone próprio, abertura em tela cheia (sem barra de navegador) e
notificações push. As 104 telas existentes são reaproveitadas sem alteração.

**Duas entregas, nesta ordem:**

1. **PWA instalável** — manifest, service worker, ícones, tela de onboarding.
   Funciona em Android, iOS 16.4+ e desktop. Independe de rede de saída do servidor.
2. **Web Push** — inscrição por aparelho, envio a partir do Django via VAPID,
   ligado a quatro gatilhos.

As duas fases são sequenciais mas independentes: a Fase 1 tem valor sozinha (ícone
e tela cheia já funcionam sem nenhum push).

## Por que PWA e não app nativo

Registrado para que a decisão não seja re-litigada:

- **Custo zero.** Play Store custa US$ 25 uma vez, App Store US$ 99/ano (isentável
  para ONG brasileira, mas com burocracia). PWA custa nada.
- **App Store rejeitaria.** A diretriz 4.2 (Minimum Functionality) rejeita "site
  empacotado", e o teste aplicado é "isso funcionaria igual no navegador?". O PCF
  é um sistema web de gestão — a resposta honesta é sim.
- **Uma pilha só.** Sem Xcode, Gradle, Mac ou CI. Quem mantém o Django mantém o app.
- **iOS não precisa de loja para push.** Desde o iOS 16.4, Web Push funciona em PWA
  adicionada à Tela de Início.

**Custo aceito:** no iOS a instalação é manual e pouco óbvia, e o push **só** funciona
depois de instalada. Por isso a tela de onboarding (`/notificacoes/instalar/`) é
parte obrigatória do escopo, não um extra.

## Passo 0 — verificação de ambiente (fazer antes de qualquer código)

**A conta do PythonAnywhere é paga — validado pelo usuário em 2026-08-16.** Isso
resolve o único risco que poderia inviabilizar o push: contas gratuitas só alcançam
sites de uma whitelist via proxy, e os servidores de push não estão nela. Conta paga
tem saída de internet irrestrita. **A Fase 2 está destravada.**

Restam duas checagens de ambiente, ambas baratas. No console Bash do PythonAnywhere:

```python
import sys, requests
print(sys.version)                      # precisa ser 3.10+
print(requests.get("https://fcm.googleapis.com", timeout=10).status_code)
```

| Resultado | Ação |
|---|---|
| Python 3.10+ e qualquer código HTTP (404/400 servem) | Segue o plano inteiro |
| Python < 3.10 | `pywebpush` 2.4.0 exige 3.10+ — trocar a versão de Python da web app **antes** de continuar. É o item de maior risco de retrabalho aqui, porque mexe na configuração da web app inteira, não só neste código |

Confirmar também que `pip install pywebpush` completa: ele arrasta
`cryptography>=47.0.0`, que é wheel binário pesado.

**Se por qualquer motivo a saída de rede aparecer bloqueada**, o contorno correto é
resolver no PythonAnywhere — não montar um relay externo. Relay significaria mandar
dado de voluntário para fora do controle do projeto.

## Contexto atual (levantado, não presumir)

- Django 4.2.27, 14 apps, 104 templates, tudo server-side. **Não existe API REST.**
- **Não existe** `manifest.json` nem service worker no projeto hoje.
- `templates/base.html` já tem `<meta name="viewport">`, `<meta name="theme-color" content="#e8560f">`
  e `<link rel="apple-touch-icon" href="{% static 'images/Logo_PCF.png' %}">`.
- `STORAGES['staticfiles']` usa `whitenoise.storage.CompressedStaticFilesStorage`
  — **sem hash no nome**, então caminhos `/static/...` são estáveis e podem ser
  escritos literalmente dentro do manifest e do service worker.
- `SECURE_PROXY_SSL_HEADER` já configurado; HTTPS é encerrado no proxy do
  PythonAnywhere. HTTPS válido é pré-requisito de PWA e **já está atendido**.
- **Conta paga no PythonAnywhere** (validado em 2026-08-16): saída de internet
  irrestrita, sem a whitelist de proxy que trava contas gratuitas. O Django pode
  falar direto com os servidores de push.
- `SESSION_COOKIE_AGE = 180 dias`, `SESSION_EXPIRE_AT_BROWSER_CLOSE = False` —
  o voluntário não reloga a cada abertura. Nada a mudar.
- `CSRF_COOKIE_SAMESITE = 'Lax'`, `CSRF_COOKIE_SECURE = not DEBUG`.
- Rotas raiz: `/` → `LandingView` (**não** é redirect para login), `/inicio/` → `inicio`.
  `LOGIN_REDIRECT_URL = 'inicio'`.
- `Pillow 11.3.0` já é dependência → **a geração de ícones não precisa de ferramenta externa**.
- `requests 2.34.2` já é dependência (pywebpush exige `>=2.21.0`).
- Sidebar (`templates/sidebar.html`) já tem drawer mobile com hambúrguer e backdrop
  abaixo de 1024px. A base responsiva existe.
- `LOGGING` hoje só declara o logger `voluntario.views`.
- Padrão de checagem de área existente: `sabado/views.py:236`
  (`AREAS_SAUDE_RESTRITA = {"TRIADE", "GESTAO_DE_TALENTOS"}`).
- Padrão de teste com mock de envio existente: `@patch('forms_pcf.views.send_mail')`
  em `forms_pcf/tests.py:110`.
- Padrão de disparo assíncrono existente: thread daemon em `voluntario/views.py`
  (`verificar_faltas_e_gerar_alertas`).

## Decisões (confirmadas com o usuário)

1. **Objetivo do app:** ícone/experiência de app **e** notificações push. Loja de
   aplicativos **não** é requisito.
2. **Sem offline real, sem câmera, sem QR code, sem leitura de dados em cache.**
3. **Quatro gatilhos de push**, todos confirmados: enquete de disponibilidade,
   ocorrências/alertas, supply/pedidos, e avisos gerais da gestão.
4. **Push soma ao e-mail, não substitui.** Quem não instalou continua recebendo
   tudo por e-mail exatamente como hoje. Nenhum `send_mail` existente é removido.
5. **O service worker não cacheia HTML.** Ver "Por que não cachear" abaixo.
6. **Sem caixa de entrada de notificações dentro do app.** A notificação leva a
   uma tela que já existe.

## Por que não cachear HTML

Decisão explícita, para o executor não "melhorar" isso:

Cachear página autenticada do Django significa servir token CSRF vencido (formulário
quebra com 403), dado de outro usuário que usou o mesmo aparelho, e tela desatualizada
sem o usuário perceber. Offline não foi pedido. O service worker existe aqui para
**receber push** e **abrir a tela certa no clique** — mais nada.

A única concessão é `/static/` em *stale-while-revalidate*, porque não tem sessão,
não tem CSRF e melhora sensivelmente a abertura em 3G no salão.

---

# Arquitetura

## Peças

| Peça | Caminho | Função |
|---|---|---|
| Manifest | `static/manifest.webmanifest` | Nome, ícones, cor, tela cheia |
| Service worker | `templates/sw.js`, servido em `/sw.js` | Push + clique + fallback offline |
| Ícones | `static/images/icons/*.png` | Gerados do logo por management command |
| App | `notificacoes/` | Inscrições, envio, onboarding, avisos |

## O service worker tem que ficar na raiz

Um service worker só controla páginas **abaixo do próprio caminho**. Servido de
`/static/js/sw.js`, o escopo seria `/static/js/` e a PWA não instalaria.

Servir em `/sw.js` via `TemplateView` no `TESTE/urls.py`:

```python
from django.views.generic import TemplateView

path("sw.js", TemplateView.as_view(
    template_name="sw.js",
    content_type="application/javascript",
), name="service_worker"),
```

Usar template (e não arquivo estático) permite embutir `{% static %}` e uma
constante de versão para invalidar cache em deploy.

---

# Models (`notificacoes/models.py`)

## `InscricaoPush`

Uma linha por **aparelho + navegador**. Um voluntário pode ter várias (celular,
tablet, desktop do escritório) e o envio percorre todas.

```python
class InscricaoPush(models.Model):
    voluntario   = models.ForeignKey(settings.AUTH_USER_MODEL,
                                     on_delete=models.CASCADE,
                                     related_name="inscricoes_push")
    endpoint     = models.URLField(max_length=500, unique=True)
    p256dh       = models.CharField(max_length=255)
    auth         = models.CharField(max_length=255)
    user_agent   = models.CharField(max_length=255, blank=True)
    criado_em    = models.DateTimeField(auto_now_add=True)
    ultimo_ok    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "inscrição push"
        verbose_name_plural = "inscrições push"
        ordering = ("-criado_em",)
```

- `endpoint` é `unique` porque o navegador reemite o mesmo endpoint ao reinscrever.
  Reinscrição do mesmo endpoint **atualiza** a linha (inclusive trocando de
  voluntário, no caso de aparelho compartilhado) — nunca duplica.
- `max_length=500`: endpoints do FCM passam de 200 caracteres com folga.
- `ultimo_ok` serve para diagnosticar inscrição zumbi. Não tem lógica dependendo dele.

## `Aviso`

Só o broadcast manual. Os outros três gatilhos já deixam rastro nos modelos deles
(`Ocorrencia`, `Pedido`, `DisponibilidadeVoluntario`), então não replicar registro.

```python
DESTINO_CHOICES = [("TODOS", "Todos"), ("AREA", "Por área")]

class Aviso(models.Model):
    autor         = models.ForeignKey(settings.AUTH_USER_MODEL,
                                      on_delete=models.SET_NULL, null=True,
                                      related_name="avisos_enviados")
    titulo        = models.CharField(max_length=80)
    mensagem      = models.CharField(max_length=300)
    destino       = models.CharField(max_length=10, choices=DESTINO_CHOICES)
    alvo          = models.CharField(max_length=30, blank=True)   # valor de LISTA_AREAS
    criado_em     = models.DateTimeField(auto_now_add=True)
    total_enviado = models.PositiveIntegerField(default=0)
```

- `titulo` 80 e `mensagem` 300 não são arbitrários: Android trunca notificação
  longa e iOS mostra ~4 linhas. O form deve mostrar contador de caracteres.
- **Não existe destino "por sala" separado.** As 7 salas (`VIOLETA`…`VERMELHO`)
  e `FAMILIA_FELIZ` **são valores de `LISTA_AREAS`** em `voluntario/models.py:10`,
  no mesmo campo `Voluntario.area` das áreas funcionais. Um destino `SALA` filtraria
  exatamente o mesmo campo que `AREA` — seriam dois nomes para uma coisa só.
- `alvo` é `CharField` validado contra `LISTA_AREAS` no form, importando a tupla de
  `voluntario.models`. **Não copiar a lista** — ela já foi duplicada demais neste
  projeto (`atendido`, `semanario`, e quatro migrations de apps diferentes).

---

# Serviço de envio (`notificacoes/services.py`)

Interface única, usada pelos quatro gatilhos:

```python
def enviar_push(voluntarios, titulo, corpo, url="/inicio/", tag=None) -> int:
    """Envia push para todas as inscrições dos voluntários. Retorna quantos foram."""

def enviar_push_async(voluntarios, titulo, corpo, url="/inicio/", tag=None) -> None:
    """Igual, em thread daemon. Usar no caminho de request."""
```

## Regras de implementação

- `voluntarios` aceita queryset ou lista. Resolver as inscrições com
  `InscricaoPush.objects.filter(voluntario__in=voluntarios).select_related("voluntario")`.
- Payload é JSON: `{"titulo": ..., "corpo": ..., "url": ..., "tag": ...}`.
- Chamada:

```python
webpush(
    subscription_info={"endpoint": i.endpoint,
                       "keys": {"p256dh": i.p256dh, "auth": i.auth}},
    data=json.dumps(payload),
    vapid_private_key=settings.VAPID_PRIVATE_KEY,
    vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
    ttl=86400,
)
```

- **`vapid_claims` tem que ser um dicionário novo a cada chamada.** O `pywebpush`
  muta o dicionário recebido (grava `exp` dentro dele); reutilizar um dict de
  módulo faz o segundo envio falhar com token expirado. Este é o bug mais provável
  de toda esta entrega — construir o dict dentro do loop.
- **Erro 404 ou 410 (Gone):** a inscrição morreu (desinstalou, trocou de celular,
  limpou o navegador). **Apagar a linha imediatamente.**
- **Qualquer outro erro:** `logger.warning` com o endpoint truncado e seguir o loop.
  Uma inscrição podre nunca pode derrubar o envio das outras 59, nem estourar a
  request do usuário.
- **Sucesso:** gravar `ultimo_ok = timezone.now()` (`update_fields`, não `save()` inteiro).
- **Se `VAPID_PRIVATE_KEY` estiver vazia:** `logger.warning` e retornar `0` sem
  tentar enviar. Isso mantém dev local e a suíte de testes funcionando sem chaves.
- `timezone.now()`, nunca `datetime.now()` (`USE_TZ = True`).

## Geração das chaves VAPID

Management command `notificacoes/management/commands/gerar_chaves_vapid.py`, que
imprime as duas chaves em base64url pronto para colar no `.env`:

```python
from py_vapid import Vapid02
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import base64

def b64(b): return base64.urlsafe_b64encode(b).decode().rstrip("=")

v = Vapid02(); v.generate_keys()
priv = b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
pub  = b64(v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))
```

**Gerar uma vez só.** Trocar a chave pública invalida **todas** as inscrições
existentes e todo mundo precisa reativar. Deixar isso escrito no output do comando.

---

# Settings (`TESTE/settings.py`)

```python
INSTALLED_APPS += ['notificacoes']

VAPID_PUBLIC_KEY  = config("VAPID_PUBLIC_KEY",  default="")
VAPID_PRIVATE_KEY = config("VAPID_PRIVATE_KEY", default="")
VAPID_ADMIN_EMAIL = config("VAPID_ADMIN_EMAIL", default="")
```

`default=""` é intencional: sem ele, o projeto quebra em qualquer máquina que não
tenha as chaves, incluindo a suíte de testes.

Adicionar ao `LOGGING['loggers']`:

```python
'notificacoes': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
```

`.env.example` ganha as três variáveis, comentadas com "gerar via
`python manage.py gerar_chaves_vapid`".

`requirements.txt` ganha `pywebpush==2.4.0` com comentário explicando que traz
`py-vapid`, `http-ece` e `cryptography` junto, e que exige Python 3.10+.

---

# Manifest (`static/manifest.webmanifest`)

```json
{
  "id": "/",
  "name": "Projeto Criança Feliz",
  "short_name": "PCF",
  "description": "Gestão do Projeto Criança Feliz",
  "start_url": "/inicio/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#ffffff",
  "theme_color": "#e8560f",
  "lang": "pt-BR",
  "dir": "ltr",
  "icons": [
    {"src": "/static/images/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/static/images/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/static/images/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

- `start_url: "/inicio/"` e não `/`: a raiz é a `LandingView` pública. Quem abre o
  app quer o painel.
- `scope: "/"` para o app não "escapar" para o navegador ao navegar entre apps.
- `theme_color` igual ao `<meta name="theme-color">` que já existe no `base.html`.
- Caminhos literais `/static/...` são seguros porque o `CompressedStaticFilesStorage`
  não coloca hash no nome.
- Servir com `Content-Type: application/manifest+json` (o WhiteNoise já resolve
  `.webmanifest` corretamente; conferir na Fase 1).

## Ícones

Management command `notificacoes/management/commands/gerar_icones_pwa.py`, usando
Pillow (já instalado), lendo `static/images/Logo_PCF.png` e gravando em
`static/images/icons/`:

| Arquivo | Tamanho | Observação |
|---|---|---|
| `icon-192.png` | 192×192 | logo ocupando a arte toda |
| `icon-512.png` | 512×512 | idem |
| `icon-512-maskable.png` | 512×512 | logo em **80% do canvas**, centralizado, resto preenchido com a cor de fundo |
| `apple-touch-icon-180.png` | 180×180 | **fundo opaco obrigatório** — iOS não respeita transparência e renderiza preto |
| `badge-72.png` | 72×72 | monocromático, silhueta branca sobre transparente (Android usa na status bar) |

O ícone *maskable* precisa da margem de 20% porque o Android recorta em círculo,
losango ou squircle conforme o fabricante — logo sem margem sai decapitado.

---

# Service worker (`templates/sw.js`)

Constante de versão no topo (`const VERSAO = 'pcf-v1';`) — **bumpar a cada deploy
que mexa no service worker**, senão o navegador serve o antigo.

## `install` / `activate`

`skipWaiting()` no install e `clients.claim()` no activate, mais limpeza de caches
com nome diferente do `VERSAO` atual. Sem isso, o service worker novo só assume na
segunda abertura do app.

## `push`

```js
self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.titulo || 'PCF', {
    body: d.corpo || '',
    icon: '/static/images/icons/icon-192.png',
    badge: '/static/images/icons/badge-72.png',
    tag: d.tag || undefined,
    data: { url: d.url || '/inicio/' },
    lang: 'pt-BR',
  }));
});
```

O `try/catch` importa: alguns servidores de push mandam evento sem payload, e uma
exceção aqui derruba o handler inteiro em silêncio.

## `notificationclick`

Focar uma janela já aberta em vez de abrir outra — senão o voluntário acumula
janelas do app:

```js
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/inicio/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((lista) => {
      for (const c of lista) {
        if ('focus' in c) return c.navigate(url).then((cl) => cl && cl.focus());
      }
      return clients.openWindow(url);
    })
  );
});
```

## `fetch`

Escopo mínimo e deliberado:

- `/static/` → *stale-while-revalidate* no cache `VERSAO`.
- Navegação (`request.mode === 'navigate'`) → **rede primeiro**; se a rede falhar,
  devolve `/notificacoes/offline/`.
- **Todo o resto passa direto**, sem tocar. Nenhuma resposta de HTML autenticado
  entra em cache, nunca.

Ignorar explicitamente requisições que não sejam `GET`.

---

# `templates/base.html`

Dentro do `<head>`, junto do `apple-touch-icon` que já existe:

```html
<link rel="manifest" href="{% static 'manifest.webmanifest' %}">
<link rel="apple-touch-icon" sizes="180x180" href="{% static 'images/icons/apple-touch-icon-180.png' %}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="PCF">
```

`apple-mobile-web-app-capable` está formalmente obsoleto em favor do `display` do
manifest, mas versões de iOS ainda em uso o respeitam — manter os dois.

No fim do `<body>`, junto do `pcf-fx.js`:

```html
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    });
  }
</script>
```

O `.catch` vazio é proposital: falha de registro de service worker não pode gerar
erro visível para o voluntário.

---

# Rotas (`notificacoes/urls.py`, prefixo `/notificacoes/`)

`app_name = 'notificacoes'`. Incluir em `TESTE/urls.py` **antes** do include da
`revista` (que monta na raiz).

| Rota | Nome | Método | Acesso |
|---|---|---|---|
| `instalar/` | `instalar` | GET | logado |
| `inscrever/` | `inscrever` | POST | logado |
| `desinscrever/` | `desinscrever` | POST | logado |
| `testar/` | `testar` | POST | logado |
| `avisos/` | `avisos` | GET/POST | TRIADE, GT, superuser |
| `offline/` | `offline` | GET | **público** |

`offline/` tem que ser público: se a sessão expirou e a rede caiu, uma tela de
offline atrás de `@login_required` vira redirect para login que também não carrega.

---

# Views (`notificacoes/views.py`)

## `instalar` — `LoginRequired`, `TemplateView`

Renderiza `notificacoes/instalar.html`. Passa no contexto:

- `vapid_public_key` — `settings.VAPID_PUBLIC_KEY`
- `push_disponivel` — `bool(settings.VAPID_PUBLIC_KEY)`
- `inscricoes` — as inscrições do usuário, para listar "aparelhos ativos"

A chave pública vai para o JS por **`data-` attribute** no elemento, não por
variável global nem por endpoint extra.

## `inscrever` — `LoginRequired`, POST, JSON

Recebe `{endpoint, keys: {p256dh, auth}}` (o `subscription.toJSON()` do navegador).

- Validar os três campos; faltando qualquer um → `400`.
- `update_or_create(endpoint=..., defaults={voluntario, p256dh, auth, user_agent})`.
  O `update_or_create` por `endpoint` é o que garante o comportamento de aparelho
  compartilhado descrito no model.
- `user_agent` truncado em 255 a partir do header.
- Responde `{"ok": true}`.

## `desinscrever` — `LoginRequired`, POST, JSON

Recebe `{endpoint}`, apaga a inscrição **daquele usuário** com aquele endpoint.
Filtrar por `voluntario=request.user` também, não só por endpoint — senão um POST
forjado apaga inscrição alheia.

## `testar` — `LoginRequired`, POST

Dispara um push "Funcionou! 🎉" para o próprio usuário, **síncrono** (não async:
o usuário está olhando para a tela esperando o resultado). Responde quantos
aparelhos receberam. É a ferramenta de diagnóstico do onboarding.

## `avisos` — `LoginRequired`, GET/POST

Restrito a `{"TRIADE", "GESTAO_DE_TALENTOS"}` **ou** `is_superuser`, seguindo
`sabado/views.py:236`. Quem não tem acesso recebe `403` (`PermissionDenied`),
não redirect silencioso.

- GET: formulário (título, mensagem, destino, alvo) + histórico dos últimos 20 avisos.
- POST: valida, resolve o público-alvo, salva o `Aviso`, dispara `enviar_push_async`,
  grava `total_enviado`, `messages.success` com a contagem, redireciona para a
  própria tela.

**Resolução do público-alvo** — sempre restrita a voluntários ativos, usando o
manager `Voluntario.objects.ativos()` que **já existe** em `voluntario/models.py`
(filtra `data_saida__isnull=True` **e** `is_active=True`). Não reescrever esse
filtro à mão: `data_saida` sozinho deixaria passar login desativado.

| destino | queryset |
|---|---|
| `TODOS` | `Voluntario.objects.ativos()` |
| `AREA` | `Voluntario.objects.ativos().filter(area=alvo)` |

O select de área usa `LISTA_AREAS` inteira — logo "mandar para a sala Violeta" já é
`destino=AREA, alvo=VIOLETA`.

## `offline` — `TemplateView`, sem login

Página estática simples: logo, "Sem conexão", botão "Tentar de novo"
(`location.reload()`). Não pode depender de nada de `/static/` que não esteja no
cache do service worker.

---

# Tela de instalação (`templates/notificacoes/instalar.html`)

É a peça que decide se o projeto pega ou não. Sem ela, ninguém no iPhone instala.

## Estados

A tela detecta e mostra **um** estado por vez:

```
já instalado (display-mode: standalone)
   ├─ push já ativo         → "Notificações ativas neste aparelho" + lista de aparelhos + botão Testar
   ├─ push negado           → instruções para reverter nas configurações do navegador
   └─ push não pedido       → botão "Ativar notificações"
não instalado
   ├─ Android/Chrome        → botão "Instalar app" (beforeinstallprompt) + passo a passo de reserva
   ├─ iOS/Safari            → passo a passo ilustrado (não existe prompt no iOS)
   ├─ iOS/outro navegador   → "Abra esta página no Safari" (Chrome no iPhone não instala PWA)
   └─ desktop               → "Você pode ativar notificações aqui mesmo" (Android/desktop não exigem instalação)
```

## Detecção

```js
const instalado = window.matchMedia('(display-mode: standalone)').matches
               || window.navigator.standalone === true;   // iOS
const iOS = /iP(hone|ad|od)/.test(navigator.userAgent);
const safari = iOS && !/CriOS|FxiOS|EdgiOS/.test(navigator.userAgent);
```

`window.navigator.standalone` é específico do iOS e é o único sinal confiável lá.

## Regra crítica de permissão

**Nunca chamar `Notification.requestPermission()` no carregamento da página.**
Só dentro do handler de clique do botão. Navegador pune pedido sem gesto do
usuário, e voluntário que nega uma vez nega para sempre — não há segunda chance
sem ele ir no menu de configurações do navegador.

## Fluxo de ativação

```
clique → Notification.requestPermission()
       → 'granted'? → navigator.serviceWorker.ready
                    → registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(chavePublica)
                      })
                    → POST /notificacoes/inscrever/ (JSON + header X-CSRFToken)
                    → estado "ativo" + oferece o botão Testar
       → 'denied'?  → instruções de como reverter
```

- `userVisibleOnly: true` é obrigatório — o navegador recusa a inscrição sem ele.
- `applicationServerKey` precisa ser `Uint8Array`; incluir o helper
  `urlBase64ToUint8Array` (padding com `=` e troca de `-_` por `+/`).
- CSRF: pegar de `{{ csrf_token }}` renderizado em `data-csrf`, não do cookie.
- Antes de inscrever, checar `pushManager.getSubscription()` — se já existe, só
  reenviar ao servidor (idempotente pelo `update_or_create`).

## Diferença Android × iOS a comunicar na tela

**No Android o push funciona sem instalar**, direto na aba do Chrome — a instalação
só melhora a experiência. **No iOS não funciona:** a API de notificação nem existe
fora da PWA instalada. Por isso o botão "Ativar notificações" **não pode aparecer**
num iPhone que ainda não instalou — mostraria um botão que estoura erro.

## Ponto de entrada

Um item **"Instalar no celular"** no menu de perfil do `templates/sidebar.html`,
visível para todo voluntário logado. Sem banner automático em `/inicio/` nesta
versão — banner intrusivo é a forma mais rápida de queimar a permissão.

---

# Os quatro gatilhos

Em todos: o push é **adicional**; nenhum `send_mail` existente sai. Todos usam a
mesma função `enviar_push`/`enviar_push_async`.

| # | Onde | Quando | Público | Título / URL |
|---|---|---|---|---|
| 1 | `sabado/management/commands/lembrete_disponibilidade.py` | junto do e-mail que já existe | quem não respondeu a enquete | "Enquete do sábado fecha amanhã" → tela da enquete |
| 2 | `voluntario/views.py` — o helper de e-mail do SAAs (`EmailMultiAlternatives`, ~linha 738) e `verificar_faltas_e_gerar_alertas` (AL13) | ao registrar `Ocorrencia` | o voluntário da ocorrência | "Você recebeu um comunicado" → detalhe da ocorrência |
| 3 | `supply/views.py:499` (`adicionar_pedidos`) e `forms_pcf/views.py:90` (reembolso) | pedido/reembolso criado | ativos das áreas `SUPPLY` e `ADM/FIN` | "Novo pedido de material" → `/supply/meus-pedidos/` (conferir o nome real da rota) |
| 4 | `notificacoes/views.py` (`avisos`) | disparo manual | todos, ou uma área de `LISTA_AREAS` | o título escrito pelo autor → `/inicio/` |

**Gatilho 1 roda em management command** → usar `enviar_push` **síncrono**. Thread
daemon em comando agendado morre quando o processo encerra, e a notificação some.

**Gatilhos 2, 3 e 4 rodam em request** → usar `enviar_push_async` (thread daemon),
seguindo o padrão que `verificar_faltas_e_gerar_alertas` já usa, para não segurar
a resposta HTTP.

Toda URL de push tem que ser **absoluta a partir da raiz** (`/voluntario/...`),
porque quem consome é o service worker, não um template.

---

# Admin (`notificacoes/admin.py`)

- `InscricaoPushAdmin`: `list_display` com voluntário, user_agent, criado_em,
  ultimo_ok; `search_fields` no voluntário; **readonly em tudo**. Ninguém edita
  chave de criptografia na mão — só apaga.
- `AvisoAdmin`: `list_display` autor/título/destino/total_enviado/criado_em,
  readonly. É registro histórico.

Diferente do resto do projeto, **não** usar `ImportExportModelAdmin` aqui:
exportar chaves de push para planilha é vazamento de credencial.

---

# Testes (`notificacoes/tests.py`)

`webpush` **sempre** mockado — nenhum teste toca a rede. Seguir o padrão
`@patch('forms_pcf.views.send_mail')` de `forms_pcf/tests.py:110`, aqui como
`@patch('notificacoes.services.webpush')`.

## Inscrição

1. POST em `inscrever/` sem login → redireciona para login.
2. POST válido cria `InscricaoPush` ligada ao `request.user`.
3. POST com o **mesmo endpoint** atualiza a linha em vez de duplicar (`count() == 1`).
4. POST sem `keys.p256dh` → `400`, nada criado.
5. `desinscrever/` com endpoint de **outro** usuário não apaga nada.

## Envio

6. `enviar_push` chama `webpush` uma vez por inscrição do voluntário.
7. Voluntário com dois aparelhos → duas chamadas.
8. `WebPushException` com `response.status_code == 410` → a inscrição é **apagada**.
9. `WebPushException` com `500` → inscrição **mantida** e a exceção **não propaga**.
10. Duas inscrições, a primeira falhando → a segunda ainda recebe (o loop não para).
11. `VAPID_PRIVATE_KEY = ""` → retorna `0`, `webpush` nunca é chamado.
12. Sucesso grava `ultimo_ok`.
13. Cada chamada recebe um dict `vapid_claims` **novo** (regressão do bug de mutação
    do `pywebpush` — assertar que dois envios seguidos não compartilham o objeto).

## Avisos

14. GET `avisos/` como voluntário de sala comum → `403`.
15. GET como `TRIADE` → `200`.
16. POST válido cria `Aviso` e dispara push só para voluntários **ativos**
    (`Voluntario.objects.ativos()`) — voluntário desligado não recebe.
17. POST com `destino=AREA` envia só para a área escolhida.

## Infraestrutura

18. `GET /sw.js` → `200` com `Content-Type` de JavaScript.
19. O manifest é JSON válido e tem `start_url`, `scope` e ao menos um ícone 192 e
    um 512. **Não testar via `self.client.get('/static/...')`** — o test client não
    serve arquivos estáticos (`DEBUG=False` na suíte, e o handler do `staticfiles`
    não é montado). Localizar o arquivo com
    `django.contrib.staticfiles.finders.find('manifest.webmanifest')` e abrir do disco.
20. `GET /notificacoes/offline/` → `200` **sem** estar logado.

---

# Ordem de execução

## Fase 0 — verificação de ambiente
Passo 0 acima: versão do Python e `pip install pywebpush`. A saída de rede já está
confirmada (conta paga).

## Fase 1 — PWA instalável
1. `gerar_icones_pwa` + rodar o comando
2. `static/manifest.webmanifest`
3. `templates/sw.js` + rota `/sw.js` + registro no `base.html`
4. meta tags iOS no `base.html`
5. tela `offline/`
6. tela `instalar/` — só a parte de instalação, sem push
7. link no menu de perfil da sidebar

**Verificação de aceite da Fase 1:** instalar de verdade num Android e num iPhone
seguindo o passo a passo, e confirmar que abre em tela cheia, sem barra de endereço,
com ícone correto.

## Fase 2 — Web Push
8. `pywebpush` no `requirements.txt` + settings + `.env.example`
9. `gerar_chaves_vapid` + gerar e guardar as chaves
10. models + migration
11. `services.enviar_push` / `enviar_push_async`
12. views `inscrever` / `desinscrever` / `testar`
13. parte de push na tela `instalar/` + handlers no service worker
14. admin
15. testes

**Verificação de aceite da Fase 2:** botão "Testar" entrega notificação num Android
e num iPhone reais, com o app **fechado**.

## Fase 3 — os gatilhos
16. gatilho 1 (enquete), 2 (ocorrências), 3 (supply), 4 (avisos, com tela)

---

# Passo a passo de instalação (texto para os voluntários)

## Android (Chrome)

1. Abrir `pcf.pythonanywhere.com` no **Chrome** e fazer login.
2. Tocar no aviso **"Instalar app"**. Se não aparecer: menu ⋮ → **Adicionar à tela inicial** → **Instalar**.
3. Confirmar. O ícone do PCF aparece junto dos outros apps.
4. Abrir pelo ícone → **Ativar notificações** → **Permitir**.

Quem não quiser instalar ainda recebe notificação pelo Chrome normalmente.

## iPhone e iPad (Safari — obrigatório)

1. Abrir `pcf.pythonanywhere.com` no **Safari** e fazer login.
   **Não funciona no Chrome do iPhone** — só o Safari instala PWA no iOS.
2. Tocar em **Compartilhar** (quadrado com seta para cima, na barra de baixo).
3. Rolar e tocar em **Adicionar à Tela de Início**.
4. Tocar em **Adicionar**, no canto superior direito.
5. **Fechar o Safari e abrir o PCF pelo ícone novo.** Não é opcional: o iOS só
   entrega notificação para app aberto pelo ícone.
6. Tocar em **Ativar notificações** → **Permitir**.

Notificações exigem **iOS 16.4 ou superior**. Em iPhone mais antigo o ícone e a
tela cheia funcionam; só o push não.

---

# Riscos e não-escopo

## Riscos conhecidos

| Risco | Mitigação |
|---|---|
| Python < 3.10 na web app (`pywebpush` exige 3.10+) | Passo 0 antes de qualquer código — mexer na versão de Python depois de escrever tudo é o pior retrabalho possível aqui |
| Adoção no iOS travada pela instalação manual | Tela de onboarding dedicada + botão "Testar" para o voluntário confirmar sozinho |
| Service worker antigo servido após deploy | Constante `VERSAO` + `skipWaiting` + `clients.claim` |
| `vapid_claims` mutado pelo `pywebpush` | Dict novo por chamada + teste 13 |
| Voluntário nega a permissão e não sabe reverter | Estado "negado" com instruções na tela |
| Push de ocorrência disciplinar aparecendo na tela de bloqueio | Título genérico ("Você recebeu um comunicado"); o detalhe só depois de abrir |

## Fora de escopo, de propósito

Offline real, câmera, leitura de QR code, biometria, caixa de entrada de
notificações dentro do app, publicação em loja (Play via TWA e App Store via
Capacitor), e notificação por WhatsApp.

## Trabalho adjacente identificado, não incluído

As 104 telas nascem responsivas na estrutura (a sidebar já tem drawer mobile), mas
as tabelas largas — semanário, supply, listagem de atendidos — provavelmente ficam
apertadas no celular. **Recomendada uma auditoria tela a tela como trabalho
separado**, depois que a PWA estiver de pé. Não faz parte desta entrega.
