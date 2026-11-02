"use strict";
// Finestre: un browser vero dentro la plancia (gira sul server, con i tuoi accessi). Pensato per il PC.
// Gli agenti abilitati leggono SOLO le schede che condividi qui; non possono cliccare ne' scrivere.
function vistaFinestre() {
  const L = 1280, A = 800;
  const S = { schede: [], attiva: null, occupato: false, ultimoTesto: "" };
  const msg = h("div", { class: "sotto" });
  const barra = h("div", { class: "fin-schede" });
  const indirizzo = h("input", { type: "text", placeholder: "Indirizzo (es. chatgpt.com, claude.ai, instagram.com)", "data-senza-voce": "1", autocomplete: "off" });
  const img = h("img", { class: "fin-schermo", alt: "Pagina", draggable: "false" });
  const quadro = h("div", { class: "fin-quadro", tabindex: "0" }, img);
  const vuoto = h("div", { class: "fin-vuoto" }, "Nessuna scheda aperta. Scrivi un indirizzo qui sopra e premi Apri: ChatGPT, Claude, la pagina dei tuoi social o qualunque sito. Gli accessi restano salvati.");
  const scrivi = h("input", { type: "text", placeholder: "Scrivi (o detta con 🎤) nel campo selezionato della pagina…", autocomplete: "off" });
  const cond = h("input", { type: "checkbox" });
  const stampa = (t, err) => { msg.textContent = t || ""; msg.style.color = err ? "var(--rosso, #b3261e)" : ""; };
  const corrente = () => S.schede.find(s => s.id === S.attiva) || null;

  const disegnaSchede = () => {
    barra.replaceChildren(...S.schede.map(s => h("span", { class: "fin-scheda" + (s.id === S.attiva ? " attiva" : "") },
      h("button", { type: "button", class: "fin-nome", title: s.url, onclick: () => scegli(s.id) }, (s.agente ? "🤖 " : "") + (s.condivisa ? "👁 " : "") + (s.titolo || s.url).slice(0, 26)),
      h("button", { type: "button", class: "fin-x", title: "Chiudi scheda", onclick: () => chiudi(s.id) }, "✕"))));
    const c = corrente();
    cond.checked = !!(c && c.condivisa); cond.disabled = !c;
    vuoto.hidden = !!c; quadro.hidden = !c;
    if (c && document.activeElement !== indirizzo) indirizzo.value = c.url;
  };
  const carica = async () => {
    try { S.schede = (await api("GET", "/finestre")).schede; if (!corrente()) S.attiva = S.schede.length ? S.schede[0].id : null; disegnaSchede(); }
    catch (e) { stampa(e.message, true); }
  };
  const scegli = (id) => { S.attiva = id; disegnaSchede(); aggiorna(true); };
  const apri = async () => {
    const u = indirizzo.value.trim(); if (!u) return;
    stampa("Apro…");
    try {
      const c = corrente();
      if (c && c.url && !c.url.startsWith("about:")) { await api("POST", "/finestre", { url: u }).then(r => { S.attiva = r.id; }); }
      else S.attiva = (await api("POST", "/finestre", { url: u })).id;
      stampa(""); await carica(); aggiorna(true);
    } catch (e) { stampa(e.message, true); }
  };
  const naviga = async () => {
    const c = corrente(); const u = indirizzo.value.trim(); if (!u) return;
    if (!c) return apri();
    stampa("Carico…");
    try { await api("POST", "/finestre/" + c.id + "/vai", { url: u }); stampa(""); await carica(); aggiorna(true); } catch (e) { stampa(e.message, true); }
  };
  const chiudi = async (id) => { try { await api("DELETE", "/finestre/" + id); if (S.attiva === id) S.attiva = null; await carica(); } catch (e) { stampa(e.message, true); } };
  const azione = async (corpo) => {
    const c = corrente(); if (!c) return;
    try { await api("POST", "/finestre/" + c.id + "/azione", corpo); setTimeout(() => aggiorna(true), 350); } catch (e) { stampa(e.message, true); }
  };
  const punto = (e) => { const r = img.getBoundingClientRect(); return { x: Math.round((e.clientX - r.left) / r.width * L), y: Math.round((e.clientY - r.top) / r.height * A) }; };
  img.addEventListener("click", (e) => { quadro.focus({ preventScroll: true }); azione({ tipo: "click", ...punto(e) }); });
  img.addEventListener("dblclick", (e) => azione({ tipo: "doppio", ...punto(e) }));
  let rotella = null;
  quadro.addEventListener("wheel", (e) => { e.preventDefault(); clearTimeout(rotella); const p = punto(e); const dy = e.deltaY; rotella = setTimeout(() => azione({ tipo: "scroll", ...p, dy }), 60); }, { passive: false });
  quadro.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey) { if (["a", "c", "v", "x"].includes(e.key.toLowerCase())) { e.preventDefault(); azione({ tipo: "tasto", testo: "Control+" + e.key.toLowerCase() }); } return; }
    const speciali = ["Enter", "Backspace", "Tab", "Escape", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End"];
    if (speciali.includes(e.key)) { e.preventDefault(); azione({ tipo: "tasto", testo: e.key }); }
    else if (e.key.length === 1) { e.preventDefault(); azione({ tipo: "testo", testo: e.key }); }
  });
  const invia = (premiInvio) => async () => {
    const t = scrivi.value; if (!t && !premiInvio) return;
    const c = corrente(); if (!c) return;
    try {
      if (t) await api("POST", "/finestre/" + c.id + "/azione", { tipo: "testo", testo: t });
      if (premiInvio) await api("POST", "/finestre/" + c.id + "/azione", { tipo: "tasto", testo: "Enter" });
      scrivi.value = ""; setTimeout(() => aggiorna(true), 400);
    } catch (e) { stampa(e.message, true); }
  };
  cond.addEventListener("change", async () => {
    const c = corrente(); if (!c) return;
    try { await api("PUT", "/finestre/" + c.id + "/condividi", { si: cond.checked }); await carica(); stampa(cond.checked ? "Gli agenti abilitati ora possono leggere questa scheda (solo lettura)." : "Scheda non più condivisa."); }
    catch (e) { stampa(e.message, true); cond.checked = !cond.checked; }
  });

  const scarFile = h("span", {}, "—");
  const caricaScar = async () => { try { const r = await api("GET", "/finestre/scaricati/elenco"); scarFile.replaceChildren(...(r.file.length ? r.file.slice(0, 8).flatMap(f => [h("a", { href: "#", onclick: async (e) => { e.preventDefault(); const x = await fetch("/finestre/scaricati/" + encodeURIComponent(f.nome), { headers: { Authorization: "Bearer " + token } }); const b = await x.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = f.nome; a.click(); } }, f.nome + " (" + f.kb + " KB)"), " · "]) : ["nessun file"])); } catch (e) { /* elenco non disponibile */ } };
  caricaScar();
  let url0 = null, volo = false;
  const aggiorna = async (subito) => {
    if (volo || !quadro.isConnected) return; const c = corrente(); if (!c || document.hidden) return;
    volo = true;
    try {
      const r = await fetch("/finestre/" + c.id + "/schermo?t=" + Date.now(), { headers: { Authorization: "Bearer " + token } });
      if (r.ok) { const b = await r.blob(); const nuovo = URL.createObjectURL(b); img.src = nuovo; if (url0) URL.revokeObjectURL(url0); url0 = nuovo; }
      else if (r.status === 422) { await carica(); }
    } catch (e) { /* riprovo al prossimo giro */ }
    volo = false;
  };
  const giro = async () => { if (!quadro.isConnected) { if (url0) URL.revokeObjectURL(url0); return; } await aggiorna(); setTimeout(giro, 900); };
  let ct = 0;
  const giroElenco = () => { if (!quadro.isConnected) return; if (++ct % 4 === 0) { carica(); caricaScar(); } setTimeout(giroElenco, 1500); };

  const bApri = h("button", { type: "button", class: "p", onclick: apri, title: "Apri in una nuova scheda" }, "Apri");
  indirizzo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); naviga(); } });
  scrivi.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); invia(true)(); } });
  const bt = (t, titolo, tipo) => h("button", { type: "button", class: "s", title: titolo, onclick: () => azione({ tipo }) }, t);
  carica().then(() => { aggiorna(true); giro(); giroElenco(); });

  return [h("h2", {}, "Finestre"),
    h("p", { class: "sotto" }, "Un browser vero dentro Opifex: apri ChatGPT, Claude, i tuoi social o qualunque sito e usalo da qui; gli accessi restano salvati sul tuo server. Gli agenti abilitati (Agenti → modifica) leggono le schede che condividi con 👁 e possono cliccare, scrivere, cercare e scaricare solo nei siti che elenchi per loro (🤖 = scheda aperta da un agente); non fanno pagamenti, eliminazioni, pubblicazioni né inseriscono password. Disponibile solo da computer."),
    h("div", { class: "fin-riga" }, bt("◀", "Indietro", "indietro"), bt("▶", "Avanti", "avanti"), bt("⟳", "Ricarica", "ricarica"), indirizzo, h("button", { type: "button", class: "s", onclick: naviga, title: "Vai a questo indirizzo nella scheda corrente" }, "Vai"), bApri),
    barra, msg, vuoto, quadro,
    h("div", { class: "fin-riga" }, scrivi, h("button", { type: "button", class: "s", onclick: invia(false) }, "Scrivi nella pagina"), h("button", { type: "button", class: "s", onclick: invia(true) }, "Scrivi e premi Invio")),
    h("div", { class: "sotto" }, "Scaricati dagli agenti: ", scarFile),
    h("label", { class: "interruttore" }, cond, h("span", {}, "👁 Condividi questa scheda con gli agenti (sola lettura)"))];
}
