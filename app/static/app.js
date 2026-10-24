"use strict";
// Interfaccia della piattaforma agenti. Nessun testo dei dati viene mai inserito come HTML: solo textContent.

const radice = document.getElementById("radice");
let token = null;
try { token = sessionStorage.getItem("token"); } catch (e) { /* sessionStorage non disponibile */ }
let stato = { vista: "dashboard", sezione: "profilo", richieste: 0, agenti: [], opzioni: null, connessioni: [], documenti: [], conversazione: [] };

function h(tag, attrs, ...figli) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v !== null && v !== undefined) el.setAttribute(k, v);
  }
  for (const f of figli.flat(Infinity)) if (f !== null && f !== undefined && f !== false) el.append(f);
  return el;
}

// Sostituisce il contenuto di un elemento accettando anche liste annidate di nodi
function riempi(el, contenuto) {
  el.replaceChildren(...[contenuto].flat(Infinity).filter(n => n !== null && n !== undefined && n !== false));
}

function messaggioErrore(d) {
  if (!d) return "Errore sconosciuto";
  if (typeof d.detail === "string") return d.detail;
  if (Array.isArray(d.detail)) return d.detail.map(x => (x.loc ? x.loc.slice(1).join(".") + ": " : "") + x.msg).join("; ");
  return "Errore sconosciuto";
}

async function api(metodo, percorso, corpo) {
  const modulo = corpo instanceof FormData;
  const r = await fetch(percorso, {
    method: metodo,
    headers: { ...(modulo ? {} : { "Content-Type": "application/json" }), ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: corpo === undefined ? undefined : (modulo ? corpo : JSON.stringify(corpo)),
  });
  let dati = null;
  try { dati = await r.json(); } catch (e) { /* risposta vuota */ }
  if (r.status === 401 && percorso !== "/login") { esci(); throw new Error("Sessione scaduta: rientra"); }
  if (!r.ok) throw new Error(messaggioErrore(dati));
  return dati;
}

function esci() {
  token = null;
  try { sessionStorage.removeItem("token"); } catch (e) { /* ignora */ }
  mostraAccesso();
}

function avviso(testo, tipo) { return h("div", { class: "messaggio " + (tipo || "avv"), role: "status" }, testo); }

// ---------- Accesso ----------
function mostraAccesso(errore) {
  const email = h("input", { type: "email", autocomplete: "username", required: true });
  const pw = h("input", { type: "password", autocomplete: "current-password", required: true });
  const msg = h("div");
  const invia = async (ev) => {
    ev.preventDefault();
    msg.replaceChildren();
    try {
      await proseguiAccesso(await api("POST", "/login", { email: email.value, password: pw.value }));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  radice.replaceChildren(h("div", { class: "accesso" },
    h("h2", {}, "Opifex"),
    h("form", { onsubmit: invia, class: "carta" },
      h("label", {}, "Email", email), h("label", {}, "Password", pw),
      msg, h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Entra")))));
  if (errore) msg.replaceChildren(avviso(errore, "no"));
}

// ---------- Struttura ----------
const VISTE = [["dashboard", "Dashboard"], ["agenti", "Agenti"], ["progetti", "Progetti"], ["documenti", "Documenti"], ["dialoghi", "Dialoghi"], ["chat", "Chat"], ["briefing", "Briefing"], ["impostazioni", "Impostazioni"]];
const VISTE_COLLABORATORE = [["chat", "Chat"], ["account", "Il mio account"]];
const SEZIONI_IMPOSTAZIONI = [["profilo", "Il mio profilo"], ["struttura", "Aziende e dipartimenti"], ["collegamenti", "Account Google"], ["connessioni", "Connessioni a siti e app"],
  ["canali", "Canali (Telegram)"], ["utenti", "Utenti e collaboratori"], ["aggiornamenti", "Aggiornamenti"], ["sicurezza", "Sicurezza e garanzie"]];

function vai(vista, sezione) { stato.vista = vista; if (sezione) stato.sezione = sezione; disegna(); }

function cornice(contenuto) {
  radice.replaceChildren(
    h("header", {}, h("h1", {}, "Opifex ", h("small", {}, "// officina")),
      h("nav", {}, (stato.ruolo === "titolare" ? VISTE : VISTE_COLLABORATORE).map(([id, nome]) =>
        h("button", { class: stato.vista === id || (id === "dashboard" && stato.vista === "richieste") ? "attivo" : "", onclick: () => vai(id) },
          nome + (id === "dashboard" && stato.richieste ? " (" + stato.richieste + ")" : "")))),
      h("button", { class: "s", onclick: esci }, "Esci")),
    h("main", { class: stato.vista === "dashboard" ? "largo" : "" }, contenuto));
}

async function avvia() {
  try {
    const io = await api("GET", "/io");
    stato.ruolo = io.ruolo_globale;
    if (stato.ruolo !== "titolare") {   // il collaboratore vede solo la chat con gli agenti delle sue divisioni
      stato.agenti = await api("GET", "/agenti");
      if (!VISTE_COLLABORATORE.some(([id]) => id === stato.vista)) stato.vista = "chat";
      return disegna();
    }
    const [agenti, opzioni, connessioni, documenti, cont] = await Promise.all([
      api("GET", "/gestione/agenti"), api("GET", "/gestione/opzioni"), api("GET", "/gestione/connessioni"),
      api("GET", "/gestione/documenti"), api("GET", "/gestione/richieste/conteggio")]);
    Object.assign(stato, { agenti, opzioni, connessioni, documenti, richieste: cont.aperte });
    disegna();
  } catch (e) {
    if (token) { mostraAccesso(e.message); }
  }
}

async function ricarica() {
  stato.agenti = await api("GET", "/gestione/agenti");
  stato.connessioni = await api("GET", "/gestione/connessioni");
  stato.documenti = await api("GET", "/gestione/documenti");
  stato.opzioni = await api("GET", "/gestione/opzioni");
  try { stato.richieste = (await api("GET", "/gestione/richieste/conteggio")).aperte; } catch (e) { /* ignora */ }
  disegna();
}

function disegna() {
  if (stato.timer) { clearInterval(stato.timer); stato.timer = null; }
  if (stato.attesa) { clearTimeout(stato.attesa); stato.attesa = null; }
  if (stato.timer2) { clearInterval(stato.timer2); stato.timer2 = null; }
  const vista = { dashboard: vistaDashboard, impostazioni: vistaImpostazioni, account: vistaAccount, progetti: vistaProgetti, agenti: vistaAgenti, documenti: vistaDocumenti, richieste: vistaRichieste, dialoghi: vistaDialoghi, chat: vistaChat, briefing: vistaBriefing }[stato.vista] || vistaDashboard;
  cornice(vista());
}

const ETICHETTA_FASCIA = { pubblico: "Solo dati pubblici", interno: "Dati interni", riservato: "Dati riservati" };

// ---------- Agenti ----------
function vistaAgenti() {
  const gruppi = new Map();
  for (const a of stato.agenti) {
    const g = a.divisione || "Agenti di sistema";
    if (!gruppi.has(g)) gruppi.set(g, []);
    gruppi.get(g).push(a);
  }
  const garanzie = (stato.opzioni.fornitori || []).filter(f => !(f.non_conservazione_attiva && f.dpa_firmato));
  return [
    h("div", { class: "riga", style: "align-items:center" },
      h("h2", {}, "Agenti"),
      h("div", { style: "text-align:right;flex:0 0 auto" }, h("button", { class: "p", onclick: () => modulo(null) }, "+ Nuovo agente"))),
    garanzie.length ? avviso("I dati interni e riservati restano bloccati verso: " +
      garanzie.map(f => f.nome).join(", ") + " (mancano le garanzie di non conservazione/DPA). Gli agenti lavorano solo su dati pubblici.", "avv") : null,
    [...gruppi].map(([nome, lista]) => [h("h3", {}, nome), h("div", { class: "griglia" }, lista.map(carta))]),
  ];
}

function carta(a) {
  return h("div", { class: "carta agente" + (a.attivo ? "" : " spento"), tabindex: 0, role: "button",
      onclick: () => modulo(a), onkeydown: (e) => { if (e.key === "Enter") modulo(a); } },
    h("div", { class: "nome" }, a.nome),
    h("div", { class: "sotto" }, a.ruolo),
    h("div", {},
      h("span", { class: "etichetta " + (a.attivo ? "ok" : "no") }, a.attivo ? "Attivo" : "Spento"),
      h("span", { class: "etichetta" }, a.modello),
      a.accesso_web ? h("span", { class: "etichetta avv" }, "Web") : null,
      a.connessioni.length ? h("span", { class: "etichetta" }, a.connessioni.length + " conn.") : null),
    h("div", { class: "sotto" }, "Questo mese: " + a.token_mese.toLocaleString("it-IT") + " token"));
}

function modulo(a) {
  const nuovo = a === null;
  const d = a || { nome: "", ruolo: "", divisione_id: null, superiore_id: null, livello: "operativo",
    modello: stato.opzioni.modelli[0]?.nome, istruzioni: "", fascia_dati_max: "pubblico", max_token_risposta: 1500,
    budget_token_mensile: null, accesso_web: false, siti_consentiti: [], max_ricerche: 3, attivo: true, connessioni: [], aziende: [] };

  const nome = h("input", { type: "text", value: d.nome, maxlength: 60 });
  const ruolo = h("input", { type: "text", value: d.ruolo, maxlength: 120, placeholder: "Es. Cerca nuovi bandi" });
  const istr = h("textarea", { style: "min-height:180px" }); istr.value = d.istruzioni;
  const div = h("select", {}, h("option", { value: "" }, "Nessuna (agente di sistema)"),
    stato.opzioni.divisioni.map(x => h("option", { value: x.id }, x.nome)));
  div.value = d.divisione_id ?? "";
  const sup = h("select", {}, h("option", { value: "" }, "Nessuno"),
    stato.agenti.filter(x => !a || x.id !== a.id).map(x => h("option", { value: x.id }, x.nome + " (" + x.ruolo + ")")));
  sup.value = d.superiore_id ?? "";
  const livello = h("select", {}, [["operativo", "Operativo"], ["manager", "Manager"], ["referente", "Referente"]]
    .map(([v, t]) => h("option", { value: v }, t)));
  livello.value = d.livello;
  const modello = h("select", {}, stato.opzioni.modelli.map(m => h("option", { value: m.nome }, m.nome + " — " + m.fornitore)));
  modello.value = d.modello;
  const fascia = h("select", {}, Object.entries({ pubblico: "Solo dati pubblici", interno: "Dati pubblici e interni", riservato: "Tutti i dati (anche riservati)" }).map(([v, t]) => h("option", { value: v }, t)));
  fascia.value = d.fascia_dati_max;
  const tetto = h("input", { type: "number", min: 100, max: 8000, value: d.max_token_risposta });
  const budget = h("input", { type: "number", min: 1, value: d.budget_token_mensile ?? "", placeholder: "Nessun limite" });
  const web = h("input", { type: "checkbox" }); web.checked = d.accesso_web;
  const siti = h("textarea", { style: "min-height:80px", placeholder: "esempio.it\nbandi.regione.it" });
  siti.value = (d.siti_consentiti || []).join("\n");
  const ricerche = h("input", { type: "number", min: 1, max: 10, value: d.max_ricerche });
  const attivo = h("input", { type: "checkbox" }); attivo.checked = d.attivo;
  const modDialogo = h("select", {}, h("option", { value: "" }, "Predefinito (il più economico)"),
    stato.opzioni.modelli.map(m => h("option", { value: m.nome }, m.nome + " — " + m.fornitore)));
  modDialogo.value = d.modello_dialogo || "";
  const dialoga = h("input", { type: "checkbox" }); dialoga.checked = !!d.dialoghi_attivi;
  const conn = stato.connessioni.map(c => {
    const cb = h("input", { type: "checkbox", value: c.id }); cb.checked = d.connessioni.includes(c.id);
    return [c, cb];
  });
  const azCb = (stato.opzioni.aziende || []).map(z => {
    const cb = h("input", { type: "checkbox", value: z.id }); cb.checked = (d.aziende || []).includes(z.id);
    return [z, cb];
  });
  const msg = h("div");

  const salva = async () => {
    msg.replaceChildren();
    const corpo = {
      nome: nome.value.trim(), ruolo: ruolo.value.trim(), istruzioni: istr.value.trim(),
      divisione_id: div.value ? Number(div.value) : null, superiore_id: sup.value ? Number(sup.value) : null,
      livello: livello.value, modello: modello.value, fascia_dati_max: fascia.value,
      max_token_risposta: Number(tetto.value), budget_token_mensile: budget.value ? Number(budget.value) : null,
      accesso_web: web.checked, siti_consentiti: siti.value.split("\n").map(s => s.trim()).filter(Boolean),
      max_ricerche: Number(ricerche.value), attivo: attivo.checked,
      modello_dialogo: modDialogo.value || null, dialoghi_attivi: dialoga.checked,
      connessioni: conn.filter(([, cb]) => cb.checked).map(([c]) => c.id),
    };
    try {
      const esito = await api(nuovo ? "POST" : "PUT", nuovo ? "/gestione/agenti" : "/gestione/agenti/" + a.id, corpo);
      await api("PUT", "/gestione/agenti/" + (nuovo ? esito.id : a.id) + "/aziende", { aziende: azCb.filter(([, cb]) => cb.checked).map(([z]) => z.id) });
      chiudi(); await ricarica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };

  // --- documenti di riferimento dell'agente (solo agenti gia' salvati)
  const sezioneDoc = h("div");
  const discendentiDi = (id) => { const r = []; const coda = [id]; while (coda.length) { const x = coda.shift(); for (const f of stato.agenti.filter(y => y.superiore_id === x)) { r.push(f); coda.push(f.id); } } return r; };
  const caricaDoc = async () => {
    if (nuovo) { sezioneDoc.replaceChildren(h("p", { class: "aiuto" }, "Prima salva l'agente: poi potrai caricare qui il suo documento di riferimento.")); return; }
    const m = h("div");
    try { stato.documenti = await api("GET", "/gestione/documenti"); } catch (e) { sezioneDoc.replaceChildren(avviso(e.message, "no")); return; }
    const miei = stato.documenti.filter(x => x.assegnazioni.some(y => y.agente_id === a.id));
    const sotto = discendentiDi(a.id);
    const file = h("input", { type: "file", accept: ".pdf,.docx,.txt,.md,.csv" });
    const fasciaDoc = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t))); fasciaDoc.value = "interno";
    const elenco = miei.map(x => {
      const mia = x.assegnazioni.find(y => y.agente_id === a.id);
      const da = mia.passato_da ? stato.agenti.find(y => y.id === mia.passato_da)?.nome : null;
      const pannello = h("div", { style: "display:none;margin:8px 0" });
      const caselle = sotto.map(f => { const cb = h("input", { type: "checkbox" }); cb.checked = x.assegnazioni.some(y => y.agente_id === f.id && y.passato_da === a.id); return [f, cb]; });
      pannello.append(h("p", { class: "aiuto" }, "Scegli chi tra i tuoi sottoposti deve usare questo documento per il suo lavoro. Tu e i tuoi superiori lo vedete comunque."),
        caselle.map(([f, cb]) => h("label", { class: "spunta" }, cb, f.nome + " (" + f.ruolo + ")")),
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try { await api("PUT", "/gestione/agenti/" + a.id + "/documenti/" + x.id + "/passa", { agenti: caselle.filter(([, cb]) => cb.checked).map(([f]) => f.id) }); caricaDoc(); }
          catch (e) { m.replaceChildren(avviso(e.message, "no")); } } }, "Salva passaggi")));
      return h("div", { class: "carta", style: "margin-bottom:8px" },
        h("div", { class: "nome" }, x.nome), h("div", { class: "sotto" }, x.nome_file + " · " + ETICHETTA_FASCIA[x.fascia_dati] + (da ? " · passato da " + da : "")),
        h("div", { class: "azioni", style: "margin-top:8px" },
          sotto.length ? h("button", { class: "s", onclick: () => { pannello.style.display = pannello.style.display === "none" ? "" : "none"; } }, "Passa ai sottoposti") : null,
          mia.passato_da ? null : h("button", { class: "s", onclick: async () => {
            if (!confirm("Togliere il documento a " + d.nome + "? Resta nel repository.")) return;
            try { await api("PUT", "/gestione/documenti/" + x.id, { agenti: x.assegnazioni.filter(y => !y.passato_da && y.agente_id !== a.id).map(y => y.agente_id) }); caricaDoc(); }
            catch (e) { m.replaceChildren(avviso(e.message, "no")); } } }, "Togli")),
        pannello);
    });
    sezioneDoc.replaceChildren(...[
      miei.length ? elenco : h("p", { class: "aiuto" }, "Nessun documento: carica qui quello di riferimento per " + d.nome + "."),
      h("label", {}, "Carica un documento", file), h("label", {}, "Riservatezza", fasciaDoc), m,
      h("div", { class: "azioni" }, h("button", { class: "s", onclick: async (ev) => {
        if (!file.files[0]) { m.replaceChildren(avviso("Scegli un file", "no")); return; }
        const b = ev.currentTarget; b.disabled = true; b.textContent = "Caricamento…";
        const f = new FormData(); f.append("file", file.files[0]); f.append("nome", ""); f.append("fascia_dati", fasciaDoc.value); f.append("per_tutti", "false"); f.append("agenti", String(a.id));
        try { await api("POST", "/gestione/documenti", f); caricaDoc(); } catch (e) { m.replaceChildren(avviso(e.message, "no")); b.disabled = false; b.textContent = "Carica"; } } }, "Carica"))].flat(Infinity));
  };
  caricaDoc();

  const chiudi = () => sfondo.remove();
  const sfondo = h("div", { class: "pannello-sfondo" },
    h("div", { class: "pannello", role: "dialog", "aria-label": nuovo ? "Nuovo agente" : "Modifica " + d.nome },
      h("h2", {}, nuovo ? "Nuovo agente" : d.nome),
      h("div", { class: "interruttore" }, attivo, h("span", {}, "Agente attivo (se spento non risponde e non lavora)")),
      h("label", {}, "Nome", nome),
      h("label", {}, "Ruolo", ruolo),
      h("label", {}, "Cosa deve fare", h("p", { class: "aiuto" }, "Istruzioni in italiano, come le daresti a un collaboratore: compiti, tono, cosa non deve fare."), istr),
      h("div", { class: "riga" }, h("label", {}, "Dipartimento", div), h("label", {}, "Risponde a", sup)),
      h("label", {}, "Aziende per cui lavora", h("p", { class: "aiuto" }, "Una o più. Se non ne scegli nessuna lavora per tutte (agente trasversale)."),
        azCb.length ? azCb.map(([z, cb]) => h("label", { class: "spunta" }, cb, z.nome)) : h("p", { class: "aiuto" }, "Nessuna azienda: creale nella scheda Struttura.")),
      h("div", { class: "riga" }, h("label", {}, "Livello", livello), h("label", {}, "Modello AI", modello)),
      h("h3", {}, "Riservatezza e costi"),
      h("label", {}, "Dati che può ricevere", h("p", { class: "aiuto" }, "Anche se qui scegli un livello alto, i dati escono verso un fornitore solo se il fornitore ha le garanzie attive."), fascia),
      h("div", { class: "riga" },
        h("label", {}, "Lunghezza massima risposta (token)", tetto),
        h("label", {}, "Budget mensile (token)", budget)),
      h("h3", {}, "Dialoghi con gli altri agenti"),
      h("div", { class: "interruttore" }, dialoga, h("span", {}, "Può fare domande a superiore, subordinati e altri manager mentre lavora")),
      h("label", {}, "Modello per i dialoghi", h("p", { class: "aiuto" }, "Per parlare con i colleghi basta un modello semplice ed economico: il modello di lavoro sopra resta per pensare e svolgere i compiti."), modDialogo),
      h("h3", {}, "Accesso al web"),
      h("div", { class: "interruttore" }, web, h("span", {}, "Può cercare sul web (solo modelli Claude per ora)")),
      h("label", {}, "Siti consentiti", h("p", { class: "aiuto" }, "Un sito per riga. Se lasci vuoto può cercare su qualsiasi sito."), siti),
      h("label", {}, "Ricerche massime per risposta", ricerche),
      h("h3", {}, "Documento di riferimento"), sezioneDoc,
      h("h3", {}, "Connessioni"),
      conn.length ? conn.map(([c, cb]) => h("label", { class: "spunta" }, cb, c.nome + " (" + c.tipo + ")"))
        : h("p", { class: "aiuto" }, "Nessuna connessione ancora: creale nella scheda Connessioni."),
      msg,
      h("div", { class: "azioni" },
        h("button", { class: "p", onclick: salva }, nuovo ? "Crea agente" : "Salva modifiche"),
        h("button", { class: "s", onclick: chiudi }, "Annulla"))));
  document.body.append(sfondo);
  nome.focus();
}

// ---------- Connessioni ----------
function vistaConnessioni() {
  const nome = h("input", { type: "text", maxlength: 60, placeholder: "Es. Canva, sito Renovatio" });
  const tipo = h("select", {}, [["sito", "Sito web"], ["app", "App"], ["altro", "Altro"]].map(([v, t]) => h("option", { value: v }, t)));
  const ind = h("input", { type: "text", placeholder: "https://…", maxlength: 300 });
  const desc = h("input", { type: "text", placeholder: "A cosa serve", maxlength: 500 });
  const msg = h("div");
  const aggiungi = async () => {
    msg.replaceChildren();
    try {
      await api("POST", "/gestione/connessioni", { nome: nome.value.trim(), tipo: tipo.value, indirizzo: ind.value.trim() || null, descrizione: desc.value.trim() || null });
      await ricarica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const nomiAgenti = (ids) => ids.map(i => stato.agenti.find(a => a.id === i)?.nome).filter(Boolean).join(", ") || "nessuno";
  return [
    h("h2", {}, "Connessioni"),
    avviso("Qui registri le app e i siti che vuoi far usare agli agenti. Il collegamento operativo (accessi, permessi, azioni) di ogni app si attiva insieme a me, una per volta: finché lo stato è «da configurare» l'agente non può agire sull'app.", "avv"),
    h("div", { class: "griglia" }, stato.connessioni.map(c =>
      h("div", { class: "carta" },
        h("div", { class: "nome" }, c.nome),
        h("div", { class: "sotto" }, c.indirizzo || "—"),
        h("div", { class: "sotto" }, c.descrizione || ""),
        h("div", {}, h("span", { class: "etichetta " + (c.stato === "attiva" ? "ok" : c.stato === "spenta" ? "no" : "avv") }, c.stato.replace("_", " ")),
          h("span", { class: "etichetta" }, c.tipo)),
        h("div", { class: "sotto" }, "Agenti: " + nomiAgenti(c.agenti)),
        c.accesso_configurato ? h("div", { class: "sotto" }, "Accesso salvato per " + c.dominio + " — contenuto: " + ETICHETTA_FASCIA[c.fascia_contenuto].toLowerCase()) : null,
        h("div", { class: "azioni" },
          h("button", { class: "s", onclick: () => modulo_accesso(c) }, c.accesso_configurato ? "Cambia accesso" : "Imposta accesso con login"),
          c.accesso_configurato ? h("button", { class: "s", onclick: async (ev) => {
            const b = ev.currentTarget; b.disabled = true; b.textContent = "Provo…";
            try {
              const r = await api("POST", "/gestione/connessioni/" + c.id + "/prova-accesso");
              alert(r.riuscita ? "Accesso riuscito: la connessione è ora attiva." : "Accesso non riuscito: " + r.errore);
              await ricarica();
            } catch (e) { alert(e.message); b.disabled = false; b.textContent = "Prova accesso"; }
          } }, "Prova accesso") : null,
          h("button", { class: "r", onclick: async () => {
          if (!confirm("Eliminare la connessione «" + c.nome + "»?")) return;
          try { await api("DELETE", "/gestione/connessioni/" + c.id); await ricarica(); } catch (e) { alert(e.message); }
        } }, "Elimina"))))),
    h("h3", {}, "Nuova connessione"),
    h("div", { class: "carta" },
      h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Tipo", tipo)),
      h("label", {}, "Indirizzo", ind), h("label", {}, "Descrizione", desc), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: aggiungi }, "Aggiungi"))),
  ];
}

function modulo_accesso(c) {
  const url = h("input", { type: "text", placeholder: "https://www.sito.it/area-personale/", value: c.url_login || c.indirizzo || "" });
  const utente = h("input", { type: "text", autocomplete: "off", placeholder: "Email o nome utente" });
  const pw = h("input", { type: "password", autocomplete: "new-password", placeholder: "Password" });
  const fascia = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t)));
  fascia.value = c.fascia_contenuto || "interno";
  const pagine = h("input", { type: "number", min: 1, max: 40, value: c.max_pagine || 12 });
  const msg = h("div");
  const chiudi = () => sfondo.remove();
  const salva = async () => {
    msg.replaceChildren();
    try {
      await api("PUT", "/gestione/connessioni/" + c.id + "/accesso", { url_login: url.value.trim(), utente: utente.value,
        password: pw.value, fascia_contenuto: fascia.value, max_pagine: Number(pagine.value) });
      pw.value = ""; chiudi(); await ricarica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const sfondo = h("div", { class: "pannello-sfondo" },
    h("div", { class: "pannello", role: "dialog" },
      h("h2", {}, "Accesso a " + c.nome),
      avviso("La password viene cifrata sul server e non viene mai mostrata né inviata ai modelli AI: la digita il browser del server. Dopo il salvataggio premi «Prova accesso».", "avv"),
      h("label", {}, "Pagina di accesso (login)", url),
      h("label", {}, "Email / utente", utente), h("label", {}, "Password", pw),
      h("label", {}, "Riservatezza di ciò che l'agente legge", h("p", { class: "aiuto" }, "Un sito con login contiene dati interni: finché il fornitore AI non ha le garanzie attive (scheda Sicurezza), l'agente non potrà elaborarli."), fascia),
      h("label", {}, "Pagine massime per ogni esecuzione", pagine), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: salva }, "Salva"), h("button", { class: "s", onclick: chiudi }, "Annulla"))));
  document.body.append(sfondo);
  utente.focus();
}


// ---------- Richieste (informazioni che servono agli agenti) ----------
function vistaRichieste() {
  const lista = h("div");
  const msg = h("div");
  let filtro = "aperta";
  const selFiltro = h("select", { onchange: () => { filtro = selFiltro.value; carica(); } },
    h("option", { value: "aperta" }, "Da risolvere"), h("option", { value: "risposta" }, "Risolte"),
    h("option", { value: "annullata" }, "Annullate"), h("option", { value: "tutte" }, "Tutte"));
  const carica = async () => {
    try {
      const el = await api("GET", "/gestione/richieste?stato=" + filtro);
      riempi(lista, el.length ? el.map(r => {
        const ris = h("textarea", { style: "min-height:60px", placeholder: "La tua risposta: l'agente la riceve al prossimo lavoro" });
        return h("div", { class: "carta", style: "margin-bottom:10px" },
          h("div", { class: "nome" }, (r.bloccante ? "BLOCCANTE · " : "") + r.agente),
          h("div", { class: "risposta" }, r.domanda),
          h("div", { class: "sotto" }, new Date(r.creata_il).toLocaleString("it-IT")),
          r.stato === "aperta" ? [ris, h("div", { class: "azioni" },
            h("button", { class: "p", onclick: async () => {
              try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); carica(); }
              catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Rispondi"),
            h("button", { class: "s", onclick: async () => {
              try { await api("POST", "/gestione/richieste/" + r.id + "/annulla"); carica(); }
              catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Non serve più"))]
          : (r.risposta ? h("div", { class: "risposta" }, "Risposta: " + r.risposta) : null));
      }) : h("p", { class: "sotto" }, "Nessuna richiesta. Se un agente non ha un'informazione, te la chiede qui: non inventa."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Informazioni che servono agli agenti"),
    h("p", { class: "aiuto" }, "Gli agenti non inventano mai: se manca un dato lo chiedono al superiore e, se serve, a te. Le richieste compaiono anche nei briefing."),
    selFiltro, msg, lista);
}

// ---------- Dialoghi ----------
function vistaDialoghi() {
  const colonnaFeed = h("div", { class: "carta", style: "max-height:70vh;overflow:auto" }, h("p", { class: "sotto" }, "Caricamento…"));
  const colonnaConv = h("div");
  const dettaglio = h("div");
  let ultimoId = 0, primo = true;
  const messaggioFeed = (m) => h("div", { style: "margin-bottom:12px" },
    h("div", { class: "sotto" }, (m.da || "?") + " → " + (m.a || "?") + " · " + new Date(m.creato_il).toLocaleTimeString("it-IT") + " · " + m.titolo),
    h("div", { class: "risposta" }, m.testo));
  const aggiornaFeed = async () => {
    try {
      const nuovi = await api("GET", "/gestione/dialoghi/feed" + (primo ? "" : "?dopo_id=" + ultimoId));
      if (primo) { colonnaFeed.replaceChildren(); if (!nuovi.length) colonnaFeed.append(h("p", { class: "sotto" }, "Nessun dialogo ancora. Quando gli agenti si parlano, lo vedi qui.")); }
      const alFondo = colonnaFeed.scrollTop + colonnaFeed.clientHeight >= colonnaFeed.scrollHeight - 40;
      if (nuovi.length && !primo && colonnaFeed.firstChild?.tagName === "P") colonnaFeed.replaceChildren();
      for (const m of nuovi) { colonnaFeed.append(messaggioFeed(m)); ultimoId = Math.max(ultimoId, m.id); }
      if (primo || (nuovi.length && alFondo)) colonnaFeed.scrollTop = colonnaFeed.scrollHeight;
      primo = false;
      const el = await api("GET", "/gestione/dialoghi");
      riempi(colonnaConv, el.length ? el.map(c => h("div", { class: "carta agente", style: "margin-bottom:8px", tabindex: 0, role: "button",
          onclick: () => apri(c.id) },
        h("div", { class: "nome" }, c.titolo),
        h("div", { class: "sotto" }, c.partecipanti + " · " + c.messaggi + " messaggi · " + (c.stato === "chiusa" ? "conclusa" : "aperta")))) : h("p", { class: "sotto" }, "Nessuna conversazione."));
    } catch (e) { /* riprova al prossimo giro */ }
  };
  const apri = async (id) => {
    try {
      const c = await api("GET", "/gestione/dialoghi/" + id);
      dettaglio.replaceChildren(h("div", { class: "carta", style: "margin-top:12px" },
        h("div", { class: "nome" }, c.titolo), h("div", { class: "sotto" }, "Dati: " + ETICHETTA_FASCIA[c.fascia_dati].toLowerCase()),
        c.messaggi.map(m => h("div", { style: "margin-top:12px" },
          h("div", { class: "sotto" }, m.da + " → " + m.a + " · " + new Date(m.creato_il).toLocaleString("it-IT") + (m.modello ? " · " + m.modello : "")),
          h("div", { class: "risposta" }, m.testo))),
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => dettaglio.replaceChildren() }, "Chiudi"))));
      dettaglio.scrollIntoView({ behavior: "smooth" });
    } catch (e) { dettaglio.replaceChildren(avviso(e.message, "no")); }
  };
  stato.timer = setInterval(aggiornaFeed, 5000);
  aggiornaFeed();

  // avvio di un dialogo
  const attivi = stato.agenti.filter(a => a.attivo);
  const opz = () => attivi.map(a => h("option", { value: a.id }, a.nome + " — " + a.ruolo));
  const da = h("select", {}, opz()); const a2 = h("select", {}, opz());
  if (attivi.length > 1) a2.selectedIndex = 1;
  const arg = h("textarea", { style: "min-height:70px", placeholder: "Es. Coordinare la ricerca dei bandi sui borghi per le imprese di Lorenzo" });
  const nmsg = h("input", { type: "number", min: 2, max: 30, value: 4 });
  const fa = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t))); fa.value = "pubblico";
  const msg = h("div");
  const avvia_ = async (ev) => {
    msg.replaceChildren(); const b = ev.currentTarget; b.disabled = true; b.textContent = "Dialogo in corso…";
    try {
      const r = await api("POST", "/gestione/dialoghi", { da_agente_id: Number(da.value), a_agente_id: Number(a2.value),
        argomento: arg.value, messaggi: Number(nmsg.value), fascia_dati: fa.value });
      arg.value = ""; await aggiornaFeed(); await apri(r.id);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false; b.textContent = "Avvia dialogo";
  };
  // limiti
  const lim = {}; const campoLim = (k, et, tipo) => { lim[k] = h("input", { type: tipo || "number" }); return h("label", {}, et, lim[k]); };
  const modelloLim = h("select", {}, stato.opzioni.modelli.map(m => h("option", { value: m.nome }, m.nome)));
  const msgLim = h("div");
  const blocLimiti = h("div", { class: "carta" },
    campoLim("dialoghi_max_messaggi", "Messaggi massimi per conversazione"),
    campoLim("dialoghi_max_domande", "Domande massime per compito (per agente)"),
    campoLim("dialoghi_budget_token_giornaliero", "Budget giornaliero di token per i dialoghi"),
    h("label", {}, "Modello predefinito per i dialoghi", modelloLim), msgLim,
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
      msgLim.replaceChildren();
      try {
        await api("PUT", "/gestione/dialoghi/limiti", { dialoghi_max_messaggi: Number(lim.dialoghi_max_messaggi.value),
          dialoghi_max_domande: Number(lim.dialoghi_max_domande.value),
          dialoghi_budget_token_giornaliero: Number(lim.dialoghi_budget_token_giornaliero.value), modello_dialogo_predefinito: modelloLim.value });
        msgLim.replaceChildren(avviso("Limiti salvati", "ok"));
      } catch (e) { msgLim.replaceChildren(avviso(e.message, "no")); }
    } }, "Salva limiti")));
  api("GET", "/gestione/dialoghi/limiti").then(l => { for (const k of Object.keys(lim)) lim[k].value = l[k]; modelloLim.value = l.modello_dialogo_predefinito; }).catch(() => {});

  return [
    h("h2", {}, "Dialoghi tra agenti"),
    h("p", { class: "sotto" }, "Il feed si aggiorna da solo. Gli agenti dialogano con un modello economico; il modello di lavoro resta per pensare e svolgere i compiti."),
    h("div", { class: "riga", style: "align-items:flex-start" },
      h("div", { style: "flex:2 1 380px" }, h("h3", {}, "Feed generale"), colonnaFeed),
      h("div", { style: "flex:1 1 280px" }, h("h3", {}, "Conversazioni"), colonnaConv)),
    dettaglio,
    h("h3", {}, "Avvia un dialogo"),
    h("div", { class: "carta" },
      h("div", { class: "riga" }, h("label", {}, "Parla per primo", da), h("label", {}, "Con", a2)),
      h("label", {}, "Argomento", arg),
      h("div", { class: "riga" }, h("label", {}, "Messaggi massimi", nmsg), h("label", {}, "Tipo di dati", fa)), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: avvia_ }, "Avvia dialogo"))),
    h("h3", {}, "Limiti"), blocLimiti,
  ];
}

// ---------- Chat ----------
function vistaChat() {
  const attivi = stato.agenti.filter(a => a.attivo);
  const scelta = h("select", {}, attivi.map(a => h("option", { value: a.id }, a.nome + " — " + a.ruolo)));
  const f = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t)));
  f.value = "pubblico";
  const testo = h("textarea", { placeholder: "Scrivi il messaggio…" });
  const msg = h("div");
  const invia = async (ev) => {
    msg.replaceChildren();
    const btn = ev.currentTarget; btn.disabled = true; btn.textContent = "Attendi…";
    try {
      const agente = attivi.find(a => a.id === Number(scelta.value));
      const r = await api("POST", "/agenti/" + scelta.value + "/chat", { messaggio: testo.value, fascia_dati: f.value });
      stato.conversazione.unshift({ agente: agente.nome, domanda: testo.value, risposta: r.risposta, t: r.token_input + r.token_output,
        usati: r.documenti_usati || [], esclusi: r.documenti_esclusi_per_riservatezza || [] });
      testo.value = ""; disegna();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); btn.disabled = false; btn.textContent = "Invia"; }
  };
  return [
    h("h2", {}, "Chat con gli agenti"),
    h("div", { class: "carta" },
      h("div", { class: "riga" }, h("label", {}, "Agente", scelta),
        h("label", {}, "Tipo di dati nel messaggio", f)),
      h("label", {}, "Messaggio", testo), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: invia }, "Invia"))),
    stato.conversazione.map(c => h("div", { class: "carta", style: "margin-top:12px" },
      h("div", { class: "sotto" }, "Tu → " + c.agente),
      h("div", { class: "risposta" }, c.domanda),
      h("div", { class: "sotto", style: "margin-top:10px" }, c.agente + " (" + c.t + " token)"),
      h("div", { class: "risposta" }, c.risposta),
      c.usati.length ? h("div", { class: "sotto", style: "margin-top:8px" }, "Documenti consultati: " + c.usati.join(", ")) : null,
      c.esclusi.length ? avviso("Non consultati per riservatezza: " + c.esclusi.join(", "), "avv") : null)),
  ];
}

// ---------- Briefing ----------
function vistaBriefing() {
  const contenitore = h("div");
  const carica = async () => {
    try {
      const lista = await api("GET", "/briefing");
      riempi(contenitore, lista.length ? lista.map(b => h("div", { class: "carta", style: "margin-top:12px" },
        h("div", { class: "nome" }, (b.tipo === "mattina" ? "Briefing del mattino" : "Briefing della sera") + " — " + new Date(b.creato_il).toLocaleString("it-IT")),
        h("div", { class: "risposta", style: "margin-top:8px" }, b.contenuto),
        b.letto ? null : h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { await api("POST", "/briefing/" + b.id + "/letto"); carica(); } }, "Segna come letto"))))
        : h("p", { class: "sotto" }, "Nessun briefing ancora."));
    } catch (e) { contenitore.replaceChildren(avviso(e.message, "no")); }
  };
  const genera = (tipo) => async (ev) => {
    const btn = ev.currentTarget; btn.disabled = true;
    try { await api("POST", "/briefing/genera?tipo=" + tipo); await carica(); } catch (e) { contenitore.prepend(avviso(e.message, "no")); }
    btn.disabled = false;
  };
  carica();
  return [h("h2", {}, "Briefing"),
    h("div", { class: "azioni", style: "margin-top:0" },
      h("button", { class: "p", onclick: genera("mattina") }, "Genera briefing del mattino"),
      h("button", { class: "s", onclick: genera("sera") }, "Genera briefing della sera")),
    contenitore];
}


// ---------- Documenti ----------
function modificaDocumento(d) {
  const nome = h("input", { type: "text", value: d.nome, maxlength: 200 });
  const fascia = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t)));
  fascia.value = d.fascia_dati;
  const tutti = h("input", { type: "checkbox" }); tutti.checked = d.per_tutti;
  const scelti = stato.agenti.filter(a => a.attivo).map(a => {
    const cb = h("input", { type: "checkbox", value: a.id }); cb.checked = d.agenti.includes(a.id); return [a, cb];
  });
  const msg = h("div");
  const chiudi = () => sfondo.remove();
  const salva = async () => {
    try {
      await api("PUT", "/gestione/documenti/" + d.id, { nome: nome.value, fascia_dati: fascia.value, per_tutti: tutti.checked,
        agenti: scelti.filter(([, cb]) => cb.checked).map(([a]) => a.id) });
      chiudi(); await ricarica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const sfondo = h("div", { class: "pannello-sfondo" },
    h("div", { class: "pannello", role: "dialog" },
      h("h2", {}, "Modifica documento"), h("label", {}, "Nome", nome), h("label", {}, "Riservatezza", fascia),
      h("label", { class: "spunta" }, tutti, "Consultabile da tutti gli agenti"),
      h("label", {}, "Oppure solo da questi agenti"),
      scelti.map(([a, cb]) => h("label", { class: "spunta" }, cb, a.nome)), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: salva }, "Salva"), h("button", { class: "s", onclick: chiudi }, "Annulla"))));
  document.body.append(sfondo);
}

// ---------- Sicurezza ----------
function vistaSicurezza() {
  return [
    h("h2", {}, "Sicurezza dei dati"),
    avviso("Qui dichiari le garanzie ottenute da ciascun fornitore AI. Attivale SOLO dopo averle configurate davvero (impostazioni di non conservazione dei dati e accordo sul trattamento dei dati, il DPA). Finché non sono entrambe attive, nessun dato interno o riservato viene inviato a quel fornitore.", "avv"),
    h("div", { class: "griglia" }, stato.opzioni.fornitori.map(f => {
      const nc = h("input", { type: "checkbox" }); nc.checked = f.non_conservazione_attiva;
      const dpa = h("input", { type: "checkbox" }); dpa.checked = f.dpa_firmato;
      const msg = h("div");
      const salva = async () => {
        try { await api("PUT", "/gestione/fornitori/" + f.nome, { non_conservazione_attiva: nc.checked, dpa_firmato: dpa.checked });
          await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      return h("div", { class: "carta" }, h("div", { class: "nome" }, f.nome),
        h("div", { class: "sotto" }, "Dati ammessi al massimo: " + ETICHETTA_FASCIA[f.fascia_dati_max]),
        h("label", { class: "spunta" }, nc, "Non conservazione dei dati attiva"),
        h("label", { class: "spunta" }, dpa, "DPA firmato"),
        msg, h("div", { class: "azioni" }, h("button", { class: "p", onclick: salva }, "Salva")));
    })),
  ];
}

// ---------- Avvio ----------
if (token) avvia(); else mostraAccesso();
