/* JS da vista staff: registo do service worker e fila offline do ponto.
   Marcações sem rede entram na fila com o timestamp do momento da
   marcação, não do envio (secção 8, Fase 3), e sincronizam ao voltar. */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  var CHAVE = "opero-fila-ponto";

  function lerFila() {
    try {
      return JSON.parse(localStorage.getItem(CHAVE)) || [];
    } catch (e) {
      return [];
    }
  }

  function gravarFila(fila) {
    localStorage.setItem(CHAVE, JSON.stringify(fila));
  }

  function tokenCsrf() {
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    try {
      var cabecalhos = JSON.parse(document.body.getAttribute("hx-headers") || "{}");
      return cabecalhos["X-CSRFToken"] || "";
    } catch (e) {
      return "";
    }
  }

  function toast(texto, tom) {
    window.dispatchEvent(new CustomEvent("toast", { detail: { texto: texto, tom: tom || "neutro" } }));
  }

  function estadoEmFila(bloco, pendentes) {
    // Sem resposta do servidor, o bloco mostra o estado "guardado na fila".
    bloco.innerHTML =
      '<div class="min-h-[40vh] w-full rounded-lg border-2 border-dashed border-ardosia flex flex-col items-center justify-center text-center px-6">' +
      '<span class="font-display text-2xl font-extrabold uppercase tracking-wide text-aco">Guardado</span>' +
      '<span class="mt-2 text-sm text-ardosia">Sem rede. ' + pendentes + " marcaç" + (pendentes === 1 ? "ão" : "ões") + " por enviar — sincroniza sozinho.</span>" +
      "</div>";
  }

  function sincronizar() {
    var fila = lerFila();
    if (!fila.length || !navigator.onLine) return;
    var item = fila[0];
    var dados = new URLSearchParams();
    dados.append("marcado_em", item.t);
    fetch("/equipa/marcar/", {
      method: "POST",
      headers: { "X-CSRFToken": tokenCsrf(), "Content-Type": "application/x-www-form-urlencoded" },
      body: dados.toString(),
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (resp.status === 403) {
          // Sessão expirou: manter a fila e pedir novo login.
          toast("Sessão expirada. Entre de novo para sincronizar o ponto.", "erro");
          return;
        }
        fila.shift();
        gravarFila(fila);
        if (fila.length) {
          sincronizar();
        } else {
          toast("Ponto sincronizado", "sucesso");
          if (document.getElementById("bloco-ponto")) window.location.reload();
        }
      })
      .catch(function () {});
  }

  document.addEventListener("htmx:sendError", function (evt) {
    var form = evt.detail.elt.closest ? evt.detail.elt.closest("#form-ponto") : null;
    if (!form) return;
    var fila = lerFila();
    fila.push({ t: new Date().toISOString() });
    gravarFila(fila);
    var bloco = document.getElementById("bloco-ponto");
    if (bloco) estadoEmFila(bloco, fila.length);
    toast("Sem rede — marcação guardada", "neutro");
  });

  window.addEventListener("online", sincronizar);
  document.addEventListener("DOMContentLoaded", sincronizar);
})();
