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
      riempi(boxRic, el.length ? [el.slice(0, 4).map(r => {
        const ris = h("input", { type: "text", placeholder: "Rispondi…", maxlength: 2000 });
        return h("div", { class: "voce" },
          h("div", { class: "nome" }, (r.bloccante ? "BLOCCANTE · " : "") + r.agente),
          h("div", { class: "sotto" }, r.domanda),
          h("div", { class: "riga-inline" }, ris, h("button", { class: "p", onclick: async (e) => {
            if (!ris.value.trim()) return; e.currentTarget.disabled = true;
            try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); caricaRichieste(); } catch (x) { alert(x.message); e.currentTarget.disabled = false; } } }, "Invia")));
      }), el.length > 4 ? h("button", { class: "s", onclick: () => vai("richieste") }, "Vedi tutte (" + el.length + ")") : null]
        : h("p", { class: "sotto" }, "Nessuna richiesta aperta. Gli agenti hanno tutto ciò che serve."));
    } catch (e) { boxRic.replaceChildren(avviso(e.message, "no")); }
  };
  const caricaProgetti = async () => {
    try {
      const d = await api("GET", "/gestione/progetti");
      const att = d.progetti.filter(p => !p.archiviato);
      riempi(boxPro, att.length ? att.map(p => h("div", { class: "voce voce-clic", tabindex: 0, role: "button", onclick: () => vai("progetti"), onkeydown: (e) => { if (e.key === "Enter") vai("progetti"); } },
        h("div", { class: "nome" }, p.nome),
        h("div", { class: "sotto" }, p.agenti.length + " agenti · Drive: " + ({ ok: "pronto", da_sincronizzare: "da creare", errore: "errore" })[p.drive_stato]))) : h("p", { class: "sotto" }, "Nessun progetto."));
    } catch (e) { boxPro.replaceChildren(avviso(e.message, "no")); }
  };
  const attivi = stato.agenti.filter(a => a.attivo);
  const si = (v, t) => h("span", { class: "chip " + (v ? "ok" : "no") }, (v ? "✓ " : "✕ ") + t);
  const boxAgenti = h("div", { class: "pan-corpo" }, attivi.map(a => h("div", { class: "voce voce-clic", tabindex: 0, role: "button", onclick: () => modulo(a), onkeydown: (e) => { if (e.key === "Enter") modulo(a); } },
    h("div", { class: "nome" }, a.nome, h("span", { class: "sotto" }, " · " + a.ruolo)),
    h("div", { class: "chips" }, h("span", { class: "chip" }, NOME_FASCIA_AGENTE[a.fascia_dati_max] || a.fascia_dati_max), si(a.accesso_web, "web"), si(a.dialoghi_attivi, "parla con i colleghi"),
      h("span", { class: "chip" }, (a.connessioni || []).length + " connessioni")))));
  const garanzie = ((stato.opzioni && stato.opzioni.fornitori) || []).filter(f => !(f.non_conservazione_attiva && f.dpa_firmato));
  const boxAvvisi = h("div", { class: "pan-corpo" },
    garanzie.length ? avviso("Dati interni e riservati bloccati verso: " + garanzie.map(f => f.nome).join(", ") + ". Mancano le garanzie del fornitore.", "avv") : avviso("Garanzie dei fornitori attive.", "ok"),
    stato.agenti.some(a => !a.attivo) ? h("p", { class: "sotto" }, stato.agenti.filter(a => !a.attivo).length + " agenti spenti.") : null);
  caricaRichieste(); caricaProgetti();
  stato.timer2 = setInterval(() => { caricaRichieste(); caricaProgetti(); }, 10000);
  return h("div", { class: "dashboard" },
    h("div", { class: "colonna col-sx" }, pannello("Richieste degli agenti", boxRic), pannello("Progetti", boxPro, h("button", { class: "s", onclick: () => vai("progetti") }, "Apri"))),
    scena,
    h("div", { class: "colonna col-dx" }, pannello("Cosa possono fare gli agenti", boxAgenti), pannello("Avvisi", boxAvvisi)));
}

function vistaImpostazioni() {
  const mappa = { profilo: vistaAccount, struttura: vistaStruttura, collegamenti: vistaCollegamenti, connessioni: vistaConnessioni, canali: vistaCanali,
    utenti: vistaUtenti, aggiornamenti: vistaAggiornamenti, sicurezza: vistaSicurezza };
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
      return h("div", { class: "carta", style: "margin-bottom:10px" },
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
    h("div", { class: "riga" }, h("label", {}, "Cerca", cerca), h("label", {}, "Livello", fFascia), h("label", {}, "Agente", fAgente)), lista];
}
