/* JS da app do colaborador: só o registo do service worker. Desde a
   Fase 7 não há marcações no telemóvel nem fila offline: o ponto pica-se
   no tablet do restaurante (/quiosque/). */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
})();
