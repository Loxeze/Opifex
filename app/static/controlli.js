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
      agente.replaceChildren(h("option", { value: "" }, "— scegli l'agente che deve imparare —"), d.agenti.map(a => h("option", { value: a.id }, a.nome + " — " + a.ruolo)));
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
