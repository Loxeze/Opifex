"use strict";
// Dashboard (3D al centro, pannelli intorno), Impostazioni e controllo del repository documenti.

const NOME_FASCIA_AGENTE = { pubblico: "dati pubblici", interno: "dati pubblici e interni", riservato: "tutti i dati" };

function pannello(titolo, corpo, azione) {
  return h("section", { class: "pan" }, h("div", { class: "pan-testa" }, h("h3", {}, titolo), azione || null), corpo);
}

function vistaDashboard() {
  const scena = vistaOrganigramma();
  scena.classList.add("scena-pagina");
  const boxRic = h("div", { class: "pan-corpo" }, h("p", { class: "sotto" }, "Caricamento…"));
  const boxPro = h("div", { class: "pan-corpo" }, h("p", { class: "sotto" }, "Caricamento…"));
  const caricaRichieste = async () => {
    try {
      const el = await api("GET", "/gestione/richieste?stato=aperta");
      stato.richieste = el.length;
      // se stai scrivendo una risposta, non ridisegnare: perderesti il testo
      if (boxRic.contains(document.activeElement) || [...boxRic.querySelectorAll("input")].some(i => i.value.trim())) return;
      riempi(boxRic, el.length ? [el.slice(0, 4).map(r => {
        const ris = h("input", { type: "text", placeholder: "Rispondi… (Invio per inviare)", maxlength: 2000 });
        const invia = async (btn) => {
          if (!ris.value.trim()) return; if (btn) btn.disabled = true; ris.disabled = true;
          try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); ris.value = ""; caricaRichieste(); }
          catch (x) { alert(x.message); ris.disabled = false; if (btn) btn.disabled = false; } };
        ris.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); invia(null); } });
        return h("div", { class: "voce" },
          h("div", { class: "nome" }, (r.bloccante ? "BLOCCANTE · " : "") + r.agente),
          h("div", { class: "sotto" }, r.domanda),
          h("div", { class: "riga-inline" }, ris, h("button", { class: "p", onclick: (e) => invia(e.currentTarget) }, "Invia")));
      }), el.length > 4 ? h("button", { class: "s", onclick: () => vai("richieste") }, "Vedi tutte (" + el.length + ")") : null]
        : h("p", { class: "sotto" }, "Nessuna richiesta aperta. Gli agenti hanno tutto ciò che serve."));
    } catch (e) { boxRic.replaceChildren(avviso(e.message, "no")); }
  };
  const caricaProgetti = async () => {
    try {
      const d = await api("GET", "/gestione/progetti");
      const att = d.progetti.filter(p => !p.archiviato && !p.eliminato_il);
      riempi(boxPro, att.length ? att.map(p => h("div", { class: "voce voce-clic", tabindex: 0, role: "button", onclick: () => vai("progetti"), onkeydown: (e) => { if (e.key === "Enter") vai("progetti"); } },
        h("div", { class: "nome" }, h("span", { class: "punto-col", style: "background:" + (p.colore || "#f3b54a") }), p.nome),
        h("div", { class: "sotto" }, (p.azienda ? p.azienda + " · " : "") + p.agenti.length + " agenti · Drive: " + ({ ok: "pronto", da_sincronizzare: "da creare", errore: "errore" })[p.drive_stato]))) : h("p", { class: "sotto" }, "Nessun progetto."));
    } catch (e) { boxPro.replaceChildren(avviso(e.message, "no")); }
  };
  // --- chat in tempo reale di tutta l'organizzazione (messaggi tra agenti)
  const boxChat = h("div", { class: "pan-corpo chat-org" }, h("p", { class: "sotto" }, "Caricamento…"));
  let ultimoId = 0, primo = true;
  const voceChat = (m) => h("div", { class: "msg-org" },
    h("div", { class: "sotto" }, h("b", {}, (m.da || "?") + " → " + (m.a || "?")), " · " + new Date(m.creato_il).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) + " · " + m.titolo),
    h("div", { class: "risposta" }, m.testo));
  const aggiornaChat = async () => {
    try {
      const nuovi = await api("GET", "/gestione/dialoghi/feed" + (primo ? "" : "?dopo_id=" + ultimoId));
      const alFondo = boxChat.scrollTop + boxChat.clientHeight >= boxChat.scrollHeight - 40;
      if (primo || (nuovi.length && boxChat.firstChild && boxChat.firstChild.tagName === "P")) boxChat.replaceChildren();
      if (primo && !nuovi.length) boxChat.append(h("p", { class: "sotto" }, "Nessuna conversazione ancora. Quando gli agenti si parlano la vedi qui, in diretta."));
      for (const m of nuovi) { boxChat.append(voceChat(m)); ultimoId = Math.max(ultimoId, m.id); }
      if (primo || (nuovi.length && alFondo)) boxChat.scrollTop = boxChat.scrollHeight;
      primo = false;
    } catch (e) { /* riprova al prossimo giro */ }
  };
  aggiornaChat();
  // --- barra dei numeri in alto
  const barra = h("div", { class: "statistiche" });
  const fm = (n) => n >= 1e6 ? (n / 1e6).toFixed(2).replace(".", ",") + " M" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(".", ",") + " k" : String(n);
  const tessera = (titolo, valore, sotto, extra) => h("div", { class: "tessera" }, h("div", { class: "sotto" }, titolo), h("div", { class: "valore" }, valore), sotto ? h("div", { class: "sotto" }, sotto) : null, extra || null);
  const aggiornaStat = async () => {
    try {
      const x = await api("GET", "/gestione/dashboard/statistiche");
      const grafico = h("canvas", { width: 120, height: 28, class: "mini", "aria-label": "Token negli ultimi 7 giorni" });
      const g = grafico.getContext("2d"), mx = Math.max(1, ...x.giorni.map(d => d.token));
      g.fillStyle = "#f3b54a"; x.giorni.forEach((d, i) => { const hh = Math.max(1, Math.round(26 * d.token / mx)); g.fillRect(i * 17 + 1, 28 - hh, 13, hh); });
      riempi(barra, [
        tessera("Token oggi", fm(x.token_oggi), "$ " + x.costo_oggi.toFixed(2) + " stimati", grafico),
        tessera("Token del mese", fm(x.token_mese), "$ " + x.costo_mese.toFixed(2) + " · in " + fm(x.input_mese) + " · out " + fm(x.output_mese)),
        tessera("Più attivi del mese", x.top_agenti.length ? x.top_agenti.map(t => t.nome).join(", ") : "—", x.top_agenti.length ? fm(x.top_agenti[0].token) + " token il primo" : "nessun consumo"),
        tessera("Messaggi tra agenti oggi", String(x.messaggi_oggi), x.limite_dialoghi_giorno ? "dialoghi: " + fm(x.token_dialoghi_oggi) + " / " + fm(x.limite_dialoghi_giorno) + " token" : null),
        tessera("Agenti attivi", x.agenti_attivi + " / " + x.agenti_totali, null),
        tessera("Richieste aperte", String(x.richieste_aperte), x.richieste_bloccanti ? x.richieste_bloccanti + " bloccanti" : "nessuna bloccante")]);
    } catch (e) { barra.replaceChildren(avviso(e.message, "no")); }
  };
  aggiornaStat();
  const garanzie = ((stato.opzioni && stato.opzioni.fornitori) || []).filter(f => !(f.non_conservazione_attiva && f.dpa_firmato));
  const boxAvvisi = h("div", { class: "pan-corpo" },
    garanzie.length ? avviso("Dati interni e riservati bloccati verso: " + garanzie.map(f => f.nome).join(", ") + ". Mancano le garanzie del fornitore.", "avv") : avviso("Garanzie dei fornitori attive.", "ok"),
    stato.agenti.some(a => !a.attivo) ? h("p", { class: "sotto" }, stato.agenti.filter(a => !a.attivo).length + " agenti spenti.") : null);
  const daFare = pannelloDaFare();
  let cicli = 0;
  caricaRichieste(); caricaProgetti();
  stato.timer2 = setInterval(() => { aggiornaChat(); if (++cicli % 3 === 0) { caricaRichieste(); caricaProgetti(); aggiornaStat(); daFare.ricarica(); } }, 3000);
  return h("div", { class: "dashboard" }, barra,
    h("div", { class: "colonna col-sx" }, daFare.el, pannello("Richieste degli agenti", boxRic), pannello("Progetti", boxPro, h("button", { class: "s", onclick: () => vai("progetti") }, "Apri"))),
    scena,
    h("div", { class: "colonna col-dx" }, pannello("Chat dell'organizzazione · in diretta", boxChat), pannello("Avvisi", boxAvvisi)));
}

function vistaImpostazioni() {
  const mappa = { profilo: vistaAccount, struttura: vistaStruttura, collegamenti: () => [vistaCollegamenti(), h("hr"), vistaEmail()].flat(Infinity), iniziative: vistaIniziative, connessioni: vistaConnessioni, canali: vistaCanali, percorsi: vistaPercorsi, social: vistaSocial,
    utenti: vistaUtenti, aggiornamenti: vistaAggiornamenti, sicurezza: vistaSicurezza, registro: vistaRegistro, sistema: vistaSistema, memoria: vistaMemoria, dossier: vistaDossier, biblioteca: vistaBiblioteca, studi: vistaStudi, cerimoniere: vistaCerimoniere, quando: vistaQuando, smistamento: vistaSmistamento, reparti: vistaReparti, sandbox: vistaSandbox, voce: vistaVoce, app: vistaApp };
  if (!mappa[stato.sezione]) stato.sezione = "profilo";
  return h("div", { class: "impostazioni" },
    h("nav", { class: "menu-imp", "aria-label": "Sezioni delle impostazioni" }, SEZIONI_IMPOSTAZIONI.map(([id, nome]) =>
      h("button", { class: stato.sezione === id ? "attivo" : "", onclick: () => vai("impostazioni", id) }, nome))),
    h("div", { class: "contenuto-imp" }, [mappa[stato.sezione]()].flat(Infinity)));
}

// Controllo di tutti i documenti del repository: i documenti si caricano dalla scheda di ciascun agente
function vistaDocumenti() {
  const lista = h("div");
  const cerca = h("input", { type: "search", placeholder: "Cerca per nome o file…", maxlength: 100 });
  const fFascia = h("select", {}, h("option", { value: "" }, "Tutti i livelli"), Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t)));
  const fAgente = h("select", {}, h("option", { value: "" }, "Tutti gli agenti"), h("option", { value: "-1" }, "Senza agente"), stato.agenti.map(a => h("option", { value: a.id }, a.nome)));
  const nomeAg = (id) => stato.agenti.find(a => a.id === id)?.nome || "?";
  const anteprima = h("div", { class: "carta anteprima-doc" }, h("p", { class: "sotto" }, "Scegli un documento a sinistra per leggerlo qui."));
  const mostraAnteprima = async (d) => {
    anteprima.replaceChildren(h("p", { class: "sotto" }, "Carico…"));
    try {
      const r = await api("GET", "/gestione/documenti/" + d.id + "/testo");
      anteprima.replaceChildren(h("div", { class: "nome" }, r.nome), h("div", { class: "sotto" }, r.nome_file + " · " + ETICHETTA_FASCIA[r.fascia_dati]),
        h("pre", { class: "testo-doc" }, r.testo || "(il documento non contiene testo leggibile)"), r.troncato ? h("p", { class: "sotto" }, "Anteprima limitata ai primi 200 mila caratteri.") : null);
    } catch (e) { anteprima.replaceChildren(avviso(e.message, "no")); }
  };
  const disegnaLista = () => {
    const q = cerca.value.trim().toLowerCase();
    const el = stato.documenti.filter(d => (!q || (d.nome + " " + d.nome_file).toLowerCase().includes(q)) && (!fFascia.value || d.fascia_dati === fFascia.value)
      && (!fAgente.value || (fAgente.value === "-1" ? (!d.per_tutti && !d.assegnazioni.length) : d.per_tutti || d.assegnazioni.some(x => x.agente_id === Number(fAgente.value)))));
    riempi(lista, el.length ? el.map(d => {
      const dirette = d.assegnazioni.filter(x => !x.passato_da);
      const chi = d.per_tutti ? "Tutti gli agenti" : dirette.length ? dirette.map(x => {
        const passati = d.assegnazioni.filter(y => y.passato_da === x.agente_id).map(y => nomeAg(y.agente_id));
        return nomeAg(x.agente_id) + (passati.length ? " → " + passati.join(", ") : "");
      }).join(" · ") : "Nessun agente (non lo usa nessuno)";
      return h("div", { class: "carta" + (stato.docAperto === d.id ? " doc-sel" : ""), style: "margin-bottom:10px;cursor:pointer", onclick: (ev) => { if (ev.target.closest("button")) return; stato.docAperto = d.id; disegnaLista(); mostraAnteprima(d); } },
        h("div", { class: "nome" }, d.nome),
        h("div", { class: "sotto" }, d.nome_file + " · " + Math.round(d.caratteri / 1000) + " mila caratteri · caricato da " + (d.caricato_da || "—") + " il " + new Date(d.creato_il).toLocaleDateString("it-IT")),
        h("div", {}, h("span", { class: "etichetta " + (d.fascia_dati === "pubblico" ? "ok" : "avv") }, ETICHETTA_FASCIA[d.fascia_dati])),
        h("div", { class: "sotto" }, "Lo usano: " + chi + " (e i loro superiori)"),
        h("div", { class: "azioni" },
          h("button", { class: "s", onclick: () => modificaDocumento(d) }, "Modifica"),
          h("button", { class: "r", onclick: async () => {
            if (!confirm("Eliminare «" + d.nome + "» dal repository?")) return;
            try { await api("DELETE", "/gestione/documenti/" + d.id); await ricarica(); } catch (e) { alert(e.message); } } }, "Elimina")));
    }) : h("p", { class: "sotto" }, stato.documenti.length ? "Nessun documento con questi filtri." : "Il repository è vuoto. Apri la scheda di un agente (Agenti) per caricare il suo documento di riferimento."));
  };
  [cerca, fFascia, fAgente].forEach(x => x.addEventListener("input", disegnaLista));
  disegnaLista();
  const nonUsati = stato.documenti.filter(d => !d.per_tutti && !d.assegnazioni.length).length;
  return [h("h2", {}, "Repository documenti"),
    h("p", { class: "sotto" }, stato.documenti.length + " documenti. Ogni documento si carica dalla scheda dell'agente a cui serve; il manager può passarlo ai suoi sottoposti, mentre i superiori lo vedono in automatico. Qui controlli tutto."),
    nonUsati ? avviso(nonUsati + " documenti non sono usati da nessun agente.", "avv") : null,
    h("div", { class: "riga" }, h("label", {}, "Cerca", cerca), h("label", {}, "Livello", fFascia), h("label", {}, "Agente", fAgente)),
    h("div", { class: "doc-doppio" }, lista, anteprima)];
}
