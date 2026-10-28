"use strict";
// Opifex Voce, tappa 1: assistente vocale (PWA) sopra l'API /v1.
// Briefing, task, ricerca contatti, note dettate, messaggi ai manager, task ed email a voce con doppia conferma. Accesso con impronta/volto (passkey).

const radice = document.getElementById("radice");
const CH = "voce_token";
let token = null, nome = "", ascoltando = null, inAttesa = null;   // inAttesa: conferma in corso {token, riepilogo}

// ---------- utilita' ----------
function h(tag, attr, ...figli) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attr || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const f of figli.flat()) if (f != null) e.append(f.nodeType ? f : document.createTextNode(String(f)));
  return e;
}
function salvaToken(t, minuti) { try { localStorage.setItem(CH, JSON.stringify({ t, fino: Date.now() + (minuti - 1) * 60000, nome })); } catch (e) { /* senza memoria locale si rientra ogni volta */ } }
function leggiToken() { try { const x = JSON.parse(localStorage.getItem(CH) || "null"); if (x && x.fino > Date.now()) { nome = x.nome || ""; return x.t; } } catch (e) { /* ignora */ } return null; }
function esci() { try { localStorage.removeItem(CH); } catch (e) { /* ignora */ } token = null; fermaAscolto(); disegnaAccesso(); }
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const daB64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0));

let ultimeDecisioni = [];
async function api(percorso, opz = {}) {
  const intest = { "Content-Type": "application/json" };
  if (token) intest.Authorization = "Bearer " + token;
  const r = await fetch(percorso, { method: opz.metodo || "GET", headers: intest, body: opz.corpo ? JSON.stringify(opz.corpo) : undefined });
  let dati = {};
  try { dati = await r.json(); } catch (e) { /* risposta vuota */ }
  if (r.status === 401 && token) { esci(); throw new Error("Sessione scaduta: rientra"); }
  if (!r.ok) throw new Error(typeof dati.detail === "string" ? dati.detail : "Errore " + r.status);
  return dati;
}

// ---------- voce ----------
const Riconoscimento = window.SpeechRecognition || window.webkitSpeechRecognition;
function parla(testo) {
  if (!("speechSynthesis" in window) || !testo) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(testo);
  u.lang = "it-IT";
  speechSynthesis.speak(u);
}
function fermaAscolto() { if (ascoltando) { try { ascoltando.stop(); } catch (e) { /* gia' fermo */ } ascoltando = null; } }
function ascolta(fine, ciclo) {
  if (!Riconoscimento) { scrivi("er", "Questo telefono non ha il riconoscimento vocale: scrivi il comando."); return; }
  fermaAscolto();
  const r = new Riconoscimento();
  r.lang = "it-IT"; r.interimResults = false; r.maxAlternatives = 1;
  r.onresult = (ev) => { const t = ev.results[0][0].transcript.trim(); fine(t); };
  r.onerror = () => { ascoltando = null; aggiornaMic(); };
  r.onend = () => { ascoltando = null; aggiornaMic(); };
  ascoltando = r; aggiornaMic();
  try { r.start(); } catch (e) { ascoltando = null; aggiornaMic(); }
}
function aggiornaMic() { const m = document.getElementById("mic"); if (m) { m.classList.toggle("on", !!ascoltando); m.setAttribute("aria-label", ascoltando ? "Sto ascoltando, tocca per fermare" : "Parla"); } }

// ---------- accesso ----------
async function entraConPasskey() {
  try {
    const o = await api("/v1/accesso/opzioni", { metodo: "POST" });
    const pk = Object.assign({}, o.publicKey, { challenge: daB64u(o.publicKey.challenge) });
    const c = await navigator.credentials.get({ publicKey: pk });
    const r = await api("/v1/accesso", { metodo: "POST", corpo: {
      sfida: o.sfida, credenziale_id: b64u(c.rawId), client_data_json: b64u(c.response.clientDataJSON),
      authenticator_data: b64u(c.response.authenticatorData), firma: b64u(c.response.signature) } });
    nome = r.nome; token = r.token; salvaToken(r.token, r.scade_tra_minuti); disegnaHome();
  } catch (e) { messaggioAccesso(e && e.name === "NotAllowedError" ? "Accesso annullato." : e.message); }
}
function messaggioAccesso(t) { const m = document.getElementById("acc-msg"); if (m) m.textContent = t; }

async function entraConPassword(ev) {
  ev.preventDefault();
  const f = ev.target;
  try {
    let r = await api("/login", { metodo: "POST", corpo: { email: f.email.value.trim(), password: f.password.value } });
    if (r.passo === "codice") {
      const codice = f.codice.value.trim();
      if (!codice) { f.codice.parentElement.hidden = false; messaggioAccesso("Inserisci il codice a 6 cifre."); return; }
      r = await api("/login/2fa", { metodo: "POST", corpo: { sfida: r.sfida, codice } });
    } else if (r.passo !== "ok") { messaggioAccesso("Completa prima la configurazione dall'app principale."); return; }
    token = r.token; nome = r.nome || ""; salvaToken(r.token, 240); disegnaHome(true);
  } catch (e) { messaggioAccesso(e.message); }
}

function disegnaAccesso() {
  radice.replaceChildren(
    h("h1", {}, "Opifex Voce"),
    h("p", { class: "dim" }, "Il tuo assistente a voce. Entra con impronta o volto."),
    h("button", { class: "pr", onclick: entraConPasskey }, "Entra con impronta o volto"),
    h("p", { id: "acc-msg", class: "dim", role: "status" }),
    h("details", { class: "sc" }, h("summary", {}, "Prima volta o nuovo telefono: entra con password"),
      h("form", { onsubmit: entraConPassword },
        h("label", { for: "e" }, "Email"), h("input", { id: "e", name: "email", type: "email", autocomplete: "username", required: true }),
        h("label", { for: "p" }, "Password"), h("input", { id: "p", name: "password", type: "password", autocomplete: "current-password", required: true }),
        h("div", { hidden: true }, h("label", { for: "c" }, "Codice a 6 cifre"), h("input", { id: "c", name: "codice", inputmode: "numeric", autocomplete: "one-time-code" })),
        h("p", {}, h("button", { class: "pr", type: "submit" }, "Entra")))));
}

async function attivaPasskey() {
  try {
    const o = await api("/v1/passkey/registra/opzioni", { metodo: "POST" });
    const pk = Object.assign({}, o.publicKey, { challenge: daB64u(o.publicKey.challenge) });
    pk.user = Object.assign({}, pk.user, { id: daB64u(pk.user.id) });
    pk.excludeCredentials = (pk.excludeCredentials || []).map((x) => Object.assign({}, x, { id: daB64u(x.id) }));
    const c = await navigator.credentials.create({ publicKey: pk });
    await api("/v1/passkey/registra", { metodo: "POST", corpo: { sfida: o.sfida, client_data_json: b64u(c.response.clientDataJSON), attestation_object: b64u(c.response.attestationObject), nome: "Telefono" } });
    scrivi("ai", "Fatto: da ora entri con impronta o volto.");
  } catch (e) { scrivi("er", e && e.name === "NotAllowedError" ? "Attivazione annullata." : e.message); }
}

// ---------- schermata principale ----------
let log;
function scrivi(chi, testo, parlalo) {
  if (!log) return;
  log.append(h("div", { class: "msg " + chi }, testo));
  log.lastChild.scrollIntoView({ block: "end", behavior: "smooth" });
  if (parlalo) parla(testo);
}
function disegnaHome(proponiPasskey) {
  log = h("div", { class: "log", role: "log" });
  const campo = h("input", { id: "cmd", placeholder: "Scrivi o parla: «briefing», «cerca Rossi»…", enterkeyhint: "send", "aria-label": "Comando" });
  const scorciatoie = [["Briefing", "briefing"], ["Le mie task", "task"], ["Ginnasio", "ginnasio"], ["Manager", "manager"],
                       ["Decisioni", "decisioni"], ["Nuova nota", "nota:"], ["Nuova email", "email"]];
  radice.replaceChildren(
    h("div", { class: "riga sp" }, h("h1", {}, nome ? "Ciao " + nome : "Opifex Voce"), h("button", { onclick: esci, "aria-label": "Esci" }, "Esci")),
    h("button", { id: "mic", class: "mic", onclick: () => { if (ascoltando) fermaAscolto(); else { parla(""); ascolta((t) => { campo.value = t; esegui(t); }); } }, "aria-label": "Parla" }, "🎤"),
    h("div", { class: "griglia" }, scorciatoie.map(([e, c]) => h("button", { onclick: () => { if (c === "nota:") { campo.value = "nota "; campo.focus(); } else esegui(c); } }, e))),
    h("form", { class: "riga", onsubmit: (ev) => { ev.preventDefault(); esegui(campo.value); campo.value = ""; } }, campo, h("button", { class: "pr", type: "submit" }, "Invia")),
    log);
  scrivi("ai", "Dimmi cosa ti serve: briefing, task, «cerca» un contatto, «nota», «scrivi a» un manager, «crea task», «email».");
  if (proponiPasskey && window.PublicKeyCredential) log.append(h("div", { class: "msg ai" }, "Vuoi entrare la prossima volta con impronta o volto? ", h("button", { class: "pr", onclick: attivaPasskey }, "Attiva")));
}

// ---------- comandi ----------
const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9@.\s'-]/g, " ").replace(/\s+/g, " ").trim();
async function esegui(testo) {
  testo = (testo || "").trim();
  if (!testo) return;
  scrivi("io", testo);
  const n = norm(testo);
  try {
    if (inAttesa) return await rispondiConferma(n);
    if (flusso) return await passoFlusso(testo);
    let m;
    if (/^(briefing|riepilogo|novita|come siamo messi)/.test(n)) {
      const r = await api("/v1/briefing" + (/sera/.test(n) ? "?tipo=sera" : /mattina/.test(n) ? "?tipo=mattina" : ""));
      return scrivi("ai", r.sintesi, true);
    }
    if (/^(crea|nuova|aggiungi) (una )?task\b/.test(n)) return avviaTask(testo.replace(/^\S+\s+(una\s+)?task\s*:?\s*/i, ""));
    if (/^(le mie )?(task|scadenze|cosa devo fare|attivita)/.test(n)) {
      const r = await api("/v1/task" + (/oggi|settimana/.test(n) ? "?entro_giorni=" + (/oggi/.test(n) ? 0 : 7) : ""));
      return scrivi("ai", r.sintesi + (r.task.length > 1 ? "\n" + r.task.slice(0, 6).map((t) => "• " + t.titolo + (t.scadenza ? " (" + t.scadenza + ")" : "")).join("\n") : ""), true);
    }
    if ((m = n.match(/^(cerca|trova|chi e|numero di|contatto)\s+(.+)/))) {
      const r = await api("/v1/crm/cerca?q=" + encodeURIComponent(m[2]));
      return scrivi("ai", r.sintesi + (r.risultati.length ? "\n" + r.risultati.slice(0, 5).map((x) => "• " + [x.nome, x.ente].filter(Boolean).join(" — ")).join("\n") : ""), true);
    }
    if ((m = testo.match(/^(documento|nota lunga|nota per aurora|detta ad aurora|scrivi la nota)\s*:?\s*(.+)/is))) {
      const r = await api("/note-aurora", { metodo: "POST", corpo: { testo: m[2] } });
      return scrivi("ai", r.sintesi + " Quando vuoi, di' «affida la nota» e ti chiedo conferma.", true);
    }
    if ((m = n.match(/^(affida|manda|passa)\s+(la\s+)?(nota|documento)(\s+(?:a|al|ad)\s+(\S+))?/))) {
      const man = m[5] ? m[5].charAt(0).toUpperCase() + m[5].slice(1) : undefined;
      return preparaAzione("nota.affida", man ? { manager: man } : {});
    }
    if ((m = testo.match(/^(nota|appunta|ricorda)\s*:?\s*(.+)/i))) {
      const r = await api("/v1/note", { metodo: "POST", corpo: { testo: m[2] } });
      return scrivi("ai", r.sintesi, true);
    }
    if (/^(decisioni|da decidere|cosa devo approvare|posta)/.test(n)) {
      const r = await api("/v1/decisioni"); ultimeDecisioni = r.decisioni;
      return scrivi("ai", r.sintesi + (r.decisioni.length ? "\n" + r.decisioni.slice(0, 8).map((x) => x.n + ". " + x.titolo).join("\n") + "\nDi' «approva 1», «respingi 2» oppure «rispondi 3 sì»." : ""), true);
    }
    if ((m = testo.match(/^(approva|respingi|rifiuta|scarta|rispondi)\s+(\d+)\s*:?\s*(.*)$/is))) {
      if (!ultimeDecisioni.length) { const r = await api("/v1/decisioni"); ultimeDecisioni = r.decisioni; }
      const v = ultimeDecisioni.find((x) => x.n === Number(m[2]));
      if (!v) return scrivi("ai", "Non trovo la decisione " + m[2] + ": di' «decisioni» per l'elenco.", true);
      const az = /^appr/i.test(m[1]) ? "approva" : /^rispondi/i.test(m[1]) ? "rispondi" : "respingi";
      return preparaAzione("decisione.prendi", { tipo: v.tipo, id: v.id, azione: az, testo: m[3] || undefined });
    }
    if (/^(ginnasio|formazione)/.test(n)) { const r = await api("/v1/ginnasio"); return scrivi("ai", r.sintesi, true); }
    if (/^(manager|agenti|chi sono i manager)/.test(n)) { const r = await api("/v1/agenti"); return scrivi("ai", r.sintesi, true); }
    if (/^(email|mail|scrivi una mail|scrivi un'email|invia una mail)/.test(n)) return avviaEmail();
    if ((m = testo.match(/^(?:scrivi a|chiedi a|di a|dì a|di' a)\s+(\S+)\s+(.+)/i))) return scriviAManager(m[1], m[2]);
    scrivi("ai", "Non ho capito. Prova: briefing, decisioni, task, cerca Rossi, nota comprare latte, documento per Aurora, scrivi a Marco com'e' andata, crea task chiamare il commercialista, email.", true);
  } catch (e) { scrivi("er", e.message); }
}

async function scriviAManager(chi, messaggio) {
  const r = await api("/v1/agenti");
  const q = norm(chi);
  const a = r.agenti.find((x) => norm(x.nome) === q) || r.agenti.find((x) => norm(x.nome).includes(q) || norm(x.ruolo || "").includes(q));
  if (!a) return scrivi("er", "Non trovo un manager che si chiami «" + chi + "». Di' «manager» per l'elenco.", true);
  const inv = await api("/v1/agenti/" + a.id + "/messaggio", { metodo: "POST", corpo: { messaggio } });
  scrivi("ai", inv.sintesi + " Ti avviso appena risponde.", true);
  for (let i = 0; i < 60; i++) {
    await new Promise((ok) => setTimeout(ok, 3000));
    const x = await api("/v1/agenti/messaggio/" + inv.messaggio_id);
    if (x.stato !== "in_coda" && x.stato !== "in_lavoro") return scrivi(x.errore ? "er" : "ai", a.nome + ": " + x.sintesi, true);
  }
  scrivi("ai", a.nome + " sta ancora lavorando: lo trovi nella chat dell'app principale.", true);
}

// ---------- azioni con doppia conferma ----------
let flusso = null;   // email guidata: {passo, dati}
const CAMPI_EMAIL = [["a", "A chi la mando? Detta l'indirizzo, per esempio «mario chiocciola gmail punto com»."], ["oggetto", "Qual e' l'oggetto?"], ["testo", "Cosa scrivo nel messaggio?"]];
function indirizzo(t) {
  return norm(t).replace(/\bchiocciola\b/g, "@").replace(/\bat\b/g, "@").replace(/\bpunto\b/g, ".").replace(/\btrattino\b/g, "-").replace(/\bunderscore\b|\btrattino basso\b/g, "_").replace(/\s+/g, "");
}
function avviaEmail() {
  flusso = { passo: 0, dati: {} };
  const q = CAMPI_EMAIL[0][1];
  scrivi("ai", q, true);
  setTimeout(() => ascolta((t) => esegui(t)), 3500);
}
async function passoFlusso(testo) {
  const n = norm(testo);
  if (/^(annulla|basta|lascia stare|stop)$/.test(n)) { flusso = null; return scrivi("ai", "Annullato.", true); }
  const [chiave] = CAMPI_EMAIL[flusso.passo];
  flusso.dati[chiave] = chiave === "a" ? indirizzo(testo) : testo;
  flusso.passo++;
  if (flusso.passo < CAMPI_EMAIL.length) {
    const q = CAMPI_EMAIL[flusso.passo][1];
    scrivi("ai", q, true);
    return setTimeout(() => ascolta((t) => esegui(t)), 2500);
  }
  const dati = flusso.dati; flusso = null;
  await preparaAzione("email.invia", dati);
}
async function avviaTask(titolo) {
  if (!titolo.trim()) return scrivi("ai", "Dimmi il titolo, per esempio: crea task chiamare il commercialista.", true);
  await preparaAzione("task.crea", { titolo: titolo.trim() });
}
async function preparaAzione(azione, parametri) {
  const r = await api("/v1/conferme", { metodo: "POST", corpo: { azione, parametri } });
  inAttesa = { token: r.conferma_token };
  const box = h("div", { class: "msg ai conf", id: "conf" }, r.riepilogo, h("div", { class: "riga", style: "margin-top:10px" },
    h("button", { class: "ok", onclick: () => esegui("si confermo") }, "Conferma"), h("button", { class: "no", onclick: () => esegui("annulla") }, "Annulla")));
  log.append(box); box.scrollIntoView({ block: "end", behavior: "smooth" });
  parla(r.riepilogo);
  setTimeout(() => { if (inAttesa) ascolta((t) => esegui(t)); }, Math.min(9000, 1500 + r.riepilogo.length * 65));
}
async function rispondiConferma(n) {
  const t = inAttesa.token;
  if (/^(si|sì|confermo|conferma|invia|ok|certo|vai)\b/.test(n)) {
    inAttesa = null; document.getElementById("conf")?.remove();
    const r = await api("/v1/conferme/esegui", { metodo: "POST", corpo: { conferma_token: t } });
    return scrivi("ai", r.sintesi, true);
  }
  if (/^(no|annulla|stop|non inviare|lascia stare)\b/.test(n)) {
    inAttesa = null; document.getElementById("conf")?.remove();
    const r = await api("/v1/conferme/annulla", { metodo: "POST", corpo: { conferma_token: t } });
    return scrivi("ai", r.sintesi, true);
  }
  scrivi("ai", "Rispondi «sì» per confermare oppure «annulla».", true);
  setTimeout(() => { if (inAttesa) ascolta((x) => esegui(x)); }, 2500);
}

// ---------- avvio ----------
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => { /* senza service worker resta una pagina normale */ });
token = leggiToken();
if (token) disegnaHome(); else disegnaAccesso();
