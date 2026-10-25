"use strict";
// Riunioni: verbali (Plaud e simili) ricevuti per email, riassunti da un agente; i task proposti si approvano qui.
// Tutti i testi arrivano dall'API e vengono inseriti come testo.

function vistaRiunioni() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const [cfg, lista] = await Promise.all([api("GET", "/gestione/riunioni/config"), api("GET", "/gestione/riunioni")]);
      riempi(corpo, [schedaRiunioni(cfg, carica), h("h3", {}, "Riunioni importate"), listaRiunioni(lista, carica)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Riunioni"), corpo];
}

function schedaRiunioni(cfg, ricarica) {
  const msg = h("div");
  const attivo = h("input", { type: "checkbox" }); attivo.checked = cfg.attivo;
  const casella = h("select", {}, [h("option", { value: "" }, "— scegli —")].concat(cfg.caselle.map(c => h("option", { value: c.id }, c.nome)))); casella.value = cfg.casella_id || "";
  const agente = h("select", {}, [h("option", { value: "" }, "— scegli —")].concat(cfg.agenti.map(a => h("option", { value: a.id }, a.nome)))); agente.value = cfg.agente_id || "";
  const mitt = h("input", { type: "text", maxlength: 80, value: cfg.mittente || "plaud" });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Verbali delle riunioni"),
    h("p", { class: "aiuto" }, "Plaud non ha un collegamento diretto: nell'app Plaud (o con Zapier) fai inviare trascrizione e riassunto di ogni registrazione per email a una casella già collegata in Sistemi → Posta. Qui scegli quella casella e come riconoscere il mittente: Opifex la legge in sola lettura, un agente riassume e propone i task. Niente viene creato senza il tuo OK."),
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

function listaRiunioni(lista, ricarica) {
  if (!lista.length) return h("p", { class: "sotto" }, "Nessuna riunione importata.");
  return lista.map(r => {
    const msg = h("div");
    const proposte = (r.proposte || []).map(p => {
      const m2 = h("div");
      const decidi = async (azione) => { m2.replaceChildren(); try { await api("POST", "/gestione/riunioni/proposte/" + p.id + "/decisione", { azione }); ricarica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } };
      return h("div", { class: "carta" }, h("div", { class: "nome" }, p.titolo),
        h("div", { class: "sotto" }, [p.priorita, p.scadenza ? "entro " + p.scadenza : "", p.assegnatario_suggerito ? "suggerito: " + p.assegnatario_suggerito : "", p.stato !== "proposta" ? p.stato : ""].filter(Boolean).join(" · ")),
        p.descrizione ? h("p", {}, p.descrizione) : null, m2,
        p.stato === "proposta" ? h("div", { class: "azioni" },
          h("button", { class: "p", onclick: () => decidi("approva") }, "Crea task (assegnato a me)"),
          h("button", { class: "s", onclick: () => decidi("scarta") }, "Scarta")) : null);
    });
    return h("div", { class: "carta" }, h("div", { class: "nome" }, r.titolo),
      h("div", { class: "sotto" }, (r.data_email ? new Date(r.data_email).toLocaleDateString("it-IT") + " · " : "") + r.stato + (r.mittente ? " · " + r.mittente : "")),
      r.riassunto ? h("p", {}, r.riassunto) : null, r.errore ? avviso(r.errore, "no") : null, proposte, msg,
      r.stato === "errore" || r.stato === "elaborata" ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
        msg.replaceChildren(avviso("Elaborazione…", "avv"));
        try { await api("POST", "/gestione/riunioni/" + r.id + "/rielabora"); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Rielabora")) : null);
  });
}
