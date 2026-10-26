"use strict";
// Task e sottotask per persone e agenti: lista, bacheca, scheda della task, blocco "Da fare" della Dashboard.
// Tutti i testi arrivano dall'API e vengono inseriti come testo, mai come HTML.

const STATI_TASK = [["da_fare", "Da fare"], ["in_corso", "In corso"], ["in_attesa", "In attesa"], ["completata", "Completata"]];
const PRIORITA_TASK = [["bassa", "Bassa"], ["normale", "Normale"], ["alta", "Alta"], ["urgente", "Urgente"]];
const COL_PRIO = { bassa: "", normale: "", alta: "avv", urgente: "no" };

function dataBreve(s) {
  if (!s) return "";
  const [a, m, g] = String(s).slice(0, 10).split("-").map(Number);
  return new Date(a, m - 1, g).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}
function giorniA(s) {   // giorni da oggi (negativo = scaduta)
  const [a, m, g] = String(s).slice(0, 10).split("-").map(Number);
  const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  return Math.round((new Date(a, m - 1, g) - oggi) / 86400000);
}
function gruppoTask(t) {
  if (t.stato === "completata") return 5;
  if (!t.scadenza) return 4;
  const d = giorniA(t.scadenza);
  return d < 0 ? 0 : d === 0 ? 1 : d <= 7 ? 2 : 3;
}
const NOMI_GRUPPO = ["Scadute", "Oggi", "Nei prossimi 7 giorni", "Più avanti", "Senza scadenza", "Completate"];

async function opzioniTask() {
  stato.taskOpz = await api("GET", "/task/opzioni");
  return stato.taskOpz;
}

function chipTask(t) {
  return h("span", { class: "task-chip" },
    t.priorita !== "normale" ? h("span", { class: "etichetta " + COL_PRIO[t.priorita] }, PRIORITA_TASK.find(p => p[0] === t.priorita)[1]) : null,
    t.scadenza ? h("span", { class: "etichetta " + (t.scaduta ? "no" : "") }, (t.scaduta ? "Scaduta · " : "") + dataBreve(t.scadenza)) : null,
    (t.utente || t.agente) ? h("span", { class: "etichetta" }, (t.agente ? "🤖 " : "") + (t.agente || t.utente)) : null,
    t.azienda ? h("span", { class: "etichetta", style: "border-left:4px solid " + (t.azienda_colore || "#7d8a99") }, t.azienda) : null,
    t.progetto ? h("span", { class: "etichetta", style: "border-left:4px solid " + (t.progetto_colore || "#7d8a99") }, t.progetto) : null,
    t.sottotask ? h("span", { class: "etichetta" }, t.sottotask_fatte + "/" + t.sottotask + " sottotask") : null,
    t.commenti ? h("span", { class: "etichetta" }, t.commenti + " 💬") : null);
}

function rigaTask(t, dopo) {
  const cb = h("input", { type: "checkbox", "aria-label": "Segna come completata" }); cb.checked = t.stato === "completata";
  cb.addEventListener("change", async () => {
    try { await api("PUT", "/task/" + t.id, { stato: cb.checked ? "completata" : "da_fare" }); dopo(); } catch (e) { cb.checked = !cb.checked; alert(e.message); }
  });
  return h("div", { class: "task-riga" + (t.stato === "completata" ? " fatta" : "") },
    cb,
    h("div", { class: "task-corpo", tabindex: 0, role: "button", onclick: () => schedaTask(t.id, null, dopo), onkeydown: (e) => { if (e.key === "Enter") schedaTask(t.id, null, dopo); } },
      h("div", { class: "nome" }, (t.padre_titolo ? t.padre_titolo + " › " : "") + t.titolo), chipTask(t)));
}

// Task a livelli: un blocco per progetto (con il colore dell'impresa e del progetto), poi le task senza progetto
function taskPerProgetto(el, carica, chiusi) {
  const gr = new Map();
  el.forEach(t => { const k = t.progetto_id || 0; if (!gr.has(k)) gr.set(k, { t }); (gr.get(k).el = gr.get(k).el || []).push(t); });
  const ordine = [...gr].sort((a, b) => (a[0] === 0) - (b[0] === 0) || String(a[1].t.azienda || "").localeCompare(String(b[1].t.azienda || "")) || String(a[1].t.progetto || "").localeCompare(String(b[1].t.progetto || "")));
  return ordine.map(([k, g]) => {
    const t0 = g.t, colP = t0.progetto_colore || "#7d8a99", colA = t0.azienda_colore || "#7d8a99";
    const d = h("details", { class: "livello", style: "border-left:5px solid " + (k ? colP : "var(--bordo)"), open: !chiusi.has(k) },
      h("summary", {}, k ? [h("span", { class: "punto-col", style: "background:" + colA }), (t0.azienda || "") + " › ", h("span", { class: "punto-col", style: "background:" + colP }), t0.progetto] : "Senza progetto",
        h("span", { class: "sotto" }, "  (" + g.el.length + ")")),
      g.el.map(t => rigaTask(t, carica)));
    d.addEventListener("toggle", () => { d.open ? chiusi.delete(k) : chiusi.add(k); });
    return d;
  });
}

// ---------- Vista completa ----------
function vistaTask() {
  let chi = stato.taskChi || "mie", modo = stato.taskModo || "lista", aperte = stato.taskAperte !== false;
  const corpo = h("div");
  const barra = h("div", { class: "task-barra" });
  const carica = async () => {
    try {
      const el = await api("GET", "/task?chi=" + chi + "&aperte=" + aperte + (modo === "bacheca" ? "&solo_principali=true" : ""));
      if (modo === "bacheca") {
        riempi(corpo, h("div", { class: "bacheca" }, STATI_TASK.filter(([s]) => aperte ? s !== "completata" : true).map(([s, nome]) => {
          const col = el.filter(t => t.stato === s);
          return h("div", { class: "colonna-task" }, h("h3", {}, nome + " (" + col.length + ")"),
            col.length ? col.map(t => h("div", { class: "task-scheda" },
              h("div", { class: "task-corpo", tabindex: 0, role: "button", onclick: () => schedaTask(t.id, null, carica), onkeydown: (e) => { if (e.key === "Enter") schedaTask(t.id, null, carica); } },
                h("div", { class: "nome" }, t.titolo), chipTask(t)),
              h("div", { class: "azioni" },
                s !== "da_fare" ? h("button", { class: "s", "aria-label": "Sposta indietro", onclick: async () => { await api("PUT", "/task/" + t.id, { stato: STATI_TASK[STATI_TASK.findIndex(x => x[0] === s) - 1][0] }); carica(); } }, "◀") : null,
                s !== "completata" ? h("button", { class: "s", "aria-label": "Sposta avanti", onclick: async () => { await api("PUT", "/task/" + t.id, { stato: STATI_TASK[STATI_TASK.findIndex(x => x[0] === s) + 1][0] }); carica(); } }, "▶") : null)))
              : h("p", { class: "sotto" }, "Nessuna task")); })));
        return;
      }
      if (modo === "progetti") { riempi(corpo, el.length ? taskPerProgetto(el, carica, stato.taskChiusi = stato.taskChiusi || new Set()) : h("p", { class: "sotto" }, "Nessuna task.")); return; }
      const gruppi = [[], [], [], [], [], []];
      el.forEach(t => gruppi[gruppoTask(t)].push(t));
      riempi(corpo, el.length ? gruppi.map((g, i) => g.length ? h("div", {}, h("h3", { class: i === 0 ? "scadute" : "" }, NOMI_GRUPPO[i] + " (" + g.length + ")"), g.map(t => rigaTask(t, carica))) : null)
        : h("p", { class: "sotto" }, chi === "mie" ? "Nessuna task assegnata a te. Creane una con «+ Nuova task»." : "Nessuna task."));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  const segm = (valore, corrente, etichetta, imposta) => h("button", { class: corrente === valore ? "p" : "s", onclick: () => { imposta(valore); disegnaBarra(); carica(); } }, etichetta);
  const disegnaBarra = () => riempi(barra, [
    h("div", { class: "gruppo-bottoni" }, segm("mie", chi, "Le mie", v => { chi = stato.taskChi = v; }), segm("tutte", chi, "Tutte", v => { chi = stato.taskChi = v; })),
    h("div", { class: "gruppo-bottoni" }, segm("lista", modo, "Lista", v => { modo = stato.taskModo = v; }), segm("bacheca", modo, "Bacheca", v => { modo = stato.taskModo = v; }), segm("progetti", modo, "Per progetto", v => { modo = stato.taskModo = v; })),
    h("label", { class: "spunta" }, (() => { const c = h("input", { type: "checkbox" }); c.checked = aperte; c.addEventListener("change", () => { aperte = stato.taskAperte = c.checked; carica(); }); return c; })(), "Solo da completare"),
    h("button", { class: "p", style: "margin-left:auto", onclick: () => schedaTask(null, null, carica) }, "+ Nuova task")]);
  disegnaBarra(); carica();
  stato.timer = setInterval(carica, 20000);
  return [h("h2", {}, "Task"), barra, corpo];
}

// ---------- Scheda di una task (si chiude solo con Salva / Chiudi) ----------
async function schedaTask(id, padreId, dopo) {
  let t = null, o;
  try { o = await opzioniTask(); if (id) t = await api("GET", "/task/" + id); } catch (e) { alert(e.message); return; }
  const nuova = !t;
  const d = t || { titolo: "", descrizione: "", stato: "da_fare", priorita: "normale", scadenza: null, progetto_id: null, azienda_id: null,
    assegnato_utente_id: o.io, assegnato_agente_id: null, supporto_agente_id: null, sotto: [], commenti_elenco: [], documenti: [], puo_modificare: true };
  const lettura = !d.puo_modificare;
  const titolo = h("input", { type: "text", maxlength: 200, value: d.titolo, placeholder: "Cosa c'è da fare?" }); titolo.disabled = lettura;
  const desc = h("textarea", { style: "min-height:110px", maxlength: 5000 }); desc.value = d.descrizione || ""; desc.disabled = lettura;
  const sSt = h("select", {}, STATI_TASK.map(([v, n]) => h("option", { value: v }, n))); sSt.value = d.stato; sSt.disabled = lettura;
  const sPr = h("select", {}, PRIORITA_TASK.map(([v, n]) => h("option", { value: v }, n))); sPr.value = d.priorita; sPr.disabled = lettura;
  const sc = h("input", { type: "date" }); sc.value = d.scadenza ? String(d.scadenza).slice(0, 10) : ""; sc.disabled = lettura;
  const ass = h("select", {}, h("option", { value: "" }, "Nessuno"),
    h("optgroup", { label: "Persone" }, o.utenti.map(u => h("option", { value: "u" + u.id }, u.nome + (u.id === o.io ? " (io)" : "")))),
    o.agenti.length ? h("optgroup", { label: "Agenti" }, o.agenti.map(a => h("option", { value: "a" + a.id }, a.etichetta || (a.nome + " — " + a.ruolo)))) : null);
  ass.value = d.assegnato_utente_id ? "u" + d.assegnato_utente_id : d.assegnato_agente_id ? "a" + d.assegnato_agente_id : ""; ass.disabled = lettura;
  const pro = h("select", {}, h("option", { value: "" }, "Nessuno"), o.progetti.map(p => h("option", { value: p.id }, p.nome))); pro.value = d.progetto_id ?? ""; pro.disabled = lettura;
  const azi = h("select", {}, h("option", { value: "" }, "Nessuna"), o.aziende.map(p => h("option", { value: p.id }, p.nome))); azi.value = d.azienda_id ?? ""; azi.disabled = lettura;
  const msg = h("div");
  const sup = h("select", {}, h("option", { value: "" }, "Nessuno"), (o.manager || []).map(m => h("option", { value: m.id }, m.nome + (m.dipartimento ? " — " + m.dipartimento : "") + " — " + m.ruolo)));
  sup.value = d.supporto_agente_id ?? ""; sup.disabled = lettura;
  const nuoviFile = h("input", { type: "file", multiple: true, accept: ".pdf,.docx,.xlsx,.pptx,.odt,.ods,.odp,.rtf,.html,.htm,.json,.xml,.eml,.txt,.md,.csv,.tsv,.png,.jpg,.jpeg,.webp,.gif" });
  const boxDoc = h("div");
  const disegnaDoc = () => riempi(boxDoc, (d.documenti || []).length ? d.documenti.map(x => h("div", { class: "sotto" }, "📎 " + x.nome)) : h("p", { class: "sotto" }, "Nessun documento associato."));
  let chiudi;
  const aggiorna = async () => { if (dopo) await dopo(); };

  const salva = async () => {
    msg.replaceChildren();
    if (!titolo.value.trim()) { msg.append(avviso("Scrivi un titolo.", "no")); return; }
    const corpo = {
      titolo: titolo.value.trim(), descrizione: desc.value.trim() || null, stato: sSt.value, priorita: sPr.value, scadenza: sc.value || null,
      progetto_id: pro.value ? Number(pro.value) : null, azienda_id: azi.value ? Number(azi.value) : null,
      assegnato_utente_id: ass.value.startsWith("u") ? Number(ass.value.slice(1)) : null,
      assegnato_agente_id: ass.value.startsWith("a") ? Number(ass.value.slice(1)) : null,
      supporto_agente_id: sup.value ? Number(sup.value) : null };
    try {
      let tid = id;
      if (nuova) tid = (await api("POST", "/task", { ...corpo, padre_id: padreId })).id;
      else await api("PUT", "/task/" + id, corpo);
      if (nuoviFile.files.length) { const fd = new FormData(); for (const x of nuoviFile.files) fd.append("file", x); await api("POST", "/task/" + tid + "/documenti/carica", fd); }
      chiudi(); await aggiorna();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };

  // sottotask e commenti (solo per una task gia' salvata): agiscono subito
  const boxSotto = h("div"), boxCom = h("div");
  const disegnaSotto = () => riempi(boxSotto, [
    d.sotto.map(s => { const cb = h("input", { type: "checkbox" }); cb.checked = s.stato === "completata";
      cb.addEventListener("change", async () => { try { await api("PUT", "/task/" + s.id, { stato: cb.checked ? "completata" : "da_fare" }); s.stato = cb.checked ? "completata" : "da_fare"; } catch (e) { cb.checked = !cb.checked; msg.replaceChildren(avviso(e.message, "no")); } });
      return h("div", { class: "task-riga" }, cb, h("div", { class: "task-corpo", onclick: () => { chiudi(); schedaTask(s.id, null, dopo); } }, h("div", { class: "nome" }, s.titolo), chipTask(s))); }),
    !lettura ? (() => { const i = h("input", { type: "text", maxlength: 200, placeholder: "Aggiungi una sottotask e premi Invio" });
      i.addEventListener("keydown", async (e) => { if (e.key !== "Enter" || !i.value.trim()) return; e.preventDefault();
        try { await api("POST", "/task", { titolo: i.value.trim(), padre_id: id, assegnato_utente_id: ass.value.startsWith("u") ? Number(ass.value.slice(1)) : null, assegnato_agente_id: ass.value.startsWith("a") ? Number(ass.value.slice(1)) : null });
          d.sotto = (await api("GET", "/task/" + id)).sotto; disegnaSotto(); await aggiorna(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } });
      return i; })() : null]);
  const disegnaCom = () => riempi(boxCom, [
    d.commenti_elenco.map(c => h("div", { class: "voce" }, h("div", { class: "sotto" }, h("b", {}, c.autore), " · " + new Date(c.creato_il).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })), h("div", {}, c.testo))),
    (() => { const i = h("textarea", { style: "min-height:56px", maxlength: 3000, placeholder: "Scrivi un commento…" });
      return h("div", {}, i, h("button", { class: "s", onclick: async () => { if (!i.value.trim()) return;
        try { await api("POST", "/task/" + id + "/commenti", { testo: i.value.trim() }); d.commenti_elenco = (await api("GET", "/task/" + id)).commenti_elenco; disegnaCom(); await aggiorna(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Commenta")); })()]);
  disegnaDoc();
  if (!nuova) { disegnaSotto(); disegnaCom(); }

  chiudi = apriPannello(nuova ? (padreId ? "Nuova sottotask" : "Nuova task") : "Task", [
    lettura ? avviso("Puoi leggere e commentare, ma non modificare questa task.", "avv") : null,
    h("label", {}, "Titolo", titolo), h("label", {}, "Descrizione", desc),
    h("div", { class: "riga" }, h("label", {}, "Stato", sSt), h("label", {}, "Priorità", sPr), h("label", {}, "Scadenza", sc)),
    h("div", { class: "riga" }, h("label", {}, "Assegnata a", ass), h("label", {}, "Progetto", pro), h("label", {}, "Azienda", azi)),
    !nuova && d.assegnato_agente_id ? h("div", { class: "azioni" }, h("span", { class: "sotto" }, "Il lavoro dell'agente è andato bene? "), pollici(d.assegnato_agente_id, "task", id)) : null,
    h("label", {}, "Manager di supporto", sup, h("span", { class: "aiuto" }, "Legge la task e ti scrive nei commenti come la affronterebbe e come alleggerirti il lavoro.")),
    !nuova && d.supporto_agente_id && !lettura ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
      try { await api("POST", "/task/" + id + "/consiglio"); msg.replaceChildren(avviso("Richiesto: il consiglio comparirà nei commenti tra qualche istante.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Chiedi un consiglio al manager")) : null,
    h("h3", {}, "Documenti"), boxDoc,
    lettura ? null : h("label", {}, "Carica uno o più documenti per questa task (PDF, Word, TXT, MD, CSV)", nuoviFile),
    !nuova ? [h("h3", {}, "Sottotask (" + d.sotto.length + ")"), boxSotto, h("h3", {}, "Commenti"), boxCom] : null,
    msg,
    h("div", { class: "azioni" },
      lettura ? null : h("button", { class: "p", onclick: salva }, nuova ? "Crea" : "Salva"),
      h("button", { class: "s", onclick: () => chiudi() }, lettura ? "Chiudi" : "Annulla"),
      (!nuova && (stato.ruolo === "titolare" || d.creato_da_utente_id === o.io)) ? h("button", { class: "s", style: "margin-left:auto", onclick: async () => {
        if (!confirm("Eliminare questa task e le sue sottotask?")) return;
        try { await api("DELETE", "/task/" + id); chiudi(); await aggiorna(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina") : null)]);
}

// ---------- Blocco "Da fare" della Dashboard ----------
function pannelloDaFare() {
  const box = h("div", { class: "pan-corpo" }, h("p", { class: "sotto" }, "Caricamento…"));
  const carica = async () => {
    try {
      const el = await api("GET", "/task?chi=mie&aperte=true");
      riempi(box, el.length ? [el.some(t => t.progetto_id) ? taskPerProgetto(el.slice(0, 12), carica, stato.taskChiusi = stato.taskChiusi || new Set()) : el.slice(0, 7).map(t => rigaTask(t, carica)),
        el.length > (el.some(t => t.progetto_id) ? 12 : 7) ? h("button", { class: "s", onclick: () => vai("task") }, "Vedi tutte (" + el.length + ")") : null]
        : h("p", { class: "sotto" }, "Nessuna task da fare. Quando te ne assegnano una la trovi qui, in ordine di scadenza."));
    } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return { el: pannello("Da fare", box, h("button", { class: "s", onclick: () => schedaTask(null, null, carica) }, "+ Task")), ricarica: carica };
}
