"use strict";
// Voce: impostazioni ElevenLabs, pulsante «Ascolta» e prova del microfono. I testi sono inseriti come testo.

function vistaVoce() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/voce");
      const chiave = h("input", { type: "password", autocomplete: "off", placeholder: d.chiave ? "Chiave già salvata (lascia vuoto per non cambiarla)" : "Chiave API di ElevenLabs" });
      const voce = h("select", {}, h("option", { value: "" }, "— scegli una voce —"), d.voci.map(v => h("option", { value: v.id }, v.nome)));
      if (d.voce_id && !d.voci.some(v => v.id === d.voce_id)) voce.append(h("option", { value: d.voce_id }, d.voce_id));
      voce.value = d.voce_id || "";
      const garanzie = h("input", { type: "checkbox" }); garanzie.checked = d.garanzie;
      const tg = h("input", { type: "checkbox" }); tg.checked = d.telegram_voce;
      const msg = h("div");
      riempi(corpo, [h("p", { class: "aiuto" }, "Per far leggere ad alta voce briefing e risposte. In ElevenLabs: profilo → «API Keys» → crea una chiave e incollala qui (viene cifrata e non viene più mostrata). Il testo letto esce verso ElevenLabs: attiva la spunta solo dopo aver verificato le loro garanzie (non conservazione dei dati, DPA)."),
        d.errore ? avviso(d.errore, "no") : null,
        h("label", {}, "Chiave API", chiave), h("label", {}, "Voce", voce),
        h("div", { class: "interruttore" }, garanzie, h("span", {}, "Ho verificato le garanzie di ElevenLabs: i testi interni possono essere letti")),
        h("div", { class: "interruttore" }, tg, h("span", {}, "Su Telegram rispondi anche a voce quando ti scrivo con un vocale (comando /voce on|off)")), msg,
        h("div", { class: "azioni" },
          h("button", { class: "p", onclick: async () => { msg.replaceChildren(); try { await api("PUT", "/gestione/voce", { chiave: chiave.value.trim() || null, voce_id: voce.value || null, garanzie: garanzie.checked, telegram_voce: tg.checked }); msg.replaceChildren(avviso("Salvato.", "ok")); setTimeout(carica, 700); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
          d.chiave ? h("button", { class: "s", onclick: async () => { if (!confirm("Scollegare ElevenLabs?")) return; try { await api("DELETE", "/gestione/voce/chiave"); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Scollega") : null,
          d.chiave && d.voce_id ? pulsanteAscolta(() => "Ciao Lorenzo, questa è la voce che userò per leggerti i briefing.", "▶ Prova la voce") : null)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Voce"), corpo];
}

// Pulsante che legge ad alta voce un testo (scaricato dal server come audio e riprodotto qui)
function pulsanteAscolta(daiTesto, etichetta, agenteId) {
  const b = h("button", { class: "s", type: "button" }, etichetta || "▶ Ascolta");
  const msg = h("span", { class: "sotto" });
  let audio = null;
  b.addEventListener("click", async () => {
    if (audio) { audio.pause(); audio = null; b.textContent = etichetta || "▶ Ascolta"; return; }
    msg.textContent = ""; b.disabled = true; b.textContent = "Preparo la voce…";
    try {
      const r = await fetch("/voce/leggi", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) }, body: JSON.stringify({ testo: daiTesto(), agente_id: typeof agenteId === "function" ? agenteId() : (agenteId || null) }) });
      if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) { /* ignora */ } throw new Error(messaggioErrore(d)); }
      const buf = await r.arrayBuffer();
      const testa = new Uint8Array(buf.slice(0, 3));
      const mp3 = (testa[0] === 0x49 && testa[1] === 0x44 && testa[2] === 0x33) || (testa[0] === 0xff && (testa[1] & 0xe0) === 0xe0);
      if (!mp3) { let m = "La risposta non è un audio"; try { m += ": " + new TextDecoder().decode(buf.slice(0, 160)); } catch (e) { /* ignora */ } throw new Error(m); }
      const blob = new Blob([buf], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);
      const finito = () => { audio = null; b.textContent = etichetta || "▶ Ascolta"; URL.revokeObjectURL(url); };
      audio = new Audio(); audio.preload = "auto";
      audio.addEventListener("ended", finito);
      audio.src = url;
      try { await audio.play(); b.textContent = "⏹ Ferma"; }
      catch (e1) {   // piano B: decodifica con WebAudio (alcuni browser rifiutano l'elemento audio ma suonano così)
        audio = null;
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) throw e1;
        const ctx = new Ctx(); await ctx.resume();
        const dati = await ctx.decodeAudioData(buf.slice(0));
        const src = ctx.createBufferSource(); src.buffer = dati; src.connect(ctx.destination);
        audio = { pause() { try { src.stop(); } catch (e) { /* ok */ } } };
        src.onended = () => { finito(); ctx.close(); };
        src.start(); b.textContent = "⏹ Ferma";
      }
    } catch (e) { audio = null; msg.textContent = e.message; b.textContent = etichetta || "▶ Ascolta"; }
    b.disabled = false;
  });
  return h("span", {}, b, " ", msg);
}

// Prova del microfono: dice passo per passo dove si blocca la dettatura
function provaMicrofono() {
  const out = h("div", { class: "sotto", style: "white-space:pre-wrap" });
  const riga = (t, ok) => out.append(h("div", {}, (ok === true ? "✅ " : ok === false ? "❌ " : "• ") + t));
  const b = h("button", { class: "s", type: "button" }, "🔧 Prova microfono");
  b.addEventListener("click", async () => {
    out.replaceChildren(); b.disabled = true;
    try {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      riga("Browser: " + navigator.userAgent.split(") ").pop().slice(0, 60), null);
      riga(SR ? "Il browser ha il riconoscimento vocale" : "Il browser NON ha il riconoscimento vocale (usa Chrome, Edge o Safari, oppure la modalità «Server con OpenAI»)", !!SR);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { riga("Il microfono non è utilizzabile: la pagina deve essere aperta in HTTPS", false); b.disabled = false; return; }
      let flusso;
      try { flusso = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { riga("Permesso al microfono negato o microfono assente (" + (e && e.name) + "). Clicca il lucchetto accanto all'indirizzo → Impostazioni sito → Microfono: Consenti.", false); b.disabled = false; return; }
      const traccia = flusso.getAudioTracks()[0];
      riga("Microfono usato dal browser: «" + (traccia && traccia.label || "sconosciuto") + "»", true);
      riga("Parla per 4 secondi (di' una frase qualsiasi)…", null);
      let massimo = 0;
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)(); const an = ctx.createAnalyser(); an.fftSize = 512;
        ctx.createMediaStreamSource(flusso).connect(an); const buf = new Uint8Array(an.fftSize);
        const fine = Date.now() + 4000;
        if (SR) {
          const rec = new SR(); rec.lang = "it-IT"; rec.interimResults = true;
          rec.onaudiostart = () => riga("Il riconoscimento ha iniziato ad ascoltare", true);
          rec.onspeechstart = () => riga("Il riconoscimento ha sentito una voce", true);
          rec.onresult = (ev) => riga("Capito: «" + ev.results[ev.results.length - 1][0].transcript + "»", true);
          rec.onerror = (ev) => riga("Errore del riconoscimento: " + ev.error + (ev.error === "network" ? " (il servizio di Chrome non è raggiungibile: usa «Server con OpenAI»)" : ev.error === "no-speech" ? " (non ha sentito parlare)" : ev.error === "not-allowed" || ev.error === "service-not-allowed" ? " (permesso negato)" : ""), false);
          try { rec.start(); } catch (e) { riga("Impossibile avviare il riconoscimento: " + e.name, false); }
          setTimeout(() => { try { rec.stop(); } catch (e) { /* ignora */ } }, 4000);
        }
        while (Date.now() < fine) { an.getByteTimeDomainData(buf); for (const v of buf) massimo = Math.max(massimo, Math.abs(v - 128)); await new Promise(r => setTimeout(r, 50)); }
        ctx.close();
      } catch (e) { riga("Non riesco a misurare il suono (" + (e && e.name) + ")", false); }
      flusso.getTracks().forEach(t => t.stop());
      riga(massimo < 4 ? "Livello del suono: nessun segnale. Il microfono scelto non capta nulla: cambialo nelle impostazioni di Chrome o controlla che non sia silenziato." : "Livello del suono: " + massimo + "/128" + (massimo < 15 ? " (molto basso: avvicinati al microfono)" : " (buono)"), massimo >= 4);
      riga("Prova finita. Se qui sopra è tutto verde e la dettatura non funziona, copia queste righe e mandamele.", null);
    } catch (e) { riga("Errore inatteso: " + (e && e.message), false); }
    b.disabled = false;
  });
  return h("div", {}, b, out);
}
