"use strict";
// Finestre: un browser vero dentro la plancia (gira sul server, con i tuoi accessi). Pensato per il PC.
// Gli agenti abilitati leggono SOLO le schede che condividi qui; non possono cliccare ne' scrivere.
function vistaFinestre(secondaria) {
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
    try { S.schede = (await api("GET", "/finestre")).schede; if (!corrente()) S.attiva = S.schede.length ? (secondaria && S.schede[1] ? S.schede[1] : S.schede[0]).id : null; disegnaSchede(); }
    catch (e) { stampa(e.message, true); }
  };
  const scegli = (id) => { S.attiva = id; disegnaSchede(); aggiorna(); };
  const apri = async () => {
    const u = indirizzo.value.trim(); if (!u) return;
    stampa("Apro…");
    try {
      const c = corrente();
      if (c && c.url && !c.url.startsWith("about:")) { await api("POST", "/finestre", { url: u }).then(r => { S.attiva = r.id; }); }
      else S.attiva = (await api("POST", "/finestre", { url: u })).id;
      stampa(""); await carica(); aggiorna();
    } catch (e) { stampa(e.message, true); }
  };
  const naviga = async () => {
    const c = corrente(); const u = indirizzo.value.trim(); if (!u) return;
    if (!c) return apri();
    stampa("Carico…");
    try { await api("POST", "/finestre/" + c.id + "/vai", { url: u }); stampa(""); await carica(); aggiorna(); } catch (e) { stampa(e.message, true); }
  };
  const chiudi = async (id) => { try { await api("DELETE", "/finestre/" + id); if (S.attiva === id) S.attiva = null; await carica(); } catch (e) { stampa(e.message, true); } };
  const azione = async (corpo) => {
    const c = corrente(); if (!c) return;
    try { await api("POST", "/finestre/" + c.id + "/azione", corpo); setTimeout(() => aggiorna(), 350); } catch (e) { stampa(e.message, true); }
  };
  const punto = (e) => { const r = img.getBoundingClientRect(); return { x: Math.round((e.clientX - r.left) / r.width * L), y: Math.round((e.clientY - r.top) / r.height * A) }; };
  img.addEventListener("click", (e) => { quadro.focus({ preventScroll: true }); azione({ tipo: "click", ...punto(e) }); });
  img.addEventListener("dblclick", (e) => azione({ tipo: "doppio", ...punto(e) }));
  let rotella = null;
  quadro.addEventListener("wheel", (e) => { e.preventDefault(); clearTimeout(rotella); const p = punto(e); const dy = e.deltaY; rotella = setTimeout(() => azione({ tipo: "scroll", ...p, dy }), 60); }, { passive: false });
  quadro.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === "v") return;                                   // niente da fare qui: scatta l'evento «paste» con gli appunti di QUESTO computer
      if (k === "a") { e.preventDefault(); azione({ tipo: "tasto", testo: "Control+a" }); }
      if (k === "c" || k === "x") { e.preventDefault(); copia(k === "x"); }
      return;
    }
    const speciali = ["Enter", "Backspace", "Tab", "Escape", "Delete", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End"];
    if (speciali.includes(e.key)) { e.preventDefault(); azione({ tipo: "tasto", testo: e.key }); }
    else if (e.key.length === 1) { e.preventDefault(); azione({ tipo: "testo", testo: e.key }); }
  });
  // Appunti: il browser gira altrove (server o altro computer), quindi copia e incolla passano da qui.
  const incolla = async (t) => {
    const c = corrente(); if (!c) return;
    if (!t) { stampa("Negli appunti non c'è testo da incollare."); return; }
    try {
      for (let i = 0; i < t.length; i += 2000) await api("POST", "/finestre/" + c.id + "/azione", { tipo: "testo", testo: t.slice(i, i + 2000) });
      stampa("Incollato (" + t.length + " caratteri)."); setTimeout(() => aggiorna(), 350);   // il testo incollato non viene mostrato: puo' essere una password
    } catch (e) { stampa(e.message, true); }
  };
  const copia = async (taglia) => {
    const c = corrente(); if (!c) return;
    try {
      const t = (await api("GET", "/finestre/" + c.id + "/selezione")).testo;
      if (!t) { stampa("Nessun testo selezionato nella pagina (i campi password non si copiano)."); return; }
      try { await navigator.clipboard.writeText(t); stampa((taglia ? "Tagliato" : "Copiato") + " negli appunti di questo computer (" + t.length + " caratteri)."); }
      catch (e) { scrivi.value = t; scrivi.select(); stampa("Il browser non mi lascia scrivere negli appunti: il testo è nel campo qui sotto, copialo da lì."); }
      await api("POST", "/finestre/" + c.id + "/azione", { tipo: "tasto", testo: taglia ? "Control+x" : "Control+c" });
      if (taglia) setTimeout(() => aggiorna(), 350);
    } catch (e) { stampa(e.message, true); }
  };
  quadro.addEventListener("paste", (e) => { e.preventDefault(); incolla(((e.clipboardData || window.clipboardData).getData("text") || "")); });
  const incollaBottone = async () => {
    quadro.focus({ preventScroll: true });
    try { incolla(await navigator.clipboard.readText()); }
    catch (e) { stampa("Il browser non mi lascia leggere gli appunti da un pulsante: clicca sul punto della pagina dove vuoi scrivere e premi Ctrl+V.", true); }
  };

  const invia = (premiInvio) => async () => {
    const t = scrivi.value; if (!t && !premiInvio) return;
    const c = corrente(); if (!c) return;
    try {
      if (t) await api("POST", "/finestre/" + c.id + "/azione", { tipo: "testo", testo: t });
      if (premiInvio) await api("POST", "/finestre/" + c.id + "/azione", { tipo: "tasto", testo: "Enter" });
      scrivi.value = ""; setTimeout(() => aggiorna(), 400);
    } catch (e) { stampa(e.message, true); }
  };
  cond.addEventListener("change", async () => {
    const c = corrente(); if (!c) return;
    try { await api("PUT", "/finestre/" + c.id + "/condividi", { si: cond.checked }); await carica(); stampa(cond.checked ? "Gli agenti abilitati ora possono leggere questa scheda (solo lettura)." : "Scheda non più condivisa."); }
    catch (e) { stampa(e.message, true); cond.checked = !cond.checked; }
  });

  const dove = h("select", { title: "Dove gira il browser" }, h("option", { value: "server" }, "☁ Sul server"), h("option", { value: "pc" }, "🖥 Sul mio computer"));
  const doveMsg = h("span", { class: "sotto" });
  const caricaDove = async () => {
    try {
      const r = await api("GET", "/finestre/dove");
      dove.value = r.destinazione;
      doveMsg.textContent = r.collegato ? (r.capacita && r.capacita.finestre ? "Computer collegato: browser pronto." : "Computer collegato, ma il browser non è ancora pronto (si prepara da solo alla prossima apertura dell'app Archivio).") : "Computer non collegato: apri l'app Archivio e accedi a Opifex.";
    } catch (e) { /* non disponibile */ }
  };
  dove.addEventListener("change", async () => {
    try { await api("PUT", "/finestre/dove", { destinazione: dove.value }); S.attiva = null; await caricaDove(); await carica(); aggiorna(); }
    catch (e) { stampa(e.message, true); await caricaDove(); }
  });
  caricaDove();
  const scarFile = h("span", {}, "—");
  const caricaScar = async () => { try { const r = await api("GET", "/finestre/scaricati/elenco"); scarFile.replaceChildren(...(r.file.length ? r.file.slice(0, 8).flatMap(f => [h("a", { href: "#", onclick: async (e) => { e.preventDefault(); const x = await fetch("/finestre/scaricati/" + encodeURIComponent(f.nome), { headers: { Authorization: "Bearer " + token } }); const b = await x.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = f.nome; a.click(); } }, f.nome + " (" + f.kb + " KB)"), " · "]) : ["nessun file"])); } catch (e) { /* elenco non disponibile */ } };
  caricaScar();
  let url0 = null, volo = false, errori = 0, ct = 0;
  const aggiorna = async () => {
    if (volo || !quadro.isConnected) return; const c = corrente(); if (!c) return;
    volo = true;
    try {
      const r = await fetch("/finestre/" + c.id + "/schermo?t=" + Date.now(), { headers: { Authorization: "Bearer " + token } });
      if (r.ok) { const b = await r.blob(); const nuovo = URL.createObjectURL(b); img.src = nuovo; if (url0) URL.revokeObjectURL(url0); url0 = nuovo; errori = 0; }
      else { errori++; if (r.status === 422) await carica(); }
    } catch (e) { errori++; }
    volo = false;
  };
  // un solo giro alla volta (mai richieste in parallelo), fermo se la scheda del browser e' nascosta, piu' lento se il server fatica
  const giro = async () => {
    if (!quadro.isConnected) { if (url0) URL.revokeObjectURL(url0); return; }
    if (!document.hidden) {
      await aggiorna();
      if (++ct % 6 === 0) { await carica(); await caricaScar(); await caricaDove(); }
    }
    setTimeout(giro, Math.min(900 * (1 + errori * 2), 10000));
  };

  const bApri = h("button", { type: "button", class: "p", onclick: apri, title: "Apri in una nuova scheda" }, "Apri");
  indirizzo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); naviga(); } });
  scrivi.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); invia(true)(); } });
  const bt = (t, titolo, tipo) => h("button", { type: "button", class: "s", title: titolo, onclick: () => azione({ tipo }) }, t);
  carica().then(() => { aggiorna(); giro(); });

  const corpo = [
    secondaria ? null : h("div", { class: "fin-riga" }, h("span", {}, "Browser:"), dove, doveMsg),
    h("div", { class: "fin-riga" }, bt("◀", "Indietro", "indietro"), bt("▶", "Avanti", "avanti"), bt("⟳", "Ricarica", "ricarica"), indirizzo, h("button", { type: "button", class: "s", onclick: naviga, title: "Vai a questo indirizzo nella scheda corrente" }, "Vai"), bApri),
    barra, msg, vuoto, quadro,
    h("div", { class: "fin-riga" }, scrivi, h("button", { type: "button", class: "s", onclick: invia(false) }, "Scrivi nella pagina"), h("button", { type: "button", class: "s", onclick: invia(true) }, "Scrivi e premi Invio")),
    h("div", { class: "fin-riga" }, h("button", { type: "button", class: "s", "data-uso": "finestre-incolla", onclick: incollaBottone, title: "Scrive nella pagina il testo che hai copiato su questo computer (anche con Ctrl+V dopo aver cliccato sulla pagina)" }, "📋 Incolla dal mio computer"),
      h("button", { type: "button", class: "s", "data-uso": "finestre-copia", onclick: () => copia(false), title: "Porta negli appunti di questo computer il testo selezionato nella pagina (anche con Ctrl+C)" }, "Copia la selezione"),
      h("span", { class: "sotto" }, "Ctrl+V incolla, Ctrl+C copia: prima clicca sulla pagina.")),
    h("div", { class: "sotto" }, "Scaricati dagli agenti: ", scarFile),
    h("label", { class: "interruttore" }, cond, h("span", {}, "👁 Condividi questa scheda con gli agenti (sola lettura)"))];
  if (secondaria) return h("div", { class: "fin-colonna" }, corpo);
  const colonne = h("div", { class: "fin-colonne" }, h("div", { class: "fin-colonna" }, corpo));
  let seconda = null;
  const bAff = h("button", { type: "button", class: "s", "data-uso": "finestre-affianca", onclick: () => {
    if (seconda) { seconda.remove(); seconda = null; colonne.classList.remove("due"); bAff.textContent = "➕ Affianca una seconda finestra"; }
    else { seconda = vistaFinestre(true); colonne.append(seconda); colonne.classList.add("due"); bAff.textContent = "✕ Togli la seconda finestra"; }
  } }, "➕ Affianca una seconda finestra");
  return [h("h2", {}, "Finestre"),
    h("p", { class: "sotto" }, "Un browser vero dentro Opifex: apri ChatGPT, Claude, i tuoi social o qualunque sito e usalo da qui; gli accessi restano salvati sul tuo server. Gli agenti abilitati (Agenti → modifica) leggono le schede che condividi con 👁 e possono cliccare, scrivere, cercare e scaricare solo nei siti che elenchi per loro (🤖 = scheda aperta da un agente); non fanno pagamenti, eliminazioni, pubblicazioni né inseriscono password. Disponibile solo da computer."),
    h("div", { class: "fin-riga" }, bAff, h("span", { class: "sotto" }, "Ogni finestra mostra una scheda diversa: le schede aperte sono le stesse, scegli in ciascuna quale guardare.")),
    colonne];
}
