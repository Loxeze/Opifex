"use strict";
// Chat a conversazioni: una per agente, in ordine di ultima attività, a tutto schermo. Cronologia, non letti e bozza stanno sul server:
// aggiornando o chiudendo la pagina si riparte da dove si era.

function tempoChat(iso) {
  if (!iso) return "";
  const d = new Date(iso), oggi = new Date();
  if (d.toDateString() === oggi.toDateString()) return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const ieri = new Date(oggi.getTime() - 86400000);
  if (d.toDateString() === ieri.toDateString()) return "ieri";
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}
function giornoChat(iso) { return new Date(iso).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" }); }
function memLocale(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* ignora */ } return null; }

// Salva la bozza anche mentre la pagina si chiude (fetch con keepalive: parte comunque).
function salvaBozzaSospesa() {
  const b = stato.bozzaSospesa;
  if (!b || !token) return;
  stato.bozzaSospesa = null;
  try { fetch("/chat/conversazioni/" + b.agenteId + "/bozza", { method: "PUT", keepalive: true, headers: { "Content-Type": "application/json", Authorization: "Bearer " + token }, body: JSON.stringify({ testo: b.testo, fascia: b.fascia }) }); } catch (e) { /* ignora */ }
}
window.addEventListener("pagehide", salvaBozzaSospesa);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") salvaBozzaSospesa(); });

// Numero di risposte non lette, sul pulsante «Chat» del menu.
function avviaConteggioChat() {
  if (stato.timerChat) return;
  const giro = async () => {
    if (!token) return;
    try {
      const r = await api("GET", "/chat/non-letti");
      stato.chatNonLetti = r.totale;
      const b = document.getElementById("badge-chat");
      if (b) { b.textContent = r.totale ? String(r.totale) : ""; b.style.display = r.totale ? "" : "none"; }
    } catch (e) { /* riprova */ }
  };
  giro(); stato.timerChat = setInterval(giro, 20000);
}

function vistaChat() {
  const collab = stato.ruolo !== "titolare";
  const tabs = [["chat", "Conversazioni"]].concat(collab ? [] : [["riunioni", "Riunioni"], ["dialoghi", "Dialoghi tra agenti"], ["richieste", "Richieste" + (stato.richieste ? " (" + stato.richieste + ")" : "")]]);
  if (!tabs.some(([id]) => id === stato.chatTab)) stato.chatTab = "chat";
  const corpo = h("div", { class: "chat-corpo" });
  const barra = h("div", { class: "azioni", style: "margin:0 0 10px" }, h("h2", { style: "flex:1;margin:0" }, "Chat"),
    tabs.length > 1 ? tabs.map(([id, nome]) => h("button", { class: stato.chatTab === id ? "p" : "s", onclick: () => { stato.chatTab = id; disegna(); } }, nome)) : null,
    collab ? null : bottoneAllinea());
  if (stato.chatTab === "dialoghi") {
    const riep = h("div", { class: "riga", style: "margin-bottom:12px" }), lavoro = h("div");
    const num = (v, et) => h("div", { class: "carta", style: "text-align:center" }, h("div", { class: "nome" }, String(v)), h("div", { class: "sotto" }, et));
    const aggiorna = async () => {
      try {
        const r = await api("GET", "/gestione/dialoghi/riepilogo");
        riempi(riep, [num(r.conversazioni + " (" + r.aperte + " aperte)", "conversazioni"), num(r.messaggi + " (" + r.messaggi_oggi + " oggi)", "messaggi tra agenti"),
          num(r.token_oggi.toLocaleString("it-IT") + " / " + r.budget_token.toLocaleString("it-IT"), "token dialoghi oggi / budget"),
          num(r.secondi_medi_tra_messaggi === null ? "–" : r.secondi_medi_tra_messaggi + " s", "tempo medio tra messaggi (7 giorni)")]);
        const l = await api("GET", "/gestione/richieste/lavoro");
        riempi(lavoro, l.length ? l.map(x => avviso(x.agente + " sta lavorando… (" + x.da_secondi + " s) · " + x.motivo, "ok")) : []);
      } catch (e) { /* riprova */ }
    };
    aggiorna(); stato.timer2 = setInterval(aggiorna, 6000);
    return [barra, riep, lavoro, vistaDialoghi(true)];
  }
  if (stato.chatTab === "richieste") return [barra, pannelloRichieste(() => {})];
  if (stato.chatTab === "riunioni") return [barra, vistaRiunioniCall()];
  corpo.append(...conversazioniChat());
  return [barra, corpo];
}

function conversazioniChat() {
  const attivi = stato.agenti.filter(a => a.attivo);
  const perId = new Map(stato.agenti.map(a => [a.id, a]));
  const S = { agenteId: null, messaggi: [], altri: false, firma: "", elenco: [], pendenti: new Set(), nuova: false };
  const lista = h("div", { class: "chat-lista-voci" });
  const pannelloNuova = h("div", { class: "chat-nuova", style: "display:none" });
  const testata = h("div", { class: "chat-testata" });
  const messaggiEl = h("div", { class: "chat-messaggi" });
  const msg = h("div");
  const testo = h("textarea", { placeholder: "Scrivi il messaggio… (Invio per inviare, Maiusc+Invio per andare a capo)", rows: 2 });
  const f = h("select", { title: "Tipo di dati nel messaggio" }, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t)));
  f.value = stato.chatFascia || "pubblico";
  f.addEventListener("change", () => { stato.chatFascia = f.value; bozzaCambiata(); });
  const allegati = h("input", { type: "file", multiple: true, style: "display:none", accept: ".pdf,.docx,.xlsx,.pptx,.odt,.ods,.odp,.rtf,.html,.htm,.json,.xml,.fcpxml,.edl,.srt,.vtt,.eml,.txt,.md,.csv,.tsv,.png,.jpg,.jpeg,.webp,.gif" });
  const elencoAll = h("span", { class: "sotto" });
  allegati.addEventListener("change", () => { elencoAll.textContent = allegati.files.length ? [...allegati.files].map(x => x.name).join(", ") : ""; });
  const bAllega = h("button", { class: "s", type: "button", title: "Allega file (fino a 5, 10 MB ciascuno)", onclick: () => allegati.click() }, "📎");
  const bInvia = h("button", { class: "p" }, "Invia");
  const bMic = h("button", { class: "s", type: "button", title: "Detta il messaggio con la voce" }, "🎤");
  const stile = (ascolto) => { bMic.textContent = ascolto ? "⏹" : "🎤"; bMic.classList.toggle("p", !!ascolto); };
  const modoVoce = h("select", {}, h("option", { value: "browser" }, "Browser (gratuito)"), h("option", { value: "server" }, "Server con OpenAI (più affidabile)"));
  modoVoce.value = Voce.modo;
  modoVoce.addEventListener("change", () => { Voce.modo = modoVoce.value; });
  const leggi = h("input", { type: "checkbox" }); leggi.checked = Voce.leggiRisposte;
  leggi.addEventListener("change", () => { Voce.leggiRisposte = leggi.checked; });
  const viva = h("input", { type: "checkbox" }); viva.checked = Voce.viva;
  const vocale = Voce.supportoDettatura || Voce.supportoLettura;

  // ----- bozza salvata sul server mentre si scrive -----
  let timerBozza = null;
  const bozzaCambiata = () => {
    if (!S.agenteId) return;
    const b = { agenteId: S.agenteId, testo: testo.value, fascia: f.value };
    stato.bozzaSospesa = b;
    clearTimeout(timerBozza);
    timerBozza = setTimeout(() => { if (stato.bozzaSospesa === b) { stato.bozzaSospesa = null; api("PUT", "/chat/conversazioni/" + b.agenteId + "/bozza", { testo: b.testo, fascia: b.fascia }).catch(() => {}); } }, 700);
  };
  testo.addEventListener("input", bozzaCambiata);

  // ----- messaggi -----
  const bolla = (m) => {
    const out = [];
    const allegatiTxt = (m.allegati || []).length ? "\n📎 " + m.allegati.join(", ") : "";
    if (m.canale === "ronda") out.push(h("div", { class: "chat-giorno" }, "🔔 Ronda automatica sui progetti · " + tempoChat(m.creato_il)));
    else out.push(h("div", { class: "bolla mia" }, h("div", { class: "risposta" }, m.messaggio + allegatiTxt), h("div", { class: "ora" }, (m.canale === "telegram" ? "📱 da Telegram · " : "") + tempoChat(m.creato_il))));
    if (m.stato === "in_coda" || m.stato === "in_lavoro") {
      out.push(h("div", { class: "bolla loro attesa" }, h("div", { class: "sotto" }, "⏳ " + (S.nomeAgente || "L'agente") + (m.stato === "in_lavoro" ? " sta scrivendo…" : " risponderà appena è libero…"))));
    } else if (m.stato === "errore") {
      out.push(h("div", { class: "bolla loro errore" }, h("div", { class: "risposta" }, "⚠️ " + (m.errore || "Risposta non riuscita")), h("div", { class: "ora" }, tempoChat(m.finito_il))));
    } else if (m.risposta !== null && m.risposta !== undefined) {
      const avvAll = (m.allegati_troncati || []).length ? ["File letti solo in parte perché lunghi: " + m.allegati_troncati.join(", ")] : [];
      out.push(h("div", { class: "bolla loro" },
        h("div", { class: "risposta" }, m.risposta),
        (m.file || []).length ? h("div", { class: "azioni" }, ...m.file.map(x => h("a", { href: x.link || "#", target: "_blank", rel: "noopener", class: "s", style: "text-decoration:none;padding:4px 10px;border:1px solid var(--bordo);border-radius:6px" }, "📎 " + x.nome))) : null,
        h("div", { class: "azioni" }, pollici(S.agenteId, "chat", null), Voce.supportoLettura ? h("button", { class: "s", type: "button", onclick: () => Voce.leggi(m.risposta) }, "🔊") : null),
        (m.usati || []).length ? h("div", { class: "sotto" }, "Documenti consultati: " + m.usati.join(", ")) : null,
        (m.esclusi || []).length ? avviso("Non consultati per riservatezza: " + m.esclusi.join(", "), "avv") : null,
        (m.avvisi || []).concat(avvAll).map(t => avviso(t, "avv")),
        h("div", { class: "ora" }, tempoChat(m.finito_il) + (m.token ? " · " + m.token + " token" : ""))));
    }
    return out;
  };
  const vaiFondo = h("button", { class: "s chat-fondo", type: "button", "aria-label": "Vai all'ultimo messaggio", hidden: true, onclick: () => { messaggiEl.scrollTop = messaggiEl.scrollHeight; } }, "↓ Ultimo messaggio");
  messaggiEl.addEventListener("scroll", () => { vaiFondo.hidden = messaggiEl.scrollHeight - messaggiEl.scrollTop - messaggiEl.clientHeight < 200; }, { passive: true });
  const disegnaMessaggi = (scendi) => {
    const vicino = messaggiEl.scrollHeight - messaggiEl.scrollTop - messaggiEl.clientHeight < 80;
    const el = [];
    if (S.altri) el.push(h("div", { style: "text-align:center" }, h("button", { class: "s", onclick: piuVecchi }, "Messaggi precedenti")));
    if (!S.messaggi.length) el.push(h("p", { class: "sotto", style: "text-align:center;margin:30px 0" }, "Nessun messaggio ancora: scrivi qui sotto per iniziare."));
    let giorno = "";
    for (const m of S.messaggi) {
      const g = giornoChat(m.creato_il);
      if (g !== giorno) { giorno = g; el.push(h("div", { class: "chat-giorno" }, g)); }
      el.push(...bolla(m));
    }
    const prima = messaggiEl.scrollHeight - messaggiEl.scrollTop;
    messaggiEl.replaceChildren(...el);
    if (scendi || vicino) messaggiEl.scrollTop = messaggiEl.scrollHeight; else messaggiEl.scrollTop = messaggiEl.scrollHeight - prima;
  };
  const piuVecchi = async () => {
    if (!S.messaggi.length) return;
    try {
      const r = await api("GET", "/chat/conversazioni/" + S.agenteId + "?prima_di=" + S.messaggi[0].id);
      S.messaggi = r.messaggi.concat(S.messaggi); S.altri = r.altri; S.firma = ""; disegnaMessaggi(false);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const firmaDi = (ms) => ms.map(m => m.id + m.stato).join(",");
  const aggiornaConversazione = async (primaVolta) => {
    if (!S.agenteId) return;
    const id = S.agenteId;
    try {
      const r = await api("GET", "/chat/conversazioni/" + id);
      if (id !== S.agenteId) return;
      S.nomeAgente = r.agente.nome;
      const precedenti = S.pendenti; S.pendenti = new Set(r.messaggi.filter(m => m.stato === "in_coda" || m.stato === "in_lavoro").map(m => m.id));
      const nuove = r.messaggi.filter(m => precedenti.has(m.id) && m.stato === "finito" && m.risposta && !m.risposta.startsWith("⚠️"));
      const firma = firmaDi(r.messaggi);
      if (primaVolta) {
        if (!testo.value && r.bozza) testo.value = r.bozza;
        if (r.fascia) { f.value = r.fascia; }
        testo.disabled = false;
      }
      if (firma !== S.firma || primaVolta) {
        const aggiunti = firma !== S.firma;
        S.messaggi = r.messaggi; S.altri = r.altri; S.firma = firma;
        disegnaMessaggi(primaVolta);
        if (aggiunti && document.visibilityState === "visible") api("POST", "/chat/conversazioni/" + id + "/letto").then(aggiornaElenco).catch(() => {});
      }
      if (nuove.length && (Voce.leggiRisposte || Voce.viva)) Voce.leggi(nuove[nuove.length - 1].risposta, () => { if (Voce.viva && Voce.avviaAscolto) Voce.avviaAscolto(); });
    } catch (e) { if (primaVolta) msg.replaceChildren(avviso(e.message, "no")); }
  };

  // ----- elenco conversazioni -----
  const riga = (c) => {
    const a = perId.get(c.agente_id);
    const anteprima = c.ha_bozza && c.agente_id !== S.agenteId ? "✎ Bozza non inviata" : (c.ultimo_stato === "finito" && c.ultima_risposta) ? c.ultima_risposta : c.ultimo_messaggio ? "Tu: " + c.ultimo_messaggio : "";
    return h("button", { class: "chat-voce" + (c.agente_id === S.agenteId ? " aperta" : ""), type: "button", onclick: () => apri(c.agente_id, true) },
      h("div", { class: "chat-sigla" }, (c.nome || "?").slice(0, 1).toUpperCase()),
      h("div", { class: "chat-voce-testo" },
        h("div", { class: "chat-voce-nome" }, h("span", {}, c.nome), h("span", { class: "ora" }, tempoChat(c.ultima_attivita))),
        h("div", { class: "chat-voce-anteprima" }, (c.in_attesa > 0 ? "⏳ " : "") + anteprima)),
      c.non_letti > 0 && c.agente_id !== S.agenteId ? h("span", { class: "badge-chat" }, String(c.non_letti)) : null);
  };
  const disegnaElenco = () => {
    lista.replaceChildren(...(S.elenco.length ? S.elenco.map(riga) : [h("p", { class: "sotto", style: "padding:12px" }, "Nessuna conversazione ancora. Premi «＋ Nuova» e scegli un agente.")]));
  };
  const aggiornaElenco = async () => {
    try {
      S.elenco = await api("GET", "/chat/conversazioni");
      if (S.agenteId && !S.elenco.some(c => c.agente_id === S.agenteId)) S.elenco.unshift({ agente_id: S.agenteId, nome: S.nomeAgente || (perId.get(S.agenteId) || {}).nome || "", in_attesa: 0, non_letti: 0 });
      disegnaElenco();
    } catch (e) { /* riprova */ }
  };

  const apri = async (id, daClick) => {
    if (S.agenteId === id) { if (daClick) { const ap = document.querySelector(".chat-app"); if (ap) ap.classList.add("aperta-mobile"); } return; }
    if (stato.bozzaSospesa) { clearTimeout(timerBozza); salvaBozzaSospesa(); }
    S.agenteId = id; S.messaggi = []; S.firma = ""; S.pendenti = new Set(); stato.chatAgente = id; memLocale("chatAgente", String(id));
    testo.value = ""; msg.replaceChildren(); allegati.value = ""; elencoAll.textContent = "";
    const a = perId.get(id);
    S.nomeAgente = a ? a.nome : "";
    riempi(testata, [h("button", { class: "s chat-indietro", type: "button", onclick: () => document.querySelector(".chat-app").classList.remove("aperta-mobile") }, "‹"),
      h("div", { class: "chat-sigla" }, (S.nomeAgente || "?").slice(0, 1).toUpperCase()),
      h("div", {}, h("div", { class: "nome" }, S.nomeAgente), h("div", { class: "sotto" }, a ? a.ruolo : ""))]);
    pannelloNuova.style.display = "none";
    const app = document.querySelector(".chat-app"); if (app && daClick) app.classList.add("aperta-mobile");
    messaggiEl.replaceChildren(h("p", { class: "sotto", style: "text-align:center" }, "Caricamento…"));
    disegnaElenco();
    await aggiornaConversazione(true);
    try { await api("POST", "/chat/conversazioni/" + id + "/letto"); } catch (e) { /* ignora */ }
    aggiornaElenco();
    const fondo = () => { messaggiEl.scrollTop = messaggiEl.scrollHeight; };   // si apre sull'ultimo messaggio, anche dopo il ridisegno del telefono
    fondo(); requestAnimationFrame(fondo); setTimeout(fondo, 150); setTimeout(fondo, 600);
    if (!(window.matchMedia && matchMedia("(pointer:coarse)").matches)) testo.focus();   // sul telefono la tastiera non si apre da sola: copriva i messaggi
  };

  // ----- nuova conversazione: ricerca tra gli agenti attivi -----
  const cerca = h("input", { type: "search", placeholder: "Cerca un agente…" });
  const risultati = h("div", { class: "chat-lista-voci", style: "max-height:260px;overflow:auto" });
  const filtra = () => {
    const q = cerca.value.trim().toLowerCase();
    const trovati = attivi.filter(a => !q || (a.nome + " " + a.ruolo + " " + (a.divisione || "")).toLowerCase().includes(q)).slice(0, 40);
    riempi(risultati, trovati.map(a => h("button", { class: "chat-voce", type: "button", onclick: () => apri(a.id, true) }, h("div", { class: "chat-sigla" }, a.nome.slice(0, 1).toUpperCase()),
      h("div", { class: "chat-voce-testo" }, h("div", { class: "chat-voce-nome" }, a.nome), h("div", { class: "chat-voce-anteprima" }, a.ruolo)))));
  };
  cerca.addEventListener("input", filtra);
  pannelloNuova.append(cerca, risultati);
  const bNuova = h("button", { class: "p", type: "button", onclick: () => { const v = pannelloNuova.style.display === "none"; pannelloNuova.style.display = v ? "" : "none"; if (v) { cerca.value = ""; filtra(); cerca.focus(); } } }, "＋ Nuova");

  // ----- invio -----
  const invia = async () => {
    if (!S.agenteId || (!testo.value.trim() && !allegati.files.length)) return;
    msg.replaceChildren(); Voce.ferma();
    bInvia.disabled = true; bInvia.textContent = "Invio…";
    const id = S.agenteId;
    try {
      if (allegati.files.length) {
        const fd = new FormData(); fd.append("messaggio", testo.value); fd.append("fascia_dati", f.value); fd.append("asincrono", "true");
        for (const x of allegati.files) fd.append("file", x);
        await api("POST", "/agenti/" + id + "/chat-allegati", fd);
      } else await api("POST", "/agenti/" + id + "/chat", { messaggio: testo.value, fascia_dati: f.value, asincrono: true });
      testo.value = ""; allegati.value = ""; elencoAll.textContent = ""; clearTimeout(timerBozza); stato.bozzaSospesa = null;
      api("PUT", "/chat/conversazioni/" + id + "/bozza", { testo: "", fascia: f.value }).catch(() => {});
      await aggiornaConversazione(false); S.firma = ""; await aggiornaConversazione(false);
      messaggiEl.scrollTop = messaggiEl.scrollHeight;
      aggiornaElenco();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); Voce.viva = false; }
    bInvia.disabled = false; bInvia.textContent = "Invia";
  };
  bInvia.addEventListener("click", invia);
  testo.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); invia(); } });

  // ----- voce -----
  const ascolta = () => {
    const fineAscolto = (t) => { stile(false); if (Voce.viva && t) invia(); else if (Voce.viva && stato.vista === "chat") setTimeout(() => Voce.viva && Voce.avviaAscolto && Voce.avviaAscolto(), 400); };
    const statoAscolto = (s) => { if (s === null) stile(false); else if (s === "ascolto") { stile(true); msg.replaceChildren(); } else if (s === "trascrivo") msg.replaceChildren(avviso("Trascrivo la registrazione…", "ok")); else if (s) msg.replaceChildren(avviso(s, "avv")); };
    if (Voce.modo === "server") {
      if (!Voce.registra(testo, fineAscolto, statoAscolto, f.value)) msg.replaceChildren(avviso("Questo browser non può registrare dal microfono.", "avv"));
      return;
    }
    if (!Voce.ascolta(testo, fineAscolto, statoAscolto)) msg.replaceChildren(avviso("Il tuo browser non supporta la dettatura vocale: usa Chrome, Edge o Safari.", "avv"));
  };
  Voce.avviaAscolto = ascolta;
  bMic.addEventListener("click", () => { if (Voce.inAscolto()) { Voce.viva = false; Voce.termina(); stile(false); } else ascolta(); });
  viva.addEventListener("change", () => { Voce.viva = viva.checked; if (viva.checked) ascolta(); else { Voce.ferma(); Voce.fermaLettura(); stile(false); } });
  if (Voce.viva && vocale && !Voce.inAscolto() && !(Voce.supportoLettura && speechSynthesis.speaking)) setTimeout(ascolta, 300);

  // ----- avvio: riprende l'ultima conversazione aperta e tiene tutto aggiornato -----
  (async () => {
    await aggiornaElenco();
    const ricordato = Number(memLocale("chatAgente")) || stato.chatAgente;
    const scelto = (stato.chatAgente && S.elenco.some(c => c.agente_id === stato.chatAgente)) ? stato.chatAgente
      : (ricordato && S.elenco.some(c => c.agente_id === ricordato)) ? ricordato : (S.elenco[0] && S.elenco[0].agente_id);
    if (scelto) await apri(scelto);
    else { const app = document.querySelector(".chat-app"); if (app) app.classList.remove("aperta-mobile"); riempi(messaggiEl, [h("p", { class: "sotto", style: "text-align:center;margin:40px 0" }, "Scegli un agente con «＋ Nuova» per iniziare una conversazione.")]); testo.disabled = true; }
  })();
  stato.timer2 = setInterval(async () => {
    if (stato.vista !== "chat") return;
    await aggiornaElenco();
    if (S.agenteId) await aggiornaConversazione(false);
  }, 4000);

  const compositore = h("div", { class: "chat-compositore" }, msg,
    h("div", { class: "chat-riga-invio" }, bAllega, allegati, testo, vocale && Voce.supportoDettatura ? bMic : null, bInvia),
    h("div", { class: "chat-opzioni" }, f, elencoAll,
      vocale ? h("details", { style: "margin-left:auto" }, h("summary", { class: "sotto" }, "Voce"),
        h("div", { class: "interruttore" }, leggi, h("span", {}, "Leggi ad alta voce le risposte")),
        Voce.supportoDettatura ? h("div", { class: "interruttore" }, viva, h("span", {}, "Vivavoce: parli, il messaggio parte quando smetti, l'agente risponde a voce e riascolta")) : null,
        h("label", {}, "Trascrizione della voce", modoVoce), provaMicrofono(),
        h("button", { class: "s", type: "button", onclick: () => { Voce.fermaTutto(); viva.checked = false; stile(false); } }, "⏹ Silenzio")) : null));
  return [h("div", { class: "chat-app" },
    h("div", { class: "chat-lista" }, h("div", { class: "chat-lista-testa" }, h("strong", {}, "Conversazioni"), bNuova), pannelloNuova, lista),
    h("div", { class: "chat-conv" }, testata, messaggiEl, vaiFondo, compositore))];
}

// ---------- ripartire da dove si era: ultima pagina aperta ----------
function etichettaVista() { return stato.vista + (stato.vista === "impostazioni" && stato.sezione ? ":" + stato.sezione : ""); }
function ricordaVista() {
  if ((VISTE.concat(VISTE_COLLABORATORE)).some(([id]) => id === stato.vista)) { memLocale("vista", stato.vista); memLocale("sezione", stato.sezione || null); }
}
function ripristinaVista() {
  if (stato.vistaRipristinata) return;
  stato.vistaRipristinata = true;
  const v = memLocale("vista"), s = memLocale("sezione");
  const ammesse = stato.ruolo === "titolare" ? VISTE : VISTE_COLLABORATORE;
  if (v && ammesse.some(([id]) => id === v)) { stato.vista = v; if (s && SEZIONI_IMPOSTAZIONI.some(([id]) => id === s)) stato.sezione = s; }
}

// ---------- come si usa la piattaforma: solo nomi delle pagine ed errori mostrati, mai i contenuti ----------
const codaUso = [];
function registraUso(vista, azione) { if (token && codaUso.length < 60) codaUso.push({ vista: String(vista).toLowerCase().replace(/[^a-z0-9_:\-]/g, "").slice(0, 60) || "x", azione }); }
async function inviaUso(finePagina) {
  if (!token || !codaUso.length) return;
  const eventi = codaUso.splice(0, 30);
  try {
    if (finePagina) fetch("/uso", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json", Authorization: "Bearer " + token }, body: JSON.stringify({ eventi }) });
    else await api("POST", "/uso", { eventi });
  } catch (e) { /* si perde qualche osservazione: non importa */ }
}
function avviaUso() {
  if (stato.timerUso) return;
  stato.timerUso = setInterval(() => inviaUso(false), 20000);
  window.addEventListener("pagehide", () => inviaUso(true));
}
