// Voce: dettatura (parli, il testo compare nel campo) e lettura ad alta voce delle risposte.
// Usa le funzioni vocali del browser (Chrome/Edge/Safari); nessuna chiave. Il microfono richiede HTTPS (c'e').
// Nota: in Chrome il riconoscimento vocale passa dal servizio del browser (Google): l'audio esce dal tuo computer.
const Voce = (() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const chiave = (k) => "opifex_voce_" + k;
  const leggiPref = (k) => { try { return localStorage.getItem(chiave(k)) === "1"; } catch (e) { return false; } };
  const scriviPref = (k, v) => { try { localStorage.setItem(chiave(k), v ? "1" : "0"); } catch (e) { /* ignora */ } };
  let rec = null;
  const v = {
    supportoDettatura: !!SR,
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
      rec.onerror = (ev) => { quandoStato && quandoStato(ev.error === "not-allowed" || ev.error === "service-not-allowed"
        ? "Il browser non ha il permesso di usare il microfono: consentilo dall'icona del lucchetto accanto all'indirizzo." : (ev.error === "no-speech" ? "" : "Dettatura interrotta (" + ev.error + ")")); };
      rec.onend = () => { rec = null; quandoStato && quandoStato(null); quandoFinito && quandoFinito(campo.value.trim()); };
      try { rec.start(); quandoStato && quandoStato("ascolto"); } catch (e) { rec = null; return false; }
      return true;
    },
    inAscolto() { return !!rec; },
    ferma() { if (rec) { const r = rec; rec = null; try { r.onend = null; r.stop(); } catch (e) { /* ignora */ } } },
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
