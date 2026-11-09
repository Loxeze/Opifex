"use strict";
// Cruscotto del progetto: schermata iniziale col materiale prodotto dagli agenti, calendario delle scadenze, Gantt e riunione con i soggetti coinvolti.

const MS_GIORNO = 86400000;
const inizioGiorno = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const chiaveGiorno = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const crDataBreve = (s) => new Date(s).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
const dataSolo = (s) => { const x = String(s).slice(0, 10).split("-"); return new Date(+x[0], +x[1] - 1, +x[2]); };   // le scadenze sono giorni, non istanti: niente scarti di fuso

function bottoneRiunione(sogg, p, msg) {
  if (!sogg || !sogg.length) return h("p", { class: "sotto" }, "Per avviare una riunione serve almeno un manager coinvolto: assegna un project manager o delle task agli agenti del progetto.");
  const b = h("button", { class: "p", "data-uso": "progetto-avvia-riunione", onclick: async () => {
    b.disabled = true;
    try {
      if (typeof CallVoce !== "undefined") CallVoce.sblocca(true);
      const r = await api("POST", "/gestione/progetti/" + p.id + "/riunione");
      stato.chatTab = "riunioni"; stato.apriCall = r.id; vai("chat");
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; }
  } }, "🎙 Avvia una riunione con loro");
  return h("div", { class: "azioni" }, b, h("span", { class: "sotto" }, "Con " + sogg.map(s => s.nome).join(", ") + ". L'ordine del giorno lo prepara il progetto."));
}

function crTessera(valore, etichetta, classe) { return h("div", { class: "cr-kpi " + (classe || "") }, h("div", { class: "cr-kpi-n" }, String(valore)), h("div", { class: "sotto" }, etichetta)); }

// Apre/chiude il testo di un contenuto prodotto (documento o scheda di agente), caricandolo solo la prima volta
function leggiMateriale(m, p, corpo, apri) {
  return async () => {
    if (!corpo.hidden) { corpo.hidden = true; apri.textContent = "Leggi"; return; }
    corpo.hidden = false; apri.textContent = "Chiudi"; if (corpo.dataset.caricato) return;
    corpo.textContent = "Carico…";
    try {
      const t = m.tipo === "documento" ? (await api("GET", "/documenti/" + m.id + "/testo")).testo : (await api("GET", "/progetti/" + p.id + "/materiale/" + m.id)).testo;
      corpo.textContent = t || "(vuoto)"; corpo.dataset.caricato = "1";
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
}
const titoloMateriale = (m) => m.tipo === "documento" ? m.nome : m.task;
const dettaglioMateriale = (m) => m.tipo === "testo" ? m.anteprima + (m.testo.length > 260 ? "…" : "")
  : [m.nome_file, m.caratteri + " caratteri", m.di_base ? "documentazione di base" : ""].filter(Boolean).join(" · ");

// Vista "Schede": carte grandi, divise per genere
function schedeMateriale(cr, p) {
  const gruppo = (titolo, voci) => voci.length ? [h("h4", { class: "cr-gruppo" }, titolo + " (" + voci.length + ")"), h("div", { class: "cr-mat" }, voci.map(m => {
    const corpo = h("div", { class: "cr-mat-testo", hidden: true });
    const apri = h("button", { class: "s", "data-uso": "progetto-leggi-materiale" }, "Leggi");
    apri.onclick = leggiMateriale(m, p, corpo, apri);
    return h("div", { class: "carta cr-mat-carta" },
      h("div", { class: "sotto" }, (m.tipo === "documento" ? "📄 Documento" : "📝 Scheda") + " · " + crDataBreve(m.creato_il) + (m.agente ? " · 🤖 " + m.agente : "")),
      h("div", { class: "nome" }, titoloMateriale(m)), h("div", { class: "sotto" }, dettaglioMateriale(m)), h("div", { class: "azioni" }, apri), corpo);
  }))] : null;
  return [gruppo("Documenti", cr.materiale.filter(m => m.tipo === "documento")), gruppo("Schede e relazioni degli agenti", cr.materiale.filter(m => m.tipo === "testo"))];
}

// Vista "Elenco": una riga per contenuto, dal più recente, con anteprima di una riga
function elencoMateriale(cr, p) {
  return h("div", { class: "cr-elenco" }, cr.materiale.map(m => {
    const corpo = h("div", { class: "cr-mat-testo", hidden: true });
    const apri = h("button", { class: "s", "data-uso": "progetto-leggi-materiale" }, "Leggi");
    apri.onclick = leggiMateriale(m, p, corpo, apri);
    return h("div", { class: "cr-el-riga" },
      h("div", { class: "cr-el-testa" },
        h("span", { class: "cr-data" }, crDataBreve(m.creato_il)),
        h("span", { class: "cr-el-tipo", title: m.tipo === "documento" ? "Documento" : "Scheda" }, m.tipo === "documento" ? "📄" : "📝"),
        h("div", { class: "cr-el-titolo" }, h("div", { class: "nome" }, titoloMateriale(m), m.agente ? h("span", { class: "sotto" }, " · 🤖 " + m.agente) : null), h("div", { class: "sotto cr-el-anteprima" }, dettaglioMateriale(m))),
        apri), corpo);
  }));
}

function carteMateriale(cr, p) {
  if (!cr.materiale.length) return h("p", { class: "sotto" }, "Ancora nessun materiale: quando gli agenti producono schede, relazioni o documenti per questo progetto li trovi qui, dal più recente.");
  let vista = "schede";
  try { vista = localStorage.getItem("opifex_vista_materiale") === "elenco" ? "elenco" : "schede"; } catch (e) { /* senza memoria del browser si parte dalle schede */ }
  const cont = h("div"), selettore = h("div", { class: "cr-vista", role: "group", "aria-label": "Modo di vedere i contenuti" });
  const disegna = () => {
    riempi(selettore, [["schede", "▦ Schede"], ["elenco", "☰ Elenco"]].map(([k, et]) => h("button", { class: "s" + (vista === k ? " attivo" : ""), "aria-pressed": String(vista === k), "data-uso": "progetto-vista-" + k,
      onclick: () => { vista = k; try { localStorage.setItem("opifex_vista_materiale", k); } catch (e) { /* ignora */ } disegna(); } }, et)));
    riempi(cont, [selettore, vista === "elenco" ? elencoMateriale(cr, p) : schedeMateriale(cr, p)]);
  };
  disegna();
  return cont;
}

function elencoScadenze(cr) {
  const oggi = inizioGiorno(new Date());
  const v = [];
  cr.task.filter(t => t.stato !== "completata" && t.scadenza).forEach(t => v.push({ quando: dataSolo(t.scadenza), testo: t.titolo, chi: t.responsabile, tipo: "task", ritardo: t.in_ritardo }));
  cr.milestone.filter(m => !m.raggiunta_il && m.scadenza).forEach(m => v.push({ quando: dataSolo(m.scadenza), testo: m.titolo, tipo: "milestone", ritardo: dataSolo(m.scadenza) < oggi }));
  v.sort((a, b) => a.quando - b.quando);
  if (!v.length) return h("p", { class: "sotto" }, "Nessuna scadenza fissata.");
  return v.slice(0, 7).map(x => h("div", { class: "cr-riga" + (x.ritardo ? " ritardo" : "") },
    h("span", { class: "cr-data" }, crDataBreve(x.quando)), h("span", {}, (x.tipo === "milestone" ? "◆ " : "") + x.testo), x.chi ? h("span", { class: "sotto" }, " · " + x.chi) : null));
}

function attivitaRecente(cr) {
  if (!cr.attivita.length) return h("p", { class: "sotto" }, "Nessuna attività ancora.");
  const verbo = { commento: "ha scritto su", completata: "ha chiuso", milestone: "ha raggiunto la milestone" };
  return cr.attivita.slice(0, 8).map(a => h("div", { class: "cr-riga" }, h("span", { class: "cr-data" }, crDataBreve(a.quando)),
    h("span", {}, (a.chi ? a.chi + " " : "") + verbo[a.tipo] + " «" + a.oggetto + "»")));
}

// Schermata iniziale del progetto
function panoramicaProgetto(p, d, cr, tit, bloccoDomande, msg) {
  const tot = d.task.length, fatte = d.conteggi.completata, perc = tot ? Math.round(100 * fatte / tot) : 0;
  return [
    h("div", { class: "cr-kpis" }, crTessera(perc + "%", "completato"), crTessera(cr.numeri.aperte, "task aperte"), crTessera(cr.numeri.in_ritardo, "in ritardo", cr.numeri.in_ritardo ? "no" : ""),
      crTessera(cr.numeri.scadenze_7g, "scadenze nei prossimi 7 giorni"), crTessera(cr.materiale.length, "contenuti prodotti")),
    tit ? bottoneRiunione(cr.soggetti, p, msg) : null,
    bloccoDomande,
    h("h3", {}, "Materiale prodotto dagli agenti"), carteMateriale(cr, p),
    h("div", { class: "riga cr-due", style: "align-items:flex-start;margin-top:14px" },
      h("div", { class: "carta" }, h("div", { class: "nome" }, "Prossime scadenze"), elencoScadenze(cr)),
      h("div", { class: "carta" }, h("div", { class: "nome" }, "Attività recente"), attivitaRecente(cr))),
    cr.riunioni.length ? [h("h3", {}, "Riunioni su questo progetto"), cr.riunioni.map(r => h("div", { class: "cr-riga" }, h("span", { class: "cr-data" }, crDataBreve(r.quando)),
      h("span", {}, r.titolo), h("span", { class: "sotto" }, " · " + ({ programmata: "programmata", in_corso: "in corso", conclusa: "conclusa", errore: "errore" }[r.stato] || r.stato))))] : null];
}

// Calendario mensile delle scadenze, delle milestone e delle riunioni
function calendarioProgetto(cr) {
  const cont = h("div"), oggi = inizioGiorno(new Date());
  let mese = new Date(oggi.getFullYear(), oggi.getMonth(), 1), scelto = chiaveGiorno(oggi);
  const eventi = {};
  const metti = (quando, e) => { (eventi[chiaveGiorno(quando)] = eventi[chiaveGiorno(quando)] || []).push(e); };
  cr.task.filter(t => t.scadenza).forEach(t => metti(dataSolo(t.scadenza), { tipo: t.stato === "completata" ? "fatta" : t.in_ritardo ? "ritardo" : "task", testo: t.titolo, chi: t.responsabile }));
  cr.milestone.filter(m => m.scadenza).forEach(m => metti(dataSolo(m.scadenza), { tipo: m.raggiunta_il ? "fatta" : "milestone", testo: "◆ " + m.titolo }));
  cr.riunioni.forEach(r => metti(new Date(r.quando), { tipo: "riunione", testo: "🎙 " + r.titolo }));
  const disegna = () => {
    const primo = (mese.getDay() + 6) % 7, giorni = new Date(mese.getFullYear(), mese.getMonth() + 1, 0).getDate();
    const celle = [];
    for (let i = 0; i < primo; i++) celle.push(h("div", { class: "cal-vuota" }));
    for (let g = 1; g <= giorni; g++) {
      const dd = new Date(mese.getFullYear(), mese.getMonth(), g), k = chiaveGiorno(dd), ev = eventi[k] || [];
      celle.push(h("button", { class: "cal-giorno" + (k === chiaveGiorno(oggi) ? " oggi" : "") + (k === scelto ? " scelto" : ""), "data-uso": "calendario-giorno", "aria-label": dd.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" }) + ", " + ev.length + " eventi", onclick: () => { scelto = k; disegna(); } },
        h("span", { class: "cal-n" }, String(g)),
        ev.slice(0, 3).map(e => h("span", { class: "cal-chip " + e.tipo }, e.testo)),
        ev.length > 3 ? h("span", { class: "cal-altri" }, "+" + (ev.length - 3)) : null,
        h("span", { class: "cal-punti" }, ev.slice(0, 4).map(e => h("i", { class: e.tipo })))));
    }
    const sel = eventi[scelto] || [];
    riempi(cont, [
      h("div", { class: "cal-testa" },
        h("button", { class: "s", "aria-label": "Mese precedente", onclick: () => { mese = new Date(mese.getFullYear(), mese.getMonth() - 1, 1); disegna(); } }, "‹"),
        h("div", { class: "nome", style: "flex:1;text-align:center;text-transform:capitalize" }, mese.toLocaleDateString("it-IT", { month: "long", year: "numeric" })),
        h("button", { class: "s", onclick: () => { mese = new Date(oggi.getFullYear(), oggi.getMonth(), 1); scelto = chiaveGiorno(oggi); disegna(); } }, "Oggi"),
        h("button", { class: "s", "aria-label": "Mese successivo", onclick: () => { mese = new Date(mese.getFullYear(), mese.getMonth() + 1, 1); disegna(); } }, "›")),
      h("div", { class: "cal-griglia" }, ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map(x => h("div", { class: "cal-nome" }, x)), celle),
      h("div", { class: "cal-legenda sotto" }, h("span", {}, h("i", { class: "task" }), "scadenza task"), h("span", {}, h("i", { class: "ritardo" }), "in ritardo"), h("span", {}, h("i", { class: "milestone" }), "milestone"), h("span", {}, h("i", { class: "riunione" }), "riunione"), h("span", {}, h("i", { class: "fatta" }), "chiusa")),
      h("div", { class: "carta", style: "margin-top:10px" }, h("div", { class: "nome" }, "Giorno " + dataSolo(scelto).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" })),
        sel.length ? sel.map(e => h("div", { class: "cr-riga" }, h("span", { class: "cal-chip " + e.tipo, style: "white-space:normal" }, e.testo), e.chi ? h("span", { class: "sotto" }, " · " + e.chi) : null)) : h("p", { class: "sotto" }, "Niente in programma."))]);
  };
  disegna();
  return cont;
}

// Gantt: una barra per task dalla creazione alla scadenza (o alla chiusura), milestone come rombi, linea dell'oggi
function ganttProgetto(cr) {
  const oggi = inizioGiorno(new Date());
  const righe = cr.task.map(t => {
    const ini = inizioGiorno(new Date(t.creata_il));
    let fine = t.completata_il ? inizioGiorno(new Date(t.completata_il)) : t.scadenza ? dataSolo(t.scadenza) : null;
    const stimata = !fine; if (!fine) fine = new Date(Math.max(+oggi, +ini) + 3 * MS_GIORNO);
    if (fine < ini) fine = ini;
    return { t, ini, fine, stimata };
  }).sort((a, b) => (a.t.stato === "completata") - (b.t.stato === "completata") || a.ini - b.ini).slice(0, 60);
  const ms = cr.milestone.filter(m => m.scadenza).map(m => ({ m, quando: dataSolo(m.scadenza) }));
  if (!righe.length && !ms.length) return h("p", { class: "sotto" }, "Il Gantt compare quando ci sono task o milestone con una data.");
  const date = [oggi, ...righe.flatMap(r => [r.ini, r.fine]), ...ms.map(x => x.quando)];
  const da = new Date(Math.min(...date) - 2 * MS_GIORNO), a = new Date(Math.max(...date) + 3 * MS_GIORNO), span = Math.max(+a - +da, MS_GIORNO);
  const pos = (d) => ((+d - +da) / span * 100).toFixed(2) + "%";
  const larg = (x, y) => Math.max((+y - +x + MS_GIORNO) / span * 100, 0.8).toFixed(2) + "%";
  const giorniTot = span / MS_GIORNO, passo = giorniTot <= 45 ? 7 : giorniTot <= 150 ? 14 : 30;
  const tacche = []; for (let d = new Date(da); d <= a; d = new Date(+d + passo * MS_GIORNO)) tacche.push(new Date(d));
  const classe = (r) => r.t.stato === "completata" ? "fatta" : r.t.in_ritardo ? "ritardo" : r.t.stato === "in_corso" ? "in_corso" : r.t.stato === "in_attesa" ? "attesa" : "da_fare";
  return h("div", { class: "gantt-scroll" }, h("div", { class: "gantt" },
    h("div", { class: "gantt-asse" }, h("div", { class: "gantt-et" }), h("div", { class: "gantt-pista" }, tacche.map(d => h("span", { class: "gantt-tacca", style: "left:" + pos(d) }, crDataBreve(d))))),
    ms.length ? h("div", { class: "gantt-riga" }, h("div", { class: "gantt-et" }, "◆ Milestone"), h("div", { class: "gantt-pista" }, ms.map(x => h("span", { class: "gantt-rombo" + (x.m.raggiunta_il ? " fatta" : ""), style: "left:" + pos(x.quando), title: x.m.titolo + " · " + crDataBreve(x.quando) }, "◆")))) : null,
    righe.map(r => h("div", { class: "gantt-riga" },
      h("div", { class: "gantt-et", title: r.t.titolo }, r.t.titolo, r.t.responsabile ? h("span", { class: "sotto" }, " · " + r.t.responsabile) : null),
      h("div", { class: "gantt-pista" }, h("span", { class: "gantt-barra " + classe(r) + (r.stimata ? " stimata" : ""), style: "left:" + pos(r.ini) + ";width:" + larg(r.ini, r.fine), title: r.t.titolo + " · " + crDataBreve(r.ini) + " → " + crDataBreve(r.fine) + (r.stimata ? " (senza scadenza)" : "") })))),
    h("div", { class: "gantt-oggi", style: "left:calc(220px + (100% - 220px) * " + ((+oggi - +da) / span).toFixed(4) + ")" }, h("span", {}, "oggi")),
    h("div", { class: "cal-legenda sotto", style: "margin-top:8px" }, h("span", {}, h("i", { class: "da_fare" }), "da fare"), h("span", {}, h("i", { class: "in_corso" }), "in corso"), h("span", {}, h("i", { class: "attesa" }), "in attesa"), h("span", {}, h("i", { class: "ritardo" }), "in ritardo"), h("span", {}, h("i", { class: "fatta" }), "completata"))));
}
