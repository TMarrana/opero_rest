/* JS da app do colaborador: o registo do service worker e a proteção
   contra o duplo envio do login. Desde a Fase 7 não há marcações no
   telemóvel nem fila offline: o ponto pica-se no tablet do restaurante
   (/quiosque/). */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  // Formulários com data-envio-unico só seguem uma vez: o login roda o
  // token CSRF e um segundo toque no botão dava 403 com a sessão já aberta.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.hasAttribute("data-envio-unico")) return;
    if (form.dataset.enviado) {
      event.preventDefault();
      return;
    }
    form.dataset.enviado = "1";
  });

  // Voltar atrás pode trazer a página da cache do browser com a marca posta.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-envio-unico]").forEach(function (form) {
      delete form.dataset.enviado;
    });
  });
})();
