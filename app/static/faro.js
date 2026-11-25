"use strict";
// Bandi (FARO): Faro cerca i bandi sulle fonti ufficiali, li abbina ai profili, avvisa per le scadenze vicine e prepara il bollettino della settimana.

const STATI_FR = { nuovo: ["nuovo", ""], interessante: ["interessante", "ok"], candidatura: ["in candidatura", "ok"], scartato: ["scartato", "no"], archiviato: ["scaduto", "no"] };
const GIORNI_FR = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
const MODI_FR = { fonti: "fonti del registro", portali: "portali collegati", libero: "su tua richiesta" };
const _btnFr = (testo, fn, cls) => h("button", { class: cls || "s", type: "button", onclick: async (ev) => { const b = ev.currentTarget; b.disabled = true; try { await fn(); } finally { b.disabled = false; } } }, testo);
const _dataFr = (x) => x ? new Date(x).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }) : "";
const _quandoFr = (x) => x ? new Date(x).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "mai";
const _euroFr = (x) => Math.round(Number(x)).toLocaleString("it-IT") + " €";

function vistaFaro() {
  const corpo = h("div", { class: "fr" }, h("p", { class: "sotto" }, "Carico…")), msg = h("div");
  const dire = (testo, tipo) => riempi(msg, avviso(testo, tipo || "ok"));
  const ricarica = async () => {
    let d;
    try { d = await api("GET", "/gestione/faro"); } catch (e) { riempi(corpo, avviso(e.message, "no")); return; }
    if (!d.pronto) { riempi(corpo, _preparaFr(ricarica, dire)); return; }
    const scheda = stato.faroScheda || "bandi", c = d.conteggi, im = d.impostazioni;
    const tab = (id, et, n) => h("button", { type: "button", class: scheda === id ? "attivo" : "", "aria-current": scheda === id ? "page" : null,
      onclick: () => { stato.faroScheda = id; ricarica(); } }, et, n ? h("span", { class: "lg-n" }, String(n)) : null);
    const tessera = (titolo, valore, sotto, filtro) => h("button", { type: "button", class: "tessera cliccabile lg-tessera",
      onclick: () => { stato.faroScheda = "bandi"; stato.faroStato = filtro; ricarica(); } },
      h("div", { class: "sotto" }, titolo), h("div", { class: "valore" }, String(valore)), sotto ? h("div", { class: "sotto" }, sotto) : null);
    const accendi = async (si) => { try { await api("PUT", "/gestione/faro/impostazioni", { ...im, acceso: si }); dire(si ? "Ricerca automatica accesa." : "Ricerca automatica spenta: Faro lavora solo quando glielo chiedi."); ricarica(); } catch (e) { dire(e.message, "no"); } };
    const pagine = { bandi: _bandiFr, bollettini: _bollettiniFr, profili: _profiliFr, fonti: _fontiFr, lavoro: _lavoroFr };
    riempi(corpo, [
      h("div", { class: "lg-stato" },
        h("span", { class: "lg-pallino" + (d.in_corso || im.acceso ? " attivo" : "") }),
        h("span", {}, d.in_corso ? d.agente.nome + " sta cercando adesso…" : im.acceso
          ? "Ricerca automatica accesa: " + d.fonti.attive + " fonti, ognuna controllata ogni " + im.giorni_fonte + " giorni"
          : "Ricerca automatica spenta"),
        d.agente.attivo ? null : h("span", { class: "etichetta no" }, d.agente.nome + " è spento (Squadra › Agenti)"),
        d.agente.portali.length ? h("span", { class: "etichetta ok" }, "portali collegati: " + d.agente.portali.map(p => p.nome).join(", ")) : null,
        _btnFr(im.acceso ? "Spegni la ricerca automatica" : "Accendi la ricerca automatica", () => accendi(!im.acceso), im.acceso ? "s" : "p"),
        _btnFr("Fai un giro adesso", async () => { try { await api("POST", "/gestione/faro/giri", {}); dire("Giro avviato: i bandi compaiono qui man mano che Faro li legge (qualche minuto)."); ricarica(); } catch (e) { dire(e.message, "no"); } })),
      msg,
      h("div", { class: "tessere" },
        tessera("Nuovi da guardare", c.nuovi, "primo setaccio", "nuovo"),
        tessera("Interessanti", c.interessanti, "da decidere", "interessante"),
        tessera("In candidatura", c.candidature, null, "candidatura"),
        tessera("In scadenza", c.in_scadenza, "entro " + im.giorni_avviso + " giorni", "aperti"),
        tessera("Trovati in 7 giorni", c.settimana, null, "aperti")),
      h("nav", { class: "schede-gruppo lg-schede", "aria-label": "Sezioni dei bandi" },
        tab("bandi", "Bandi", c.nuovi), tab("bollettini", "Bollettini"), tab("profili", "Per chi cerca"), tab("fonti", "Fonti (" + d.fonti.attive + ")"), tab("lavoro", "Come lavora")),
      await (pagine[scheda] || _bandiFr)(d, ricarica, dire)]);
  };
  ricarica();
  const timer = setInterval(() => { if (!corpo.isConnected) { clearInterval(timer); return; } if (!corpo.querySelector("textarea:focus, input:focus, select:focus, details[open]")) ricarica(); }, 30000);
  return [h("h2", {}, "Bandi"), corpo];
}

function _preparaFr(ricarica, dire) {
  const esito = h("div");
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "FARO: la ricerca dei bandi dentro Opifex"),
    h("p", {}, "Un agente, Faro, controlla a rotazione le fonti ufficiali (ministeri, regioni, fondazioni, programmi europei), legge i bandi sulla pagina dell'ente e li segnala qui, " +
      "abbinati alle tue imprese con il motivo. Il sistema scarta da solo i doppioni, i bandi scaduti e quelli sotto la soglia minima."),
    h("p", { class: "sotto" }, "La preparazione crea Faro nel reparto Bandi e carica le fonti e i profili di partenza. Non parte nessuna ricerca finché non la accendi tu."),
    h("div", { class: "azioni" }, _btnFr("Prepara Faro", async () => {
      try { const r = await api("POST", "/gestione/faro/prepara"); ricarica(); }
      catch (e) { riempi(esito, avviso(e.message, "no")); }
    }, "p")), esito);
}

async function _bandiFr(d, ricarica, dire) {
  const st = stato.faroStato || "aperti", prof = stato.faroProfilo || "";
  let righe;
  try { righe = await api("GET", "/gestione/faro/bandi?stato=" + encodeURIComponent(st) + (prof ? "&profilo=" + prof : "") + (stato.faroCerca ? "&q=" + encodeURIComponent(stato.faroCerca) : "")); }
  catch (e) { return avviso(e.message, "no"); }
  const selS = h("select", { "aria-label": "Stato", onchange: (e) => { stato.faroStato = e.target.value; ricarica(); } },
    [["aperti", "Aperti (nuovi, interessanti, in candidatura)"], ["nuovo", "Nuovi da guardare"], ["interessante", "Interessanti"], ["candidatura", "In candidatura"], ["scartato", "Scartati"], ["archiviato", "Scaduti"], ["tutti", "Tutti"]]
      .map(([v, t]) => h("option", { value: v, selected: v === st }, t)));
  const selP = h("select", { "aria-label": "Per chi", onchange: (e) => { stato.faroProfilo = e.target.value; ricarica(); } },
    h("option", { value: "" }, "Tutti i profili"), d.profili.map(p => h("option", { value: String(p.id), selected: String(p.id) === String(prof) }, p.nome + " (" + p.bandi + ")")));
  const cerca = h("input", { type: "search", placeholder: "Cerca nel titolo, nell'ente, nella sintesi", value: stato.faroCerca || "", onkeydown: (e) => { if (e.key === "Enter") { stato.faroCerca = e.target.value.trim(); ricarica(); } } });
  const passa = async (b, nuovo) => {
    const nota = nuovo === "scartato" ? (prompt("Perché lo scarti? (facoltativo: aiuta a capire che cosa non serve)", b.nota || "") ?? null) : undefined;
    if (nota === null) return;
    try { await api("PUT", "/gestione/faro/bandi/" + b.id, nota === undefined ? { stato: nuovo } : { stato: nuovo, nota }); ricarica(); } catch (e) { dire(e.message, "no"); }
  };
  const scad = (b) => {
    if (b.giorni === null) return h("span", { class: "etichetta" }, b.scadenza_nota || "scadenza non indicata");
    const cls = b.giorni < 0 ? "no" : b.giorni <= 7 ? "no" : b.giorni <= d.impostazioni.giorni_avviso ? "avv" : "";
    return h("span", { class: "etichetta " + cls }, "scade il " + _dataFr(b.scadenza) + (b.giorni < 0 ? " (scaduto)" : b.giorni === 0 ? " (oggi)" : " · tra " + b.giorni + " giorni"));
  };
  const carta = (b) => h("div", { class: "carta fr-bando" },
    h("div", { class: "fr-testa" },
      h("a", { class: "nome", href: b.url, target: "_blank", rel: "noopener" }, b.titolo, " ↗"),
      h("span", { class: "etichetta " + STATI_FR[b.stato][1] }, STATI_FR[b.stato][0])),
    h("div", { class: "sotto" }, [b.ente, b.regione, b.categoria, b.fonte ? "fonte: " + b.fonte : null].filter(Boolean).join(" · ")),
    h("div", {}, scad(b),
      h("span", { class: "etichetta" }, b.importo !== null ? "fino a " + _euroFr(b.importo) : (b.importo_nota || "importo non indicato")),
      b.copertura ? h("span", { class: "etichetta" + (b.profili.some(p => p.esito === "da_valutare") ? " avv" : "") }, "copre il " + b.copertura + "% dei costi") : null),
    h("p", {}, b.sintesi),
    b.beneficiari ? h("p", { class: "sotto" }, "Chi può partecipare: " + b.beneficiari) : null,
    b.importo !== null && b.importo_nota ? h("p", { class: "sotto" }, b.importo_nota) : null,
    b.profili.map(p => h("div", { class: "fr-perche" }, h("span", { class: "etichetta " + (p.esito === "da_valutare" ? "avv" : "ok") }, p.profilo + (p.esito === "da_valutare" ? " · da valutare" : "")), " ", p.motivo)),
    b.nota ? h("p", { class: "sotto" }, "Nota: " + b.nota) : null,
    h("div", { class: "azioni" },
      b.stato !== "interessante" && b.stato !== "candidatura" ? _btnFr("Interessante", () => passa(b, "interessante"), "p") : null,
      b.stato === "interessante" ? _btnFr("Ci candidiamo", () => passa(b, "candidatura"), "p") : null,
      b.stato !== "scartato" && b.stato !== "archiviato" ? _btnFr("Scarta", () => passa(b, "scartato")) : null,
      b.stato !== "nuovo" ? _btnFr("Rimetti tra i nuovi", () => passa(b, "nuovo")) : null));
  return [h("div", { class: "riga fr-filtri" }, selS, selP, cerca),
    righe.length ? righe.map(carta) : h("p", { class: "sotto" }, d.fonti.mai === d.fonti.attive && !d.giri.length
      ? "Faro non ha ancora fatto nessun giro. Premi «Fai un giro adesso» per provarlo su sei fonti, oppure accendi la ricerca automatica."
      : "Nessun bando con questi filtri.")];
}

async function _bollettiniFr(d, ricarica, dire) {
  let righe;
  try { righe = await api("GET", "/gestione/faro/bollettini"); } catch (e) { return avviso(e.message, "no"); }
  return [h("p", { class: "aiuto" }, "Ogni " + GIORNI_FR[d.impostazioni.bollettino_giorno] + " mattina Opifex prepara un bollettino per ogni profilo acceso che ha bandi nuovi: bando, scadenza, contributo, che cosa finanzia e perché riguarda quel profilo. " +
      "È scritto con i dati letti da Faro, senza aggiunte. Non viene inviato a nessuno: lo copi e lo mandi tu, o lo passi a chi fa il primo setaccio."),
    h("div", { class: "azioni" }, _btnFr("Prepara adesso il bollettino", async () => {
      try { const r = await api("POST", "/gestione/faro/bollettini"); dire(r.bollettini ? "Bollettini preparati: " + r.bollettini + "." : "Nessun bando nuovo dall'ultimo bollettino.", r.bollettini ? "ok" : "avv"); ricarica(); } catch (e) { dire(e.message, "no"); }
    }, "p")),
    righe.length ? righe.map(b => h("details", { class: "carta" },
      h("summary", {}, h("b", {}, b.profilo), " · " + b.bandi + (b.bandi === 1 ? " bando" : " bandi") + " · dal " + _dataFr(b.dal) + " al " + _dataFr(b.al), b.tipo === "esterno" ? h("span", { class: "etichetta" }, "per terzi") : null),
      h("pre", { class: "fr-bollettino" }, b.testo),
      h("div", { class: "azioni" }, _btnFr("Copia il testo", async () => { try { await navigator.clipboard.writeText(b.testo); dire("Bollettino copiato."); } catch (e) { dire("Non riesco a copiare: seleziona il testo a mano.", "avv"); } }))))
      : h("p", { class: "sotto" }, "Ancora nessun bollettino.")];
}

function _formProfiloFr(p, ricarica, dire) {
  const nome = h("input", { type: "text", maxlength: 80, value: p ? p.nome : "" });
  const tipo = h("select", {}, h("option", { value: "impresa", selected: !p || p.tipo === "impresa" }, "Una mia impresa o associazione"), h("option", { value: "esterno", selected: p && p.tipo === "esterno" }, "Un profilo tipo, per un bollettino a terzi"));
  const descr = h("textarea", { rows: 5, maxlength: 4000, placeholder: "Chi è, dove ha sede, che cosa fa, che cosa cerca nei bandi e che cosa non gli interessa." }, p ? p.descrizione : "");
  const regioni = h("input", { type: "text", maxlength: 300, value: p ? p.regioni : "", placeholder: "Es. Liguria, Toscana, nazionale, europeo" });
  const imin = h("input", { type: "number", min: 0, step: 500, value: p ? p.importo_min : 5000 });
  const cmin = h("input", { type: "number", min: 0, max: 100, value: p ? p.copertura_min : 50 });
  const att = h("input", { type: "checkbox", checked: p ? p.attivo : true });
  return h("div", {},
    h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Tipo", tipo)),
    h("label", {}, "Descrizione (Faro la legge a ogni giro)", descr),
    h("div", { class: "riga" }, h("label", {}, "Dove può partecipare", regioni), h("label", {}, "Contributo minimo (€): sotto si scarta", imin), h("label", {}, "Copertura minima (%): sotto è «da valutare»", cmin)),
    h("label", { class: "fr-spunta" }, att, " Faro cerca per questo profilo"),
    h("div", { class: "azioni" },
      _btnFr(p ? "Salva" : "Aggiungi il profilo", async () => {
        const corpo = { nome: nome.value.trim(), tipo: tipo.value, descrizione: descr.value.trim(), regioni: regioni.value.trim(), importo_min: Number(imin.value || 0), copertura_min: Number(cmin.value || 0), attivo: att.checked };
        try { await api(p ? "PUT" : "POST", "/gestione/faro/profili" + (p ? "/" + p.id : ""), corpo); dire("Profilo salvato."); ricarica(); } catch (e) { dire(e.message, "no"); }
      }, "p"),
      p ? _btnFr("Elimina", async () => { if (!confirm("Eliminare il profilo «" + p.nome + "»? I bandi restano, spariscono i suoi abbinamenti.")) return; try { await api("DELETE", "/gestione/faro/profili/" + p.id); ricarica(); } catch (e) { dire(e.message, "no"); } }) : null));
}

function _profiliFr(d, ricarica, dire) {
  return [h("p", { class: "aiuto" }, "Faro cerca per questi profili e abbina ogni bando a quelli a cui serve. Le soglie le applica il sistema: sotto il contributo minimo il bando non entra, sotto la copertura minima entra come «da valutare». " +
      "Un profilo tipo (per esempio il piccolo museo locale) serve a preparare un bollettino per terzi con la stessa ricerca."),
    d.profili.map(p => h("details", { class: "carta" },
      h("summary", {}, h("b", {}, p.nome), " ", h("span", { class: "etichetta " + (p.attivo ? "ok" : "") }, p.attivo ? "acceso" : "spento"),
        p.tipo === "esterno" ? h("span", { class: "etichetta" }, "per terzi") : null, h("span", { class: "sotto" }, " " + p.bandi + (p.bandi === 1 ? " bando aperto" : " bandi aperti") + " · minimo " + _euroFr(p.importo_min) + " · copertura " + p.copertura_min + "%")),
      _formProfiloFr(p, ricarica, dire))),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Aggiungi un profilo")), _formProfiloFr(null, ricarica, dire))];
}

async function _fontiFr(d, ricarica, dire) {
  let fonti;
  try { fonti = await api("GET", "/gestione/faro/fonti"); } catch (e) { return avviso(e.message, "no"); }
  const gruppi = {};
  for (const f of fonti) (gruppi[f.categoria] = gruppi[f.categoria] || []).push(f);
  const salva = async (f, cambi) => { try { await api("PUT", "/gestione/faro/fonti/" + f.id, { nome: f.nome, url: f.url, categoria: f.categoria, regione: f.regione, attiva: f.attiva, ...cambi }); ricarica(); } catch (e) { dire(e.message, "no"); } };
  const riga = (f) => h("li", { class: "fr-fonte" + (f.attiva ? "" : " spenta") },
    h("div", {}, h("a", { href: f.url, target: "_blank", rel: "noopener" }, f.nome, " ↗"), f.regione ? h("span", { class: "etichetta" }, f.regione) : null,
      h("div", { class: "sotto" }, "ultimo controllo: " + _quandoFr(f.ultima_il) + " · bandi trovati: " + f.trovati)),
    h("div", { class: "fr-azioni" }, _btnFr(f.attiva ? "Metti in pausa" : "Riattiva", () => salva(f, { attiva: !f.attiva })),
      _btnFr("Togli", async () => { if (!confirm("Togliere «" + f.nome + "» dal registro?")) return; try { await api("DELETE", "/gestione/faro/fonti/" + f.id); ricarica(); } catch (e) { dire(e.message, "no"); } })));
  const nome = h("input", { type: "text", maxlength: 200, placeholder: "Es. Fondazione Carige – Bandi" }), url = h("input", { type: "url", maxlength: 500, placeholder: "https://…" });
  const cat = h("input", { type: "text", maxlength: 60, placeholder: "Es. Fondazioni", list: "fr-categorie" }), reg = h("select", {}, h("option", { value: "" }, "Nazionale o non legata a una regione"), d.regioni.map(r => h("option", { value: r }, r)));
  const elenco = h("textarea", { rows: 6, placeholder: "[Fondazioni bancarie]\n- Fondazione Carige: https://www.fondazionecarige.it/bandi/\n- Fondazione CRT: https://www.fondazionecrt.it/bandi/" });
  return [h("p", { class: "aiuto" }, "Il registro delle fonti originali: " + d.fonti.attive + " attive su " + d.fonti.n + ". A ogni giro Faro ne controlla " + d.impostazioni.fonti_per_giro + ", partendo da quelle che non vede da più tempo" +
      (d.fonti.mai ? " (" + d.fonti.mai + " non ancora controllate)" : "") + ". Le fonti che non portano mai bandi utili si mettono in pausa."),
    h("datalist", { id: "fr-categorie" }, Object.keys(gruppi).map(c => h("option", { value: c }))),
    Object.keys(gruppi).sort().map(c => h("details", { class: "carta", open: Object.keys(gruppi).length === 1 },
      h("summary", {}, h("b", {}, c), h("span", { class: "sotto" }, " " + gruppi[c].filter(f => f.attiva).length + " attive su " + gruppi[c].length)), h("ul", { class: "fr-fonti" }, gruppi[c].map(riga)))),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Aggiungi una fonte")),
      h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Pagina dei bandi", url)), h("div", { class: "riga" }, h("label", {}, "Categoria", cat), h("label", {}, "Regione", reg)),
      h("div", { class: "azioni" }, _btnFr("Aggiungi", async () => { try { await api("POST", "/gestione/faro/fonti", { nome: nome.value.trim(), url: url.value.trim(), categoria: cat.value.trim() || "Altro", regione: reg.value || null }); dire("Fonte aggiunta."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"))),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Importa un elenco di fonti")),
      h("p", { class: "sotto" }, "Incolla un elenco con una fonte per riga («Nome: indirizzo»); una riga tra parentesi quadre fa da categoria per quelle che seguono. Le fonti già presenti non si duplicano. " +
        "Se n8n è collegato a Opifex, puoi recuperare in un colpo le fonti scritte nei flussi di FARO."),
      elenco,
      h("div", { class: "azioni" },
        _btnFr("Importa l'elenco incollato", async () => { try { const r = await api("POST", "/gestione/faro/fonti/importa", { testo: elenco.value }); dire("Lette " + r.lette + " fonti, nuove " + r.fonti + "."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"),
        _btnFr("Recupera le fonti dai flussi n8n", async () => { try { const r = await api("POST", "/gestione/faro/fonti/n8n"); dire("Da n8n: " + r.fonti + " fonti nuove, lette in " + r.flussi + " flussi."); ricarica(); } catch (e) { dire(e.message, "no"); } })))];
}

function _lavoroFr(d, ricarica, dire) {
  const im = d.impostazioni;
  const num = (v, min, max) => h("input", { type: "number", min, max, value: v });
  const gf = num(im.giorni_fonte, 1, 60), fg = num(im.fonti_per_giro, 1, 12), gg = num(im.giri_al_giorno, 1, 12), ga = num(im.giorni_avviso, 1, 90);
  const bg = h("select", {}, GIORNI_FR.map((g, i) => h("option", { value: String(i), selected: i === im.bollettino_giorno }, g)));
  const rich = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Es. Cerca bandi per mostre d'arte italiana all'estero, in particolare in Cina." });
  const settimana = Math.ceil(d.fonti.attive / Math.max(1, im.fonti_per_giro));
  return [
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Chiedi a Faro una ricerca"),
      h("p", { class: "sotto" }, "Un giro su una richiesta tua, anche fuori dal registro delle fonti. I bandi che trova entrano nell'elenco come gli altri."), rich,
      h("div", { class: "azioni" }, _btnFr("Cerca", async () => { try { await api("POST", "/gestione/faro/giri", { modo: "libero", richiesta: rich.value.trim() }); dire("Ricerca avviata."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"),
        d.agente.portali.length ? _btnFr("Giro sui portali collegati", async () => { try { await api("POST", "/gestione/faro/giri", { modo: "portali" }); dire("Giro sui portali avviato."); ricarica(); } catch (e) { dire(e.message, "no"); } }) : null),
      d.agente.portali.length ? null : h("p", { class: "sotto" }, "Per far entrare Faro in un portale con accesso (per esempio Obiettivo Europa): Impostazioni › Collegamenti, aggiungi il sito con nome utente e password e assegnalo a Faro. " +
        "Il login lo fa il sistema: l'agente non vede le credenziali.")),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Ritmo della ricerca automatica"),
      h("p", { class: "sotto" }, "Con questi numeri servono circa " + settimana + " giri per passare tutte le fonti attive. Ogni giro è una ricerca sul web con il modello " + d.agente.modello + ": è il costo da tenere d'occhio in Controllo › Consumi."),
      h("div", { class: "riga" }, h("label", {}, "Ogni fonte si ricontrolla dopo (giorni)", gf), h("label", {}, "Fonti per giro", fg), h("label", {}, "Giri al giorno, al massimo", gg)),
      h("div", { class: "riga" }, h("label", {}, "Avviso di scadenza (giorni prima)", ga), h("label", {}, "Bollettino della settimana", bg)),
      h("div", { class: "azioni" }, _btnFr("Salva", async () => {
        try { await api("PUT", "/gestione/faro/impostazioni", { acceso: im.acceso, giorni_fonte: Number(gf.value), fonti_per_giro: Number(fg.value), giri_al_giorno: Number(gg.value), giorni_avviso: Number(ga.value), bollettino_giorno: Number(bg.value) }); dire("Salvato."); ricarica(); }
        catch (e) { dire(e.message, "no"); }
      }, "p"))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Ultimi giri"),
      d.giri.length ? h("ul", { class: "fr-fonti" }, d.giri.map(g => h("li", { class: "fr-fonte" }, h("div", {},
        h("b", {}, _quandoFr(g.creato_il)), " · " + MODI_FR[g.modo] + (g.modo === "fonti" ? " (" + g.fonti + ")" : "") + " · ",
        h("span", { class: "etichetta " + (g.stato === "concluso" ? "ok" : g.stato === "errore" ? "no" : "avv") }, g.stato === "in_corso" ? "in corso" : g.stato),
        h("span", { class: "sotto" }, " segnalati " + g.segnalati + ", scartati dal sistema " + g.scartati),
        g.esito ? h("details", {}, h("summary", { class: "sotto" }, "Che cosa ha riferito"), h("p", { class: "fr-esito" }, g.esito)) : null))))
        : h("p", { class: "sotto" }, "Nessun giro ancora."))];
}
