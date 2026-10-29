"use strict";
// Riunioni vocali con i manager (Chat → Riunioni): si creano, si lancia la call, ogni manager risponde con la sua voce.

const CallVoce = {
  server: false, attiva: true, audio: null,
  voceBrowser(agenteId) {
    const it = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter(v => v.lang && v.lang.toLowerCase().startsWith("it"));
    return { voce: it.length ? it[agenteId % it.length] : null, tono: 0.75 + (agenteId % 6) * 0.11, ritmo: 0.92 + (agenteId % 4) * 0.05 };
  },
  async parla(agenteId, testo) {
    if (!this.attiva) return;
    if (this.server) {
      try {
        const r = await fetch("/voce/leggi", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: JSON.stringify({ testo: testo.slice(0, 4400), agente_id: agenteId }) });
        if (r.ok) {
          const url = URL.createObjectURL(await r.blob());
          await new Promise((ok) => { const a = new Audio(url); this.audio = a; a.onended = a.onerror = () => { URL.revokeObjectURL(url); this.audio = null; ok(); }; a.play().catch(() => ok()); });
          return;
        }
      } catch (e) { /* ripiego sulla voce del browser */ }
    }
    if (!("speechSynthesis" in window)) return;
    const c = this.voceBrowser(agenteId);
    await new Promise((ok) => { const u = new SpeechSynthesisUtterance(testo.slice(0, 1500)); u.lang = "it-IT"; if (c.voce) u.voice = c.voce; u.pitch = c.tono; u.rate = c.ritmo; u.onend = u.onerror = () => ok(); speechSynthesis.speak(u); });
  },
  ferma() { if (this.audio) { this.audio.pause(); this.audio = null; } if ("speechSynthesis" in window) speechSynthesis.cancel(); },
};

function pannelloVociManager() {
  const box = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/voci-manager");
      CallVoce.server = d.elevenlabs;
      riempi(box, [d.errore ? avviso(d.errore, "no") : null,
        h("p", { class: "aiuto" }, d.elevenlabs ? "Ogni manager parla con una voce ElevenLabs diversa. Puoi cambiarla qui." : "ElevenLabs non è collegato (Impostazioni → Voce): uso le voci del browser, con tono e ritmo diversi per ogni manager."),
        d.elevenlabs ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/gestione/voci-manager/auto"); msg.replaceChildren(avviso(r.sintesi, "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Assegna le voci mancanti")) : null,
        d.manager.map(m => {
          const sel = h("select", {}, h("option", { value: "" }, d.elevenlabs ? "— voce predefinita —" : "voce del browser"), d.voci.map(v => h("option", { value: v.id }, v.nome)));
          sel.value = m.voce_id || "";
          sel.addEventListener("change", async () => { try { await api("PUT", "/gestione/voci-manager/" + m.id, { voce_id: sel.value || null }); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } });
          return h("div", { class: "riga", style: "align-items:center;margin-bottom:4px" }, h("span", { style: "min-width:150px" }, m.nome), d.elevenlabs ? sel : null,
            pulsanteAscoltaVoce(m));
        })]);
    } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("details", { class: "carta", style: "margin-bottom:12px" }, h("summary", {}, "Voci dei manager"), box, msg);
}

function pulsanteAscoltaVoce(m) {
  return h("button", { class: "s", type: "button", onclick: () => CallVoce.parla(m.id, "Ciao Lorenzo, sono " + m.nome + ". Questa è la mia voce nelle riunioni.") }, "▶ Prova");
}

function vistaRiunioniCall() {
  const corpo = h("div");
  const apri = (id) => { corpo.replaceChildren(schermataCall(id, () => { schermaElenco(); })); };
  const schermaElenco = async () => {
    const msg = h("div"), lista = h("div");
    const titolo = h("input", { maxlength: 200, placeholder: "Titolo della riunione" });
    const odg = h("textarea", { style: "min-height:70px", placeholder: "Argomenti (facoltativo): di cosa vuoi parlare con i manager" });
    const quando = h("input", { type: "datetime-local" });
    const scelti = h("div", { class: "riga", style: "flex-wrap:wrap" });
    let manager = [];
    try { manager = (await api("GET", "/gestione/riunioni-call/manager")).manager; CallVoce.server = (await api("GET", "/gestione/voci-manager")).elevenlabs; } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    const caselle = manager.map(m => { const c = h("input", { type: "checkbox" }); return [m, c, h("label", { class: "interruttore", style: "margin-right:12px" }, c, h("span", {}, m.nome + (m.reparto ? " (" + m.reparto + ")" : "")))]; });
    scelti.append(...caselle.map(x => x[2]));
    const carica = async () => {
      try {
        const d = await api("GET", "/gestione/riunioni-call");
        riempi(lista, d.riunioni.length ? d.riunioni.map(r => h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, r.titolo),
          h("div", { class: "sotto" }, [{ programmata: "Programmata", in_corso: "In corso", conclusa: "Conclusa", errore: "Errore" }[r.stato], r.programmata_il ? new Date(r.programmata_il).toLocaleString("it-IT") : "", r.partecipanti].filter(Boolean).join(" · ")),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { if (r.stato === "programmata") await api("POST", "/gestione/riunioni-call/" + r.id + "/avvia"); apri(r.id); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } },
            r.stato === "conclusa" || r.stato === "errore" ? "Apri verbale" : r.stato === "in_corso" ? "Rientra nella call" : "Avvia la call")))) : h("p", { class: "sotto" }, "Nessuna riunione ancora."));
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    };
    riempi(corpo, [pannelloVociManager(), h("h3", {}, "Nuova riunione"), titolo, odg, h("label", {}, "Quando (facoltativo)", quando), h("p", { class: "aiuto" }, "Chi partecipa:"), scelti,
      h("div", { class: "azioni" },
        h("button", { class: "p", onclick: async () => {
          const part = caselle.filter(x => x[1].checked).map(x => x[0].nome);
          try { const r = await api("POST", "/gestione/riunioni-call", { titolo: titolo.value.trim(), ordine_del_giorno: odg.value.trim(), partecipanti: part, programmata_il: quando.value ? new Date(quando.value).toISOString() : null });
            titolo.value = odg.value = ""; msg.replaceChildren(avviso("Riunione creata.", "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea la riunione"),
        h("button", { class: "s", onclick: async () => {
          const part = caselle.filter(x => x[1].checked).map(x => x[0].nome);
          try { const r = await api("POST", "/gestione/riunioni-call", { titolo: titolo.value.trim() || "Riunione del " + new Date().toLocaleDateString("it-IT"), ordine_del_giorno: odg.value.trim(), partecipanti: part });
            await api("POST", "/gestione/riunioni-call/" + r.id + "/avvia"); apri(r.id); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea e lancia subito la call")),
      msg, h("h3", {}, "Le tue riunioni"), lista]);
    carica();
  };
  schermaElenco();
  return corpo;
}

function schermataCall(tid, esci) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let ultimo = 0, coda = [], parlando = false, vivo = true, riunione = null, ascolto = null, continuo = false, occupato = false;
  const tessere = h("div", { class: "riga", style: "flex-wrap:wrap;gap:10px;margin-bottom:10px" });
  const log = h("div", { style: "max-height:46vh;overflow:auto;margin-bottom:10px" });
  const stato = h("div", { class: "sotto" }), msg = h("div");
  const campo = h("input", { placeholder: "Parla o scrivi: nomina un manager per rivolgerti solo a lui", maxlength: 4000, style: "flex:1" });
  const bMic = h("button", { class: "s", type: "button", title: "Parla" }, "🎤");
  const bInvia = h("button", { class: "p", type: "button" }, "Invia");
  const tessera = {};
  const evidenzia = (id, on) => { const t = tessera[id]; if (t) t.style.outline = on ? "3px solid #3fd3c0" : "none"; };
  const riga = (chi, testo, utente) => { log.append(h("div", { class: "risposta", style: "margin-bottom:6px;white-space:pre-wrap" + (utente ? ";border-left:3px solid #f3b54a" : "") }, h("b", {}, chi + ": "), testo)); log.scrollTop = log.scrollHeight; };
  const nomeDi = (id) => ((riunione.partecipanti.find(p => p.id === id) || {}).nome) || "?";

  const ferma = () => { if (ascolto) { try { ascolto.abort(); } catch (e) { /* già fermo */ } ascolto = null; bMic.textContent = "🎤"; } };
  const ascolta = () => {
    if (!SR || ascolto || parlando || occupato || !vivo) return;
    const r = new SR(); r.lang = "it-IT"; r.interimResults = false; r.continuous = false; ascolto = r; bMic.textContent = "⏺";
    r.onresult = (e) => { const t = Array.from(e.results).map(x => x[0].transcript).join(" ").trim(); if (t) { campo.value = t; invia(); } };
    r.onend = r.onerror = () => { ascolto = null; bMic.textContent = "🎤"; if (continuo && vivo && !parlando && !occupato) setTimeout(ascolta, 400); };
    try { r.start(); } catch (e) { ascolto = null; }
  };
  const riproduci = async () => {
    if (parlando) return; parlando = true; ferma();
    while (coda.length && vivo) { const i = coda.shift(); evidenzia(i.agente_id, true); stato.textContent = nomeDi(i.agente_id) + " sta parlando…"; await CallVoce.parla(i.agente_id, i.testo); evidenzia(i.agente_id, false); }
    parlando = false; stato.textContent = occupato ? "I manager stanno pensando…" : "Tocca a te."; if (continuo && !occupato) ascolta();
  };
  const sondaggio = async () => {
    if (!vivo) return;
    if (!document.body.contains(log)) { vivo = false; CallVoce.ferma(); ferma(); return; }
    try {
      const d = await api("GET", "/gestione/riunioni-call/" + tid + "?dopo=" + ultimo);
      riunione = riunione || d; occupato = d.occupato;
      for (const i of d.interventi) { ultimo = Math.max(ultimo, i.id); if (i.da_utente) { /* gia' mostrato quando l'hai inviato */ } else { riga(nomeDi(i.agente_id), i.testo, false); coda.push(i); } }
      if (coda.length) riproduci(); else if (!parlando) stato.textContent = occupato ? "I manager stanno pensando…" : d.stato === "in_corso" ? "Tocca a te." : "";
      if (d.stato === "conclusa" || d.stato === "errore") { vivo = false; mostraVerbale(d); return; }
    } catch (e) { stato.textContent = e.message; }
    setTimeout(sondaggio, 1500);
  };
  const mostraVerbale = (d) => { stato.textContent = ""; barraIn.replaceChildren(); riempi(msg, [h("h3", {}, "Verbale"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, d.verbale || "Il verbale non è disponibile." )]); };
  const invia = async () => {
    const t = campo.value.trim(); if (!t || occupato) return; campo.value = ""; ferma(); CallVoce.ferma(); coda = []; riga("Tu", t, true); occupato = true;
    try { await api("POST", "/gestione/riunioni-call/" + tid + "/turno", { testo: t }); stato.textContent = "I manager stanno pensando…"; } catch (e) { occupato = false; msg.replaceChildren(avviso(e.message, "no")); }
  };
  bInvia.addEventListener("click", invia);
  campo.addEventListener("keydown", (e) => { if (e.key === "Enter") invia(); });
  bMic.addEventListener("click", () => { if (!SR) { msg.replaceChildren(avviso("Questo browser non ha il riconoscimento vocale: scrivi nel campo.", "avv")); return; } if (ascolto) ferma(); else ascolta(); });
  const cont = h("input", { type: "checkbox" }); cont.addEventListener("change", () => { continuo = cont.checked; if (continuo) ascolta(); else ferma(); });
  const voceOn = h("input", { type: "checkbox" }); voceOn.checked = true; voceOn.addEventListener("change", () => { CallVoce.attiva = voceOn.checked; if (!voceOn.checked) CallVoce.ferma(); });
  const barraIn = h("div", { class: "riga", style: "align-items:center" }, bMic, campo, bInvia);
  const termina = h("button", { class: "r", onclick: async () => { if (!confirm("Chiudere la riunione e generare il verbale?")) return; ferma(); CallVoce.ferma(); coda = [];
    try { const r = await api("POST", "/gestione/riunioni-call/" + tid + "/chiudi"); msg.replaceChildren(avviso(r.sintesi, "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Termina e scrivi il verbale");
  const fuori = h("button", { class: "s", onclick: () => { vivo = false; ferma(); CallVoce.ferma(); esci(); } }, "← Esci (la call resta aperta)");
  api("GET", "/gestione/riunioni-call/" + tid).then(d => {
    riunione = d;
    riempi(tessere, d.partecipanti.map(p => { const t = h("div", { class: "carta", style: "text-align:center;min-width:92px;padding:8px" }, h("div", { class: "chat-sigla", style: "margin:0 auto 4px" }, p.nome.slice(0, 1).toUpperCase()), h("div", { class: "sotto" }, p.nome)); tessera[p.id] = t; return t; }));
    h2.textContent = d.titolo;
    if (d.stato === "conclusa" || d.stato === "errore") { mostraVerbale(d); return; }
    d.interventi.forEach(i => { ultimo = Math.max(ultimo, i.id); riga(i.da_utente ? "Tu" : nomeDi(i.agente_id), i.testo, i.da_utente); }); stato.textContent = d.occupato ? "I manager stanno pensando…" : "Tocca a te.";
    if (d.ordine_del_giorno && !d.interventi.length) riga("Argomenti", d.ordine_del_giorno, false);
    sondaggio();
  }).catch(e => msg.replaceChildren(avviso(e.message, "no")));
  const h2 = h("h2", {}, "Riunione");
  return h("div", {}, fuori, h2, tessere, log, stato, barraIn,
    h("div", { class: "riga", style: "margin-top:6px" }, h("label", { class: "interruttore" }, cont, h("span", {}, "Conversazione continua (ascolto automatico)")), h("label", { class: "interruttore" }, voceOn, h("span", {}, "Voci attive"))),
    h("div", { class: "azioni" }, termina), msg);
}
