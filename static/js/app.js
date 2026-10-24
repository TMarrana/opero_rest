/* JS da vista staff: registo do service worker e fila offline do ponto.
   Marcações sem rede entram na fila com o timestamp do momento da
   marcação, não do envio (secção 8, Fase 3), e sincronizam ao voltar.

   Cada marcação guarda a ação que o botão mostrava e quem a fez. Só é
   enviada na sessão desse colaborador — num tablet partilhado nunca entra
   em nome de outra pessoa. Estados: "por enviar" e "recusada"; uma
   recusada mostra o motivo que o servidor devolveu até ser dispensada. */
(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  var CHAVE = "opero-fila-ponto";
  var POR_ENVIAR = "por enviar";
  var RECUSADA = "recusada";

  function lerFila() {
    try {
      return JSON.parse(localStorage.getItem(CHAVE)) || [];
    } catch (e) {
      return [];
    }
  }

  function gravarFila(fila) {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(fila));
    } catch (e) {}
  }

  function trabalhadorAtual() {
    return document.body.getAttribute("data-trabalhador") || "";
  }

  // Marcações deste colaborador. As anteriores a esta versão não dizem
  // quem marcou e ficam com quem tiver a sessão, como antes.
  function eDoAtual(item) {
    return !item.trabalhador || item.trabalhador === trabalhadorAtual();
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

  function hora(iso) {
    var d = new Date(iso);
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function nomeAcao(acao) {
    if (acao === "entrada") return "Entrada";
    if (acao === "saida") return "Saída";
    if (acao === "pausa") return "Início de pausa";
    if (acao === "fim_pausa") return "Fim de pausa";
    return "Marcação";
  }

  function estadoEmFila(bloco, pendentes) {
    // Sem resposta do servidor, o bloco mostra o estado "guardado na fila".
    bloco.innerHTML =
      '<div class="min-h-[40vh] w-full rounded-lg border-2 border-dashed border-ardosia flex flex-col items-center justify-center text-center px-6">' +
      '<span class="font-display text-2xl font-extrabold uppercase tracking-wide text-aco">Guardado</span>' +
      '<span class="mt-2 text-sm text-ardosia">Sem rede. ' + pendentes + " marcaç" + (pendentes === 1 ? "ão" : "ões") + " por enviar — sincroniza sozinho.</span>" +
      "</div>";
  }

  function mostrarFila() {
    var seccao = document.getElementById("fila-ponto");
    if (!seccao) return;
    var lista = seccao.querySelector("ul");
    var fila = lerFila();
    lista.innerHTML = "";
    var visiveis = 0;
    fila.forEach(function (item, indice) {
      if (!eDoAtual(item)) return;
      visiveis += 1;
      var li = document.createElement("li");
      var recusada = item.estado === RECUSADA;
      li.className =
        "rounded-md border px-3 py-2 text-sm " +
        (recusada ? "border-chama text-aco" : "border-dashed border-ardosia text-aco/80");
      var linha = document.createElement("div");
      linha.className = "flex items-center justify-between gap-3";
      var texto = document.createElement("span");
      texto.className = "font-dados";
      texto.textContent = nomeAcao(item.acao) + " · " + hora(item.t);
      var estado = document.createElement("span");
      estado.className = "text-xs font-semibold uppercase tracking-wide " + (recusada ? "text-chama" : "text-ardosia");
      estado.textContent = recusada ? RECUSADA : POR_ENVIAR;
      linha.appendChild(texto);
      linha.appendChild(estado);
      li.appendChild(linha);
      if (recusada) {
        var motivo = document.createElement("p");
        motivo.className = "mt-1 text-xs text-aco/80";
        motivo.textContent = (item.motivo || "O servidor recusou a marcação.") + " Peça ao gerente para corrigir o registo.";
        var dispensar = document.createElement("button");
        dispensar.type = "button";
        dispensar.className = "mt-2 min-h-toque text-xs font-semibold underline underline-offset-2";
        dispensar.textContent = "Dispensar";
        dispensar.addEventListener("click", function () {
          var atual = lerFila();
          atual.splice(indice, 1);
          gravarFila(atual);
          mostrarFila();
        });
        li.appendChild(motivo);
        li.appendChild(dispensar);
      }
      lista.appendChild(li);
    });
    seccao.classList.toggle("hidden", visiveis === 0);
  }

  function proximoPorEnviar(fila) {
    for (var i = 0; i < fila.length; i++) {
      if (fila[i].estado !== RECUSADA && eDoAtual(fila[i])) return i;
    }
    return -1;
  }

  function sincronizar() {
    if (!trabalhadorAtual() || !navigator.onLine) return;
    var fila = lerFila();
    var indice = proximoPorEnviar(fila);
    if (indice < 0) return;
    var item = fila[indice];
    var dados = new URLSearchParams();
    dados.append("marcado_em", item.t);
    if (item.acao) dados.append("acao", item.acao);
    if (item.trabalhador) dados.append("trabalhador", item.trabalhador);
    if (item.tipoPausa) dados.append("tipo_pausa", item.tipoPausa);
    fetch("/equipa/marcar/", {
      method: "POST",
      headers: {
        "X-CSRFToken": tokenCsrf(),
        "X-Opero-Fila": "1",
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: dados.toString(),
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (resp.status === 403) {
          // Sessão expirou: manter a fila e pedir novo login.
          toast("Sessão expirada. Entre de novo para sincronizar o ponto.", "erro");
          return null;
        }
        return resp.json().then(function (corpo) {
          return { status: resp.status, corpo: corpo };
        });
      })
      .then(function (resultado) {
        if (!resultado) return;
        var atual = lerFila();
        var pos = atual.findIndex(function (x) {
          return x.t === item.t && x.trabalhador === item.trabalhador;
        });
        if (resultado.status === 200 && resultado.corpo.ok) {
          if (pos >= 0) atual.splice(pos, 1);
          gravarFila(atual);
          toast(nomeAcao(item.acao) + " das " + hora(item.t) + " enviada", "sucesso");
        } else {
          if (pos >= 0) {
            atual[pos].estado = RECUSADA;
            atual[pos].motivo = resultado.corpo.texto || "";
          }
          gravarFila(atual);
          toast("Marcação recusada: " + (resultado.corpo.texto || "sem motivo"), "erro");
        }
        mostrarFila();
        if (resultado.corpo.sessao_terminada) {
          // Tablet partilhado: a sessão terminou com esta marcação.
          window.location.href = document.body.getAttribute("data-pin-url") || "/equipa/entrar/";
          return;
        }
        if (proximoPorEnviar(atual) >= 0) {
          sincronizar();
        } else if (document.getElementById("bloco-ponto")) {
          window.location.reload();
        }
      })
      .catch(function () {});
  }

  document.addEventListener("htmx:sendError", function (evt) {
    var form = evt.detail.elt.closest ? evt.detail.elt.closest("form.form-ponto") : null;
    if (!form) return;
    var acao = form.querySelector("input[name=acao]");
    var trabalhador = form.querySelector("input[name=trabalhador]");
    var tipoPausa = form.querySelector("input[name=tipo_pausa]");
    var fila = lerFila();
    fila.push({
      t: new Date().toISOString(),
      acao: acao ? acao.value : "",
      trabalhador: trabalhador ? trabalhador.value : trabalhadorAtual(),
      tipoPausa: tipoPausa ? tipoPausa.value : "",
      estado: POR_ENVIAR,
    });
    gravarFila(fila);
    var bloco = document.getElementById("bloco-ponto");
    if (bloco) estadoEmFila(bloco, fila.filter(eDoAtual).filter(function (x) { return x.estado !== RECUSADA; }).length);
    mostrarFila();
    toast("Sem rede — marcação guardada", "neutro");
  });

  window.addEventListener("online", sincronizar);
  document.addEventListener("DOMContentLoaded", function () {
    mostrarFila();
    sincronizar();
  });
})();
