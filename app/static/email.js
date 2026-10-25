"use strict";
// Email: collegamento a Brevo e coda delle campagne preparate dagli agenti, da approvare prima dell'invio.
// Tutti i testi arrivano dall'API e vengono inseriti come testo; l'anteprima dell'HTML e' solo testo, mai HTML.

const STATI_CAMP = { da_approvare: ["Da approvare", "avv"], inviata: ["Inviata / programmata su Brevo", "ok"], bozza_brevo: ["Bozza salvata su Brevo", "ok"], rifiutata: ["Rifiutata", "no"], errore: ["Errore", "no"] };

function vistaEmail() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const [bv, lista] = await Promise.all([api("GET", "/gestione/email/brevo"), api("GET", "/gestione/email/campagne")]);
      riempi(corpo, [schedaBrevo(bv, carica), h("h3", {}, "Campagne preparate dagli agenti"), listaCampagne(lista, bv, carica)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Email marketing"), corpo];
}

function schedaBrevo(bv, ricarica) {
  const msg = h("div");
  if (bv.collegato) {
    return h("div", { class: "carta" }, h("div", { class: "nome" }, "Brevo collegato" + (bv.account && bv.account.azienda ? " · " + bv.account.azienda : "")),
      bv.errore ? avviso(bv.errore, "no") : null,
      h("div", { class: "sotto" }, "Liste: " + (bv.liste.map(l => l.nome + " (" + (l.iscritti ?? "?") + ")").join(", ") || "nessuna")),
      h("div", { class: "sotto" }, "Mittenti attivi: " + (bv.mittenti.map(m => m.email).join(", ") || "nessuno: aggiungine uno in Brevo")),
      h("p", { class: "aiuto" }, "Per far preparare campagne a un agente, accendi «Può preparare campagne email (Brevo)» nella sua scheda. Le campagne restano qui in attesa del tuo OK: nessuna email parte da sola."),
      msg, h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
        if (!confirm("Scollegare Brevo?")) return;
        try { await api("DELETE", "/gestione/email/brevo"); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Scollega Brevo")));
  }
  const chiave = h("input", { type: "password", autocomplete: "off", placeholder: "Chiave API v3 di Brevo" });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Collega Brevo"),
    h("p", { class: "aiuto" }, "In Brevo: clicca il tuo nome in alto a destra → «SMTP e API» → scheda «Chiavi API» → «Genera una nuova chiave API». Incollala qui: viene cifrata e non verrà più mostrata. Se nelle impostazioni di sicurezza di Brevo hai limitato gli indirizzi IP consentiti, aggiungi quello del server (81.2.251.34)."),
    h("label", {}, "Chiave API", chiave), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (ev) => {
      const b = ev.currentTarget; b.disabled = true; msg.replaceChildren();
      try { await api("PUT", "/gestione/email/brevo", { chiave: chiave.value.trim() }); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Collega e verifica")));
}

function listaCampagne(lista, bv, ricarica) {
  if (!lista.length) return h("p", { class: "sotto" }, "Nessuna campagna ancora.");
  return lista.map(c => {
    const [t, cl] = STATI_CAMP[c.stato] || [c.stato, ""];
    const msg = h("div");
    const modificabile = c.stato === "da_approvare" || c.stato === "errore";
    const nome = h("input", { type: "text", maxlength: 200, value: c.nome });
    const oggetto = h("input", { type: "text", maxlength: 300, value: c.oggetto });
    const html = h("textarea", { style: "min-height:160px;font-family:monospace" }); html.value = c.html;
    const quando = h("input", { type: "datetime-local" }); if (c.programmata_il) quando.value = perInput(c.programmata_il);
    const mitt = h("select", {}, (bv.mittenti || []).map(m => h("option", { value: m.email }, m.nome + " <" + m.email + ">"))); mitt.value = c.mittente_email || "";
    const cb = (bv.liste || []).map(l => { const x = h("input", { type: "checkbox" }); x.checked = (c.liste || []).some(z => z.id === l.id); return [l, x]; });
    const salvaModifiche = () => api("PUT", "/gestione/email/campagne/" + c.id, {
      nome: nome.value, oggetto: oggetto.value, html: html.value, liste: cb.filter(([, x]) => x.checked).map(([l]) => l.id), mittente_email: mitt.value || undefined,
      ...(quando.value ? { programmata_il: new Date(quando.value).toISOString() } : { senza_orario: true }) });
    const azione = async (az, conferma) => {
      msg.replaceChildren();
      if (conferma && !confirm(conferma)) return;
      try { if (az !== "rifiuta") await salvaModifiche(); await api("POST", "/gestione/email/campagne/" + c.id + "/decisione", { azione: az }); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    };
    return h("div", { class: "carta", style: "margin-top:12px" },
      h("div", { class: "nome" }, c.nome),
      h("div", { class: "sotto" }, (c.agente ? "Preparata da " + c.agente + " · " : "") + new Date(c.creata_il).toLocaleString("it-IT")),
      h("div", {}, h("span", { class: "etichetta " + cl }, t)),
      modificabile ? [h("label", {}, "Nome interno", nome), h("label", {}, "Oggetto", oggetto), h("label", {}, "Mittente", mitt),
        h("label", {}, "Destinatari (liste)"), h("div", { class: "spunte" }, cb.map(([l, x]) => h("label", { class: "spunta" }, x, l.nome + " (" + (l.iscritti ?? "?") + ")"))),
        h("label", {}, "Testo (HTML semplice; il link per annullare l'iscrizione viene aggiunto da solo)", html),
        h("label", {}, "Data e ora di invio (vuoto = subito, all'approvazione)", quando)]
        : [h("div", { class: "sotto" }, "Oggetto: " + c.oggetto + " · Liste: " + (c.liste || []).map(l => l.nome).join(", ")), h("div", { class: "risposta" }, "Anteprima: " + (c.html || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").slice(0, 300))],
      c.errore ? avviso(c.errore, "no") : null, msg,
      modificabile ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => azione("rifiuta") }, "Rifiuta"),
        h("button", { class: "s", onclick: () => azione("bozza") }, "Salva come bozza su Brevo"),
        h("button", { class: "p", onclick: () => azione("invia", "Inviare davvero questa campagna a tutti gli iscritti delle liste scelte? Dopo l'invio non si può annullare.") }, quando.value ? "Approva e programma" : "Approva e invia")) : null);
  });
}
