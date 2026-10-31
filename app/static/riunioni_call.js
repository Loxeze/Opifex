"use strict";
// Riunioni vocali con i manager (Chat → Riunioni): si creano, si lancia la call, ogni manager risponde con la sua voce.

const CallVoce = {
  server: false, attiva: true, audio: null, sbloccato: false, mancata: false, risolvi: null, errore: "", bloccato: false, fermato: false,
  el: null, ctxA: null, elOk: false, ctxOk: false,
  SILENZIO: "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
  elemento() {   // UN solo elemento audio, tenuto nella pagina: una volta sbloccato da un tocco, il telefono lo lascia suonare anche piu' tardi
    if (!this.el) { const a = document.createElement("audio"); a.setAttribute("playsinline", ""); a.setAttribute("webkit-playsinline", ""); a.preload = "auto"; a.style.display = "none"; document.body.appendChild(a); this.el = a; }
    return this.el;
  },
  sblocca(forza) {   // da chiamare dentro un tocco: sblocca sia l'elemento audio sia il WebAudio (iOS e Android lo chiedono)
    if (this.elOk && this.ctxOk && !forza) return;
    try { const a = this.elemento(); a.src = this.SILENZIO; const p = a.play(); if (p && p.then) p.then(() => { this.elOk = true; }).catch(() => {}); } catch (e) { /* ignora */ }
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) { if (!this.ctxA) this.ctxA = new AC(); const r = this.ctxA.resume(); const ok = () => { if (this.ctxA.state === "running") this.ctxOk = true; }; if (r && r.then) r.then(ok).catch(() => {}); ok();
        const b = this.ctxA.createBuffer(1, 1, 22050), src = this.ctxA.createBufferSource(); src.buffer = b; src.connect(this.ctxA.destination); src.start(0); }
    } catch (e) { /* ignora */ }
    try { if (window.speechSynthesis && !this.sbloccato) { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); } } catch (e) { /* ignora */ }
    this.sbloccato = true;
  },
  async suona(blob) {   // 1) elemento audio gia' sbloccato (suona anche col tasto silenzioso dell'iPhone) 2) WebAudio. Restituisce "ok" | "errore" | "bloccato"
    const url = URL.createObjectURL(blob);
    const via_elemento = () => new Promise((ok) => {
      const a = this.elemento(); this.audio = a;
      const fine = (e) => { a.onended = a.onerror = null; this.audio = null; this.risolvi = null; ok(e); };
      this.risolvi = () => fine("ok"); a.onended = () => fine("ok"); a.onerror = () => fine("errore");
      a.src = url; a.volume = 1; a.muted = false;
      const p = a.play(); if (p && p.catch) p.catch((e) => fine(e && e.name === "NotAllowedError" ? "bloccato" : "errore"));
    });
    let esito = await via_elemento();
    if (esito !== "ok" && this.ctxA) {   // piano B: WebAudio
      try {
        await this.ctxA.resume();
        if (this.ctxA.state === "running") {
          const dati = await this.ctxA.decodeAudioData(await blob.arrayBuffer());
          esito = await new Promise((ok) => { const src = this.ctxA.createBufferSource(); src.buffer = dati; src.connect(this.ctxA.destination); this.fonte = src; this.risolvi = () => { try { src.stop(); } catch (e) { /* ok */ } ok("ok"); }; src.onended = () => { this.risolvi = null; ok("ok"); }; src.start(0); });
        }
      } catch (e) { /* resta l'esito di prima */ }
    }
    URL.revokeObjectURL(url);
    return esito;
  },
  prova() {   // suono generato qui, senza server: dice se l'audio del telefono funziona
    const n = 8000 * 0.5, v = new DataView(new ArrayBuffer(44 + n * 2)), sc = (o, t) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    sc(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); sc(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 16000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); sc(36, "data"); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.sin(2 * Math.PI * 523 * i / 8000) * 12000 * Math.min(1, (n - i) / 800), true);
    return this.suona(new Blob([v.buffer], { type: "audio/wav" }));
  },
  voceBrowser(agenteId) {
    const it = (window.speechSynthesis ? speechSynthesis.getVoices() : []).filter(v => v.lang && v.lang.toLowerCase().startsWith("it"));
    return { voce: it.length ? it[agenteId % it.length] : null, tono: 0.75 + (agenteId % 6) * 0.11, ritmo: 0.92 + (agenteId % 4) * 0.05 };
  },
  cache: new Map(),
  scarica(agenteId, testo) {   // chiede l'audio al server (ElevenLabs); si puo' fare in anticipo mentre un altro sta parlando
    const k = agenteId + "|" + testo;
    if (!this.cache.has(k)) {
      this.cache.set(k, (async () => {
        const r = await fetch("/voce/leggi", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: JSON.stringify({ testo: testo.slice(0, 4400), agente_id: agenteId, veloce: true }) });
        if (!r.ok) { let m = "voce non disponibile"; try { m = (await r.json()).detail || m; } catch (e) { /* ok */ } throw new Error(m); }
        return await r.blob();
      })());
    }
    return this.cache.get(k);
  },
  spezza(testo) {   // 2-3 parti a fine frase: la prima corta (parte prima), le altre piu' lunghe
    const frasi = testo.match(/[^.!?…]+[.!?…]*\s*/g) || [testo], parti = [];
    let cur = "", soglia = 90;
    for (const f of frasi) { cur += f; if (cur.length >= soglia) { parti.push(cur.trim()); cur = ""; soglia = 260; } }
    if (cur.trim()) { if (parti.length && cur.trim().length < 40) parti[parti.length - 1] += " " + cur.trim(); else parti.push(cur.trim()); }
    return parti.length ? parti : [testo];
  },
  precarica(agenteId, testo) { if (this.server && this.attiva) this.spezza(testo).forEach(p => this.scarica(agenteId, p).catch(() => {})); },
  async parla(agenteId, testo) {
    if (!this.attiva) return;
    this.bloccato = false;
    if (this.server) {
      try {
        const parti = this.spezza(testo);   // la prima frase parte subito, le altre si preparano mentre si ascolta
        parti.forEach(p => this.scarica(agenteId, p).catch(() => {}));
        for (const p of parti) {
          const blob = await this.scarica(agenteId, p);
          this.cache.delete(agenteId + "|" + p);
          const esito = await this.suona(blob);
          if (esito === "bloccato") { this.bloccato = true; return; }
          if (esito !== "ok") { this.errore = "audio non riproducibile"; this.mancata = true; return; }
          if (!this.attiva || this.fermato) return;
        }
        return;
      } catch (e) { this.cache.clear(); this.errore = (e && e.message) || "voce non disponibile"; }
      this.mancata = true;   // ElevenLabs e' collegato: niente voce robotica al suo posto, si dice cosa non va
      return;
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
  ferma() { this.fermato = true; setTimeout(() => { this.fermato = false; }, 400); if (this.audio) { try { this.audio.pause(); } catch (e) { /* ok */ } this.audio = null; } if (this.risolvi) { const f = this.risolvi; this.risolvi = null; f(); } if ("speechSynthesis" in window) speechSynthesis.cancel(); },
};

["pointerdown", "touchstart", "touchend", "keydown", "click"].forEach(ev => document.addEventListener(ev, () => CallVoce.sblocca(), { passive: true }));

function pannelloQualita() {
  const box = h("div"), msg = h("div");
  (async () => {
    try {
      const d = await api("GET", "/gestione/riunioni-call/qualita");
      const mod = h("select", {}, h("option", { value: "" }, "Il modello di ciascun agente"), d.modelli.map(m => h("option", { value: m }, m)));
      mod.value = d.modello || "";
      const sf = h("select", {}, [["", "Quello di ciascun agente"], ["low", "Basso (più veloce)"], ["medium", "Medio"], ["high", "Alto (ragiona di più)"]].map(([v, t]) => h("option", { value: v }, t)));
      sf.value = d.sforzo || "";
      const salva = async () => { try { await api("PUT", "/gestione/riunioni-call/qualita", { modello: mod.value, sforzo: sf.value }); msg.replaceChildren(avviso("Salvato: vale dalla prossima risposta.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
      mod.addEventListener("change", salva); sf.addEventListener("change", salva);
      riempi(box, [h("p", { class: "aiuto" }, "Qui i manager rispondono col modello più capace e ragionano a fondo (consigliato: claude-sonnet-5-5, ragionamento medio: intelligente e veloce). Opus è più profondo ma più lento e costoso, «alto» ragiona di più ma risponde più lentamente; fuori dalle riunioni ogni agente usa il suo modello."),
        h("div", { class: "riga", style: "align-items:center;gap:8px;flex-wrap:wrap" }, h("span", { style: "min-width:150px" }, "Modello"), mod), h("div", { class: "riga", style: "align-items:center;gap:8px;flex-wrap:wrap;margin-top:4px" }, h("span", { style: "min-width:150px" }, "Ragionamento"), sf)]);
    } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
  })();
  return h("details", { class: "carta", style: "margin-bottom:12px" }, h("summary", {}, "Qualità delle risposte"), box, msg);
}

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
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { CallVoce.sblocca(true); try { if (r.stato === "programmata") await api("POST", "/gestione/riunioni-call/" + r.id + "/avvia"); apri(r.id); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } },
            r.stato === "conclusa" || r.stato === "errore" ? "Apri verbale" : r.stato === "in_corso" ? "Rientra nella call" : "Avvia la call")))) : h("p", { class: "sotto" }, "Nessuna riunione ancora."));
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    };
    riempi(corpo, [pannelloQualita(), pannelloVociManager(), h("h3", {}, "Nuova riunione"), titolo, odg, h("label", {}, "Quando (facoltativo)", quando), h("p", { class: "aiuto" }, "Chi partecipa:"), scelti,
      h("div", { class: "azioni" },
        h("button", { class: "p", onclick: async () => {
          const part = caselle.filter(x => x[1].checked).map(x => x[0].nome);
          try { const r = await api("POST", "/gestione/riunioni-call", { titolo: titolo.value.trim(), ordine_del_giorno: odg.value.trim(), partecipanti: part, programmata_il: quando.value ? new Date(quando.value).toISOString() : null });
            titolo.value = odg.value = ""; msg.replaceChildren(avviso("Riunione creata.", "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea la riunione"),
        h("button", { class: "s", onclick: async () => {
          CallVoce.sblocca(true);
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
  let ultimoBrowser = "", ultimaDetta = null, ultimo = 0, coda = [], parlando = false, vivo = true, riunione = null, occupato = false, inAttesa = "";
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
    try { const r = await api("POST", "/gestione/riunioni-call/" + tid + "/turno", { testo: t }); if (r.registrata) { occupato = false; log.append(h("div", { class: "sotto", style: "margin:0 0 6px 8px" }, "✔ Registrato")); log.scrollTop = log.scrollHeight; aggiornaStato(); } } catch (e) { occupato = false; msg.replaceChildren(avviso(e.message, "no")); aggiornaStato(); }
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
      if (ora - ultimaVoce > 750 || ora - inizioReg > 60000) { chiudiRegistrazione(); }
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
      r.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) {
          let t = String(e.results[i][0].transcript || "").trim();
          if (!t || (ultimoBrowser && (t === ultimoBrowser || ultimoBrowser.endsWith(t)))) continue;   // Android ripete i risultati gia' finali
          const prima = ultimoBrowser; ultimoBrowser = t; setTimeout(() => { if (ultimoBrowser === t) ultimoBrowser = ""; }, 4000);
          if (prima && t.startsWith(prima)) t = t.slice(prima.length).trim();
          if (t) invia(t);
        }
      };
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
    while (coda.length && vivo) { const i = coda.shift(); evidenzia(i.agente_id, true); stato.textContent = "🔊 " + nomeDi(i.agente_id) + " sta parlando… (tocca «Interrompi» per fermarli)"; ultimaDetta = i; if (coda.length) CallVoce.precarica(coda[0].agente_id, coda[0].testo);
      await CallVoce.parla(i.agente_id, i.testo); evidenzia(i.agente_id, false);
      if (CallVoce.mancata) { CallVoce.mancata = false; msg.replaceChildren(avviso("ElevenLabs non riesce a leggere (" + CallVoce.errore + "). Controlla chiave, voce e garanzie in Impostazioni → Voce. Le risposte restano scritte.", "no")); CallVoce.errore = ""; continue; }
      if (CallVoce.bloccato) { coda = []; msg.replaceChildren(avviso("Il telefono non mi lascia far partire la voce da sola" + (CallVoce.errore ? " (" + CallVoce.errore + ")" : "") + ".", "avv"), h("button", { class: "p", type: "button", onclick: () => { CallVoce.sblocca(true); msg.replaceChildren(); if (ultimaDetta) { coda = [ultimaDetta]; riproduci(); } } }, "🔊 Tocca per sentire")); break; } }
    parlando = false; forte = 0; aggiornaStato();
  };
  const sondaggio = async () => {
    if (!vivo) return;
    if (!document.body.contains(log)) { vivo = false; CallVoce.ferma(); arresta(); return; }
    try {
      const d = await api("GET", "/gestione/riunioni-call/" + tid + "?dopo=" + ultimo);
      riunione = riunione || d; occupato = d.occupato; bCoda.textContent = "Richieste in coda" + (d.in_coda ? " (" + d.in_coda + ")" : ""); bCoda.disabled = !d.in_coda;
      for (const i of d.interventi) { ultimo = Math.max(ultimo, i.id); if (!i.da_utente) { riga(nomeDi(i.agente_id), i.testo, false); coda.push(i); CallVoce.precarica(i.agente_id, i.testo); } }
      if (coda.length) riproduci();
      if (!occupato && inAttesa) { const t = inAttesa; inAttesa = ""; manda(t, false); }
      aggiornaStato();
      if (d.stato === "conclusa" || d.stato === "errore") { vivo = false; arresta(); mostraVerbale(d); return; }
    } catch (e) { stato.textContent = e.message; }
    setTimeout(sondaggio, occupato || parlando || trascrivendo ? 450 : 1000);
  };
  const mostraVerbale = (d) => { stato.textContent = ""; barra.style.width = "0%"; riempi(msg, [h("h3", {}, "Verbale"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, d.verbale || "Il verbale non è disponibile." )]); };
  bInvia.addEventListener("click", () => { const t = campo.value; campo.value = ""; invia(t); });
  campo.addEventListener("keydown", (e) => { if (e.key === "Enter") { const t = campo.value; campo.value = ""; invia(t); } });
  bMuto.addEventListener("click", () => { muto = !muto; bMuto.textContent = muto ? "🔇 Microfono spento" : "🎙 Microfono attivo"; aggiornaStato(); });
  const bStop = h("button", { class: "s", type: "button", onclick: () => { CallVoce.ferma(); coda = []; } }, "✋ Interrompi");
  const bProva = h("button", { class: "s", type: "button" }, "🔊 Prova audio");
  bProva.addEventListener("click", async () => {
    CallVoce.sblocca(true); msg.replaceChildren(avviso("Ascolta: dovresti sentire un breve suono…", "avv"));
    const e = await CallVoce.prova();
    msg.replaceChildren(e === "ok" ? avviso("Il suono è partito. Se non l'hai sentito: alza il volume del telefono; su iPhone controlla la levetta del silenzioso e che non sia attiva la modalità «Non disturbare»; su Android il volume «contenuti multimediali». Se l'hai sentito, anche le voci dei manager si sentiranno.", "ok")
      : avviso("Il telefono ha bloccato l'audio (" + e + "). Tocca di nuovo «Prova audio»; se resta così dimmi che telefono e che browser usi.", "no"));
  });
  const bCoda = h("button", { class: "s", type: "button", onclick: () => invia("Avete richieste in coda?") }, "Richieste in coda");
  const termina = h("button", { class: "r", onclick: async () => { if (!confirm("Chiudere la riunione e generare il verbale?")) return; CallVoce.ferma(); coda = []; muto = true; aggiornaStato();
    try { const r = await api("POST", "/gestione/riunioni-call/" + tid + "/chiudi"); msg.replaceChildren(avviso(r.sintesi, "ok")); } catch (e) { muto = false; msg.replaceChildren(avviso(e.message, "no")); } } }, "Termina e scrivi il verbale");
  const fuori = h("button", { class: "s", onclick: () => { vivo = false; arresta(); CallVoce.ferma(); esci(); } }, "← Esci (la call resta aperta)");
  const h2 = h("h2", {}, "Riunione");
  const d_regole = h("details", { class: "carta", style: "margin:6px 0" }, h("summary", {}, "Regole della riunione"), h("div", { class: "sotto", style: "white-space:pre-wrap" }, "…"));
  api("GET", "/gestione/voci-manager").then(v => { CallVoce.server = !!v.elevenlabs; }).catch(() => {});
  api("GET", "/gestione/riunioni-call/" + tid).then(d => {
    riunione = d;
    riempi(tessere, d.partecipanti.map(p => { const t = h("div", { class: "carta", style: "text-align:center;min-width:92px;padding:8px" }, h("div", { class: "chat-sigla", style: "margin:0 auto 4px" }, p.nome.slice(0, 1).toUpperCase()), h("div", { class: "sotto" }, p.nome + (p.moderatore ? " (moderatrice)" : ""))); tessera[p.id] = t; return t; }));
    h2.textContent = d.titolo; if (d.regole) d_regole.lastChild.textContent = d.regole;
    if (d.stato === "conclusa" || d.stato === "errore") { mostraVerbale(d); return; }
    const nuova = !d.interventi.some(i => i.da_utente) && d.interventi.length <= 1;   // apertura appena fatta: la leggo a voce
    d.interventi.forEach(i => { ultimo = Math.max(ultimo, i.id); riga(i.da_utente ? "Tu" : nomeDi(i.agente_id), i.testo, i.da_utente); if (nuova && !i.da_utente) coda.push(i); });
    occupato = d.occupato; if (coda.length) riproduci();
    avviaMic(); sondaggio();
  }).catch(e => msg.replaceChildren(avviso(e.message, "no")));
  return h("div", {}, fuori, h2, tessere, log, stato, h("div", { style: "height:6px;background:rgba(255,255,255,.08);border-radius:3px;margin-bottom:8px" }, barra),
    h("div", { class: "riga", style: "align-items:center" }, bMuto, campo, bInvia),
    d_regole,
    h("p", { class: "aiuto" }, "Parla normalmente, come in una videochiamata: quando fai una pausa rispondono. Per fermare chi sta parlando tocca «Interrompi»."),
    h("div", { class: "azioni" }, bStop, bProva, bCoda, termina), msg);
}
