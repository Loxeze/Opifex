"use strict";
// Riunioni vocali con i manager (Chat → Riunioni): si creano, si lancia la call, ogni manager risponde con la sua voce.

const CallVoce = {
  server: false, attiva: true, audio: null, sbloccato: false, risolvi: null, errore: "", bloccato: false,
  sblocca() {   // un solo gesto dell'utente basta a permettere l'audio automatico anche a telefono (iOS/Android) mentre guidi
    if (this.sbloccato) return; this.sbloccato = true;
    try { const a = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="); a.play().catch(() => {}); this.audio = null; } catch (e) { /* ignora */ }
    try { if (window.speechSynthesis) { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); } } catch (e) { /* ignora */ }
  },
  voceBrowser(agenteId) {
    const it = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter(v => v.lang && v.lang.toLowerCase().startsWith("it"));
    return { voce: it.length ? it[agenteId % it.length] : null, tono: 0.75 + (agenteId % 6) * 0.11, ritmo: 0.92 + (agenteId % 4) * 0.05 };
  },
  async parla(agenteId, testo) {
    if (!this.attiva) return;
    this.bloccato = false;
    if (this.server) {
      try {
        const r = await fetch("/voce/leggi", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: JSON.stringify({ testo: testo.slice(0, 4400), agente_id: agenteId }) });
        if (!r.ok) { try { this.errore = (await r.json()).detail || "voce non disponibile"; } catch (e) { this.errore = "voce non disponibile"; } }
        if (r.ok) {
          const url = URL.createObjectURL(await r.blob());
          const esito = await new Promise((ok) => { const a = new Audio(url); this.audio = a; const fine = (e) => { URL.revokeObjectURL(url); this.audio = null; this.risolvi = null; ok(e); }; this.risolvi = () => fine("ok"); a.onended = () => fine("ok"); a.onerror = () => fine("errore"); a.play().catch(() => fine("bloccato")); });
          if (esito === "bloccato") { this.bloccato = true; return; }
          if (esito === "ok") return;
          this.errore = "audio non riproducibile";
        }
      } catch (e) { this.errore = "rete: " + (e && e.message || e); }
    }
    if (!("speechSynthesis" in window)) { this.errore = this.errore || "questo browser non ha la sintesi vocale"; this.bloccato = true; return; }
    const c = this.voceBrowser(agenteId);
    await new Promise((ok) => {
      const u = new SpeechSynthesisUtterance(testo.slice(0, 1500)); u.lang = "it-IT"; if (c.voce) u.voice = c.voce; u.pitch = c.tono; u.rate = c.ritmo;
      let partita = false;
      u.onstart = () => { partita = true; }; u.onend = u.onerror = () => { this.risolvi = null; ok(); };
      this.risolvi = ok;
      speechSynthesis.speak(u);
      setTimeout(() => { if (!partita && !speechSynthesis.speaking) { speechSynthesis.cancel(); this.bloccato = true; this.risolvi = null; ok(); } }, 3000);   // il telefono non lo lascia partire senza un tocco
    });
  },
  ferma() { if (this.audio) { this.audio.pause(); this.audio = null; } if (this.risolvi) { const f = this.risolvi; this.risolvi = null; f(); } if ("speechSynthesis" in window) speechSynthesis.cancel(); },
};

["pointerdown", "touchstart", "keydown", "click"].forEach(ev => document.addEventListener(ev, () => CallVoce.sblocca(), { once: true, passive: true }));

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
  // Riunione continua stile Meet/Zoom: il microfono resta aperto, il sistema capisce da solo quando parli e quando fai una pausa.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const SERVER = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  let ultimaDetta = null, ultimo = 0, coda = [], parlando = false, vivo = true, riunione = null, occupato = false, inAttesa = "";
  let motore = SERVER ? "server" : SR ? "browser" : "nessuno", muto = false, flusso = null, ctx = null, an = null, buf = null, timer = null;
  let mr = null, pezzi = [], registrando = false, inizioReg = 0, inizioVoce = 0, ultimaVoce = 0, rumore = 4, forte = 0, livello = 0, rec = null, trascrivendo = 0;
  const tessere = h("div", { class: "riga", style: "flex-wrap:wrap;gap:10px;margin-bottom:10px" });
  const log = h("div", { style: "max-height:42vh;overflow:auto;margin-bottom:10px" });
  const stato = h("div", { style: "font-weight:600;margin:6px 0" }), msg = h("div");
  const barra = h("div", { style: "height:6px;border-radius:3px;background:#3fd3c0;width:0%;transition:width .08s" });
  const campo = h("input", { placeholder: "Oppure scrivi qui", maxlength: 4000, style: "flex:1" });
  const bInvia = h("button", { class: "p", type: "button" }, "Invia");
  const bMuto = h("button", { class: "s", type: "button" }, "🎙 Microfono attivo");
  const tessera = {};
  const evidenzia = (id, on) => { const t = tessera[id]; if (t) t.style.outline = on ? "3px solid #3fd3c0" : "none"; };
  const riga = (chi, testo, utente) => { log.append(h("div", { class: "risposta", style: "margin-bottom:6px;white-space:pre-wrap" + (utente ? ";border-left:3px solid #f3b54a" : "") }, h("b", {}, chi + ": "), testo)); log.scrollTop = log.scrollHeight; };
  const nomeDi = (id) => ((riunione.partecipanti.find(p => p.id === id) || {}).nome) || "?";
  const aggiornaStato = () => {
    stato.textContent = !vivo ? "" : muto ? "🔇 Microfono spento: tocca «Microfono spento» per riprendere"
      : parlando ? "🔊 Sta parlando… (tocca «Interrompi» per fermarli)" : occupato ? "💭 I manager stanno pensando…" : trascrivendo ? "✍️ Ti sto ascoltando…"
      : registrando ? "🎙 Ti sento…" : motore === "nessuno" ? "Il browser non ha il microfono: scrivi nel campo" : "🎙 Ti ascolto: parla quando vuoi";
  };

  // ---- invio ----
  const manda = async (t, mostra) => {
    if (mostra) riga("Tu", t, true);
    occupato = true; aggiornaStato();
    try { await api("POST", "/gestione/riunioni-call/" + tid + "/turno", { testo: t }); } catch (e) { occupato = false; msg.replaceChildren(avviso(e.message, "no")); aggiornaStato(); }
  };
  const invia = (t) => {
    t = String(t || "").trim(); if (!t) return;
    if (parlando || coda.length) { CallVoce.ferma(); coda = []; }   // se parli tu, si fermano
    if (occupato) { inAttesa = (inAttesa + " " + t).trim(); riga("Tu", t, true); return; }   // la mandero' appena finiscono di rispondere
    manda(t, true);
  };

  // ---- microfono continuo ----
  const arresta = () => {
    try { clearInterval(timer); } catch (e) { /* ok */ }
    if (rec) { const r = rec; rec = null; try { r.onend = null; r.abort(); } catch (e) { /* ok */ } }
    if (mr && mr.state !== "inactive") { mr.onstop = null; try { mr.stop(); } catch (e) { /* ok */ } }
    registrando = false;
    if (flusso) flusso.getTracks().forEach(t => t.stop());
    if (ctx) ctx.close().catch(() => {});
    flusso = ctx = an = mr = null;
  };
  const chiudiRegistrazione = () => {
    if (!registrando || !mr) return;
    registrando = false;
    const durata = ultimaVoce - inizioVoce;
    mr.onstop = async () => {
      const blob = new Blob(pezzi, { type: mr.mimeType || "audio/webm" }); pezzi = [];
      if (durata < 450 || blob.size < 1500) { aggiornaStato(); return; }   // un colpo di tosse o un click, non una frase
      trascrivendo++; aggiornaStato();
      try {
        const est = (mr.mimeType || "").includes("mp4") ? "mp4" : (mr.mimeType || "").includes("ogg") ? "ogg" : "webm";
        const fd = new FormData(); fd.append("audio", blob, "voce." + est);
        const r = await api("POST", "/gestione/riunioni-call/" + tid + "/audio", fd);
        if (r.testo) invia(r.testo);
      } catch (e) {
        if (/consentit|chiave|garanzie|OpenAI/i.test(e.message || "") && SR) { msg.replaceChildren(avviso("La trascrizione sul server non è disponibile (" + e.message + "): passo al riconoscimento del browser.", "avv")); passaABrowser(); }
        else msg.replaceChildren(avviso(e.message, "no"));
      }
      trascrivendo--; aggiornaStato();
    };
    try { mr.stop(); } catch (e) { /* ok */ }
  };
  const ciclo = () => {
    if (!an || !vivo) return;
    an.getByteTimeDomainData(buf); let somma = 0; for (const x of buf) somma += (x - 128) * (x - 128);
    const rms = Math.sqrt(somma / buf.length); livello = rms; barra.style.width = Math.min(100, rms * 6) + "%";
    if (muto) { if (registrando) { registrando = false; pezzi = []; try { mr.onstop = null; mr.stop(); } catch (e) { /* ok */ } } return; }
    const soglia = Math.max(5, rumore * 2.6), ora = Date.now();
    if (parlando) return;   // mentre parlano non registro (eco del telefono); per fermarli c'e' il pulsante «Interrompi»
    if (!registrando) {
      if (rms > soglia) {
        pezzi = []; mr = new MediaRecorder(flusso, MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : undefined);
        mr.ondataavailable = (e) => { if (e.data && e.data.size) pezzi.push(e.data); };
        try { mr.start(); registrando = true; inizioReg = inizioVoce = ultimaVoce = ora; aggiornaStato(); } catch (e) { registrando = false; }
      } else rumore = rumore * 0.96 + rms * 0.04;
    } else {
      if (rms > soglia) ultimaVoce = ora;
      if (ora - ultimaVoce > 1300 || ora - inizioReg > 60000) { chiudiRegistrazione(); }
    }
  };
  const passaABrowser = () => {
    motore = "browser"; arresta(); avviaBrowser();
  };
  const avviaBrowser = () => {   // riconoscimento continuo del browser: si riavvia da solo e si ferma mentre parlano i manager
    if (!SR || !vivo || motore !== "browser") return;
    const nuovo = () => {
      if (!vivo || motore !== "browser" || muto || parlando || rec) return;
      const r = new SR(); r.lang = "it-IT"; r.interimResults = false; r.continuous = true; rec = r;
      r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) invia(e.results[i][0].transcript); };
      r.onerror = () => {}; r.onend = () => { rec = null; setTimeout(nuovo, 300); };
      try { r.start(); } catch (e) { rec = null; }
    };
    timer = setInterval(() => { if ((muto || parlando) && rec) { const r = rec; rec = null; try { r.onend = null; r.abort(); } catch (e) { /* ok */ } } else if (!rec) nuovo(); aggiornaStato(); }, 700);
    nuovo();
  };
  const avviaMic = async () => {
    if (motore === "nessuno") { aggiornaStato(); return; }
    if (motore === "browser") { avviaBrowser(); aggiornaStato(); return; }
    try {
      flusso = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      ctx = new (window.AudioContext || window.webkitAudioContext)(); an = ctx.createAnalyser(); an.fftSize = 1024; buf = new Uint8Array(an.fftSize);
      ctx.createMediaStreamSource(flusso).connect(an);
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      timer = setInterval(ciclo, 80);
    } catch (e) {
      msg.replaceChildren(avviso("Non riesco a usare il microfono (" + (e && e.name === "NotAllowedError" ? "permesso negato: consentilo dal lucchetto accanto all'indirizzo" : e && e.name) + ")." + (SR ? " Provo col riconoscimento del browser." : " Scrivi nel campo."), "avv"));
      if (SR) { motore = "browser"; avviaBrowser(); } else motore = "nessuno";
    }
    aggiornaStato();
  };

  // ---- lettura delle risposte ----
  const riproduci = async () => {
    if (parlando) return; parlando = true;
    while (coda.length && vivo) { const i = coda.shift(); evidenzia(i.agente_id, true); stato.textContent = "🔊 " + nomeDi(i.agente_id) + " sta parlando… (tocca «Interrompi» per fermarli)"; ultimaDetta = i; await CallVoce.parla(i.agente_id, i.testo); evidenzia(i.agente_id, false);
      if (CallVoce.bloccato) { coda = []; msg.replaceChildren(avviso("Il telefono non mi lascia far partire la voce da sola" + (CallVoce.errore ? " (" + CallVoce.errore + ")" : "") + ".", "avv"), h("button", { class: "p", type: "button", onclick: () => { CallVoce.sblocca(true); msg.replaceChildren(); if (ultimaDetta) { coda = [ultimaDetta]; riproduci(); } } }, "🔊 Tocca per sentire")); break; } if (CallVoce.errore) { msg.replaceChildren(avviso("Voce ElevenLabs non disponibile (" + CallVoce.errore + "): uso la voce del browser.", "avv")); CallVoce.errore = ""; } }
    parlando = false; forte = 0; aggiornaStato();
  };
  const sondaggio = async () => {
    if (!vivo) return;
    if (!document.body.contains(log)) { vivo = false; CallVoce.ferma(); arresta(); return; }
    try {
      const d = await api("GET", "/gestione/riunioni-call/" + tid + "?dopo=" + ultimo);
      riunione = riunione || d; occupato = d.occupato; bCoda.textContent = "Richieste in coda" + (d.in_coda ? " (" + d.in_coda + ")" : ""); bCoda.disabled = !d.in_coda;
      for (const i of d.interventi) { ultimo = Math.max(ultimo, i.id); if (!i.da_utente) { riga(nomeDi(i.agente_id), i.testo, false); coda.push(i); } }
      if (coda.length) riproduci();
      if (!occupato && inAttesa) { const t = inAttesa; inAttesa = ""; manda(t, false); }
      aggiornaStato();
      if (d.stato === "conclusa" || d.stato === "errore") { vivo = false; arresta(); mostraVerbale(d); return; }
    } catch (e) { stato.textContent = e.message; }
    setTimeout(sondaggio, 1200);
  };
  const mostraVerbale = (d) => { stato.textContent = ""; barra.style.width = "0%"; riempi(msg, [h("h3", {}, "Verbale"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, d.verbale || "Il verbale non è disponibile." )]); };
  bInvia.addEventListener("click", () => { const t = campo.value; campo.value = ""; invia(t); });
  campo.addEventListener("keydown", (e) => { if (e.key === "Enter") { const t = campo.value; campo.value = ""; invia(t); } });
  bMuto.addEventListener("click", () => { muto = !muto; bMuto.textContent = muto ? "🔇 Microfono spento" : "🎙 Microfono attivo"; aggiornaStato(); });
  const bStop = h("button", { class: "s", type: "button", onclick: () => { CallVoce.ferma(); coda = []; } }, "✋ Interrompi");
  const bCoda = h("button", { class: "s", type: "button", onclick: () => invia("Avete richieste in coda?") }, "Richieste in coda");
  const termina = h("button", { class: "r", onclick: async () => { if (!confirm("Chiudere la riunione e generare il verbale?")) return; CallVoce.ferma(); coda = []; muto = true; aggiornaStato();
    try { const r = await api("POST", "/gestione/riunioni-call/" + tid + "/chiudi"); msg.replaceChildren(avviso(r.sintesi, "ok")); } catch (e) { muto = false; msg.replaceChildren(avviso(e.message, "no")); } } }, "Termina e scrivi il verbale");
  const fuori = h("button", { class: "s", onclick: () => { vivo = false; arresta(); CallVoce.ferma(); esci(); } }, "← Esci (la call resta aperta)");
  const h2 = h("h2", {}, "Riunione");
  api("GET", "/gestione/riunioni-call/" + tid).then(d => {
    riunione = d;
    riempi(tessere, d.partecipanti.map(p => { const t = h("div", { class: "carta", style: "text-align:center;min-width:92px;padding:8px" }, h("div", { class: "chat-sigla", style: "margin:0 auto 4px" }, p.nome.slice(0, 1).toUpperCase()), h("div", { class: "sotto" }, p.nome + (p.moderatore ? " (moderatrice)" : ""))); tessera[p.id] = t; return t; }));
    h2.textContent = d.titolo;
    if (d.stato === "conclusa" || d.stato === "errore") { mostraVerbale(d); return; }
    const nuova = !d.interventi.some(i => i.da_utente) && d.interventi.length <= 1;   // apertura appena fatta: la leggo a voce
    d.interventi.forEach(i => { ultimo = Math.max(ultimo, i.id); riga(i.da_utente ? "Tu" : nomeDi(i.agente_id), i.testo, i.da_utente); if (nuova && !i.da_utente) coda.push(i); });
    occupato = d.occupato; if (coda.length) riproduci();
    avviaMic(); sondaggio();
  }).catch(e => msg.replaceChildren(avviso(e.message, "no")));
  return h("div", {}, fuori, h2, tessere, log, stato, h("div", { style: "height:6px;background:rgba(255,255,255,.08);border-radius:3px;margin-bottom:8px" }, barra),
    h("div", { class: "riga", style: "align-items:center" }, bMuto, campo, bInvia),
    h("p", { class: "aiuto" }, "Parla normalmente, come in una videochiamata: quando fai una pausa rispondono. Per fermare chi sta parlando tocca «Interrompi»."),
    h("div", { class: "azioni" }, bStop, bCoda, termina), msg);
}
