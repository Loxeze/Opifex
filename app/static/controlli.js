"use strict";
// Spesa per reparto e controllo delle librerie.

function vistaSpesaReparti() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/spesa-reparti");
      riempi(corpo, d.reparti.map(r => {
        const t = h("input", { type: "number", min: "1", step: "1", placeholder: "nessun tetto", style: "width:120px" }); if (r.tetto) t.value = r.tetto;
        const pc = r.tetto ? Math.round(100 * r.speso / r.tetto) : null;
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, r.nome),
          h("div", { class: "sotto" }, "Speso questo mese: " + r.speso.toFixed(2) + (pc !== null ? " · " + pc + "% del tetto" + (pc >= 100 ? " — REPARTO FERMO" : pc >= 80 ? " — vicino al tetto" : "") : "")),
          h("div", { class: "riga", style: "align-items:center" }, h("label", {}, "Tetto mensile", t),
            h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/spesa-reparti/" + r.id, { tetto: t.value ? Number(t.value) : null }); msg.replaceChildren(avviso("Salvato.", "ok")); await carica(); }
              catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
      }));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Spesa per reparto"),
    h("p", { class: "aiuto" }, "Un tetto mensile per ogni reparto (stessa unità del tetto generale). All'80% ricevi un avviso; al 100% gli agenti di quel reparto si fermano fino al mese dopo o finché non alzi il tetto. Aurora e gli agenti di sistema non si fermano."),
    msg, corpo);
}

function vistaDipendenze() {
  const corpo = h("div"), msg = h("div");
  const mostra = (u) => riempi(corpo, u ? [h("p", {}, "Ultimo controllo: " + new Date(u.eseguito_il).toLocaleString("it-IT") + " — " +
    ({ ok: "nessuna vulnerabilità nota", vulnerabilita: "ATTENZIONE: vulnerabilità trovate", non_raggiungibile: "servizio non raggiungibile (si riprova)" })[u.esito]),
    (u.dettagli || []).map(t => h("div", { class: "carta", style: "margin-bottom:6px" }, h("b", {}, t.libreria + " " + t.versione), h("div", { class: "sotto" }, t.vulnerabilita.join(", "))))] : h("p", { class: "sotto" }, "Nessun controllo ancora eseguito."));
  api("GET", "/gestione/dipendenze").then(d => mostra(d.ultimo)).catch(e => msg.replaceChildren(avviso(e.message, "no")));
  return h("div", {}, h("h2", {}, "Controllo delle librerie"),
    h("p", { class: "aiuto" }, "Ogni settimana le librerie usate da Opifex vengono confrontate con il database pubblico delle vulnerabilità (OSV). Se ne trova ricevi un avviso: l'aggiornamento arriva con la prossima versione."),
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { msg.replaceChildren(avviso("Controllo in corso…", "ok"));
      try { const r = await api("POST", "/gestione/dipendenze/controlla"); msg.replaceChildren(); const d = await api("GET", "/gestione/dipendenze"); mostra(d.ultimo); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Controlla adesso")), msg, corpo);
}


function vistaDiagnostica() {
  const msg = h("div");
  const ore = h("select", {}, [["6", "ultime 6 ore"], ["24", "ultime 24 ore"], ["72", "ultimi 3 giorni"], ["168", "ultima settimana"]].map(([v, t]) => h("option", { value: v }, t)));
  ore.value = "24";
  const scarica = h("button", { class: "p", type: "button" }, "⬇ Scarica il file di diagnostica");
  scarica.addEventListener("click", async () => {
    scarica.disabled = true; msg.replaceChildren(avviso("Preparo il file…", "ok"));
    try {
      const r = await fetch("/gestione/diagnostica?ore=" + ore.value, { headers: token ? { Authorization: "Bearer " + token } : {} });
      if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) { /* ok */ } throw new Error(messaggioErrore(d)); }
      const blob = await r.blob(), url = URL.createObjectURL(blob), a = document.createElement("a");
      a.href = url; a.download = ((r.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/) || [])[1] || "diagnostica-opifex.json";
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
      msg.replaceChildren(avviso("File scaricato (" + Math.round(blob.size / 1024) + " KB). Mandamelo in chat e lo analizzo.", "ok"));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    scarica.disabled = false;
  });
  return h("div", {}, h("h2", {}, "Diagnostica"),
    h("p", { class: "aiuto" }, "Un unico file con tutto cio' che serve per capire cosa e' andato storto: segnali sospetti in cima, errori, impostazioni e prompt degli agenti, riunioni (cosa e' stato detto, le richieste in coda), task, chiamate ai modelli, spese, notifiche e registro delle azioni. Chiavi, token e password non ci sono mai. Dentro ci sono pero' conversazioni reali: condividilo solo per l'analisi."),
    h("label", {}, "Periodo", ore), h("div", { class: "azioni" }, scarica), msg);
}


function vistaEsempio() {
  const corpo = h("div"), msg = h("div"), lista = h("div");
  const agente = h("select", {}), comp = h("input", { maxlength: 100, placeholder: "Nome della competenza, es. Costruire un sito vetrina" });
  const obiettivo = h("input", { maxlength: 1000, placeholder: "Cosa volevi ottenere (facoltativo ma utile)" });
  const testo = h("textarea", { style: "min-height:240px", placeholder: "Incolla qui la conversazione (tutta: le tue richieste e le risposte)" });
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/ginnasio/da-esempio");
      const scelto = agente.value; riempi(agente, [h("option", { value: "" }, "— scegli l'agente che deve imparare —"), d.agenti.map(a => h("option", { value: a.id }, a.nome + " — " + a.ruolo))]); agente.value = scelto;
      riempi(lista, d.esempi.length ? d.esempi.map(e => h("div", { class: "carta", style: "margin-bottom:6px" }, h("b", {}, e.competenza + " → " + (e.agente || "?")),
        h("div", { class: "sotto" }, ({ in_studio: "Padre Casati sta studiando…", da_approvare: "Metodo pronto: approvalo in Ginnasio", errore: "Errore: " + (e.errore || "") })[e.stato] + " · " + new Date(e.creato_il).toLocaleString("it-IT") + " · " + e.caratteri + " caratteri"))) : h("p", { class: "sotto" }, "Nessun esempio ancora."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const invia = h("button", { class: "p", type: "button" }, "Fai studiare a Padre Casati");
  invia.addEventListener("click", async () => {
    invia.disabled = true;
    try {
      await api("POST", "/gestione/ginnasio/da-esempio", { agente_id: Number(agente.value), competenza: comp.value.trim(), trascrizione: testo.value, obiettivo: obiettivo.value.trim() });
      msg.replaceChildren(avviso("Esempio ricevuto: Padre Casati lo studia e ti avvisa quando il metodo e' pronto (Ginnasio → bozze da approvare).", "ok"));
      testo.value = ""; comp.value = ""; obiettivo.value = ""; carica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    invia.disabled = false;
  });
  carica();
  const t = setInterval(() => { if (!document.body.contains(lista)) clearInterval(t); else carica(); }, 8000);
  return h("div", {}, h("h2", {}, "Impara da un esempio"),
    h("p", { class: "aiuto" }, "Hai ottenuto un buon risultato in una conversazione (per esempio con ChatGPT)? Incollala qui e scegli l'agente: Padre Casati ne ricava un metodo di lavoro (stile, passi, scelte, frasi che hanno funzionato, criteri di qualita', errori da evitare). Lo rivedi e lo approvi in Ginnasio: da quel momento l'agente lavora cosi'. La conversazione e' solo materiale da studiare, non puo' dare ordini al sistema."),
    h("label", {}, "Agente", agente), h("label", {}, "Competenza", comp), h("label", {}, "Obiettivo", obiettivo), h("label", {}, "Conversazione", testo),
    h("div", { class: "azioni" }, invia), msg, h("h3", {}, "I tuoi esempi"), lista);
}

function vistaMemoriaVett() {
  const stato = h("div"), msg = h("div"), elenco = h("div");
  const file = h("input", { type: "file", accept: ".zip,.json" });
  const tutti = h("input", { type: "checkbox", checked: true });
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/memoria-vettoriale");
      const pc = d.pezzi ? Math.round(100 * d.indicizzati / d.pezzi) : 100;
      riempi(stato, h("div", { class: "carta" },
        h("b", {}, d.indicizzati + " brani su " + d.pezzi + " ricercabili per significato (" + pc + "%)"),
        h("div", { class: "sotto" }, d.chiave ? "Da indicizzare: " + d.da_indicizzare + " · esclusi per riservatezza: " + d.esclusi_per_riservatezza + " · fasce consentite: " + (d.fasce_consentite.join(", ") || "nessuna") : "Manca la chiave OpenAI (Impostazioni): senza, resta la sola ricerca per parole."),
        d.fasce_consentite.length ? "" : h("div", { class: "sotto" }, "Per indicizzare i documenti dichiara le garanzie di OpenAI in Sicurezza e garanzie.")));
      riempi(temiBox, d.temi && d.temi.length ? [h("h3", {}, "Argomenti con più fonti (" + d.relazioni + " collegamenti)"), d.temi.map(t => h("div", { class: "carta", style: "margin-bottom:6px" }, h("b", {}, t.quanti + " documenti sullo stesso tema"), h("div", { class: "sotto" }, t.documenti.join(" · "))))] : h("p", { class: "sotto" }, "Collegamenti tra documenti: " + d.relazioni + ". Gli agenti ricevono l'indicazione quando esistono più fonti sullo stesso tema."));
      caricaBlocco();
      riempi(elenco, d.importazioni.length ? d.importazioni.map(i => h("div", { class: "carta", style: "margin-bottom:6px" },
        h("b", {}, i.origine + " — " + i.nome_file), h("div", { class: "sotto" }, ({ in_corso: "In corso…", conclusa: "Conclusa", errore: "Errore: " + (i.errore || "") })[i.stato] + " · " + i.importate + " importate, " + i.saltate + " saltate (brevi o già presenti) su " + i.conversazioni))) : h("p", { class: "sotto" }, "Nessuna importazione ancora."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const temiBox = h("div"), bloccoMsg = h("div");
  const files = h("input", { type: "file", multiple: true, accept: ".zip,.pdf,.docx,.txt,.md,.csv,.xlsx,.pptx,.html,.json,.rtf,.odt,.png,.jpg,.jpeg" });
  const fasciaB = h("select", {}, ["interno", "pubblico", "riservato"].map(f => h("option", { value: f }, f)));
  const tuttiB = h("input", { type: "checkbox", checked: true });
  const vaiB = h("button", { class: "p", type: "button" }, "Carica tutto");
  vaiB.addEventListener("click", async () => {
    if (!files.files.length) { bloccoMsg.replaceChildren(avviso("Scegli i file (o uno zip con una cartella).", "no")); return; }
    vaiB.disabled = true;
    try {
      const fd = new FormData(); for (const f of files.files) fd.append("file", f); fd.append("fascia_dati", fasciaB.value); fd.append("per_tutti", tuttiB.checked ? "true" : "false");
      await api("POST", "/gestione/documenti-blocco", fd); files.value = "";
      bloccoMsg.replaceChildren(avviso("Caricamento avviato: lavora in sottofondo, qui sotto vedi l'avanzamento.", "ok")); caricaBlocco();
    } catch (e) { bloccoMsg.replaceChildren(avviso(e.message, "no")); }
    vaiB.disabled = false;
  });
  const bloccoLista = h("div");
  const caricaBlocco = async () => { try { const l = await api("GET", "/gestione/documenti-blocco"); riempi(bloccoLista, l.map(b => h("div", { class: "sotto" }, "#" + b.id + " · " + ({ in_corso: "in corso…", concluso: "concluso", errore: "errore" })[b.stato] + " · " + b.caricati + " caricati, " + b.saltati + " saltati su " + b.totale + (b.problemi.length ? " · problemi: " + b.problemi.slice(0, 5).map(p => p.file + " (" + p.motivo + ")").join("; ") : "")))); } catch (e) { /* ignora */ } };
  caricaBlocco();
  const bloccoForm = h("div", {}, h("label", {}, "File (anche molti insieme) o uno zip con una cartella", files), h("label", {}, "Riservatezza", fasciaB),
    h("label", {}, tuttiB, " Disponibili a tutti gli agenti (altrimenti li assegni tu dai Documenti)"), h("div", { class: "azioni" }, vaiB), bloccoMsg, bloccoLista);
  const indicizza = h("button", { class: "s", type: "button" }, "Indicizza ora");
  indicizza.addEventListener("click", async () => {
    indicizza.disabled = true;
    try { const r = await api("POST", "/gestione/memoria-vettoriale/indicizza"); msg.replaceChildren(avviso(r.fatti + " brani indicizzati.", "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    indicizza.disabled = false;
  });
  const importa = h("button", { class: "p", type: "button" }, "Importa le conversazioni");
  importa.addEventListener("click", async () => {
    if (!file.files[0]) { msg.replaceChildren(avviso("Scegli prima il file.", "no")); return; }
    importa.disabled = true;
    try {
      const fd = new FormData(); fd.append("file", file.files[0]); fd.append("per_tutti", tutti.checked ? "true" : "false");
      await api("POST", "/gestione/memoria-vettoriale/importa", fd);
      msg.replaceChildren(avviso("Importazione avviata: puoi continuare a lavorare, i brani saranno indicizzati nei prossimi minuti.", "ok")); file.value = ""; carica();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    importa.disabled = false;
  });
  carica();
  const t = setInterval(() => { if (!document.body.contains(stato)) clearInterval(t); else carica(); }, 10000);
  return h("div", {}, h("h2", {}, "Memoria condivisa (per significato)"),
    h("p", { class: "aiuto" }, "Tutti i documenti caricati sono ricercabili anche per significato, non solo per parole: un agente che lavora a un progetto trova i brani pertinenti anche se usano termini diversi. Ognuno vede solo i documenti che già poteva vedere. Qui puoi anche importare le tue conversazioni di ChatGPT (Impostazioni → Controlli dati → Esporta) e di Claude (Impostazioni → Privacy → Esporta dati): carica lo zip o il file conversations.json."),
    stato, h("div", { class: "azioni" }, indicizza), temiBox, h("h3", {}, "Carica documenti in blocco"), bloccoForm, h("h3", {}, "Importa conversazioni"), h("label", {}, "File di esportazione (.zip o .json)", file),
    h("label", {}, tutti, " Disponibili a tutti gli agenti (altrimenti li assegni tu uno a uno dai Documenti)"),
    h("div", { class: "azioni" }, importa), msg, h("h3", {}, "Importazioni"), elenco);
}

function vistaGiro() {
  const corpo = h("div"), msg = h("div"), fatti = h("div"), nuovo = h("input", { maxlength: 500, placeholder: "Aggiungi tu un fatto (es. Renovatio collabora con X dal 2024)" });
  const giorni = h("input", { type: "number", min: 0, max: 90, style: "width:70px" });
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/giro");
      if (document.activeElement !== giorni) giorni.value = d.giorni;
      riempi(corpo, d.aperto ? d.domande.map(q => {
        if (q.stato !== "attesa") return h("div", { class: "sotto", style: "margin-bottom:6px" }, (q.stato === "risposta" ? "✓ " : "— ") + q.agente + ": " + q.domanda);
        const r = h("input", { maxlength: 600, placeholder: "Risposta breve", style: "flex:1" });
        const ok = h("button", { class: "p", type: "button" }, "Rispondi"), no = h("button", { class: "s", type: "button" }, "Salta");
        const manda = async (url, body) => { try { await api("POST", url, body); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
        ok.addEventListener("click", () => r.value.trim() && manda("/gestione/giro/domande/" + q.id + "/risposta", { risposta: r.value }));
        r.addEventListener("keydown", e => { if (e.key === "Enter") ok.click(); });
        no.addEventListener("click", () => manda("/gestione/giro/domande/" + q.id + "/salta"));
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("b", {}, q.agente + " chiede: " + q.domanda), h("div", { style: "display:flex;gap:6px;margin-top:6px" }, r, ok, no));
      }) : h("p", { class: "sotto" }, "Nessun giro aperto."));
      riempi(fatti, d.fatti.length ? d.fatti.map(f => h("div", { class: "sotto", style: "margin-bottom:4px" }, f.testo + " ",
        h("a", { href: "#", onclick: async ev => { ev.preventDefault(); try { await api("DELETE", "/gestione/giro/fatti/" + f.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "togli"))) : h("p", { class: "sotto" }, "Ancora nessun fatto."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const avvia = h("button", { class: "p", type: "button" }, "Avvia un giro ora");
  avvia.addEventListener("click", async () => { avvia.disabled = true; try { await api("POST", "/gestione/giro/avvia"); msg.replaceChildren(); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } avvia.disabled = false; });
  const salva = h("button", { class: "s", type: "button" }, "Salva frequenza");
  salva.addEventListener("click", async () => { try { await api("PUT", "/gestione/giro/impostazioni", { giorni: Number(giorni.value) }); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } });
  const aggiungi = h("button", { class: "s", type: "button" }, "Aggiungi");
  aggiungi.addEventListener("click", async () => { if (nuovo.value.trim().length < 5) return; try { await api("POST", "/gestione/giro/fatti", { testo: nuovo.value }); nuovo.value = ""; carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } });
  carica();
  const t = setInterval(() => { if (!document.body.contains(corpo)) clearInterval(t); else if (document.activeElement.tagName !== "INPUT") carica(); }, 15000);
  return h("div", {}, h("h2", {}, "Giro di aggiornamento"),
    h("p", { class: "aiuto" }, "Ogni tanto Aurora e i manager ti fanno poche domande brevissime sulle strutture e sui progetti (relazioni con un ente, a che punto è un progetto). Le tue risposte diventano fatti che tutti gli agenti ricevono. Puoi rispondere a voce con la dettatura del telefono."),
    h("label", {}, "Ogni quanti giorni (0 = mai in automatico)", giorni), h("div", { class: "azioni" }, salva, avvia), msg,
    h("h3", {}, "Domande"), corpo, h("h3", {}, "Cosa sanno ora tutti gli agenti"), h("div", { style: "display:flex;gap:6px" }, nuovo, aggiungi), fatti);
}

// ---------- Contenuti: brief e stili di montaggio ----------
function vistaContenuti() {
  const msgB = h("div"), msgS = h("div"), lista = h("div"), schedaBox = h("div");
  const campo = (et, el) => h("label", {}, et, el);
  const sel = (voci, val) => h("select", {}, voci.map(v => h("option", { value: v }, v)), val ? null : null);
  // --- brief ---
  const titolo = h("input", { maxlength: 150, placeholder: "Es. Puntata 12 del podcast / Reel mostra Montarrenti" });
  const formato = sel(["video", "podcast", "reel", "documentario", "spot", "grafica", "audio", "foto", "testo", "altro"]);
  const programma = sel(["indifferente", "premiere", "resolve"]);
  const obiettivo = h("textarea", { rows: 2, maxlength: 800, placeholder: "Cosa deve ottenere e per chi" });
  const durata = h("input", { maxlength: 60, placeholder: "Es. 45 secondi / 12 minuti" });
  const materiali = h("textarea", { rows: 2, maxlength: 1200, placeholder: "Che materiale c'è: riprese, interviste, audio, foto, trascrizioni…" });
  const stile = h("select", {}, h("option", { value: "" }, "Nessuno in particolare"));
  const esempi = h("textarea", { rows: 4, maxlength: 3000, placeholder: "Incolla qui esempi: trascrizioni, descrizioni di un montaggio che ti piace, un elenco di clip con i tempi, un copione…" });
  const note = h("input", { maxlength: 800, placeholder: "Altre note" });
  const manda = h("button", { class: "p", type: "button" }, "Manda il brief al Direttore dei Contenuti");
  manda.addEventListener("click", async () => {
    manda.disabled = true;
    try {
      const r = await api("POST", "/gestione/contenuti/brief", { titolo: titolo.value, formato: formato.value, programma: programma.value, obiettivo: obiettivo.value, durata: durata.value,
        materiali: materiali.value, stile_id: stile.value ? Number(stile.value) : null, esempi: esempi.value, note: note.value });
      msgB.replaceChildren(avviso("Brief inviato: è la task #" + r.task_id + ", la trovi nelle Task.", "ok")); titolo.value = ""; obiettivo.value = ""; esempi.value = "";
    } catch (e) { msgB.replaceChildren(avviso(e.message, "no")); }
    manda.disabled = false;
  });
  // --- stili ---
  const nome = h("input", { maxlength: 120, placeholder: "Es. Il mio stile documentario / Stile podcast di X" });
  const tipo = h("select", {}, h("option", { value: "mio" }, "È il mio stile (miei montaggi)"), h("option", { value: "riferimento" }, "Stile di riferimento da imitare"));
  const nota = h("input", { maxlength: 1000, placeholder: "Cosa ti piace di questo stile, cosa va imitato" });
  const testo = h("textarea", { rows: 4, maxlength: 60000, placeholder: "Incolla esempi (descrizioni, trascrizioni, elenchi di clip con i tempi)" });
  const urls = h("textarea", { rows: 2, placeholder: "Indirizzi di video YouTube, uno per riga: se hanno i sottotitoli ne leggo parole, tempi e ritmo del parlato" });
  const files = h("input", { type: "file", multiple: true, accept: ".xml,.fcpxml,.edl,.srt,.vtt,.txt,.md,.pdf,.docx" });
  const docs = h("select", { multiple: true, size: 5 });
  const crea = h("button", { class: "p", type: "button" }, "Studia e crea la scheda di stile");
  crea.addEventListener("click", async () => {
    crea.disabled = true;
    try {
      const fd = new FormData(); fd.append("nome", nome.value); fd.append("tipo", tipo.value); fd.append("note", nota.value); fd.append("testo", testo.value); fd.append("urls", urls.value);
      fd.append("documenti", [...docs.selectedOptions].map(o => o.value).join(","));
      for (const f of files.files) fd.append("files", f);
      const r = await api("POST", "/gestione/contenuti/stili", fd);
      msgS.replaceChildren(avviso("Studio avviato: la scheda sarà pronta fra poco." + (r.avvisi.length ? " Non letto: " + r.avvisi.join("; ") : ""), r.avvisi.length ? "no" : "ok"));
      files.value = ""; testo.value = ""; urls.value = ""; nome.value = ""; carica();
    } catch (e) { msgS.replaceChildren(avviso(e.message, "no")); }
    crea.disabled = false;
  });
  const apri = async (id) => {
    try {
      const s = await api("GET", "/gestione/contenuti/stili/" + id);
      const chiudi = h("button", { class: "s", type: "button", onclick: () => schedaBox.replaceChildren() }, "Chiudi");
      const rifai = h("button", { class: "s", type: "button" }, "Rianalizza");
      rifai.addEventListener("click", async () => { try { await api("POST", "/gestione/contenuti/stili/" + id + "/rianalizza"); schedaBox.replaceChildren(); carica(); } catch (e) { msgS.replaceChildren(avviso(e.message, "no")); } });
      schedaBox.replaceChildren(h("div", { class: "carta" }, h("h3", {}, s.nome), h("pre", { style: "white-space:pre-wrap;font:inherit" }, s.scheda || (s.errore ? "Errore: " + s.errore : "Analisi in corso…")), h("div", { class: "azioni" }, rifai, chiudi)));
    } catch (e) { msgS.replaceChildren(avviso(e.message, "no")); }
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/contenuti");
      riempi(stile, [h("option", { value: "" }, "Nessuno in particolare"), d.stili.filter(s => s.ha_scheda).map(s => h("option", { value: s.id }, s.nome))]);
      riempi(docs, d.documenti.map(x => h("option", { value: x.id }, x.nome)));
      riempi(lista, !d.attivo ? h("p", { class: "aiuto" }, "Il reparto Contenuti non è ancora attivo: attivalo da «Reparti pronti».") : d.stili.length ? d.stili.map(s => h("div", { class: "carta", style: "margin-bottom:6px" },
        h("b", {}, s.nome), " · " + (s.tipo === "mio" ? "mio stile" : "riferimento") + " · " + ({ in_analisi: "in analisi…", pronto: "pronta", errore: "errore" })[s.stato] + (s.errore ? " (" + s.errore + ")" : ""),
        h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => apri(s.id) }, "Apri la scheda"),
          h("button", { class: "s", type: "button", onclick: async () => { if (!confirm("Eliminare lo stile «" + s.nome + "»?")) return; try { await api("DELETE", "/gestione/contenuti/stili/" + s.id); carica(); } catch (e) { msgS.replaceChildren(avviso(e.message, "no")); } } }, "Elimina")))) : h("p", { class: "sotto" }, "Nessuno stile ancora."));
    } catch (e) { msgS.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  const t = setInterval(() => { if (!document.body.contains(lista)) clearInterval(t); else if (document.activeElement.tagName !== "TEXTAREA" && document.activeElement.tagName !== "INPUT") carica(); }, 15000);
  return h("div", {}, h("h2", {}, "Contenuti: brief e stili di montaggio"),
    h("h3", {}, "Nuovo brief"), h("p", { class: "aiuto" }, "Descrivi cosa serve; il Direttore dei Contenuti lo smista a copy, grafica, audio, foto e montatori. Puoi indicare uno stile e incollare esempi da replicare."),
    campo("Titolo", titolo), campo("Formato", formato), campo("Programma di montaggio", programma), campo("Obiettivo e pubblico", obiettivo), campo("Durata", durata), campo("Materiali disponibili", materiali),
    campo("Stile di riferimento", stile), campo("Esempi da replicare", esempi), campo("Note", note), h("div", { class: "azioni" }, manda), msgB,
    h("h3", {}, "Stili di montaggio"), h("p", { class: "aiuto" }, "Fai studiare ai montatori il tuo modo di montare: carica gli XML di Premiere, i fcpxml di DaVinci o le EDL dei tuoi montaggi (ne misuro ritmo dei tagli, transizioni, titoli), aggiungi sottotitoli, esempi incollati o video YouTube. Ne esce una scheda di stile che i montatori usano nei brief."),
    campo("Nome dello stile", nome), campo("Tipo", tipo), campo("Note", nota), campo("File (XML, fcpxml, EDL, SRT/VTT, testo)", files),
    campo("Oppure documenti già in memoria (tieni premuto per sceglierne più d'uno)", docs), campo("Testo incollato", testo), campo("Video YouTube", urls), h("div", { class: "azioni" }, crea), msgS, schedaBox, lista);
}

// ---------- Profili social monitorati ----------
function vistaMonitorSocial() {
  const msg = h("div"), lista = h("div"), rapporti = h("div"), testoRapporto = h("div");
  const num = (n) => n === null || n === undefined ? "—" : Number(n).toLocaleString("it-IT");
  const piatt = h("select", {}, ["instagram", "youtube", "facebook", "linkedin", "altro"].map(v => h("option", { value: v }, v.charAt(0).toUpperCase() + v.slice(1))));
  const indirizzo = h("input", { maxlength: 300, placeholder: "Indirizzo del profilo oppure @nome" }), nome = h("input", { maxlength: 120, placeholder: "Nome (facoltativo)" });
  const proprio = h("input", { type: "checkbox" });
  const aggiungi = h("button", { class: "p", type: "button" }, "Aggiungi il profilo");
  const ytK = h("input", { type: "password", placeholder: "Chiave YouTube Data API", autocomplete: "off" }), mTok = h("input", { type: "password", placeholder: "Token Meta (Instagram Graph API)", autocomplete: "off" });
  const mId = h("input", { placeholder: "ID account Instagram professionale (numero)" });
  const ore = h("input", { type: "number", min: 1, max: 168, style: "width:70px" }), gg = h("input", { type: "number", min: 0, max: 60, style: "width:70px" });
  const salva = h("button", { class: "s", type: "button" }, "Salva collegamenti e frequenze");
  const stCol = h("div", { class: "sotto" });
  const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
  aggiungi.addEventListener("click", async () => {
    try { const r = await api("POST", "/gestione/social-monitor/profili", { piattaforma: piatt.value, indirizzo: indirizzo.value, nome: nome.value, proprio: proprio.checked });
      indirizzo.value = ""; nome.value = ""; msg.replaceChildren(avviso(r.automatico ? "Aggiunto: provo a raccogliere i dati." : "Aggiunto. Per questa piattaforma i dati si inseriscono a mano (o li legge l'Analista dalle statistiche che incolli).", "ok"));
      if (r.automatico) { try { await api("POST", "/gestione/social-monitor/profili/" + r.id + "/raccogli"); } catch (e) { err(e); } } carica();
    } catch (e) { err(e); }
  });
  salva.addEventListener("click", async () => {
    const b = { ore: Number(ore.value), giorni_rapporto: Number(gg.value) };
    if (ytK.value.trim()) b.youtube_chiave = ytK.value; if (mTok.value.trim()) b.meta_token = mTok.value; if (mId.value.trim()) b.meta_ig_id = mId.value;
    try { await api("PUT", "/gestione/social-monitor/collegamenti", b); ytK.value = ""; mTok.value = ""; msg.replaceChildren(avviso("Salvato.", "ok")); carica(); } catch (e) { err(e); }
  });
  const rilev = (p) => {
    const s = h("input", { type: "number", min: 0, placeholder: "Seguaci", style: "width:110px" }), t = h("textarea", { rows: 3, placeholder: "Incolla qui le statistiche (esportazione, numeri dei post, note)" });
    const ok = h("button", { class: "p", type: "button" }, "Salva la rilevazione");
    ok.addEventListener("click", async () => { try { await api("POST", "/gestione/social-monitor/profili/" + p.id + "/rilevazione", { seguaci: s.value === "" ? null : Number(s.value), testo: t.value }); carica(); } catch (e) { err(e); } });
    return h("div", { class: "carta", style: "margin-top:6px" }, h("div", { style: "display:flex;gap:6px;flex-wrap:wrap" }, s, ok), t);
  };
  const apriRapporto = async (id) => { try { const r = await api("GET", "/gestione/social-monitor/rapporti/" + id);
    testoRapporto.replaceChildren(h("div", { class: "carta" }, h("pre", { style: "white-space:pre-wrap;font:inherit" }, r.testo || (r.errore ? "Errore: " + r.errore : "In preparazione…")), h("button", { class: "s", type: "button", onclick: () => testoRapporto.replaceChildren() }, "Chiudi"))); } catch (e) { err(e); } };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/social-monitor");
      if (document.activeElement !== ore) ore.value = d.ore; if (document.activeElement !== gg) gg.value = d.giorni_rapporto;
      stCol.textContent = "YouTube: " + (d.collegamenti.youtube ? "collegato" : "non collegato") + " · Instagram: " + (d.collegamenti.instagram ? "collegato" : "non collegato") + ". Facebook e LinkedIn: solo rilevazioni inserite a mano.";
      riempi(lista, d.profili.length ? d.profili.map(p => {
        const u = p.ultima, tr = (p.storico || []).length > 1 ? (p.storico[p.storico.length - 1] - p.storico[0]) : null;
        const box = h("div", { class: "carta", style: "margin-bottom:8px" },
          h("b", {}, p.nome), " · " + p.piattaforma + (p.proprio ? " · nostro" : " · seguito") + (p.azienda ? " · " + p.azienda : ""),
          h("div", { class: "sotto" }, u ? "Seguaci " + num(u.seguaci) + " · contenuti " + num(u.contenuti) + (u.visualizzazioni ? " · visualizzazioni " + num(u.visualizzazioni) : "") + (tr !== null ? " · da " + p.storico.length + " rilevazioni: " + (tr >= 0 ? "+" : "") + tr : "") + " · " + new Date(u.rilevata_il).toLocaleDateString("it-IT") + " (" + u.origine + ")" : "Nessuna rilevazione ancora."),
          p.errore ? h("div", { class: "sotto", style: "color:#e8795a" }, p.errore) : null);
        const az = h("div", { class: "azioni" });
        if (["youtube", "instagram"].includes(p.piattaforma)) az.append(h("button", { class: "s", type: "button", onclick: async () => { try { await api("POST", "/gestione/social-monitor/profili/" + p.id + "/raccogli"); msg.replaceChildren(); } catch (e) { err(e); } carica(); } }, "Raccogli ora"));
        let aperto = null;
        az.append(h("button", { class: "s", type: "button", onclick: () => { if (aperto) { aperto.remove(); aperto = null; } else { aperto = rilev(p); box.append(aperto); } } }, "Inserisci rilevazione"));
        az.append(h("button", { class: "s", type: "button", onclick: async () => { if (!confirm("Togliere «" + p.nome + "» dal monitoraggio (con le sue rilevazioni)?")) return; try { await api("DELETE", "/gestione/social-monitor/profili/" + p.id); carica(); } catch (e) { err(e); } } }, "Togli"));
        box.append(az); return box;
      }) : h("p", { class: "sotto" }, "Nessun profilo ancora."));
      riempi(rapporti, d.rapporti.map(r => h("div", { class: "sotto" }, new Date(r.creato_il).toLocaleString("it-IT") + " · " + ({ in_corso: "in preparazione…", pronto: "pronto", errore: "errore" })[r.stato] + " (" + r.origine + ") ", h("a", { href: "#", onclick: ev => { ev.preventDefault(); apriRapporto(r.id); } }, "apri"))));
    } catch (e) { err(e); }
  };
  const rapp = h("button", { class: "p", type: "button" }, "Prepara il rapporto ora"), imp = h("button", { class: "s", type: "button" }, "Aggiungi i canali collegati a Buffer");
  rapp.addEventListener("click", async () => { try { await api("POST", "/gestione/social-monitor/rapporto"); msg.replaceChildren(avviso("Rapporto in preparazione: compare qui sotto fra poco.", "ok")); setTimeout(carica, 4000); } catch (e) { err(e); } });
  imp.addEventListener("click", async () => { try { const r = await api("POST", "/gestione/social-monitor/importa-canali"); msg.replaceChildren(avviso(r.aggiunti + " canali aggiunti come «nostri».", "ok")); carica(); } catch (e) { err(e); } });
  carica();
  const t = setInterval(() => { if (!document.body.contains(lista)) clearInterval(t); else if (!["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) carica(); }, 20000);
  return h("div", {}, h("h2", {}, "Profili social monitorati"),
    h("p", { class: "aiuto" }, "Indica i profili (tuoi e di altri) che il reparto Social deve seguire: l'Analista ne rileva seguaci e contenuti, confronta l'andamento e scrive un rapporto con le raccomandazioni. Per YouTube e Instagram i dati arrivano dalle API ufficiali; per Facebook e LinkedIn non esiste un accesso ufficiale ai dati di altri, quindi si inseriscono a mano."),
    h("h3", {}, "Nuovo profilo"), h("label", {}, "Piattaforma", piatt), h("label", {}, "Indirizzo o @nome", indirizzo), h("label", {}, "Nome", nome), h("label", {}, proprio, " È un profilo nostro (su cui operiamo)"), h("div", { class: "azioni" }, aggiungi, imp), msg,
    h("h3", {}, "Profili"), lista, h("h3", {}, "Rapporti"), h("div", { class: "azioni" }, rapp), rapporti, testoRapporto,
    h("h3", {}, "Collegamenti e frequenza"), stCol, h("p", { class: "aiuto" }, "YouTube: crea una chiave «YouTube Data API v3» (gratuita) nella console Google Cloud. Instagram: serve un account Instagram professionale collegato a una pagina Facebook e un'app Meta; il token e l'ID dell'account si ricavano da lì. Le chiavi si conservano cifrate e non vengono mai mostrate."),
    ytK, mTok, mId, h("label", {}, "Raccogli ogni (ore)", ore), h("label", {}, "Rapporto automatico ogni (giorni, 0 = mai)", gg), h("div", { class: "azioni" }, salva));
}
