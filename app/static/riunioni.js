"use strict";
// Riunioni: verbali (Plaud e simili) ricevuti per email, riassunti da un agente; i task proposti si approvano qui.
// Tutti i testi arrivano dall'API e vengono inseriti come testo.

function vistaRiunioni() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const [cfg, dati] = await Promise.all([api("GET", "/gestione/riunioni/config"), api("GET", "/gestione/riunioni")]);
      riempi(corpo, [formVerbale(dati, carica), h("h3", {}, "Riunioni"), listaRiunioni(dati, carica), h("h3", {}, "Collegamento con la posta"), schedaRiunioni(cfg, carica)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Riunioni"), corpo];
}

function formVerbale(dati, ricarica) {
  const msg = h("div"), titolo = h("input", { type: "text", maxlength: 200, placeholder: "Es. Riunione Interreg del 20 ottobre" });
  const testo = h("textarea", { style: "min-height:110px", maxlength: 60000, placeholder: "Incolla qui la trascrizione o il verbale (almeno 80 caratteri)" });
  const pr = h("select", {}, [h("option", { value: "" }, "— lo capisce l'agente —")].concat(dati.progetti.map(p => h("option", { value: p.id }, p.nome))));
  return h("details", { class: "carta" }, h("summary", {}, "+ Incolla un verbale a mano"),
    h("p", { class: "aiuto" }, "I verbali di PLAUD arrivano da soli dalla posta. Se ne hai uno già pronto lo incolli qui: l'agente lo legge, riconosce progetto e partecipanti, registra la riunione nella scheda CRM di chi era presente e propone le task."),
    h("label", {}, "Titolo", titolo), h("label", {}, "Progetto", pr), h("label", {}, "Verbale", testo), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (ev) => {
      const b = ev.currentTarget; b.disabled = true; msg.replaceChildren(avviso("Elaborazione in corso…", "avv"));
      try { const r = await api("POST", "/gestione/riunioni/manuale", { titolo: titolo.value, testo: testo.value, progetto_id: pr.value ? Number(pr.value) : null }); msg.replaceChildren(avviso(r.proposte + " task proposte.", "ok")); setTimeout(ricarica, 700); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Elabora")));
}

function schedaRiunioni(cfg, ricarica) {
  const msg = h("div");
  const attivo = h("input", { type: "checkbox" }); attivo.checked = cfg.attivo;
  const casella = h("select", {}, [h("option", { value: "" }, "— scegli —")].concat(cfg.caselle.map(c => h("option", { value: c.id }, c.nome)))); casella.value = cfg.casella_id || "";
  const agente = h("select", {}, [h("option", { value: "" }, "— scegli —")].concat(cfg.agenti.map(a => h("option", { value: a.id }, a.nome)))); agente.value = cfg.agente_id || "";
  const mitt = h("input", { type: "text", maxlength: 80, value: cfg.mittente || "plaud" });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Verbali delle riunioni"),
    h("p", { class: "aiuto" }, "Plaud non ha un collegamento diretto: nell'app Plaud (o con Zapier) fai inviare trascrizione e riassunto di ogni registrazione per email a una casella già collegata in Impostazioni → Collegamenti (posta). Non serve affidarla a un agente: la legge il sistema con il controllo qui sotto. Qui scegli quella casella e come riconoscere il mittente: Opifex la legge in sola lettura, un agente riassume e propone i task. Niente viene creato senza il tuo OK."),
    h("div", { class: "interruttore" }, attivo, h("span", {}, "Importazione attiva (controllo ogni 10 minuti)")),
    h("label", {}, "Casella di posta", casella), h("label", {}, "Il mittente contiene", mitt), h("label", {}, "Agente che elabora i verbali", agente),
    cfg.ultimo_controllo ? h("div", { class: "sotto" }, "Ultimo controllo: " + new Date(cfg.ultimo_controllo).toLocaleString("it-IT")) : null,
    cfg.ultimo_errore ? avviso(cfg.ultimo_errore, "no") : null, msg,
    h("div", { class: "azioni" },
      h("button", { class: "p", onclick: async () => {
        msg.replaceChildren();
        try { await api("PUT", "/gestione/riunioni/config", { attivo: attivo.checked, casella_id: casella.value ? Number(casella.value) : null, agente_id: agente.value ? Number(agente.value) : null, mittente: mitt.value });
          msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
      h("button", { class: "s", onclick: async (ev) => {
        const b = ev.currentTarget; b.disabled = true; msg.replaceChildren(avviso("Controllo in corso…", "avv"));
        try { const r = await api("POST", "/gestione/riunioni/controlla"); msg.replaceChildren(avviso(r.elaborate + " riunioni elaborate.", "ok")); setTimeout(ricarica, 800); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Controlla ora")));
}

function listaRiunioni(dati, ricarica) {
  const lista = dati.riunioni;
  if (!lista.length) return h("p", { class: "sotto" }, "Nessuna riunione importata.");
  return lista.map(r => {
    const msg = h("div");
    const pr = h("select", {}, [h("option", { value: "" }, "— nessun progetto —")].concat(dati.progetti.map(p => h("option", { value: p.id }, p.nome)))); pr.value = r.progetto_id || "";
    const proposte = (r.proposte || []).map(p => {
      const m2 = h("div");
      const chi = h("select", {}, [h("option", { value: "" }, p.suggerito_utente_id || p.suggerito_agente_id ? "Come indicato nel verbale" : "A me")]
        .concat(dati.utenti.map(u => h("option", { value: "u" + u.id }, "👤 " + u.nome)), dati.agenti.map(a => h("option", { value: "a" + a.id }, "🤖 " + a.nome))));
      const decidi = async (azione) => {
        m2.replaceChildren();
        const body = { azione }; if (chi.value.startsWith("u")) body.assegnato_utente_id = Number(chi.value.slice(1)); if (chi.value.startsWith("a")) body.assegnato_agente_id = Number(chi.value.slice(1));
        try { await api("POST", "/gestione/riunioni/proposte/" + p.id + "/decisione", body); ricarica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } };
      return h("div", { class: "carta" }, h("div", { class: "nome" }, p.titolo),
        h("div", { class: "sotto" }, [p.priorita, p.scadenza ? "entro " + p.scadenza : "", p.assegnatario_suggerito ? "indicato: " + p.assegnatario_suggerito : "", p.progetto, p.stato !== "proposta" ? p.stato : ""].filter(Boolean).join(" · ")),
        p.descrizione ? h("p", {}, p.descrizione) : null, m2,
        p.stato === "proposta" ? h("div", { class: "azioni" }, chi, h("button", { class: "p", onclick: () => decidi("approva") }, "Crea la task"), h("button", { class: "s", onclick: () => decidi("scarta") }, "Scarta")) : null);
    });
    return h("div", { class: "carta" }, h("div", { class: "nome" }, r.titolo),
      h("div", { class: "sotto" }, ((r.data_riunione || r.data_email) ? new Date(r.data_riunione || r.data_email).toLocaleDateString("it-IT") + " · " : "") + r.stato + (r.mittente ? " · " + r.mittente : "")),
      r.partecipanti && r.partecipanti.length ? h("div", { class: "sotto" }, "Presenti: " + r.partecipanti.map(x => x.nome + (x.contatto_id ? " (CRM)" : x.utente_id ? " (team)" : "")).join(", ")) : null,
      r.riassunto ? h("p", {}, r.riassunto) : null, r.errore ? avviso(r.errore, "no") : null,
      h("div", { class: "riga" }, h("label", {}, "Progetto", pr), h("button", { class: "s", style: "align-self:flex-end", onclick: async () => { try { await api("PUT", "/gestione/riunioni/" + r.id + "/progetto", { progetto_id: pr.value ? Number(pr.value) : null }); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Collega")),
      proposte, msg,
      r.stato === "errore" || r.stato === "elaborata" ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
        msg.replaceChildren(avviso("Elaborazione…", "avv"));
        try { await api("POST", "/gestione/riunioni/" + r.id + "/rielabora"); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Rielabora")) : null);
  });
}
