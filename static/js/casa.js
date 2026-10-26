/* Backoffice (Fase 9): cada formulário leva a casa em que a página foi
   aberta. A sessão é partilhada pelos separadores, por isso quem mudar de
   casa noutro separador vê o POST recusado antes de gravar
   (core/middleware.py). Os pedidos HTMX levam-na no cabeçalho
   X-Opero-Casa, definido no <body>. */
(function () {
  "use strict";

  var casa = document.body.getAttribute("data-casa");
  if (!casa) return;

  document.addEventListener("submit", function (evento) {
    var form = evento.target;
    if (!(form instanceof HTMLFormElement) || (form.method || "").toLowerCase() !== "post") return;
    if (form.querySelector('input[name="_casa"]')) return;
    var campo = document.createElement("input");
    campo.type = "hidden";
    campo.name = "_casa";
    campo.value = casa;
    form.appendChild(campo);
  }, true);
})();
