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
  el._falliti = 0; el._pausaFino = 0;
  el.replaceChildren(...[contenuto].flat(Infinity).filter(n => n !== null && n !== undefined && n !== false));
}

function messaggioErrore(d) {
  if (!d) return "Errore sconosciuto";
  if (typeof d.detail === "string") return d.detail;
  if (Array.isArray(d.detail)) return d.detail.map(x => (x.loc ? x.loc.slice(1).join(".") + ": " : "") + x.msg).join("; ");
  return "Errore sconosciuto";
}

const SCADENZA_LETTURA_MS = 30000;   // una lettura che non risponde entro 30 secondi si interrompe e lo si dice (scritture e caricamenti di file non hanno limite: possono durare)
function erroreApi(messaggio, categoria, percorso, codice) { const e = new Error(messaggio); e.categoria = categoria; e.percorso = percorso; e.codice = codice || 0; return e; }
async function api(metodo, percorso, corpo, opzioni) {
  const modulo = corpo instanceof FormData;
  const ctl = new AbortController();
  const limite = (opzioni && opzioni.scadenzaMs) || ((metodo === "GET" || percorso.startsWith("/login")) ? SCADENZA_LETTURA_MS : 0);
  const scadenza = limite ? setTimeout(() => ctl.abort(), limite) : null;
  const vistaAllora = typeof etichettaVista === "function" ? etichettaVista() : "";   // l'errore va alla pagina che ha chiesto, non a quella aperta dopo
  const base = percorso.split("?")[0];
  const t0 = Date.now();
  let r;
  try {
    r = await fetch(percorso, {
      method: metodo,
      headers: { ...(modulo ? {} : { "Content-Type": "application/json" }), ...(token ? { Authorization: "Bearer " + token } : {}) },
      body: corpo === undefined ? undefined : (modulo ? corpo : JSON.stringify(corpo)),
      signal: ctl.signal,
    });
  } catch (e) {
    if (e && e.name === "AbortError") { segnalaErrore(vistaAllora, "timeout", base, Date.now() - t0); throw erroreApi("Il server non ha risposto in tempo (" + base + "). Riprova tra qualche secondo.", "timeout", base); }
    segnalaErrore(vistaAllora, "rete", base, Date.now() - t0);
    throw erroreApi("Connessione al server non riuscita. Controlla la rete e riprova.", "rete", base);
  } finally { if (scadenza) clearTimeout(scadenza); }
  let dati = null;
  try { dati = await r.json(); } catch (e) { /* risposta vuota */ }
  if (r.status === 401 && percorso !== "/login" && percorso !== "/v1/accesso") { esci(); throw erroreApi("Sessione scaduta: rientra", "sessione", base, 401); }
  if (!r.ok) {
    const cat = r.status >= 500 ? "server" : "validazione";
    segnalaErrore(vistaAllora, cat, base, Date.now() - t0);
    const testo = (dati && (typeof dati.detail === "string" || Array.isArray(dati.detail))) ? messaggioErrore(dati) : (r.status >= 500 ? "Il server ha avuto un problema (codice " + r.status + ")." : "Richiesta non accettata (codice " + r.status + ").");
    throw erroreApi(testo, cat, base, r.status);
  }
  return dati;
}

// Un errore di caricamento conta una volta sola per episodio (stessa pagina, stesso tipo, stesso indirizzo entro un minuto): i ricaricamenti automatici non lo moltiplicano.
const ultimiErrori = new Map();
const _contatoreVisto = {};
function segnalaErrore(vista, categoria, percorso, durataMs) {
  if (typeof registraUso !== "function") return;
  const chiave = vista + "|" + categoria + "|" + percorso, ora = Date.now();
  if (ultimiErrori.get(chiave) && ora - ultimiErrori.get(chiave) < 60000) return;
  ultimiErrori.set(chiave, ora);
  registraUso(vista, "errore", { categoria, componente: componenteDa(percorso), durata_ms: Math.min(Math.round(durataMs || 0), 600000) });
}
// Il componente che ha dato errore e' l'indirizzo della richiesta senza identificativi: "/gestione/agenti/12" diventa "/gestione/agenti/:x". Mai parametri, mai testi.
function componenteDa(percorso) {
  return String(percorso || "").split("?")[0].toLowerCase().split("/").filter(Boolean).slice(0, 5).map(s => /^[a-z_-]{1,24}$/.test(s) ? s : ":x").join("/").replace(/^/, "/").slice(0, 100);
}

// Banner unico per un riquadro che non si carica: cosa e' successo, cosa fare, Riprova, contatore dei tentativi. Con tieni=true i dati gia' mostrati restano sotto il banner.
// Esito di "Riprova": se subito dopo compare di nuovo un errore e' fallito, altrimenti riuscito. Si registrano solo pagina, componente, esito e durata.
function provaDiNuovo(host, e, riprova) {
  const lavoro = { t0: Date.now(), vista: typeof etichettaVista === "function" ? etichettaVista() : "x", componente: componenteDa(e && e.percorso), categoria: e && e.categoria };
  host._riprovando = lavoro;
  const chiudi = (esito) => { if (host._riprovando === lavoro) { host._riprovando = null; if (typeof registraUso === "function") registraUso(lavoro.vista, "riprova", { esito, componente: lavoro.componente, categoria: ["rete", "timeout", "server", "validazione"].includes(lavoro.categoria) ? lavoro.categoria : undefined, durata_ms: Math.min(Date.now() - lavoro.t0, 600000) }); } };
  Promise.resolve().then(() => riprova()).catch(() => chiudi("fallito")).then(() => setTimeout(() => chiudi("riuscito"), 1500));
}
function mostraErrore(host, e, riprova, tieni) {
  if (host._riprovando) { const l = host._riprovando; host._riprovando = null; if (typeof registraUso === "function") registraUso(l.vista, "riprova", { esito: "fallito", componente: l.componente, categoria: ["rete", "timeout", "server", "validazione"].includes(l.categoria) ? l.categoria : undefined, durata_ms: Math.min(Date.now() - l.t0, 600000) }); }
  host._falliti = (host._falliti || 0) + 1;
  host._pausaFino = Date.now() + Math.min(60000, 5000 * Math.pow(2, host._falliti - 1));   // gli aggiornamenti automatici rallentano: 5 s, 10 s, 20 s... fino a 1 minuto
  const cat = e && e.categoria;
  const cosa = cat === "timeout" || cat === "rete" ? "" : cat === "server" ? "Riprova; se succede ancora, segnalalo a chi gestisce il server." : cat === "sessione" ? "Rientra con la tua password." : "Controlla i dati e riprova.";
  const bottone = riprova ? h("button", { class: "s", type: "button", onclick: (ev) => { ev.currentTarget.disabled = true; host._pausaFino = 0; provaDiNuovo(host, e, riprova); } }, "Riprova") : null;
  const banner = h("div", { class: "messaggio no banner-errore", role: "alert" },
    h("div", {}, (e && e.message) || "Errore"), h("div", { class: "sotto" }, [cosa, host._falliti > 1 ? host._falliti + " tentativi non riusciti" : ""].filter(Boolean).join(" · ")), bottone);
  const vecchio = host.querySelector(":scope > .banner-errore");
  if (tieni && host.children.length && !(host.children.length === 1 && vecchio)) { if (vecchio) vecchio.replaceWith(banner); else host.prepend(banner); }
  else host.replaceChildren(banner);
}
const inPausa = (host) => !!(host && host._pausaFino && host._pausaFino > Date.now());

// Aggiornamento automatico sicuro: si ferma quando il riquadro sparisce o la scheda e' nascosta, non si sovrappone, e dopo un errore aspetta di piu'.
function ticker(host, fn, ms) {
  let occupato = false;
  const t = setInterval(async () => {
    if (!document.body.contains(host)) { clearInterval(t); return; }
    if (document.hidden || occupato || inPausa(host)) return;
    occupato = true;
    try { await fn(); } finally { occupato = false; }
  }, ms);
  return t;
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
      msg, h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Entra"), (typeof Passkey !== "undefined") ? Passkey.pulsanteAccesso(msg) : null))));
  if (errore) msg.replaceChildren(avviso(errore, "no"));
}

// ---------- Struttura ----------
const VISTE = [["dashboard", "Plancia"], ["chat", "Chat"], ["task", "Task"], ["riunioni", "Riunioni"], ["progetti", "Progetti"], ["documenti", "Documenti"], ["crm", "CRM"], ["social", "Social"], ["finestre", "Finestre"], ["briefing", "Briefing"], ["agenti", "Agenti"], ["ginnasio", "Ginnasio"], ["impostazioni", "Impostazioni"]];
// il menu laterale: dopo queste voci comincia un nuovo gruppo con la sua intestazione
const GRUPPO_MENU = { progetti: "Lavoro", agenti: "Laboratorio" };
const ICONE = { finestre: "M3 5h18v14H3zM3 9h18M7 7h.01", dashboard: "M4 11l8-7 8 7v9H4z", chat: "M4 5h16v11H9l-5 4z", task: "M5 12l4 4 10-10", riunioni: "M12 3a3 3 0 013 3v5a3 3 0 01-6 0V6a3 3 0 013-3zM5 11a7 7 0 0014 0M12 18v3",
  progetti: "M3 7h6l2 2h10v10H3z", documenti: "M7 3h8l4 4v14H7z", crm: "M9 4.5a3.5 3.5 0 110 7 3.5 3.5 0 010-7zM3 20c0-3.5 3-6 6-6s6 2.5 6 6M16 5a3.5 3.5 0 010 7", social: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  briefing: "M5 4h14v16H5zM9 8h6M9 12h6M9 16h3", agenti: "M12 4a4 4 0 110 8 4 4 0 010-8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7", ginnasio: "M3 9l9-5 9 5-9 5zM7 11.5V16c0 1.5 2.2 3 5 3s5-1.5 5-3v-4.5",
  impostazioni: "M12 9a3 3 0 110 6 3 3 0 010-6zM12 3v3M12 18v3M3 12h3M18 12h3", iniziative: "M5 12l4 4 10-10", percorsi: "M3 7h6l2 2h10v10H3z", account: "M12 4a4 4 0 110 8 4 4 0 010-8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" };
function icona(id) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "1.7"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round"); s.setAttribute("aria-hidden", "true"); s.setAttribute("class", "ico");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", ICONE[id] || ICONE.dashboard); s.append(p);
  return s;
}
const GRUPPI_IMP = [["Io e account", ["profilo", "voce", "app"]], ["Organizzazione", ["struttura", "utenti", "reparti", "tavoli", "cerimoniere", "quando", "smistamento"]],
  ["Collegamenti", ["collegamenti", "connessioni", "siti", "canali", "social", "monitorsocial", "archivio", "percorsi"]], ["Conoscenza e formazione", ["biblioteca", "studi", "memoria", "imprese", "noteaurora", "miglioramenti", "dossier"]],
  ["Controllo e sicurezza", ["sicurezza", "registro", "sentinelle", "salute", "sandbox"]], ["Sistema", ["aggiornamenti", "misure", "spesareparti", "dipendenze", "diagnostica", "esempio", "memoriavett", "giro", "contenuti", "sistema"]]];
const VISTE_COLLABORATORE = [["task", "Task"], ["progetti", "Progetti"], ["iniziative", "Iniziative"], ["percorsi", "Percorsi"], ["chat", "Chat"], ["account", "Il mio account"]];
const SEZIONI_IMPOSTAZIONI = [["profilo", "Il mio profilo"], ["struttura", "Aziende e dipartimenti"], ["collegamenti", "Collegamenti (Google, posta)"], ["connessioni", "Connessioni a siti e app"], ["siti", "Siti e hosting (chiavi)"],
  ["canali", "Canali (Telegram)"], ["social", "Social"], ["monitorsocial", "Profili social monitorati"], ["archivio", "Archivio NAS"], ["percorsi", "Percorsi"], ["utenti", "Utenti e collaboratori"], ["aggiornamenti", "Aggiornamenti"], ["sicurezza", "Sicurezza e garanzie"], ["registro", "Registro decisioni"], ["memoria", "Memoria di lavoro"], ["imprese", "Schede d'impresa"], ["tavoli", "Tavoli di lavoro"], ["noteaurora", "Note di Aurora"], ["miglioramenti", "Miglioramento degli agenti"], ["spesareparti", "Spesa per reparto"], ["dipendenze", "Controllo delle librerie"], ["diagnostica", "Diagnostica (log scaricabile)"], ["esempio", "Impara da un esempio"], ["memoriavett", "Memoria condivisa (vettoriale)"], ["giro", "Giro di aggiornamento"], ["contenuti", "Contenuti: brief e stili di montaggio"], ["dossier", "Dossier e fiducia"], ["biblioteca", "Biblioteca (Padre Casati)"], ["studi", "Studi di Padre Casati"], ["cerimoniere", "Cerimoniere"], ["quando", "Quando lavora"], ["smistamento", "Smistamento e consegne"], ["reparti", "Reparti pronti"], ["sandbox", "Sandbox del codice"], ["salute", "Salute degli agenti"], ["sentinelle", "Sentinelle e casi di prova"], ["app", "App su smartphone"], ["voce", "Voce"], ["misure", "Consumi (dove vanno i token)"], ["sistema", "Backup e costi"]];

function vai(vista, sezione) { if (_contatoreVisto[vista] && stato.novita && stato.novita[vista] > 0) registraUso(etichettaVista(), "contatore_aperto", { elemento: vista }); segnaVisto(vista); if (stato.ruolo === "titolare" && vista === "email") { sezione = "collegamenti"; vista = "impostazioni"; } if (stato.ruolo === "titolare" && (vista === "percorsi" || vista === "iniziative")) { sezione = vista; vista = "impostazioni"; } if (vista !== "chat") { try { Voce.fermaTutto(); } catch (e) { /* la voce non deve mai impedire di cambiare pagina */ } } stato.percorsoAperto = null; stato.vista = vista; if (sezione) stato.sezione = sezione; disegna(); }

function cornice(contenuto) {
  if (window.name === "opifex-organigramma" || location.hash === "#organigramma") {   // finestra a parte: solo l'organigramma
    radice.replaceChildren(h("main", { class: "largo org-finestra" }, contenuto)); return;
  }
  const soloPC = matchMedia("(max-width:800px), (pointer:coarse)").matches;   // le Finestre servono il PC: da telefono non compaiono
  const voci = (stato.ruolo === "titolare" ? VISTE : VISTE_COLLABORATORE).filter(v => !(soloPC && v[0] === "finestre"));
  const attiva = (id) => stato.vista === id || (id === "dashboard" && (stato.vista === "richieste" || stato.vista === "organigramma")) || (id === "progetti" && stato.vista === "progetto") || (id === "crm" && stato.vista === "contatto");
  const nav = [];
  for (const [id, nome] of voci) {
    if (stato.ruolo === "titolare" && GRUPPO_MENU[id]) nav.push(h("div", { class: "bt-gruppo" }, GRUPPO_MENU[id]));
    nav.push(h("button", { "data-uso": "menu-" + id, class: attiva(id) ? "attivo" : "", "aria-current": attiva(id) ? "page" : null, onclick: () => vai(id) },
      icona(id), h("span", { class: "bt-et" }, nome + (id === "dashboard" && stato.richieste ? " (" + stato.richieste + ")" : "")),
      id === "progetti" && stato.ruolo === "titolare" ? h("span", { id: "badge-progetti", class: "badge-chat", title: "Domande degli agenti e squadre da approvare", style: (stato.richieste + (stato.squadreAttesa || 0)) ? "" : "display:none" }, String((stato.richieste || 0) + (stato.squadreAttesa || 0))) : null,
      (id === "ginnasio" || id === "documenti" || id === "progetti") && stato.ruolo === "titolare" ? h("span", { id: "novita-" + id, class: "badge-chat badge-novita", title: "Novità dall'ultima volta che hai guardato", style: stato.novita && stato.novita[id] ? "" : "display:none" }, stato.novita && stato.novita[id] ? String(stato.novita[id]) : "") : null,
      id === "chat" ? h("span", { id: "badge-chat", class: "badge-chat", style: stato.chatNonLetti ? "" : "display:none" }, stato.chatNonLetti ? String(stato.chatNonLetti) : "") : null));
  }
  radice.replaceChildren(
    h("header", {}, h("h1", {}, "Opifex", h("small", {}, "la bottega degli agenti")),
      h("nav", { "aria-label": "Menu principale" }, nav),
      h("div", { class: "bt-piede" }, h("button", { class: "s", onclick: esci }, "Esci"), h("button", { class: "bt-riduci", type: "button", title: "Riduci o allarga il menu", "aria-label": "Riduci o allarga il menu", onclick: () => Vetro.riduciMenu() }, "⇔"), h("span", { class: "bt-ver" }, "2.0"))),
    h("main", { class: stato.vista === "dashboard" || stato.vista === "chat" || stato.vista === "organigramma" ? "largo" : "" }, contenuto));
}

async function avvia() {
  try {
    const io = await api("GET", "/io");
    stato.ruolo = io.ruolo_globale; stato.nome = io.nome || "";
    await Vetro.carica();
    ripristinaVista();
    if (window.name === "opifex-organigramma" || location.hash === "#organigramma") stato.vista = "organigramma";
    avviaConteggioChat(); avviaUso();
    if (stato.ruolo !== "titolare") {   // il collaboratore vede solo la chat con gli agenti delle sue divisioni
      stato.agenti = await api("GET", "/agenti");
      if (!VISTE_COLLABORATORE.some(([id]) => id === stato.vista)) stato.vista = "chat";
      return disegna();
    }
    const [agenti, opzioni, connessioni, documenti, cont] = await Promise.all([
      api("GET", "/gestione/agenti"), api("GET", "/gestione/opzioni"), api("GET", "/gestione/connessioni"),
      api("GET", "/gestione/documenti"), api("GET", "/gestione/richieste/conteggio")]);
    Object.assign(stato, { agenti, opzioni, connessioni, documenti, richieste: cont.aperte, squadreAttesa: cont.squadre || 0 });
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
  try { const c = await api("GET", "/gestione/richieste/conteggio"); stato.richieste = c.aperte; stato.squadreAttesa = c.squadre || 0; } catch (e) { /* ignora */ }
  disegna();
}

function disegna() {
  if (stato.vista === "dialoghi") stato.vista = "chat";
  if (stato.timer) { clearInterval(stato.timer); stato.timer = null; }
  if (stato.attesa) { clearTimeout(stato.attesa); stato.attesa = null; }
  if (stato.timer2) { clearInterval(stato.timer2); stato.timer2 = null; }
  if (typeof registraUso === "function") { const e = etichettaVista(); if (e !== stato.ultimaEtichetta) { chiudiVistaUso(stato.ultimaEtichetta); stato.ultimaEtichetta = e; registraUso(e, "vista"); } ricordaVista(); }
  const vista = { dashboard: vistaDashboard, task: vistaTask, impostazioni: vistaImpostazioni, account: vistaAccount, progetti: (stato.ruolo === "titolare" ? vistaProgetti : vistaProgettiMiei), progetto: vistaProgetto, contatto: vistaContatto, agenti: vistaAgenti, ginnasio: vistaGinnasio, documenti: vistaDocumenti, richieste: vistaRichieste, dialoghi: vistaChat, chat: vistaChat, percorsi: vistaPercorsi, social: vistaSocial, finestre: vistaFinestre, email: vistaEmail, riunioni: vistaRiunioni, crm: vistaCrm, iniziative: vistaIniziative, briefing: vistaBriefing, organigramma: vistaOrganigrammaPagina }[stato.vista] || vistaDashboard;
  let contenuto;
  try { contenuto = vista(); }
  catch (e) {   // una schermata che si rompe non deve bloccare il menu: si mostra l'errore e si puo' andare altrove
    if (typeof registraUso === "function") registraUso(etichettaVista(), "errore", { categoria: "interfaccia" });
    if (stato.vista === "impostazioni") stato.sezione = "profilo";
    contenuto = h("div", { class: "carta" }, avviso("Questa schermata non si è aperta (" + (e && e.message ? e.message : "errore") + "). Scegli un'altra voce dal menu: il resto funziona.", "no"),
      h("button", { class: "s", type: "button", onclick: () => vai("dashboard") }, "Torna alla plancia"));
  }
  cornice(contenuto);
}

// I fornitori fatturano in dollari: si mostrano in euro con il cambio impostato in Backup e costi.
function euro(usd) { const c = (stato.opzioni && stato.opzioni.cambio_eur) || 0.92; const v = Number(usd) * c; return "€ " + v.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: v < 1 ? 3 : 2 }); }

const ETICHETTA_FASCIA = { pubblico: "Solo dati pubblici", interno: "Dati interni", riservato: "Dati riservati" };

// ---------- Agenti ----------
function vistaAgenti() {
  const gruppi = new Map();
  for (const a of stato.agenti) {
    const g = a.categoria === "sentinella" ? "Agenti sentinella" : a.categoria === "referente" ? "Referente" : (a.divisione || "Agenti di sistema");
    if (!gruppi.has(g)) gruppi.set(g, []);
    gruppi.get(g).push(a);
  }
  const garanzie = (stato.opzioni.fornitori || []).filter(f => !(f.non_conservazione_attiva && f.dpa_firmato));
  return [
    h("div", { class: "riga", style: "align-items:center" },
      h("h2", {}, "Agenti"),
      h("div", { style: "text-align:right;flex:0 0 auto;display:flex;gap:8px" },
        h("button", { class: "s", title: "Scarica l'elenco di tutti gli agenti con compito e istruzioni", onclick: async () => {
          try { const r = await fetch("/gestione/competenze/esporta", { headers: { Authorization: "Bearer " + token } }); if (!r.ok) throw new Error("Download non riuscito");
            const l = h("a", { href: URL.createObjectURL(await r.blob()), download: "agenti-competenze.md" }); document.body.append(l); l.click(); l.remove(); } catch (e) { alert(e.message); } } }, "Scarica competenze"),
        h("button", { class: "p", onclick: () => modulo(null) }, "+ Nuovo agente"))),
    garanzie.length ? avviso("I dati interni e riservati restano bloccati verso: " +
      garanzie.map(f => f.nome).join(", ") + " (mancano le garanzie di non conservazione/DPA). Gli agenti lavorano solo su dati pubblici.", "avv") : null,
    codaEmailUscita(),
    (() => {
      const chiusi = (() => { try { return new Set(JSON.parse(localStorage.getItem("agenti_chiusi") || "[]")); } catch (e) { return new Set(); } })();
      const salva = () => { try { localStorage.setItem("agenti_chiusi", JSON.stringify([...chiusi])); } catch (e) { /* facoltativo */ } };
      const sezioni = [...gruppi].map(([nome, lista]) => {
        const griglia = h("div", { class: "griglia" }, lista.map(carta));
        const freccia = h("span", { class: "gruppo-freccia", "aria-hidden": "true" });
        const testa = h("button", { type: "button", class: "gruppo-testa", "aria-expanded": "true" }, freccia, h("span", { class: "gruppo-nome" }, nome), h("span", { class: "gruppo-conta" }, String(lista.length)));
        const imposta = (chiuso) => { griglia.hidden = chiuso; testa.setAttribute("aria-expanded", chiuso ? "false" : "true"); freccia.textContent = chiuso ? "▸" : "▾"; };
        testa.onclick = () => { const c = !griglia.hidden; imposta(c); c ? chiusi.add(nome) : chiusi.delete(nome); salva(); };
        imposta(chiusi.has(nome));
        return { nome, griglia, imposta, nodo: h("section", { class: "gruppo-agenti" }, testa, griglia) };
      });
      const tutti = (chiudi) => { sezioni.forEach(x => { x.imposta(chiudi); chiudi ? chiusi.add(x.nome) : chiusi.delete(x.nome); }); salva(); };
      const blocco = h("div", {}, h("div", { class: "gruppo-comandi" }, h("button", { class: "s", type: "button", onclick: () => tutti(true) }, "Chiudi tutti"), h("button", { class: "s", type: "button", onclick: () => tutti(false) }, "Apri tutti")), sezioni.map(x => x.nodo));
      riempiExtraAgenti(blocco); riempiVociAgenti(blocco); avviaStatoAgenti(blocco); return blocco;
    })(),
  ];
}

// Email preparate dagli agenti in attesa di approvazione (e ultime inviate / in errore)
function codaEmailUscita() {
  const box = h("div");
  const carica = async () => {
    let lista = [];
    try { lista = await api("GET", "/gestione/email-uscita"); } catch (e) { return; }
    const attesa = lista.filter(x => x.stato === "da_approvare" || x.stato === "errore");
    const recenti = lista.filter(x => x.stato === "inviata" || x.stato === "rifiutata").slice(0, 8);
    if (!attesa.length && !recenti.length) { box.replaceChildren(); return; }
    const msg = h("div");
    const scheda = (x) => {
      const dest = h("input", { value: x.destinatari, style: "width:100%" }), ogg = h("input", { value: x.oggetto, style: "width:100%" }), testo = h("textarea", { style: "min-height:110px;width:100%" }, x.testo);
      const agisci = async (azione, b) => { b.disabled = true; msg.replaceChildren();
        try {
          if (azione === "approva") await api("PUT", "/gestione/email-uscita/" + x.id, { destinatari: dest.value, oggetto: ogg.value, testo: testo.value });
          await api("POST", "/gestione/email-uscita/" + x.id + "/decisione", { azione }); carica();
        } catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } };
      const bi = h("button", { class: "p", type: "button", onclick: () => agisci("approva", bi) }, x.stato === "errore" ? "Riprova a inviare" : "Invia");
      const bs = h("button", { class: "s", type: "button", onclick: () => agisci("rifiuta", bs) }, "Scarta");
      return h("div", { class: "carta", style: "margin-top:10px" },
        h("div", { class: "sotto" }, (x.agente ? x.agente + " · " : "") + (x.mittente ? "da " + x.mittente + " · " : "") + new Date(x.creata_il).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })),
        x.stato === "errore" ? avviso("Invio non riuscito: " + (x.errore || "errore"), "no") : null,
        h("label", {}, "A", dest), h("label", {}, "Oggetto", ogg), h("label", {}, "Testo", testo), h("div", { class: "azioni" }, bi, bs));
    };
    riempi(box, [h("h3", {}, "Email da approvare" + (attesa.length ? " (" + attesa.length + ")" : "")),
      attesa.length ? attesa.map(scheda) : h("p", { class: "sotto" }, "Nessuna email in attesa."), msg,
      recenti.length ? h("details", { style: "margin-top:10px" }, h("summary", {}, "Ultime email inviate o scartate"),
        recenti.map(x => h("div", { class: "sotto" }, (x.stato === "inviata" ? "Inviata" : "Scartata") + " · " + x.destinatari + " · «" + x.oggetto + "»" + (x.agente ? " · " + x.agente : "") + (x.diretta ? " · diretta" : "")))) : null]);
  };
  carica();
  return box;
}

// Schede (tab) dentro i moduli lunghi: tutti i campi restano nel documento, se ne vede una sezione alla volta
function schede(elenco, iniziale) {
  const corpi = elenco.map(([nome, figli], i) => h("div", { class: "scheda-corpo", role: "tabpanel", hidden: i !== (iniziale || 0) }, figli));
  const bott = elenco.map(([nome], i) => h("button", { type: "button", role: "tab", class: "scheda-tab" + (i === (iniziale || 0) ? " attivo" : ""), "aria-selected": i === (iniziale || 0) ? "true" : "false",
    onclick: () => { bott.forEach((b, j) => { b.classList.toggle("attivo", i === j); b.setAttribute("aria-selected", i === j ? "true" : "false"); corpi[j].hidden = i !== j; }); } }, nome));
  return h("div", { class: "schede" }, h("div", { class: "scheda-barra", role: "tablist" }, bott), corpi);
}

function carta(a) {
  return h("div", { class: "carta agente" + (a.attivo ? "" : " spento"), tabindex: 0, role: "button",
      onclick: () => modulo(a), onkeydown: (e) => { if (e.key === "Enter") modulo(a); } },
    h("div", { class: "nome" }, a.nome + (a.livello_formazione ? " (" + a.livello_formazione + ")" : "")),
    h("div", { class: "sotto" }, a.ruolo),
    h("div", {},
      h("span", { class: "etichetta " + (a.attivo ? "ok" : "no") }, a.attivo ? "Attivo" : "Spento"),
      h("span", { class: "etichetta" }, a.modello),
      a.accesso_web ? null : h("span", { class: "etichetta avv" }, "Senza web"),
      a.connessioni.length ? h("span", { class: "etichetta" }, a.connessioni.length + " conn.") : null),
    h("div", { class: "sotto" }, "Questo mese: " + a.token_mese.toLocaleString("it-IT") + " token"),
    h("div", { class: "agente-stato", "data-id": String(a.id), "aria-live": "off", onclick: (e) => e.stopPropagation(), onkeydown: (e) => e.stopPropagation() }),
    h("div", { class: "agente-voce-posto", "data-id": String(a.id), onclick: (e) => e.stopPropagation(), onkeydown: (e) => e.stopPropagation() }),
    h("div", { class: "agente-extra-posto", "data-id": String(a.id) }));
}

function sezioneProfiloAlto(a) {
  const esito = h("div");
  const b = h("button", { class: "s", type: "button", onclick: async () => {
    b.disabled = true; esito.replaceChildren();
    try {
      const r = await api("POST", "/gestione/agenti/" + a.id + "/profilo-alto");
      esito.replaceChildren(avviso("Profilo alto attivo: modello " + r.modello + ", fino a " + r.passi + " passaggi, ragionamento alto, metodo di lavoro aggiunto." + (r.avviso ? " " + r.avviso : ""), r.avviso ? "avv" : "ok"));
    } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false;
  } }, "Attiva profilo alto");
  const r0 = h("button", { class: "s", type: "button", onclick: async () => {
    try { await api("DELETE", "/gestione/agenti/" + a.id + "/profilo-alto"); esito.replaceChildren(avviso("Ripristinato come prima.", "ok")); } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
  } }, "Ripristina");
  return h("div", {}, h("h3", {}, "Profilo alto"), h("p", { class: "aiuto" }, "Per i lavori difficili (montaggio, consegne): usa il modello migliore, fino a 40 passaggi con gli strumenti, ragionamento alto e un metodo scritto (piano, verifica, nuovi tentativi). Costa di più in token: usalo solo dove serve."), b, " ", r0, esito);
}

function sezioneProva(a) {
  const esito = h("div");
  const b = h("button", { class: "s", type: "button", onclick: async () => {
    b.disabled = true; b.textContent = "Provo…"; esito.replaceChildren();
    try {
      const r = await api("POST", "/gestione/agenti/" + a.id + "/prova");
      esito.replaceChildren(r.riuscita
        ? h("div", {}, avviso("Risponde (" + r.secondi + " s, " + r.token_output + " token in uscita).", "ok"), h("div", { class: "carta", style: "white-space:pre-wrap" }, r.risposta))
        : avviso(r.errore || (r.risposta + (r.dettagli ? " [" + JSON.stringify(r.dettagli) + "]" : "")), "no"));
    } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false; b.textContent = "Prova agente";
  } }, "Prova agente");
  return h("div", {}, h("h3", {}, "Prova"), h("p", { class: "aiuto" }, "Manda una domanda semplice e mostra la risposta com'è, con tempi e consumi. Se è vuota, ne spiega la causa."), b, esito);
}

function modulo(a) {
  const nuovo = a === null;
  const d = a || { nome: "", ruolo: "", divisione_id: null, superiore_id: null, livello: "operativo",
    modello: stato.opzioni.modelli[0]?.nome, istruzioni: "", fascia_dati_max: "pubblico", max_token_risposta: 16000,
    budget_token_mensile: null, accesso_web: true, siti_consentiti: [], max_ricerche: 3, attivo: true, connessioni: [], aziende: [] };

  const nome = h("input", { type: "text", value: d.nome, maxlength: 60 });
  const ruolo = h("input", { type: "text", value: d.ruolo, maxlength: 120, placeholder: "Es. Cerca nuovi bandi" });
  const rimanda = h("input", { type: "text", value: d.rimanda_a || "", maxlength: 300, placeholder: "Es. Per i testi chiedi a Sofia; per i contatti al CRM" });
  const istr = h("textarea", { style: "min-height:180px" }); istr.value = d.istruzioni;
  const div = h("select", {}, h("option", { value: "" }, "Nessuna (agente di sistema)"),
    stato.opzioni.divisioni.map(x => h("option", { value: x.id }, x.nome)));
  div.value = d.divisione_id ?? "";
  const sup = h("select", {}, h("option", { value: "" }, "Nessuno"),
    stato.agenti.filter(x => !a || x.id !== a.id).map(x => h("option", { value: x.id }, x.etichetta || (x.nome + " (" + x.ruolo + ")"))));
  sup.value = d.superiore_id ?? "";
  const livello = h("select", {}, [["operativo", "Operativo"], ["manager", "Manager"], ["referente", "Referente"], ["sentinella", "Sentinella (osserva e segnala)"]]
    .map(([v, t]) => h("option", { value: v }, t)));
  livello.value = d.categoria === "sentinella" ? "sentinella" : d.livello;
  const modello = h("select", {}, stato.opzioni.modelli.map(m => h("option", { value: m.nome }, m.nome + " — " + m.fornitore)));
  modello.value = d.modello;
  const fascia = h("select", {}, Object.entries({ pubblico: "Solo dati pubblici", interno: "Dati pubblici e interni", riservato: "Tutti i dati (anche riservati)" }).map(([v, t]) => h("option", { value: v }, t)));
  fascia.value = d.fascia_dati_max;
  const tetto = h("input", { type: "number", min: 100, max: 64000, value: d.max_token_risposta });
  const sforzo = h("select", {}, [["", "Predefinito del modello"], ["low", "Basso"], ["medium", "Medio"], ["high", "Alto"]].map(([v, t]) => h("option", { value: v }, t))); sforzo.value = d.sforzo || "";
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
  const vedeTutto = h("input", { type: "checkbox" }); vedeTutto.checked = !!d.vede_tutto;
  const gmailSel = h("select", {}, h("option", { value: "" }, "Nessuna casella"),
    (stato.opzioni.account_gmail || []).map(g => h("option", { value: g.id }, g.etichetta + " — " + g.email)));
  gmailSel.value = d.gmail_account_id || "";
  const OPZ_INVIO = [["bozze", "Solo bozze", "legge e prepara bozze, non invia"], ["approvazione", "Invio con la mia approvazione", "prepara l'email e resta in coda «Email da approvare»: parte solo quando la approvi"], ["diretto", "Invio diretto", "l'email parte subito, senza approvazione (massimo 5 per richiesta)"]];
  const gruppoInvio = "invio-" + (d.id || "nuovo");
  const radiInvio = OPZ_INVIO.map(([v, et, aiuto]) => { const r = h("input", { type: "radio", name: gruppoInvio, value: v }); r.checked = (d.invio_posta || "bozze") === v;
    return h("label", { class: "interruttore", style: "cursor:pointer" }, r, h("span", {}, h("b", {}, et), " — " + aiuto)); });
  const invioScelto = () => (radiInvio.map(l => l.querySelector("input")).find(r => r.checked) || { value: "bozze" }).value;
  const socialAttivo = h("input", { type: "checkbox" }); socialAttivo.checked = !!d.social_attivo;
  const emailAttivo = h("input", { type: "checkbox" }); emailAttivo.checked = !!d.email_attivo;
  const crmAttivo = h("input", { type: "checkbox" }); crmAttivo.checked = !!d.crm_attivo;
  const crmNominativo = h("input", { type: "checkbox" }); crmNominativo.checked = !!d.crm_nominativo;
  const canvaAttivo = h("input", { type: "checkbox" }); canvaAttivo.checked = !!d.canva_attivo;
  const finestreAttivo = h("input", { type: "checkbox" }); finestreAttivo.checked = !!d.finestre_attivo;
  const finestreSiti = h("textarea", { rows: 3, placeholder: "Siti in cui può cliccare, scrivere e scaricare (uno per riga, es. chatgpt.com). Vuoto = solo lettura delle schede condivise." }); finestreSiti.value = (d.finestre_siti || []).join("\n");
  const archivioAttivo = h("input", { type: "checkbox" }); archivioAttivo.checked = !!d.archivio_attivo;
  const driveAttivo = h("input", { type: "checkbox" }); driveAttivo.checked = !!d.drive_attivo;
  const conn = stato.connessioni.map(c => {
    const cb = h("input", { type: "checkbox", value: c.id }); cb.checked = d.connessioni.includes(c.id);
    return [c, cb];
  });
  const azCb = (stato.opzioni.aziende || []).map(z => {
    const cb = h("input", { type: "checkbox", value: z.id }); cb.checked = (d.aziende || []).includes(z.id);
    return [z, cb];
  });
  // --- fasi di lavoro (facoltative): se ci sono, il lavoro viene svolto una fase alla volta nell'ordine indicato
  const fasi = (d.fasi || []).map(f => ({ titolo: f.titolo, istruzioni: f.istruzioni || "", approvazione: f.approvazione !== false, parere_superiore: !!f.parere_superiore }));
  const contFasi = h("div");
  const disegnaFasi = () => {
    riempi(contFasi, [
      fasi.length ? null : h("p", { class: "aiuto" }, "Nessuna fase: l'agente lavora liberamente, seguendo solo il prompt."),
      fasi.map((f, i) => {
        const t = h("input", { type: "text", maxlength: 120, value: f.titolo, placeholder: "Titolo della fase, es. Proposte generali" });
        t.addEventListener("input", () => { f.titolo = t.value; });
        const ist = h("textarea", { style: "min-height:90px", placeholder: "Cosa deve fare in questa fase e cosa deve consegnare" }); ist.value = f.istruzioni;
        ist.addEventListener("input", () => { f.istruzioni = ist.value; });
        const ap = h("input", { type: "checkbox" }); ap.checked = f.approvazione; ap.addEventListener("change", () => { f.approvazione = ap.checked; });
        const pa = h("input", { type: "checkbox" }); pa.checked = f.parere_superiore; pa.addEventListener("change", () => { f.parere_superiore = pa.checked; });
        const muovi = (dx) => { const j = i + dx; if (j < 0 || j >= fasi.length) return; [fasi[i], fasi[j]] = [fasi[j], fasi[i]]; disegnaFasi(); };
        return h("div", { class: "carta", style: "margin-top:10px" },
          h("div", { class: "riga", style: "align-items:center" }, h("div", { class: "nome", style: "flex:0 0 auto" }, "Fase " + (i + 1)),
            h("div", { style: "text-align:right;flex:1" },
              h("button", { class: "s", type: "button", onclick: () => muovi(-1) }, "↑"), " ", h("button", { class: "s", type: "button", onclick: () => muovi(1) }, "↓"), " ",
              h("button", { class: "s", type: "button", onclick: () => { fasi.splice(i, 1); disegnaFasi(); } }, "Elimina"))),
          h("label", {}, "Titolo", t), h("label", {}, "Istruzioni della fase", ist),
          h("div", { class: "interruttore" }, ap, h("span", {}, "A fine fase si ferma e attende la mia decisione (approva, chiede modifiche, sceglie tra le proposte)")),
          h("div", { class: "interruttore" }, pa, h("span", {}, "Prima della decisione il suo superiore scrive un parere sul risultato")));
      }),
      h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => { fasi.push({ titolo: "", istruzioni: "", approvazione: true, parere_superiore: false }); disegnaFasi(); } }, "+ Aggiungi fase"))]);
  };
  disegnaFasi();
  const msg = h("div");
  const nasBox = h("div", { class: "sotto", style: "margin:4px 0 10px 28px" }), nasScelte = [];
  if (!nuovo) {
    api("GET", "/gestione/archivio/cartelle-agente/" + a.id).then(r => {
      if (!r.cartelle.length) return;
      r.cartelle.forEach(k => { const cb = h("input", { type: "checkbox" }); cb.checked = r.scelte.includes(k.id); nasScelte.push([k.id, cb]); });
      nasBox.replaceChildren(h("div", {}, "Cartelle del NAS che può consultare (nessuna selezionata = tutte):"),
        h("div", { class: "riga", style: "flex-wrap:wrap" }, nasScelte.map(([id, cb], i) => h("label", { style: "flex:0 0 auto;margin-right:14px" }, cb, " " + r.cartelle[i].nome))));
    }).catch(() => {});
  }

  const salva = async () => {
    msg.replaceChildren();
    const corpo = {
      nome: nome.value.trim(), ruolo: ruolo.value.trim(), rimanda_a: rimanda.value.trim() || null, istruzioni: istr.value.trim(),
      divisione_id: livello.value === "sentinella" ? null : (div.value ? Number(div.value) : null), superiore_id: livello.value === "sentinella" ? null : (sup.value ? Number(sup.value) : null),
      livello: livello.value === "sentinella" ? "manager" : livello.value, sentinella: livello.value === "sentinella", modello: modello.value, fascia_dati_max: fascia.value,
      max_token_risposta: Number(tetto.value), sforzo: sforzo.value, budget_token_mensile: budget.value ? Number(budget.value) : null,
      accesso_web: web.checked, siti_consentiti: siti.value.split("\n").map(s => s.trim()).filter(Boolean),
      max_ricerche: Number(ricerche.value), attivo: attivo.checked,
      fasi: fasi.filter(f => f.titolo.trim()).map(f => ({ ...f, titolo: f.titolo.trim() })),
      modello_dialogo: modDialogo.value || null, dialoghi_attivi: dialoga.checked, vede_tutto: vedeTutto.checked, drive_attivo: driveAttivo.checked, social_attivo: socialAttivo.checked, email_attivo: emailAttivo.checked, crm_attivo: crmAttivo.checked, crm_nominativo: crmNominativo.checked, canva_attivo: canvaAttivo.checked, finestre_attivo: finestreAttivo.checked, finestre_siti: finestreSiti.value.split("\n").map(x => x.trim()).filter(Boolean), archivio_attivo: archivioAttivo.checked, gmail_account_id: gmailSel.value ? Number(gmailSel.value) : null, invio_posta: invioScelto(),
      connessioni: conn.filter(([, cb]) => cb.checked).map(([c]) => c.id),
    };
    try {
      const esito = await api(nuovo ? "POST" : "PUT", nuovo ? "/gestione/agenti" : "/gestione/agenti/" + a.id, corpo);
      await api("PUT", "/gestione/agenti/" + (nuovo ? esito.id : a.id) + "/aziende", { aziende: azCb.filter(([, cb]) => cb.checked).map(([z]) => z.id) });
      if (!nuovo && nasScelte.length) await api("PUT", "/gestione/archivio/cartelle-agente/" + a.id, { cartelle: nasScelte.filter(([, cb]) => cb.checked).map(([id]) => id) });
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
    const file = h("input", { type: "file", multiple: true, accept: ".pdf,.docx,.xlsx,.pptx,.odt,.ods,.odp,.rtf,.html,.htm,.json,.xml,.fcpxml,.edl,.srt,.vtt,.eml,.txt,.md,.csv,.tsv,.png,.jpg,.jpeg,.webp,.gif" });
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
      h("label", {}, "Carica uno o più documenti", h("p", { class: "aiuto" }, "Puoi sceglierne quanti vuoi insieme: tutti avranno la stessa riservatezza."), file), h("label", {}, "Riservatezza", fasciaDoc), m,
      h("div", { class: "azioni" }, h("button", { class: "s", onclick: async (ev) => {
        const scelti = [...file.files];
        if (!scelti.length) { m.replaceChildren(avviso("Scegli almeno un file", "no")); return; }
        const b = ev.currentTarget; b.disabled = true;
        const riusciti = [], falliti = [];
        for (let i = 0; i < scelti.length; i++) {
          b.textContent = "Caricamento " + (i + 1) + " di " + scelti.length + "…";
          const f = new FormData(); f.append("file", scelti[i]); f.append("nome", ""); f.append("fascia_dati", fasciaDoc.value); f.append("per_tutti", "false"); f.append("agenti", String(a.id));
          try { await api("POST", "/gestione/documenti", f); riusciti.push(scelti[i].name); } catch (e) { falliti.push(scelti[i].name + ": " + e.message); }
        }
        await caricaDoc();
        // dopo il ridisegno l'esito resta visibile in cima alla sezione
        if (falliti.length || riusciti.length > 1) sezioneDoc.prepend(falliti.length ? avviso(riusciti.length + " caricati, " + falliti.length + " non riusciti — " + falliti.join(" · "), "avv") : avviso(riusciti.length + " documenti caricati.", "ok"));
      } }, "Carica"))].flat(Infinity));
  };
  caricaDoc();

  const chiudi = () => sfondo.remove();
  const sfondo = h("div", { class: "pannello-sfondo" },
    h("div", { class: "pannello", role: "dialog", "aria-label": nuovo ? "Nuovo agente" : "Modifica " + d.nome },
      h("h2", {}, nuovo ? "Nuovo agente" : d.nome),
      h("div", { class: "interruttore" }, attivo, h("span", {}, "Agente attivo (se spento non risponde e non lavora)")),
      schede([
        ["Identità", [
          h("label", {}, "Nome", nome),
          h("label", {}, "Compito specifico (lo vedono anche gli altri agenti)", ruolo),
          h("label", {}, "Cosa NON fa / a chi rimanda (facoltativo)", rimanda),
          h("div", { class: "riga" }, h("label", {}, "Dipartimento", div), h("label", {}, "Risponde a", sup)),
          h("label", {}, "Aziende per cui lavora", h("p", { class: "aiuto" }, "Una o più. Se non ne scegli nessuna lavora per tutte (agente trasversale)."),
            azCb.length ? azCb.map(([z, cb]) => h("label", { class: "spunta" }, cb, z.nome)) : h("p", { class: "aiuto" }, "Nessuna azienda: creale nella scheda Struttura.")),
          h("div", { class: "riga" }, h("label", {}, "Categoria", h("p", { class: "aiuto" }, "La sentinella osserva e segnala, sta fuori dai dipartimenti. Per tutte le altre scegli dipartimento o superiore."), livello), h("label", {}, "Modello AI", modello))]],
        ["Prompt", [
          assistentePrompt(istr, () => ({ nome: nome.value.trim(), ruolo: ruolo.value.trim(), rimanda_a: rimanda.value.trim(), livello: livello.value,
            divisione: div.selectedOptions[0] ? div.selectedOptions[0].textContent : "", aziende: (stato.opzioni.aziende || []).filter(z => (d.aziende || []).includes(z.id)).map(z => z.nome).join(", ") })),
          h("label", {}, "Cosa deve fare", h("p", { class: "aiuto" }, "In italiano, come lo spiegheresti a un collaboratore: i suoi compiti, le sue relazioni con gli altri agenti, cosa deve guardare e cosa scaricare, il tono, cosa non deve fare."), istr),
          nuovo ? null : versioniPrecedenti(a, istr),
          h("h3", {}, "Fasi di lavoro"),
          [h("p", { class: "aiuto" }, "Facoltative. Se le lasci vuote l'agente non ha percorsi da seguire. Se le scrivi, per un lavoro avviato dalla pagina «Percorsi» l'agente le svolge una alla volta, nell'ordine, senza saltarne né anticiparne: a fine fase mostra il risultato e (se lo chiedi) aspetta la tua decisione."), contFasi]]],
        ["Dati e costi", [
          h("label", {}, "Dati che può ricevere", h("p", { class: "aiuto" }, "Anche se qui scegli un livello alto, i dati escono verso un fornitore solo se il fornitore ha le garanzie attive."), fascia),
          h("div", { class: "riga" },
            h("label", {}, "Lunghezza massima risposta (token)", tetto),
            h("label", {}, "Sforzo di ragionamento (modelli Claude)", sforzo),
            h("label", {}, "Budget mensile (token)", budget)),
          nuovo ? null : sezioneProva(a), nuovo ? null : sezioneProfiloAlto(a)]],
        ["Strumenti", [      h("h3", {}, "Dialoghi con gli altri agenti"),
      h("div", { class: "interruttore" }, dialoga, h("span", {}, "Può fare domande a superiore, subordinati e altri manager mentre lavora")),
      h("div", { class: "interruttore" }, vedeTutto, h("span", {}, "Vede cosa fai e cosa ti dicono gli altri agenti (sintesi recente, nei limiti di riservatezza)")),
      h("label", {}, "Casella di posta che gestisce", gmailSel),
      h("h3", {}, "Invio delle email"),
      h("p", { class: "aiuto" }, "Vale per l'agente che ha una casella (Gmail scelta qui sopra, oppure una casella IMAP assegnata in Collegamenti). Puoi provare prima con l'approvazione e passare all'invio diretto quando ti fidi."),
      ...radiInvio,
      h("div", { class: "interruttore" }, socialAttivo, h("span", {}, "Può preparare post per i social (non pubblica: li approvi tu dalla pagina Social)")),
      h("div", { class: "interruttore" }, archivioAttivo, h("span", {}, "Può cercare foto e video nell'Archivio NAS e chiedere foto pronte o trascrizioni (serve il connettore sul NAS)")),
      nasBox,
      h("div", { class: "interruttore" }, finestreAttivo, h("span", {}, "Può usare il browser (Finestre): leggere le schede che condividi e agire solo nei siti elencati qui sotto")),
      finestreSiti,
      h("div", { class: "interruttore" }, canvaAttivo, h("span", {}, "Può creare ed esportare design su Canva (serve Canva collegato in Collegamenti)")),
      h("div", { class: "interruttore" }, crmAttivo, h("span", {}, "Può consultare i conteggi del CRM (solo numeri aggregati, mai nomi o recapiti)")),
      h("div", { class: "interruttore" }, crmNominativo, h("span", {}, "Può vedere i singoli contatti del CRM, fare ricerche online su di loro e preparare email personalizzate (solo agenti Claude; segue il tuo «Invio email»: di norma va in coda da approvare)")),
      h("div", { class: "interruttore" }, emailAttivo, h("span", {}, "Può preparare campagne email via Brevo (non invia: le approvi tu dalla pagina Email)")),
      h("div", { class: "interruttore" }, driveAttivo, h("span", {}, "Può creare e modificare fogli e documenti Google nella cartella Opifex (non può cancellare)")),
      h("label", {}, "Modello per i dialoghi", h("p", { class: "aiuto" }, "Per parlare con i colleghi basta un modello semplice ed economico: il modello di lavoro sopra resta per pensare e svolgere i compiti."), modDialogo),
      h("h3", {}, "Accesso al web"),
      h("div", { class: "interruttore" }, web, h("span", {}, "Può cercare sul web (attivo per tutti; spegni per bloccarlo a questo agente — solo modelli Claude per ora)")),
      h("label", {}, "Siti consentiti", h("p", { class: "aiuto" }, "Un sito per riga. Se lasci vuoto può cercare su qualsiasi sito."), siti),
      h("label", {}, "Ricerche massime per risposta", ricerche)]],
        ["Fonti", [h("h3", {}, "Documento di riferimento"), sezioneDoc,
          h("h3", {}, "Connessioni"),
          conn.length ? conn.map(([c, cb]) => h("label", { class: "spunta" }, cb, c.nome + " (" + c.tipo + ")"))
            : h("p", { class: "aiuto" }, "Nessuna connessione ancora: creale nella scheda Connessioni.")]],
      ]),
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


// Pulsante microfono per un campo di testo: detta la risposta con la voce (stesso motore della chat)
function bottoneMic(campo, msg) {
  if (typeof Voce === "undefined" || !Voce.supportoDettatura) return null;
  const b = h("button", { class: "s", type: "button", title: "Detta la risposta con la voce" }, "🎤");
  const stile = (on) => { b.textContent = on ? "⏹" : "🎤"; b.classList.toggle("p", !!on); };
  const fine = () => stile(false);
  const stato_ = (s) => { if (s === null) stile(false); else if (s === "ascolto") { stile(true); msg.replaceChildren(); } else if (s === "trascrivo") msg.replaceChildren(avviso("Trascrivo la registrazione…", "ok")); else if (s) msg.replaceChildren(avviso(s, "avv")); };
  b.addEventListener("click", () => {
    if (Voce.inAscolto()) { Voce.viva = false; Voce.termina(); stile(false); return; }
    Voce.viva = false;
    if (Voce.modo === "server") { if (!Voce.registra(campo, fine, stato_, "")) msg.replaceChildren(avviso("Questo browser non può registrare dal microfono.", "avv")); return; }
    if (!Voce.ascolta(campo, fine, stato_)) msg.replaceChildren(avviso("Il tuo browser non supporta la dettatura vocale: usa Chrome, Edge o Safari.", "avv"));
  });
  return b;
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
        const ris = h("textarea", { style: "min-height:60px", placeholder: "La tua risposta: l'agente la riceve al prossimo lavoro (Invio per inviare, Maiusc+Invio per andare a capo)" });
        ris.addEventListener("keydown", async (e) => {
          if (e.key !== "Enter" || e.shiftKey || !ris.value.trim()) return; e.preventDefault();
          try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); carica(); }
          catch (x) { msg.replaceChildren(avviso(x.message, "no")); } });
        return h("div", { class: "carta", style: "margin-bottom:10px" },
          h("div", { class: "nome" }, (r.bloccante ? "BLOCCANTE · " : "") + r.agente),
          h("div", { class: "risposta" }, r.domanda),
          h("div", { class: "sotto" }, new Date(r.creata_il).toLocaleString("it-IT")),
          r.stato === "aperta" ? [ris, h("div", { class: "azioni" }, bottoneMic(ris, msg),
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
  const iniz = h("div");
  const caricaIniz = async () => {
    try {
      const d = await api("GET", "/gestione/iniziative");
      riempi(iniz, [schedaSoglie(d, caricaIniz), d.iniziative.length ? d.iniziative.map(i => cartaIniziativa(i, caricaIniz)) : h("p", { class: "sotto" }, "Nessuna iniziativa ancora. Le apre un manager quando vede un'opportunità.")]);
    } catch (e) { iniz.replaceChildren(avviso(e.message, "no")); }
  };
  caricaIniz();
  return h("div", {}, h("h2", {}, "Richieste e iniziative"),
    h("p", { class: "aiuto" }, "Gli agenti non inventano mai: se manca un dato lo chiedono al superiore e, se serve, a te. Le iniziative sopra soglia aspettano qui il tuo via libera."),
    h("h3", {}, "Informazioni che servono agli agenti"), selFiltro, msg, lista,
    h("h3", {}, "Iniziative dei manager"), iniz);
}

// ---------- Dialoghi ----------
function vistaDialoghi(senzaTitoli) {
  const colonnaFeed = h("div", { class: "carta", style: "max-height:70vh;overflow:auto" }, h("p", { class: "sotto" }, "Caricamento…"));
  const colonnaConv = h("div");
  const dettaglio = h("div");
  let ultimoId = 0, primo = true;
  const CODICI_MSG = { R: "Richiesta", E: "Eseguito", C: "Chiarito", D: "Dubbio", A: "D'accordo", N: "Rifiuto", B: "Bloccato", P: "In corso", I: "Informazione" };
  const testoCodice = (t) => { const x = /^\s*#([RECDANBPI])(?=$|[\s:.,;\-—–])/.exec(t || ""); return x ? "[" + x[1] + " · " + CODICI_MSG[x[1]] + "]" + (t.slice(x[0].length) ? " " + t.slice(x[0].length).trim() : "") : t; };
  const messaggioFeed = (m) => h("div", { style: "margin-bottom:12px" },
    h("div", { class: "sotto" }, (m.da || "?") + " → " + (m.a || "?") + " · " + new Date(m.creato_il).toLocaleTimeString("it-IT") + " · " + m.titolo),
    h("div", { class: "risposta" }, testoCodice(m.testo)));
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
          h("div", { class: "risposta" }, testoCodice(m.testo)))),
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => dettaglio.replaceChildren() }, "Chiudi"))));
      dettaglio.scrollIntoView({ behavior: "smooth" });
    } catch (e) { dettaglio.replaceChildren(avviso(e.message, "no")); }
  };
  stato.timer = setInterval(aggiornaFeed, 5000);
  aggiornaFeed();

  // avvio di un dialogo
  const attivi = stato.agenti.filter(a => a.attivo);
  const opz = () => attivi.map(a => h("option", { value: a.id }, a.etichetta || (a.nome + " — " + a.ruolo)));
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
    h("h3", {}, "Dialoghi tra agenti"),
    h("p", { class: "sotto" }, "Il feed si aggiorna da solo. Gli agenti dialogano con un modello economico; il modello di lavoro resta per pensare e svolgere i compiti."),
    h("h4", {}, "Feed generale"), colonnaFeed,
    h("h4", {}, "Conversazioni"), colonnaConv,
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


// Pannello «Richieste da risolvere»: raggruppate per agente, ognuna espandibile con la propria risposta
function pannelloRichieste(dopo) {
  const box = h("div", { class: "carta", style: "margin-bottom:14px" });
  const msg = h("div");
  let firma = null;
  const aperte = stato.richAperte = stato.richAperte || new Set();
  const carica = async (forza) => {
    let el;
    try { el = await api("GET", "/gestione/richieste?stato=aperta"); } catch (e) { return; }
    const f = el.map(r => r.id).join(",");
    if (!forza && f === firma) return;                      // niente cambiamenti: non cancello le risposte che sto scrivendo
    if (!forza && box.querySelector("textarea") && [...box.querySelectorAll("textarea")].some(t => t.value)) return;
    firma = f; stato.richieste = el.length;
    const gruppi = new Map();
    for (const r of el) { if (!gruppi.has(r.agente)) gruppi.set(r.agente, []); gruppi.get(r.agente).push(r); }
    const invia = async (r, ris) => {
      if (!ris.value.trim()) { msg.replaceChildren(avviso("Scrivi la risposta", "no")); return; }
      try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); aperte.delete(r.id); carica(true); if (dopo) dopo(); }
      catch (x) { msg.replaceChildren(avviso(x.message, "no")); }
    };
    const carta = (r) => {
      const ris = h("textarea", { style: "min-height:70px", placeholder: "La tua risposta (Invio per inviare, Maiusc+Invio per andare a capo)" });
      ris.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); invia(r, ris); } });
      const d = h("details", { class: "richiesta" + (r.bloccante ? " bloccante" : "") },
        h("summary", {}, (r.bloccante ? "BLOCCANTE · " : "") + (r.progetto ? "[" + r.progetto + "] " : "") + (r.domanda.length > 110 ? r.domanda.slice(0, 110) + "…" : r.domanda)),
        h("div", { class: "risposta" }, r.domanda),
        h("div", { class: "sotto" }, new Date(r.creata_il).toLocaleString("it-IT")), ris,
        h("div", { class: "azioni" }, bottoneMic(ris, msg), h("button", { class: "p", onclick: () => invia(r, ris) }, "Rispondi"),
          h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/richieste/" + r.id + "/annulla"); aperte.delete(r.id); carica(true); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Non serve più")));
      if (aperte.has(r.id)) d.open = true;
      d.addEventListener("toggle", () => { if (d.open) aperte.add(r.id); else aperte.delete(r.id); });
      return d;
    };
    const tutteAperte = () => box.querySelectorAll("details.richiesta").forEach(x => { x.open = true; });
    const tutteChiuse = () => box.querySelectorAll("details.richiesta").forEach(x => { x.open = false; });
    riempi(box, [
      h("div", { class: "riga", style: "align-items:center;justify-content:space-between" },
        h("h3", { style: "margin:0" }, el.length ? "Richieste da risolvere (" + el.length + ")" : "Nessuna richiesta da risolvere"),
        el.length ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: tutteAperte }, "Espandi tutte"), h("button", { class: "s", onclick: tutteChiuse }, "Comprimi tutte")) : null),
      el.length ? null : h("p", { class: "sotto" }, "Quando un agente ha bisogno di un'informazione la trovi qui."),
      [...gruppi].map(([nome, rr]) => h("details", { class: "gruppo-richieste", open: true },
        h("summary", {}, nome + " · " + rr.length + (rr.some(x => x.bloccante) ? " (con bloccanti)" : "")), rr.map(carta))),
      msg]);
  };
  carica(true);
  stato.timerRich = setInterval(() => { if (!document.body.contains(box)) { clearInterval(stato.timerRich); return; } carica(false); }, 8000);
  return box;
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
        h("div", { class: "azioni" }, pulsanteAscolta(() => b.contenuto)),
        (b.manager || []).length ? h("details", { class: "carta" }, h("summary", {}, "Brief dei manager (" + b.manager.length + ")"),
          b.manager.map(m => h("div", {}, h("div", { class: "nome" }, m.nome + (m.divisione ? " — " + m.divisione : "")), h("div", { class: "risposta", style: "white-space:pre-wrap" }, m.contenuto), pulsanteAscolta(() => m.contenuto)))) : null,
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
          stato.salvatoSicurezza = f.nome; await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      const completo = f.non_conservazione_attiva && f.dpa_firmato;
      if (stato.salvatoSicurezza === f.nome) { msg.replaceChildren(avviso("Salvato.", "ok")); stato.salvatoSicurezza = null; }
      return h("div", { class: "carta" }, h("div", { class: "nome" }, f.nome),
        completo ? avviso("Garanzie complete: a questo fornitore possono arrivare anche dati interni e riservati (entro il limite sotto).", "ok")
                 : avviso("Garanzie incomplete: a questo fornitore arrivano solo dati pubblici. Servono entrambe le spunte.", "avv"),
        h("div", { class: "sotto" }, "Dati ammessi al massimo: " + ETICHETTA_FASCIA[f.fascia_dati_max]),
        h("label", { class: "spunta" }, nc, "Non conservazione dei dati attiva"),
        h("label", { class: "spunta" }, dpa, "DPA firmato"),
        msg, h("div", { class: "azioni" }, h("button", { class: "p", onclick: salva }, "Salva")));
    })),
    blocchiFornitori(),
    bloccoN8n(),
  ];
}

// ---------- Avvio ----------
// Si parte solo a pagina completa: gli script sono caricati uno dopo l'altro e la prima risposta
// del server potrebbe arrivare prima che l'ultimo sia pronto.
function parti() { if (token) avvia(); else mostraAccesso(); }
if (document.readyState === "complete") parti(); else window.addEventListener("load", parti);


// Versioni precedenti delle istruzioni di un agente: si possono rimettere nel campo e poi salvare
function versioniPrecedenti(agente, campo) {
  const box = h("div", { class: "sotto" });
  const bottone = h("button", { class: "s", type: "button", onclick: async () => {
    try {
      const d = await api("GET", "/gestione/agenti/" + agente.id + "/istruzioni-storico");
      if (!d.versioni.length) { box.replaceChildren("Nessuna versione precedente."); return; }
      const sel = h("select", {}, d.versioni.map((v, i) => h("option", { value: i }, new Date(v.creato_il).toLocaleString("it-IT") + " · " + v.motivo)));
      box.replaceChildren(sel, h("button", { class: "s", type: "button", style: "margin-left:8px", onclick: () => { campo.value = d.versioni[Number(sel.value)].istruzioni; box.append(h("div", {}, "Messa nel campo: premi Salva per confermare.")); } }, "Rimetti nel campo"));
    } catch (e) { box.replaceChildren(e.message); }
  } }, "Versioni precedenti");
  return h("div", { style: "margin:6px 0" }, bottone, box);
}

// il numerino su «Progetti» (domande degli agenti + squadre da approvare) si aggiorna da solo ogni minuto
setInterval(async () => {
  if (document.hidden || stato.ruolo !== "titolare") return;
  try {
    const c = await api("GET", "/gestione/richieste/conteggio"); stato.richieste = c.aperte; stato.squadreAttesa = c.squadre || 0;
    const b = document.getElementById("badge-progetti"), n = (c.aperte || 0) + (c.squadre || 0);
    if (b) { b.textContent = String(n); b.style.display = n ? "" : "none"; }
  } catch (e) { /* ignora */ }
}, 60000);

// Avviso in alto quando il NAS ha indicizzato un gruppo di file nuovi: chi e' collegato lo vede e puo' aprire l'elenco
async function controllaNovitaArchivio() {
  if (document.hidden || stato.ruolo !== "titolare" || !localStorage.getItem) return;
  let el = [];
  try { el = await api("GET", "/gestione/archivio/novita"); } catch (e) { return; }
  let box = document.getElementById("avviso-nas");
  if (!el.length) { if (box) box.remove(); return; }
  if (!box) { box = h("div", { id: "avviso-nas", role: "status", style: "position:fixed;left:50%;transform:translateX(-50%);top:calc(10px + env(safe-area-inset-top,0px));z-index:60;max-width:min(560px,92vw);background:var(--carta,#fff);color:var(--testo,#222);border:2px solid #C4502A;border-radius:12px;padding:10px 14px;box-shadow:0 6px 24px rgba(0,0,0,.25)" }); document.body.appendChild(box); }
  const n = el[0];
  box.replaceChildren(h("div", { style: "font-weight:700" }, "Nel NAS sono stati aggiunti " + n.nuovi + " file nuovi"),
    h("div", { class: "sotto" }, "Cartella «" + n.cartella + "»: " + n.esempi.join(", ") + (n.nuovi > n.esempi.length ? "…" : "")),
    h("div", { class: "azioni" },
      h("button", { class: "p", onclick: () => { stato.archivioNovita = n.id; box.remove(); api("POST", "/gestione/archivio/novita/" + n.id + "/vista").catch(() => {}); vai("impostazioni", "archivio"); } }, "Guarda cosa è stato aggiunto"),
      h("button", { class: "s", onclick: () => { box.remove(); api("POST", "/gestione/archivio/novita/" + n.id + "/vista").catch(() => {}); } }, "Ok")));
}
setInterval(controllaNovitaArchivio, 60000);
setTimeout(controllaNovitaArchivio, 8000);


// Novità non viste (Progetti, Ginnasio, Documenti): il numero compare sul menu e si azzera dopo aver guardato la pagina per un paio di secondi.
function mostraNovita() {
  for (const id of ["progetti", "ginnasio", "documenti"]) {
    const b = document.getElementById("novita-" + id), n = (stato.novita || {})[id] || 0;
    if (n > 0 && !_contatoreVisto[id] && b && b.offsetParent !== null) { _contatoreVisto[id] = true; registraUso(etichettaVista(), "contatore_visto", { elemento: id }); }
    if (!n) _contatoreVisto[id] = false;
    if (b) { b.textContent = n ? String(n) : ""; b.style.display = n ? "" : "none"; }
  }
}
async function caricaNovita() {
  if (document.hidden || stato.ruolo !== "titolare" || !token) return;
  try { stato.novita = await api("GET", "/novita"); mostraNovita(); } catch (e) { /* riprova al prossimo giro */ }
}
let _timerVisto = null;
function segnaVisto(vista) {
  clearTimeout(_timerVisto);
  if (stato.ruolo !== "titolare" || !["progetti", "ginnasio", "documenti"].includes(vista)) return;
  _timerVisto = setTimeout(async () => {
    if (stato.vista !== vista || document.hidden) return;
    try { await api("POST", "/novita/" + vista + "/visto"); if (stato.novita) stato.novita[vista] = 0; mostraNovita(); } catch (e) { /* ignora */ }
  }, 2000);
}
setInterval(caricaNovita, 60000);
setTimeout(() => { caricaNovita(); segnaVisto(stato.vista); }, 3000);
