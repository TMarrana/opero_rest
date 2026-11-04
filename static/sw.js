/* Service worker do Opero: casca da app do colaborador em cache (Fase 3).
   Estáticos com hash no nome: cache-first; sem hash: network-first.
   Páginas: network-first com fallback ao cache.
   POSTs nunca passam por aqui. Desde a Fase 7 não há fila offline: a app
   só consulta e pede, e o ponto pica-se no tablet. */
const CACHE = "opero-shell-v24";
const SHELL = [
  "/static/css/app.css",
  "/static/js/htmx.min.js",
  "/static/js/alpine.min.js",
  "/static/js/app.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/fonts/inter-v20-latin-variable.woff2",
  "/static/fonts/playfair-display-v40-latin-variable.woff2",
  "/static/img/logo-opero-escuro.png",
];

// Nome com o hash do ManifestStaticFilesStorage: nome.<12 hex>.extensão.
const COM_HASH = /\.[0-9a-f]{12}\.[a-z0-9]+$/i;

function guardar(request, resp) {
  if (resp.ok && !resp.redirected) {
    const copia = resp.clone();
    caches.open(CACHE).then((c) => c.put(request, copia));
  }
  return resp;
}

function cacheFirst(request) {
  return caches.match(request).then((hit) => hit || fetch(request).then((resp) => guardar(request, resp)));
}

function networkFirst(request) {
  return fetch(request)
    .then((resp) => guardar(request, resp))
    .catch(() => caches.match(request));
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((chaves) => Promise.all(chaves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    // Com o hash no nome (produção: app.3f2a9c1b7d4e.css), o ficheiro nunca
    // muda: cache-first. Sem hash (dev, ou o mesmo nome com conteúdo novo),
    // vai sempre à rede e a cópia guardada só serve sem ligação. Assim uma
    // alteração ao CSS ou ao JS aparece logo, sem mudar o nome da cache.
    event.respondWith(COM_HASH.test(url.pathname) ? cacheFirst(request) : networkFirst(request));
    return;
  }

  if (url.pathname.startsWith("/equipa/")) {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          // Nunca guardar respostas redirecionadas: servir uma delas a um
          // pedido de navegação rebenta com "redirected response used".
          // Sem sessão, /equipa/ redireciona para o login.
          if (!resp.redirected && resp.ok) {
            const copia = resp.clone();
            caches.open(CACHE).then((c) => c.put(request, copia));
          }
          return resp;
        })
        .catch(() => caches.match(request))
    );
  }
});
