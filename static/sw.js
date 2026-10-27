/* Service worker do Opero: casca da app do colaborador em cache (Fase 3).
   Estáticos: cache-first. Páginas: network-first com fallback ao cache.
   POSTs nunca passam por aqui. Desde a Fase 7 não há fila offline: a app
   só consulta e pede, e o ponto pica-se no tablet. */
const CACHE = "opero-shell-v21";
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
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((resp) => {
        const copia = resp.clone();
        caches.open(CACHE).then((c) => c.put(request, copia));
        return resp;
      }))
    );
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
