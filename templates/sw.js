/* Service worker do PCF.
 *
 * Escopo deliberadamente pequeno: recebe push, abre a tela certa no clique, e
 * mostra uma página de "sem conexão" quando a navegação falha.
 *
 * NÃO cacheia HTML. Página autenticada do Django em cache significa token CSRF
 * vencido (formulário quebra com 403) e dado de outro usuário no mesmo aparelho.
 *
 * Ao alterar este arquivo, BUMPAR a constante VERSAO — senão o navegador
 * continua servindo o service worker antigo.
 */
const VERSAO = 'pcf-v1';
const CACHE_ESTATICO = `${VERSAO}-estatico`;
const PAGINA_OFFLINE = '/notificacoes/offline/';

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_ESTATICO)
      .then((c) => c.add(PAGINA_OFFLINE))
      .catch(() => {})            // sem rede na instalação não pode travar o install
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(
        nomes.filter((n) => !n.startsWith(VERSAO)).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Estáticos: stale-while-revalidate. Sem sessão, sem CSRF, seguro de cachear.
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(CACHE_ESTATICO).then((cache) =>
        cache.match(req).then((cacheado) => {
          const rede = fetch(req)
            .then((resp) => { if (resp.ok) cache.put(req, resp.clone()); return resp; })
            .catch(() => cacheado);
          return cacheado || rede;
        })
      )
    );
    return;
  }

  // Navegação: rede primeiro; se cair, a página de offline.
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match(PAGINA_OFFLINE)));
  }

  // Todo o resto passa direto, sem tocar.
});

self.addEventListener('push', (e) => {
  let d = {};
  // Alguns servidores de push mandam evento sem payload; uma exceção aqui
  // derruba o handler inteiro em silêncio.
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

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/inicio/';

  // Focar uma janela já aberta em vez de abrir outra — senão o voluntário
  // acumula janelas do app.
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((lista) => {
      for (const c of lista) {
        if ('focus' in c) return c.navigate(url).then((cl) => cl && cl.focus());
      }
      return self.clients.openWindow(url);
    })
  );
});
