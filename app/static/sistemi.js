"use strict";
// Fornitori AI: chiavi (cifrate), stato di funzionamento e registrazione di nuovi modelli.

function blocchiFornitori() {
  const corpo = h("div");
  const verifica = h("div");
  const NOMI = { anthropic: "Anthropic (Claude)", openai: "OpenAI (ChatGPT)", xai: "xAI (Grok)" };
  const ORIGINE = { app: "chiave inserita nell'app", server: "chiave nel file .env del server", mancante: "chiave mancante" };
  const carica = async () => {
    let origini = {};
    try { origini = await api("GET", "/gestione/fornitori/chiavi"); } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); return; }
    const schede = Object.keys(NOMI).map(n => {
      const campo = h("input", { type: "password", autocomplete: "off", placeholder: "Incolla qui la chiave API (non viene mai mostrata dopo il salvataggio)" });
      const msg = h("div");
      return h("div", { class: "carta" }, h("div", { class: "nome" }, NOMI[n]),
        h("div", { class: "sotto" }, "Stato: " + ORIGINE[origini[n]]),
        h("label", {}, "Chiave API", campo), msg,
        h("div", { class: "azioni" },
          h("button", { class: "p", onclick: async () => {
            try { await api("PUT", "/gestione/fornitori/" + n + "/chiave", { chiave: campo.value }); campo.value = ""; await carica(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva chiave"),
          origini[n] === "app" ? h("button", { class: "s", onclick: async () => {
            if (!confirm("Rimuovere la chiave inserita nell'app?")) return;
            try { await api("PUT", "/gestione/fornitori/" + n + "/chiave", { chiave: null }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Rimuovi") : null));
    });
    // nuovo modello
    const forn = h("select", {}, Object.keys(NOMI).map(n => h("option", { value: n }, NOMI[n])));
    const nome = h("input", { type: "text", maxlength: 80, placeholder: "Nome esatto del modello, es. gpt-4.1" });
    const fascia = h("select", {}, ["economico", "standard", "avanzato"].map(f => h("option", { value: f }, f))); fascia.value = "standard";
    const ci = h("input", { type: "number", min: 0, step: "any", placeholder: "facoltativo" });
    const co = h("input", { type: "number", min: 0, step: "any", placeholder: "facoltativo" });
    const msgM = h("div");
    riempi(corpo, [
      h("div", { class: "griglia" }, schede),
      h("p", { class: "aiuto" }, "La chiave salvata qui è cifrata e ha la precedenza su quella del file .env. Le chiavi API sono a pagamento a consumo e separate dagli abbonamenti (ChatGPT Plus, Grok)."),
      h("h4", {}, "Modelli registrati"),
      h("p", { class: "sotto" }, (stato.opzioni.modelli || []).map(m => m.nome + " (" + m.fornitore + ")").join(" · ")),
      h("div", { class: "carta" }, h("div", { class: "nome" }, "Registra un modello"),
        h("div", { class: "riga" }, h("label", {}, "Fornitore", forn), h("label", {}, "Nome del modello", nome), h("label", {}, "Livello", fascia)),
        h("div", { class: "riga" }, h("label", {}, "Costo input per milione di token", ci), h("label", {}, "Costo output per milione di token", co)), msgM,
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try { await api("POST", "/gestione/modelli", { fornitore: forn.value, nome: nome.value.trim(), fascia: fascia.value,
              costo_input_per_milione: ci.value === "" ? null : Number(ci.value), costo_output_per_milione: co.value === "" ? null : Number(co.value) });
            await ricarica(); } catch (e) { msgM.replaceChildren(avviso(e.message, "no")); } } }, "Registra"))),
    ]);
  };
  carica();
  const bVer = h("button", { class: "p", onclick: async (e) => {
    const b = e.currentTarget; b.disabled = true; b.textContent = "Verifica in corso…"; verifica.replaceChildren();
    try {
      const r = await api("POST", "/gestione/fornitori/verifica");
      verifica.replaceChildren(h("div", { class: "griglia" }, r.map(x => h("div", { class: "carta" },
        h("div", { class: "nome" }, (x.ok ? "🟢 " : "🔴 ") + NOMI[x.fornitore]),
        h("div", { class: "sotto" }, x.modello ? "Modello provato: " + x.modello : "Nessun modello registrato"),
        h("div", { class: "sotto" }, x.ok ? "Attivo · risposta in " + x.ms + " ms" : "Non funziona: " + x.dettaglio)))));
    } catch (er) { verifica.replaceChildren(avviso(er.message, "no")); }
    b.disabled = false; b.textContent = "Verifica ora";
  } }, "Verifica ora");
  return [h("h3", {}, "Stato dei sistemi AI"),
    h("p", { class: "aiuto" }, "Fa una richiesta minima a ciascun fornitore con il suo modello più economico: costa una frazione di centesimo."),
    h("div", { class: "azioni" }, bVer), verifica,
    h("h3", {}, "Chiavi e modelli"), corpo];
}

// Posta generica (IMAP, es. Aruba): l'agente legge e prepara bozze, non invia mai.
function bloccoPosta() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/posta");
      const et = h("input", { type: "text", maxlength: 60, placeholder: "Es. Posta Logos" });
      const em = h("input", { type: "email", maxlength: 200, placeholder: "nome@tuodominio.it" });
      const host = h("input", { type: "text", value: "imaps.aruba.it", maxlength: 253 });
      const porta = h("input", { type: "number", value: 993 });
      const ut = h("input", { type: "text", maxlength: 200, placeholder: "Di solito è l'indirizzo email completo" });
      const pw = h("input", { type: "password", autocomplete: "off", placeholder: "Password della casella" });
      const msg = h("div");
      const STATO = { attiva: "attiva", errore: "errore", da_provare: "da provare" };
      riempi(corpo, [
        d.caselle.length ? d.caselle.map(c => {
          const cb = d.agenti.map(a => ({ a, c: h("input", { type: "checkbox" }) })); cb.forEach(x => { x.c.checked = c.agenti.includes(x.a.id); });
          const m2 = h("div");
          return h("div", { class: "carta", style: "margin-bottom:12px" },
            h("div", { class: "nome" }, c.etichetta + " — " + c.email),
            h("div", { class: "sotto" }, c.host + ":" + c.porta + " · stato: " + STATO[c.stato]),
            c.ultimo_errore ? avviso(c.ultimo_errore, "no") : null,
            h("div", { class: "sotto" }, "Agenti che la gestiscono (leggono e preparano bozze, mai invio):"),
            h("div", { class: "riga" }, cb.map(x => h("label", { style: "flex:0 0 auto;margin-right:12px" }, x.c, " " + x.a.nome))), m2,
            h("div", { class: "azioni" },
              h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/posta/" + c.id + "/agenti", { agenti: cb.filter(x => x.c.checked).map(x => x.a.id) }); m2.replaceChildren(avviso("Salvato", "ok")); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Salva agenti"),
              h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/gestione/posta/" + c.id + "/prova"); m2.replaceChildren(avviso(r.esito, r.ok ? "ok" : "no")); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Prova"),
              h("button", { class: "r", onclick: async () => { if (!confirm("Scollegare questa casella?")) return; try { await api("DELETE", "/gestione/posta/" + c.id); carica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Scollega")));
        }) : h("p", { class: "sotto" }, "Nessuna casella collegata."),
        h("div", { class: "carta" }, h("div", { class: "nome" }, "Collega una casella email (Aruba o altro)"),
          h("div", { class: "riga" }, h("label", {}, "Nome", et), h("label", {}, "Indirizzo email", em)),
          h("div", { class: "riga" }, h("label", {}, "Server IMAP", host), h("label", {}, "Porta", porta)),
          h("div", { class: "riga" }, h("label", {}, "Utente", ut), h("label", {}, "Password", pw)),
          h("p", { class: "aiuto" }, "La password viene cifrata e non è più visibile. Gli agenti possono cercare, leggere e preparare bozze nella cartella Bozze; non inviano e non cancellano. Per le caselle Aruba il server è imaps.aruba.it, porta 993." ), msg,
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { const r = await api("POST", "/gestione/posta", { etichetta: et.value, email: em.value, host: host.value, porta: Number(porta.value), utente: ut.value || null, password: pw.value });
              await carica(); if (!r.ok) corpo.prepend(avviso(r.esito, "no")); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Collega e prova")))]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h3", {}, "Posta (IMAP, es. Aruba)"), corpo];
}
