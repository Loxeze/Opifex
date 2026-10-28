"use strict";
// Ginnasio: a sinistra lo studio di Padre Casati (studi e biblioteca), a destra la formazione (coda, bozze, competenze).

function vistaGinnasio() {
  const msg = h("div"), destra = h("div");
  const sinistra = h("div", {}, h("h3", { style: "margin-top:0" }, "Studio"), vistaStudi(), vistaBiblioteca());
  const NOMI = { 1: "Junior", 2: "Medium", 3: "Senior", 4: "Expert", 5: "Master" };
  const ORIGINI = { manuale: "tu", manager: "un manager", pm: "un project manager", lacuna: "lacuna rilevata", cerimoniere: "Cerimoniere" };
  const errore = (e) => msg.replaceChildren(avviso(e.message, "no"));
  const livelloOpz = () => [1, 2, 3, 4, 5].map(n => h("option", { value: n }, n + " — " + NOMI[n]));
  let timer = null;
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/ginnasio"), im = d.impostazioni;
      const perc = im.senza_limite ? 0 : Math.min(100, Math.round(100 * im.usati_oggi / im.budget));
      const budget = h("input", { type: "number", min: 0, step: 1000, value: im.budget, style: "width:120px" });
      const comp = h("input", { maxlength: 100, list: "elenco-competenze", placeholder: "Es. Project management" });
      const dl = h("datalist", { id: "elenco-competenze" }, d.competenze.map(c => h("option", { value: c.nome })));
      const liv = h("select", {}, livelloOpz());
      const ag = h("select", {}, h("option", { value: "" }, "— solo la libreria —"), d.agenti.map(a => h("option", { value: a.id }, a.nome + " (" + a.livello_formazione + ")" + (a.tipo === "pm" ? " · PM" : a.tipo === "manager" ? " · manager" : ""))));
      const mot = h("textarea", { style: "min-height:56px", maxlength: 800, placeholder: "Perché serve (quale lacuna, quale progetto)" });
      const urg = h("select", {}, h("option", { value: 2 }, "Urgenza normale"), h("option", { value: 3 }, "Urgenza alta"), h("option", { value: 1 }, "Urgenza bassa"));
      const prog = h("select", {}, h("option", { value: "" }, "— nessun progetto —"), d.progetti.map(p => h("option", { value: p.id }, p.nome)));
      const azione = (f) => async () => { try { await f(); await carica(); } catch (e) { errore(e); } };
      riempi(destra, [
        h("h3", { style: "margin-top:0" }, "Formazione"),
        h("div", { class: "carta" },
          h("div", { class: "nome" }, im.attivo ? "Formazione attiva" : "Formazione in pausa"),
          h("div", { style: "margin:8px 0 4px;height:8px;border-radius:99px;background:var(--bordo);overflow:hidden" }, h("div", { style: "height:100%;width:" + perc + "%;background:linear-gradient(90deg,#f3b54a,#e58bd0)" })),
          h("div", { class: "sotto" }, "Oggi " + im.usati_oggi.toLocaleString("it-IT") + " token" + (im.senza_limite ? " · nessun tetto giornaliero" : " su " + im.budget.toLocaleString("it-IT")) + (im.in_corso ? " · una formazione è in corso…" : "")),
          h("div", { class: "riga" }, h("label", { style: "flex:0 0 auto" }, "Budget giornaliero (token, 0 = senza tetto)", budget),
            h("button", { class: "s", style: "align-self:flex-end", onclick: azione(() => api("PUT", "/gestione/ginnasio/impostazioni", { budget: Number(budget.value) })) }, "Salva budget"),
            h("button", { class: im.attivo ? "s" : "p", style: "align-self:flex-end", onclick: azione(() => api("PUT", "/gestione/ginnasio/impostazioni", { attivo: !im.attivo })) }, im.attivo ? "Metti in pausa" : "Attiva la formazione")),
          h("label", { style: "display:flex;gap:8px;align-items:center;margin-top:6px" }, h("input", { type: "checkbox", checked: im.pausa_studio, onchange: azione(() => api("PUT", "/gestione/ginnasio/impostazioni", { pausa_studio: !im.pausa_studio })) }),
            h("span", { class: "sotto" }, "Fermati dopo lo studio e fammi leggere gli appunti prima della stesura (consigliato all'inizio)")),
          h("p", { class: "aiuto" }, "In pausa nulla parte da solo: puoi provare una richiesta alla volta con «Esegui ora» e vedere quanto costa. Costi stimati per livello: " +
            [1, 2, 3, 4, 5].map(n => NOMI[n] + " ≈ " + Number(d.stime[n]).toLocaleString("it-IT")).join(" · ") + " token. Il Master parte solo con il tuo via libera.")),
        msg,
        h("h4", {}, "Da approvare" + (d.da_approvare.length ? " (" + d.da_approvare.length + ")" : "")),
        d.da_approvare.length ? d.da_approvare.map(b => bozza(b, carica, errore)) : h("p", { class: "sotto" }, "Nessuna bozza in attesa."),
        h("h4", {}, "Coda di formazione" + (d.coda.length ? " (" + d.coda.length + ")" : "")),
        d.coda.length ? d.coda.map((r, i) => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, (i + 1) + ". " + r.competenza_nome + " — livello " + r.livello + " (" + NOMI[r.livello] + ")"),
          h("div", { class: "sotto" }, [r.agente ? "per " + r.agente : "solo libreria", r.progetto ? "progetto " + r.progetto : "", "chiesta da " + (r.richiedente || r.richiedente_persona || ORIGINI[r.origine]), r.peso > 1 ? r.peso + " richieste unite" : "",
            "urgenza " + r.urgenza, "punteggio " + r.punteggio, r.ordine_manuale != null ? "ordine deciso da te" : "", "≈ " + Number(r.stima_token).toLocaleString("it-IT") + " token"].filter(Boolean).join(" · ")),
          r.motivo ? h("div", { style: "white-space:pre-wrap" }, r.motivo) : null,
          r.note ? h("div", { class: "sotto" }, "Nota sulla bozza precedente: " + r.note) : null,
          h("div", { class: "azioni" },
            h("button", { class: "s", title: "In cima alla coda", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/sposta", { azione: "cima" })) }, "⇈"),
            h("button", { class: "s", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/sposta", { azione: "su" })) }, "▲"),
            h("button", { class: "s", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/sposta", { azione: "giu" })) }, "▼"),
            r.ordine_manuale != null ? h("button", { class: "s", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/sposta", { azione: "automatico" })) }, "Automatico") : null,
            r.livello === 5 && !r.via_libera ? h("button", { class: "s", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/via-libera")) }, "Via libera al Master") : null,
            h("button", { class: "p", onclick: async () => { if (!confirm("Eseguire ora «" + r.competenza_nome + "» livello " + r.livello + "? Costo stimato ≈ " + Number(r.stima_token).toLocaleString("it-IT") + " token.")) return;
              try { await api("POST", "/gestione/ginnasio/richieste/" + r.id + "/esegui"); msg.replaceChildren(avviso("Formazione avviata: Padre Casati ci sta lavorando.", "ok")); await carica(); } catch (e) { errore(e); } } }, "Esegui ora"),
            h("button", { class: "s", onclick: azione(() => api("POST", "/gestione/ginnasio/richieste/" + r.id + "/annulla")) }, "Annulla"))))
          : h("p", { class: "sotto" }, "Coda vuota. Le richieste arrivano da manager e project manager, dai segnali automatici o da te."),
        h("h4", {}, "Nuova richiesta"),
        h("div", { class: "carta" }, dl,
          h("div", { class: "riga" }, h("label", {}, "Competenza", comp), h("label", { style: "flex:0 0 auto" }, "Livello", liv)),
          h("div", { class: "riga" }, h("label", {}, "Chi formare", ag), h("label", {}, "Progetto", prog)), mot,
          h("div", { class: "riga" }, h("label", { style: "flex:0 0 auto" }, urg),
            h("button", { class: "p", style: "align-self:flex-end", onclick: async () => {
              try { const r = await api("POST", "/gestione/ginnasio/richieste", { competenza: comp.value, livello: Number(liv.value), agente_id: ag.value ? Number(ag.value) : null, motivo: mot.value, progetto_id: prog.value ? Number(prog.value) : null, urgenza: Number(urg.value) });
                comp.value = mot.value = ""; msg.replaceChildren(avviso(r.assegnata ? "La competenza esisteva già: assegnata subito." : r.unita ? "Unita a una richiesta già in coda." : "Messa in coda.", "ok")); await carica(); } catch (e) { errore(e); } } }, "Metti in coda"))),
        h("h4", {}, "Formazioni in corso e recenti"),
        d.recenti.length ? d.recenti.map(x => avanzamento(x, carica, errore)) : h("p", { class: "sotto" }, "Nessuna formazione ancora."),
        h("h4", {}, "Competenze"),
        d.competenze.length ? d.competenze.map(c => schedaCompetenza(c, d, carica, errore)) : h("p", { class: "sotto" }, "Nessuna competenza ancora: nasce dalla prima formazione approvata."),
        h("h4", {}, "Livello di formazione degli agenti"),
        h("p", { class: "aiuto" }, "Il numero è la media dei livelli delle competenze dell'agente e dice cosa gli è stato installato, non quanto lavora bene (per quello c'è il dossier)."),
        h("table", { class: "tabella" }, h("thead", {}, h("tr", {}, ["Agente", "Ruolo", "Livello"].map(t => h("th", {}, t)))),
          h("tbody", {}, d.agenti.slice().sort((a, b) => (b.tipo === "pm") - (a.tipo === "pm") || (b.tipo === "manager") - (a.tipo === "manager") || a.livello_formazione - b.livello_formazione).map(a => h("tr", {},
            h("td", {}, a.nome), h("td", {}, a.tipo === "pm" ? "Project manager" : a.tipo === "manager" ? "Manager" : a.ruolo || "—"), h("td", {}, String(a.livello_formazione))))))]);
      if ((im.in_corso || d.recenti.some(x => x.stato === "in_corso")) && !timer) timer = setInterval(() => { if (!document.body.contains(destra)) { clearInterval(timer); return; } carica(); }, 8000);
      if (!im.in_corso && timer) { clearInterval(timer); timer = null; }
    } catch (e) { destra.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Ginnasio"),
    h("p", { class: "aiuto" }, "A sinistra Padre Casati studia e custodisce la biblioteca; a destra forma gli agenti: ogni competenza ha cinque livelli (Junior, Medium, Senior, Expert, Master) e arriva a un agente solo dopo la tua approvazione. Si procede piano, nei limiti del budget giornaliero."),
    h("div", { class: "ginnasio" }, h("section", {}, sinistra), h("section", {}, destra))];
}

function bozza(b, ricarica, errore) {
  const corpo = h("textarea", { style: "min-height:260px;width:100%", maxlength: 12000 }); corpo.value = b.corpo;
  const nota = h("input", { maxlength: 500, placeholder: "Se la respingi: cosa va cambiato" });
  return h("div", { class: "carta", style: "margin-bottom:8px" },
    h("div", { class: "nome" }, b.competenza + " — livello " + b.livello + " (v" + b.versione + ")"),
    h("div", { class: "sotto" }, [b.descrizione, b.agente ? "per " + b.agente : "", b.token_usati ? b.token_usati.toLocaleString("it-IT") + " token" : ""].filter(Boolean).join(" · ")),
    h("details", {}, h("summary", { style: "cursor:pointer" }, "Leggi e modifica il testo"), corpo,
      h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/ginnasio/livelli/" + b.id, { corpo: corpo.value }); ricarica(); } catch (e) { errore(e); } } }, "Salva le modifiche"))),
    nota,
    h("div", { class: "azioni" },
      h("button", { class: "p", onclick: async () => { try { await api("PUT", "/gestione/ginnasio/livelli/" + b.id, { corpo: corpo.value }); const r = await api("POST", "/gestione/ginnasio/livelli/" + b.id + "/decisione", { azione: "approva" }); await ricarica(); } catch (e) { errore(e); } } }, b.agente ? "Approva e assegna a " + b.agente : "Approva"),
      h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/ginnasio/livelli/" + b.id + "/decisione", { azione: "respingi", nota: nota.value }); await ricarica(); } catch (e) { errore(e); } } }, "Respingi")));
}

function schedaCompetenza(c, d, ricarica, errore) {
  const ag = h("select", {}, d.agenti.map(a => h("option", { value: a.id }, a.nome)));
  const approvati = c.livelli.filter(l => l.stato === "approvata").map(l => l.livello);
  const lv = h("select", {}, approvati.map(n => h("option", { value: n }, n + " — " + d.livelli[n])));
  const visto = h("pre", { style: "white-space:pre-wrap;display:none;max-height:340px;overflow:auto" });
  return h("div", { class: "carta", style: "margin-bottom:8px" },
    h("div", { class: "nome" }, c.nome),
    h("div", { class: "sotto" }, c.descrizione || "—"),
    h("div", {}, [1, 2, 3, 4, 5].map(n => { const l = c.livelli.find(x => x.livello === n);
      return h("span", { class: "etichetta " + (l && l.stato === "approvata" ? "ok" : ""), title: l ? (l.stato === "approvata" ? "approvato" + (l.verifica_il ? ", da verificare entro il " + new Date(l.verifica_il).toLocaleDateString("it-IT") : "") : "bozza") : "non ancora scritto" }, n + " " + d.livelli[n] + (l ? (l.stato === "bozza" ? " (bozza)" : "") : " ·")); })),
    c.agenti.length ? h("div", { class: "sotto" }, "La hanno: " + c.agenti.map(a => a.nome + " (" + a.livello + ")").join(", ")) : h("div", { class: "sotto" }, "Nessun agente la ha ancora."),
    visto,
    approvati.length ? h("div", { class: "azioni" }, ag, lv,
      h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/ginnasio/assegna", { agente_id: Number(ag.value), competenza_id: c.id, livello: Number(lv.value) }); ricarica(); } catch (e) { errore(e); } } }, "Assegna"),
      h("button", { class: "s", onclick: async () => { const l = c.livelli.find(x => x.livello === Number(lv.value) && x.stato === "approvata"); if (!l) return;
        if (visto.style.display === "none") { try { visto.textContent = (await api("GET", "/gestione/ginnasio/livelli/" + l.id)).corpo; visto.style.display = "block"; } catch (e) { errore(e); } } else visto.style.display = "none"; } }, "Leggi il livello")) : null,
    c.agenti.length ? h("div", { class: "azioni" }, c.agenti.map(a => h("button", { class: "s", title: "Toglie la competenza", onclick: async () => { if (!confirm("Togliere «" + c.nome + "» a " + a.nome + "?")) return;
      try { await api("DELETE", "/gestione/ginnasio/assegna/" + a.id + "/" + c.id); ricarica(); } catch (e) { errore(e); } } }, "Togli a " + a.nome))) : null);
}

const STATO_FORMAZIONE = { in_corso: "in corso", appunti_pronti: "appunti pronti: aspetta il tuo via libera", da_approvare: "bozza da approvare", conclusa: "conclusa", errore: "non riuscita", annullata: "annullata" };
const NOME_FASE = { ricerca: "1 · Ricerca e download", studio: "2 · Studio", stesura: "3 · Stesura" };
const ICONA_FASE = { finita: "✅", in_corso: "⏳", in_attesa: "⚪", saltata: "↪️", interrotta: "⛔" };

// Avanzamento di una formazione: tappe, documenti scaricati, appunti e passaggi di Padre Casati
function avanzamento(x, carica, errore) {
  const corpo = h("div", { class: "sotto" }, "Apri per vedere a che punto è.");
  let timer = null, caricato = false;
  const carica_ = async () => {
    try {
      const a = await api("GET", "/gestione/ginnasio/richieste/" + x.id + "/avanzamento");
      riempi(corpo, [
        h("div", { style: "display:flex;gap:10px;flex-wrap:wrap;margin:6px 0" }, a.fasi.map(f => h("div", { class: "carta", style: "padding:6px 10px;flex:1;min-width:140px" },
          h("div", {}, ICONA_FASE[f.stato] + " " + NOME_FASE[f.nome]), h("div", { class: "sotto" }, ({ finita: "finita", in_corso: "in corso…", in_attesa: "in attesa", saltata: "già fatta", interrotta: "interrotta" })[f.stato] + (f.token ? " · " + f.token.toLocaleString("it-IT") + " token" : "") + (f.durata_ms ? " · " + Math.round(f.durata_ms / 1000) + " s" : ""))))),
        a.errore ? h("div", { class: "sotto", style: "color:#c44" }, "Motivo: " + a.errore) : null,
        h("div", { class: "nome" }, "Documenti scaricati (" + a.materiali.length + ")"),
        a.materiali.length ? a.materiali.map(m => { let sito = "?"; try { sito = new URL(m.fonte_url).hostname; } catch (e) {}
          return h("div", { class: "sotto" }, "📄 " + m.nome + (m.autori ? " — " + m.autori : "") + (m.anno ? " (" + m.anno + ")" : "") + " · " + sito + " · " + Math.round(m.byte / 1024) + " KB" + (m.licenza ? " · " + m.licenza : "")); })
          : h("div", { class: "sotto" }, "Nessuno finora."),
        a.ricerche.length ? h("details", {}, h("summary", { class: "sotto", style: "cursor:pointer" }, "Ricerche fatte (" + a.ricerche.length + ")"), a.ricerche.map(r => h("div", { class: "sotto" }, "🔎 " + r.replace(/^cerca_fonti: /, "")))) : null,
        a.appunti ? h("details", { open: x.stato === "appunti_pronti" }, h("summary", { class: "nome", style: "cursor:pointer" }, "Appunti di studio"), h("div", { class: "sotto", style: "white-space:pre-wrap;max-height:320px;overflow:auto" }, a.appunti)) : null,
        x.stato === "appunti_pronti" ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("POST", "/gestione/ginnasio/richieste/" + x.id + "/stesura"); await carica(); } catch (e) { errore(e); } } }, "Procedi alla stesura")) : null,
        a.passaggi.length ? h("details", {}, h("summary", { class: "sotto", style: "cursor:pointer" }, "Passaggi di Padre Casati (" + a.passaggi.length + ")"), a.passaggi.map(p => h("div", { class: "sotto" }, new Date(p.creato_il).toLocaleTimeString("it-IT") + " · " + p.dettaglio))) : null]);
    } catch (e) { corpo.replaceChildren(h("div", { class: "sotto" }, e.message)); }
  };
  const det = h("details", { open: x.stato === "in_corso" || x.stato === "appunti_pronti", ontoggle: () => { if (det.open && !caricato) { caricato = true; carica_(); } } },
    h("summary", { style: "cursor:pointer;padding:4px 0" }, h("b", {}, x.competenza_nome + " · liv. " + x.livello), (x.agente ? " · " + x.agente : "") + " · " + STATO_FORMAZIONE[x.stato] + (x.token_usati ? " · " + x.token_usati.toLocaleString("it-IT") + " token" : "")), corpo);
  if (det.open) { caricato = true; carica_(); if (x.stato === "in_corso") timer = setInterval(() => { if (!document.body.contains(det)) { clearInterval(timer); return; } carica_(); }, 6000); }
  return det;
}
