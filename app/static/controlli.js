"use strict";
// Spesa per reparto e controllo delle librerie.

function vistaSpesaReparti() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/spesa-reparti");
      riempi(corpo, d.reparti.map(r => {
        const t = h("input", { type: "number", min: "1", step: "1", placeholder: "nessun tetto", style: "width:120px" }); if (r.tetto) t.value = r.tetto;
        const pc = r.tetto ? Math.round(100 * r.speso / r.tetto) : null;
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, r.nome),
          h("div", { class: "sotto" }, "Speso questo mese: " + r.speso.toFixed(2) + (pc !== null ? " · " + pc + "% del tetto" + (pc >= 100 ? " — REPARTO FERMO" : pc >= 80 ? " — vicino al tetto" : "") : "")),
          h("div", { class: "riga", style: "align-items:center" }, h("label", {}, "Tetto mensile", t),
            h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/spesa-reparti/" + r.id, { tetto: t.value ? Number(t.value) : null }); msg.replaceChildren(avviso("Salvato.", "ok")); await carica(); }
              catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
      }));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Spesa per reparto"),
    h("p", { class: "aiuto" }, "Un tetto mensile per ogni reparto (stessa unità del tetto generale). All'80% ricevi un avviso; al 100% gli agenti di quel reparto si fermano fino al mese dopo o finché non alzi il tetto. Aurora e gli agenti di sistema non si fermano."),
    msg, corpo);
}

function vistaDipendenze() {
  const corpo = h("div"), msg = h("div");
  const mostra = (u) => riempi(corpo, u ? [h("p", {}, "Ultimo controllo: " + new Date(u.eseguito_il).toLocaleString("it-IT") + " — " +
    ({ ok: "nessuna vulnerabilità nota", vulnerabilita: "ATTENZIONE: vulnerabilità trovate", non_raggiungibile: "servizio non raggiungibile (si riprova)" })[u.esito]),
    (u.dettagli || []).map(t => h("div", { class: "carta", style: "margin-bottom:6px" }, h("b", {}, t.libreria + " " + t.versione), h("div", { class: "sotto" }, t.vulnerabilita.join(", "))))] : h("p", { class: "sotto" }, "Nessun controllo ancora eseguito."));
  api("GET", "/gestione/dipendenze").then(d => mostra(d.ultimo)).catch(e => msg.replaceChildren(avviso(e.message, "no")));
  return h("div", {}, h("h2", {}, "Controllo delle librerie"),
    h("p", { class: "aiuto" }, "Ogni settimana le librerie usate da Opifex vengono confrontate con il database pubblico delle vulnerabilità (OSV). Se ne trova ricevi un avviso: l'aggiornamento arriva con la prossima versione."),
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { msg.replaceChildren(avviso("Controllo in corso…", "ok"));
      try { const r = await api("POST", "/gestione/dipendenze/controlla"); msg.replaceChildren(); const d = await api("GET", "/gestione/dipendenze"); mostra(d.ultimo); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Controlla adesso")), msg, corpo);
}


function vistaDiagnostica() {
  const msg = h("div");
  const ore = h("select", {}, [["6", "ultime 6 ore"], ["24", "ultime 24 ore"], ["72", "ultimi 3 giorni"], ["168", "ultima settimana"]].map(([v, t]) => h("option", { value: v }, t)));
  ore.value = "24";
  const scarica = h("button", { class: "p", type: "button" }, "⬇ Scarica il file di diagnostica");
  scarica.addEventListener("click", async () => {
    scarica.disabled = true; msg.replaceChildren(avviso("Preparo il file…", "ok"));
    try {
      const r = await fetch("/gestione/diagnostica?ore=" + ore.value, { headers: token ? { Authorization: "Bearer " + token } : {} });
      if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) { /* ok */ } throw new Error(messaggioErrore(d)); }
      const blob = await r.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
      a.href = url; a.download = ((r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/) || [])[1] || "diagnostica-opifex.json";
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
      msg.replaceChildren(avviso("File scaricato (" + Math.round(blob.size / 1024) + " KB). Mandamelo in chat e lo analizzo.", "ok"));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    scarica.disabled = false;
  });
  return h("div", {}, h("h2", {}, "Diagnostica"),
    h("p", { class: "aiuto" }, "Un unico file con tutto cio' che serve per capire cosa e' andato storto: segnali sospetti in cima, errori, impostazioni e prompt degli agenti, riunioni (cosa e' stato detto, le richieste in coda), task, chiamate ai modelli, spese, notifiche e registro delle azioni. Chiavi, token e password non ci sono mai. Dentro ci sono pero' conversazioni reali: condividilo solo per l'analisi."),
    h("label", {}, "Periodo", ore), h("div", { class: "azioni" }, scarica), msg);
}
