"use strict";
// Dashboard (3D al centro, pannelli intorno), Impostazioni e controllo del repository documenti.

const NOME_FASCIA_AGENTE = { pubblico: "dati pubblici", interno: "dati pubblici e interni", riservato: "tutti i dati" };

function pannello(titolo, corpo, azione) {
  return h("section", { class: "pan" }, h("div", { class: "pan-testa" }, h("h3", {}, titolo), azione || null), corpo);
}

function mappaImpostazioni() {
  return { profilo: vistaAccount, struttura: vistaStruttura, collegamenti: vistaCollegamenti, iniziative: vistaIniziative, connessioni: vistaConnessioni, canali: vistaCanali, percorsi: vistaPercorsi, social: vistaSocialCanali,
    utenti: vistaUtenti, aggiornamenti: vistaAggiornamenti, sicurezza: vistaSicurezza, registro: vistaRegistro, sistema: vistaSistema, memoria: vistaMemoria, noteaurora: vistaNoteAurora, diagnostica: vistaDiagnostica, esempio: vistaEsempio, memoriavett: vistaMemoriaVett, giro: vistaGiro, contenuti: vistaContenuti, monitorsocial: vistaMonitorSocial, archivio: vistaArchivio, miglioramenti: vistaMiglioramenti, imprese: vistaImprese, tavoli: vistaTavoli, spesareparti: vistaSpesaReparti, dipendenze: vistaDipendenze, sentinelle: vistaSentinelle, misure: vistaMisure, siti: vistaSiti, dossier: vistaDossier, biblioteca: vistaBiblioteca, studi: vistaStudi, cerimoniere: vistaCerimoniere, quando: vistaQuando, smistamento: vistaSmistamento, reparti: vistaReparti, sandbox: vistaSandbox, scatolanera: vistaScatolaNera, voce: vistaVoce, app: vistaApp, salute: vistaSalute };
}

// Una sezione spostata fuori dalle Impostazioni (Conoscenza, Squadra, Controllo…): la stessa pagina, senza il menu delle impostazioni
function vistaSezione() {
  const mappa = mappaImpostazioni();
  if (!mappa[stato.sezione]) stato.sezione = "memoria";
  return h("div", { class: "contenuto-sez" }, [mappa[stato.sezione]()].flat(Infinity));
}

// Posta: le email preparate dagli agenti da approvare, e dove si collegano le caselle
function vistaPosta() {
  return [h("h2", {}, "Posta"),
    h("p", { class: "sotto" }, "Le email che gli agenti hanno preparato e aspettano il tuo via libera. Le caselle Gmail si collegano nella scheda «Caselle e Google»; quali agenti possono inviare e come si sceglie nella scheda di ciascun agente."),
    codaEmailUscita(),
    h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => vai("sez", "collegamenti") }, "Collega o controlla le caselle"), h("button", { class: "s", type: "button", onclick: () => vai("email") }, "Email marketing (Brevo)"))];
}

// Controllo › Computer locali: i computer con Ollama, i tachimetri, la prova di affidabilita', l'assegnazione e i cantieri
function vistaComputer() {
  return [h("h2", {}, "Computer locali"), pannelloPortatile(), bloccoModelloLocale(ricarica)];
}

function vistaImpostazioni() {
  const mappa = mappaImpostazioni();
  if (!mappa[stato.sezione]) stato.sezione = "profilo";
  const nomeSez = (id) => (SEZIONI_IMPOSTAZIONI.find(x => x[0] === id) || [])[1] || id;
  const noti = new Set(GRUPPI_IMP.flatMap(g => g[1]));
  if (SEZIONI_FUORI.has(stato.sezione)) stato.sezione = "profilo";
  const gruppi = GRUPPI_IMP.concat([["Altro", SEZIONI_IMPOSTAZIONI.map(x => x[0]).filter(id => !noti.has(id) && !SEZIONI_FUORI.has(id))]]).map(([t, ids]) => [t, ids.filter(id => mappa[id])]).filter(g => g[1].length);
  // Il browser scambiava questo campo per il «nome utente» delle chiavi API della pagina e ci scriveva da solo l'email salvata, filtrando via tutte le voci.
  // Resta in sola lettura finche' non lo tocchi tu, e cio' che vi compare senza che tu ci stia scrivendo viene scartato.
  const cerca = h("input", { type: "search", class: "cerca-imp", name: "cerca-impostazioni", placeholder: "Cerca nelle impostazioni…", "aria-label": "Cerca nelle impostazioni",
    autocomplete: "off", readonly: "", "data-lpignore": "true", "data-1p-ignore": "true", "data-bwignore": "true", "data-form-type": "other" });
  const sblocca = () => cerca.removeAttribute("readonly");
  cerca.addEventListener("focus", sblocca); cerca.addEventListener("pointerdown", sblocca);
  cerca.addEventListener("blur", () => cerca.setAttribute("readonly", ""));
  const nav = h("nav", { class: "menu-imp", "aria-label": "Sezioni delle impostazioni" });
  const disegnaNav = () => {
    const q = cerca.value.trim().toLowerCase();
    riempi(nav, gruppi.map(([titolo, ids]) => {
      const vis = ids.filter(id => !q || (nomeSez(id) + " " + titolo).toLowerCase().includes(q));
      if (!vis.length) return null;
      const det = h("details", { class: "gruppo-imp" }, h("summary", {}, titolo),
        vis.map(id => h("button", { class: stato.sezione === id ? "attivo" : "", "aria-current": stato.sezione === id ? "page" : null, onclick: () => vai("impostazioni", id) }, nomeSez(id))));
      det.open = !!q || ids.includes(stato.sezione);
      return det;
    }));
    if (q) {   // cio' che hai cercato potrebbe essersi spostato nel menu: lo si mostra con la sua nuova casa
      const fuori = MENU.flatMap(g => g[2].map(t => [g[1], t])).filter(([gn, t]) => t[1] !== "impostazioni" && (t[0] + " " + gn + " " + (t[2] ? nomeSez(t[2]) : "")).toLowerCase().includes(q));
      if (fuori.length) nav.append(h("details", { class: "gruppo-imp", open: true }, h("summary", {}, "Nel menu"),
        fuori.map(([gn, t]) => h("button", { onclick: () => vai(t[1], t[2]) }, gn + " › " + t[0]))));
    }
    if (!nav.children.length) nav.append(h("p", { class: "sotto" }, "Nessuna voce trovata."), h("button", { class: "s", onclick: () => { cerca.value = ""; disegnaNav(); } }, "Mostra tutte le voci"));
  };
  cerca.addEventListener("input", () => { if (document.activeElement !== cerca) cerca.value = ""; disegnaNav(); });
  cerca.addEventListener("change", () => { if (document.activeElement !== cerca && cerca.value) { cerca.value = ""; disegnaNav(); } });
  disegnaNav();
  const scelta = h("select", { class: "imp-select", "aria-label": "Sezione delle impostazioni", onchange: (e) => vai("impostazioni", e.target.value) },
    gruppi.map(([t, ids]) => h("optgroup", { label: t }, ids.map(id => { const o = h("option", { value: id }, nomeSez(id)); if (id === stato.sezione) o.selected = true; return o; }))));
  return h("div", { class: "impostazioni" },
    h("div", { class: "menu-imp-box" }, cerca, scelta, nav),
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
