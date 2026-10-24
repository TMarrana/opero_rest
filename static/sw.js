/* Service worker do Opero: shell da vista staff em cache (secção 8, Fase 3).
   Estáticos: cache-first. Páginas: network-first com fallback ao cache.
   POSTs nunca passam por aqui — a fila offline vive em app.js. */
const CACHE = "opero-shell-v4";
const SHELL = [
  "/static/css/app.css",
  "/static/js/htmx.min.js",
  "/static/js/alpine.min.js",
  "/static/js/app.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/fonts/archivo-v25-latin-700.woff2",
  "/static/fonts/archivo-v25-latin-800.woff2",
  "/static/fonts/ibm-plex-sans-v23-latin-regular.woff2",
  "/static/fonts/ibm-plex-sans-v23-latin-600.woff2",
  "/static/fonts/ibm-plex-mono-v20-latin-regular.woff2",
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
          // Sem sessão, /equipa/ redireciona para o ecrã de PIN.
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
