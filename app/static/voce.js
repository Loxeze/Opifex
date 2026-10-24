// Voce: dettatura (parli, il testo compare nel campo) e lettura ad alta voce delle risposte.
// Usa le funzioni vocali del browser (Chrome/Edge/Safari); nessuna chiave. Il microfono richiede HTTPS (c'e').
// Nota: in Chrome il riconoscimento vocale passa dal servizio del browser (Google): l'audio esce dal tuo computer.
const Voce = (() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const chiave = (k) => "opifex_voce_" + k;
  const leggiPref = (k) => { try { return localStorage.getItem(chiave(k)) === "1"; } catch (e) { return false; } };
  const scriviPref = (k, v) => { try { localStorage.setItem(chiave(k), v ? "1" : "0"); } catch (e) { /* ignora */ } };
  let rec = null, reg = null;
  const SERVER = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  const v = {
    supportoDettatura: !!SR || SERVER,
    supportoBrowser: !!SR,
    supportoServer: SERVER,
    // modo: "browser" (riconoscimento del browser) oppure "server" (registra e trascrive OpenAI dal server)
    get modo() { try { const m = localStorage.getItem(chiave("modo")); if (m === "server" && SERVER) return "server"; if (m === "browser" && SR) return "browser"; } catch (e) { /* ignora */ } return SR ? "browser" : "server"; },
    set modo(x) { try { localStorage.setItem(chiave("modo"), x); } catch (e) { /* ignora */ } },
    supportoLettura: "speechSynthesis" in window,
    get leggiRisposte() { return leggiPref("leggi"); },
    set leggiRisposte(x) { scriviPref("leggi", x); if (!x) v.fermaLettura(); },
    viva: false,            // conversazione a mani libere: ascolta -> invia -> legge -> riascolta
    avviaAscolto: null,     // la pagina chat lo imposta ad ogni disegno
    ascolta(campo, quandoFinito, quandoStato) {
      v.ferma();
      if (!SR) return false;
      v.fermaLettura();
      rec = new SR();
      rec.lang = "it-IT"; rec.interimResults = true; rec.continuous = !v.viva;
      const base = campo.value ? campo.value.replace(/\s+$/, "") + " " : "";
      let finale = "";
      rec.onresult = (ev) => {
        let provvisorio = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const t = ev.results[i][0].transcript;
          if (ev.results[i].isFinal) finale += t; else provvisorio += t;
        }
        campo.value = (base + finale + provvisorio).trim();
      };
      let ricevuto = false, errore = false;
      const spiega = (e) => e === "not-allowed" || e === "service-not-allowed"
        ? "Il browser non ha il permesso di usare il microfono: consentilo dall'icona del lucchetto accanto all'indirizzo."
        : e === "network" ? "Il servizio di riconoscimento del browser non risponde (errore di rete: succede con Brave, con blocchi di rete o senza internet). Passa a «Trascrizione sul server» qui sotto."
        : e === "audio-capture" ? "Non trovo nessun microfono: controlla che sia collegato e scelto nelle impostazioni del browser."
        : e === "language-not-supported" ? "Il browser non supporta il riconoscimento in italiano: usa «Trascrizione sul server»."
        : e === "no-speech" ? "" : "Dettatura interrotta (" + e + ")";
      const risultato0 = rec.onresult;
      rec.onresult = (ev) => { ricevuto = true; risultato0(ev); };
      rec.onerror = (ev) => { errore = true; quandoStato && quandoStato(spiega(ev.error) || "Non ho sentito nulla: parla vicino al microfono o prova «Trascrizione sul server»."); };
      rec.onend = () => {
        rec = null;
        if (!ricevuto && !errore) quandoStato && quandoStato("Non ho trascritto nulla: il microfono non ha captato parole. Controlla il microfono scelto nel browser, oppure passa a «Trascrizione sul server».");
        quandoStato && quandoStato(null); quandoFinito && quandoFinito(campo.value.trim());
      };
      try { rec.start(); quandoStato && quandoStato("ascolto"); } catch (e) { rec = null; return false; }
      return true;
    },
    inAscolto() { return !!rec || !!reg; },
    // chiude la dettatura: in modo server la registrazione fatta fin qui viene trascritta
    termina() { if (reg) reg.stop(); else v.ferma(); },
    ferma() {
      if (rec) { const r = rec; rec = null; try { r.onend = null; r.stop(); } catch (e) { /* ignora */ } }
      if (reg) { const r = reg; reg = null; r.annulla = true; r.stop(); }
    },
    // dettatura sul server: registra, si ferma da sola dopo un po' di silenzio, trascrive con OpenAI
    registra(campo, quandoFinito, quandoStato, fascia) {
      v.ferma(); v.fermaLettura();
      if (!SERVER) return false;
      let chiuso = false, mr = null, ctx = null, timer = null, flusso = null;
      const me = { annulla: false, stop() { chiuso = true; try { if (mr && mr.state !== "inactive") mr.stop(); else if (!mr) { me.annulla = true; } } catch (e) { /* ignora */ } } };
      reg = me;
      const avviso_ = (t) => quandoStato && quandoStato(t);
      navigator.mediaDevices.getUserMedia({ audio: true }).then((s) => {
        flusso = s;
        if (chiuso) { s.getTracks().forEach(t => t.stop()); return; }
        const tipo = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find(t => MediaRecorder.isTypeSupported(t)) || "";
        mr = new MediaRecorder(s, tipo ? { mimeType: tipo } : undefined);
        const pezzi = [];
        mr.ondataavailable = (e) => { if (e.data && e.data.size) pezzi.push(e.data); };
        let parlato = false, picco = 0;
        const inizio = Date.now(); let ultimaVoce = inizio;
        try {
          ctx = new (window.AudioContext || window.webkitAudioContext)();
          const an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(s).connect(an);
          const buf = new Uint8Array(an.fftSize);
          timer = setInterval(() => {
            an.getByteTimeDomainData(buf); let max = 0; for (const x of buf) max = Math.max(max, Math.abs(x - 128));
            picco = Math.max(picco, max);
            if (max > 8) { parlato = true; ultimaVoce = Date.now(); }
            const ora = Date.now();
            if (!chiuso && ((parlato && ora - ultimaVoce > 1600) || ora - inizio > 90000 || (!parlato && ora - inizio > 8000))) me.stop();
          }, 100);
        } catch (e) { parlato = true; /* niente analisi del livello: si fida del pulsante di stop */ }
        mr.onstop = async () => {
          clearInterval(timer); s.getTracks().forEach(t => t.stop()); if (ctx) ctx.close().catch(() => {});
          if (reg === me) reg = null;
          if (me.annulla) return;
          if (!parlato) {
            avviso_("Non ho sentito la tua voce: il microfono non capta suono (livello " + picco + "). Controlla quale microfono è selezionato nel browser e nel sistema, e che non sia muto.");
            avviso_(null); quandoFinito && quandoFinito(campo.value.trim()); return;
          }
          avviso_("trascrivo");
          try {
            const est = (mr.mimeType || "").includes("mp4") ? "mp4" : (mr.mimeType || "").includes("ogg") ? "ogg" : "webm";
            const fd = new FormData();
            fd.append("audio", new Blob(pezzi, { type: mr.mimeType || "audio/webm" }), "voce." + est);
            fd.append("fascia_dati", fascia || "pubblico");
            const r = await api("POST", "/voce/trascrivi", fd);
            campo.value = ((campo.value ? campo.value.replace(/\s+$/, "") + " " : "") + r.testo).trim();
          } catch (e) { avviso_(e.message); }
          avviso_(null); quandoFinito && quandoFinito(campo.value.trim());
        };
        mr.start(); avviso_("ascolto");
        if (chiuso) me.stop();
      }).catch((e) => {
        if (reg === me) reg = null;
        avviso_(e && e.name === "NotAllowedError" ? "Il browser non ha il permesso di usare il microfono: consentilo dall'icona del lucchetto accanto all'indirizzo."
          : e && e.name === "NotFoundError" ? "Non trovo nessun microfono collegato." : "Microfono non disponibile (" + (e && e.name) + ").");
        avviso_(null);
      });
      return true;
    },
    // test del microfono: mostra se il browser sente la tua voce (livello da 0 a 100) per 4 secondi
    async provaMicrofono(mostra) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { mostra("Questo browser non permette di usare il microfono."); return; }
      let s = null;
      try { s = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { mostra("Microfono non utilizzabile: " + (e && e.name === "NotAllowedError" ? "permesso negato (icona del lucchetto accanto all'indirizzo)." : (e && e.name) || "errore")); return; }
      const nome = (s.getAudioTracks()[0] || {}).label || "microfono";
      const ctx = new (window.AudioContext || window.webkitAudioContext)(); const an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(s).connect(an);
      const buf = new Uint8Array(an.fftSize); let picco = 0; const fine = Date.now() + 4000;
      mostra("Parla adesso… microfono: " + nome);
      await new Promise((ok) => { const t = setInterval(() => { an.getByteTimeDomainData(buf); let m = 0; for (const x of buf) m = Math.max(m, Math.abs(x - 128)); picco = Math.max(picco, m);
        mostra("Parla adesso… livello: " + Math.min(100, Math.round(picco / 128 * 400)) + " (" + nome + ")"); if (Date.now() > fine) { clearInterval(t); ok(); } }, 100); });
      s.getTracks().forEach(t => t.stop()); ctx.close().catch(() => {});
      mostra(picco > 8 ? "Il microfono «" + nome + "» funziona: il browser sente la tua voce." + (SR ? "" : " Questo browser non ha il riconoscimento vocale: usa «Trascrizione sul server».")
        : "Il browser NON sente la voce da «" + nome + "». Controlla che sia il microfono giusto e non sia muto (impostazioni del browser e del sistema).");
    },
    leggi(testo, quandoFinito) {
      if (!v.supportoLettura) { quandoFinito && quandoFinito(); return; }
      v.fermaLettura();
      const pulito = String(testo).replace(/[*_#`>|]/g, " ").replace(/https?:\/\/\S+/g, " collegamento ").replace(/\s+/g, " ").trim().slice(0, 3000);
      const u = new SpeechSynthesisUtterance(pulito);
      u.lang = "it-IT";
      const voce = speechSynthesis.getVoices().find(x => x.lang && x.lang.toLowerCase().startsWith("it"));
      if (voce) u.voice = voce;
      u.onend = u.onerror = () => { quandoFinito && quandoFinito(); };
      speechSynthesis.speak(u);
    },
    fermaLettura() { if (v.supportoLettura) speechSynthesis.cancel(); },
    fermaTutto() { v.viva = false; v.ferma(); v.fermaLettura(); },
  };
  return v;
})();
