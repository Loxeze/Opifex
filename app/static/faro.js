"use strict";
// Bandi (FARO): Faro cerca i bandi sulle fonti ufficiali e li abbina ai profili; chi ha il reparto Bandi fa il primo setaccio (interessante o scartato, con il motivo);
// il titolare decide la candidatura, che diventa un progetto con task e scadenze. La lettura approfondita apre pagina e PDF e compila la scheda del bando.

const STATI_FR = { nuovo: ["nuovo", ""], interessante: ["interessante", "ok"], candidatura: ["in candidatura", "ok"], scartato: ["scartato", "no"], archiviato: ["scaduto", "no"] };
const GIORNI_FR = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
const MODI_FR = { fonti: "fonti del registro", portali: "portali collegati", libero: "su tua richiesta" };
const VERIFICA_FR = { confermato: ["ritrovato sulla pagina", "ok"], da_controllare: ["da controllare", "avv"], non_trovato: ["non ritrovato sulla pagina", "no"] };
const CONSIGLIO_FR = { candidarsi: ["Consiglio: candidarsi", "ok"], valutare: ["Consiglio: valutare", "avv"], lasciare: ["Consiglio: lasciare", "no"] };
const LETTURA_FR = { interessanti: "Quando un bando passa il primo setaccio (interessante)", tutti: "Su tutti i bandi segnalati, subito dopo il giro", mai: "Solo quando la chiedo io" };
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
    if (!d.pronto) { riempi(corpo, d.gestione ? _preparaFr(ricarica, dire) : h("p", { class: "sotto" }, "Faro non è ancora stato preparato dal titolare.")); return; }
    const ges = d.gestione, c = d.conteggi, im = d.impostazioni;
    const ammesse = ges ? ["bandi", "mensile", "clienti", "bollettini", "profili", "fonti", "lavoro"] : ["bandi", "mensile", "bollettini"];
    let scheda = stato.faroScheda || "bandi";
    if (!ammesse.includes(scheda) || (scheda === "clienti" && !im.clienti_acceso)) scheda = "bandi";
    const tab = (id, et, n) => h("button", { type: "button", class: scheda === id ? "attivo" : "", "aria-current": scheda === id ? "page" : null,
      onclick: () => { stato.faroScheda = id; ricarica(); } }, et, n ? h("span", { class: "lg-n" }, String(n)) : null);
    const tessera = (titolo, valore, sotto, filtro) => h("button", { type: "button", class: "tessera cliccabile lg-tessera",
      onclick: () => { stato.faroScheda = "bandi"; stato.faroStato = filtro; ricarica(); } },
      h("div", { class: "sotto" }, titolo), h("div", { class: "valore" }, String(valore)), sotto ? h("div", { class: "sotto" }, sotto) : null);
    const accendi = async (si) => { try { await api("PUT", "/gestione/faro/impostazioni", { ...im, acceso: si }); dire(si ? "Ricerca automatica accesa." : "Ricerca automatica spenta: Faro lavora solo quando glielo chiedi."); ricarica(); } catch (e) { dire(e.message, "no"); } };
    const pagine = { bandi: (dd, r, di) => _bandiFr(dd, r, di, "mie"), mensile: (dd, r, di) => _bandiFr(dd, r, di, "mensile"), clienti: (dd, r, di) => _bandiFr(dd, r, di, "clienti"),
      bollettini: _bollettiniFr, profili: _profiliFr, fonti: _fontiFr, lavoro: _lavoroFr };
    riempi(corpo, [
      h("div", { class: "lg-stato" },
        h("span", { class: "lg-pallino" + (d.in_corso || im.acceso ? " attivo" : "") }),
        h("span", {}, d.in_corso ? d.agente.nome + " sta cercando adesso…" : im.acceso
          ? "Ricerca automatica accesa: " + d.fonti.attive + " fonti, ognuna controllata ogni " + im.giorni_fonte + " giorni"
          : "Ricerca automatica spenta"),
        ges && !d.agente.attivo ? h("span", { class: "etichetta no" }, d.agente.nome + " è spento (Squadra › Agenti)") : null,
        ges && d.agente.portali.length ? h("span", { class: "etichetta ok" }, "portali collegati: " + d.agente.portali.map(p => p.nome).join(", ")) : null,
        ges ? _btnFr(im.acceso ? "Spegni la ricerca automatica" : "Accendi la ricerca automatica", () => accendi(!im.acceso), im.acceso ? "s" : "p") : null,
        ges ? _btnFr("Fai un giro adesso", async () => { try { await api("POST", "/gestione/faro/giri", {}); dire("Giro avviato: i bandi compaiono qui man mano che Faro li legge (qualche minuto)."); ricarica(); } catch (e) { dire(e.message, "no"); } }) : null),
      msg,
      h("div", { class: "tessere" },
        tessera("Nuovi da guardare", c.nuovi, "primo setaccio", "nuovo"),
        tessera("Interessanti", c.interessanti, "da decidere", "interessante"),
        tessera("In candidatura", c.candidature, null, "candidatura"),
        tessera("In scadenza", c.in_scadenza, "entro " + im.giorni_avviso + " giorni", "aperti"),
        ges ? h("div", { class: "tessera lg-tessera", title: "Costo del modello per i giri di ricerca e le letture approfondite" },
          h("div", { class: "sotto" }, "Costo del mese"), h("div", { class: "valore" }, euro(d.costi.mese)),
          h("div", { class: "sotto" }, "giri " + euro(d.costi.giri_mese) + " · letture " + euro(d.costi.letture_mese))) : tessera("Trovati in 7 giorni", c.settimana, null, "aperti")),
      h("nav", { class: "schede-gruppo lg-schede", "aria-label": "Sezioni dei bandi" },
        tab("bandi", "Le mie società", c.nuovi), tab("mensile", "Nuove imprese · mensile", c.mensili),
        ges && im.clienti_acceso ? tab("clienti", "Clienti", c.clienti) : null, tab("bollettini", "Bollettini"),
        ges ? tab("profili", "Per chi cerca") : null, ges ? tab("fonti", "Fonti (" + d.fonti.attive + ")") : null, ges ? tab("lavoro", "Come lavora") : null),
      await (pagine[scheda] || pagine.bandi)(d, ricarica, dire)]);
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
      try { await api("POST", "/gestione/faro/prepara"); ricarica(); }
      catch (e) { riempi(esito, avviso(e.message, "no")); }
    }, "p")), esito);
}

// ---------- scheda del bando (lettura approfondita) ----------
function _schedaFr(s) {
  const sc = s.scheda || {}, g = sc.giudizio || {}, campi = sc.campi || {};
  const doc = (id) => (sc.documenti || []).find(x => x.id === id);
  const lista = (titolo, v) => v && v.length ? h("div", {}, h("b", {}, titolo), h("ul", {}, v.map(x => h("li", {}, x)))) : null;
  const cons = CONSIGLIO_FR[g.consiglio] || CONSIGLIO_FR.valutare;
  return h("div", { class: "fr-scheda" },
    h("div", { class: "fr-giudizio" },
      h("span", { class: "etichetta " + cons[1] }, cons[0]), g.profilo ? h("span", { class: "sotto" }, " per " + g.profilo) : null,
      g.motivo ? h("p", {}, g.motivo) : null,
      lista("Requisiti che abbiamo", g.requisiti_ok), lista("Requisiti che mancano o da verificare", g.requisiti_mancanti),
      g.impegno ? h("p", {}, h("b", {}, "Impegno richiesto: "), g.impegno) : null, lista("Rischi", g.rischi)),
    h("table", { class: "fr-campi" }, h("tbody", {}, s.campi.map(({ chiave, etichetta }) => {
      const c = campi[chiave], dd = c ? doc(c.documento) : null;
      return h("tr", {}, h("th", { scope: "row" }, etichetta),
        c ? h("td", {}, h("div", {}, c.valore),
              h("div", { class: "sotto" }, "Fonte: ", dd ? h("a", { href: dd.url, target: "_blank", rel: "noopener" }, c.documento + " · " + dd.titolo) : c.documento, ", " + c.punto),
              h("details", { class: "fr-cit" }, h("summary", { class: "sotto" }, "citazione"), h("q", {}, c.citazione)))
          : h("td", { class: "sotto" }, "Non scritto nei documenti letti"));
    }))),
    sc.non_confermati && sc.non_confermati.length ? h("details", { class: "fr-cit" }, h("summary", { class: "sotto" }, (sc.non_confermati.length === 1 ? "1 dato proposto dal modello ma non ritrovato nel testo: escluso" : sc.non_confermati.length + " dati proposti dal modello ma non ritrovati nel testo: esclusi")),
      h("ul", {}, sc.non_confermati.map(x => h("li", { class: "sotto" }, x.campo + ": «" + x.proposto + "» (" + (x.documento || "?") + (x.punto ? ", " + x.punto : "") + ")")))) : null,
    h("div", { class: "sotto" }, "Documenti letti: ", (sc.documenti || []).map((x, i) => [i ? " · " : "", h("a", { href: x.url, target: "_blank", rel: "noopener" }, x.id + " " + x.titolo), x.errore ? " (" + x.errore + ")" : ""])),
    h("div", { class: "sotto" }, "Letto il " + _quandoFr(s.scheda_il) + " con " + (sc.modello || "?") + " · costo " + euro(s.scheda_costo)));
}

function _bloccoSchedaFr(b, d, ricarica, dire) {
  const ges = d.gestione;
  const leggi = () => _btnFr((b.scheda_stato === "pronta" ? "Rileggi" : "Leggi a fondo") + " (≈ " + euro(d.stima_lettura.costo) + ")", async () => {
    try { await api("POST", "/gestione/faro/bandi/" + b.id + "/lettura"); dire("Lettura avviata: Faro apre la pagina e i documenti del bando (un paio di minuti)."); ricarica(); } catch (e) { dire(e.message, "no"); }
  });
  if (b.scheda_stato === "in_corso") return h("p", { class: "sotto" }, "⏳ Lettura approfondita in corso: pagina, avviso, allegati e FAQ…");
  if (b.scheda_stato === "errore") return h("div", { class: "riga" }, h("span", { class: "etichetta no" }, "Lettura non riuscita: " + (b.scheda_errore || "")), ges ? leggi() : null);
  if (b.scheda_stato !== "pronta") return ges ? h("div", { class: "azioni" }, leggi()) : null;
  const box = h("div", {}, h("p", { class: "sotto" }, "Carico la scheda…"));
  const cons = b.scheda && b.scheda.giudizio ? CONSIGLIO_FR[b.scheda.giudizio.consiglio] : null;
  return h("details", { class: "fr-lettura", ontoggle: async (e) => {
      if (!e.target.open || box.dataset.ok) return;
      try { riempi(box, _schedaFr(await api("GET", "/gestione/faro/bandi/" + b.id + "/scheda"))); box.dataset.ok = "1"; } catch (er) { riempi(box, avviso(er.message, "no")); }
    } },
    h("summary", {}, h("b", {}, "Scheda del bando"), " · lettura approfondita", cons ? h("span", { class: "etichetta " + cons[1] }, cons[0]) : null),
    box, ges ? h("div", { class: "azioni" }, leggi()) : null);
}

// ---------- il bando su Drive: cartella con il materiale e scheda tecnica ----------
function _driveFr(b, d, ricarica, dire) {
  const ges = d.gestione, st = b.drive_stato || "";
  const salva = ges && d.drive_collegato ? _btnFr(st === "salvato" ? "Aggiorna su Drive" : "Salva su Drive", async () => {
    try { await api("POST", "/gestione/faro/bandi/" + b.id + "/drive"); dire("Sto scaricando il materiale del bando nella sua cartella su Drive, con la scheda tecnica."); ricarica(); } catch (e) { dire(e.message, "no"); }
  }) : null;
  if (st === "salvato") return h("div", { class: "fr-drive" },
    h("a", { href: "https://docs.google.com/document/d/" + b.drive_scheda_id + "/edit", target: "_blank", rel: "noopener", class: "fr-scheda-link" }, "📄 Scheda tecnica"),
    h("a", { href: "https://drive.google.com/drive/folders/" + b.drive_cartella_id, target: "_blank", rel: "noopener" }, "📁 Cartella su Drive (" + (b.drive_file || []).length + " file)"), salva);
  if (st === "in_corso") return h("p", { class: "sotto" }, "⏳ Sto salvando il materiale su Drive…");
  if (st.startsWith("errore")) return h("div", { class: "fr-drive" }, h("span", { class: "etichetta avv", title: st }, "Drive: non riuscito, riprovo da solo tra un'ora"), salva);
  if (st === "drive_non_collegato") return ges ? h("p", { class: "sotto" }, "Il materiale andrà su Drive appena colleghi Google Drive (Impostazioni › Collegamenti).") : null;
  return salva ? h("div", { class: "fr-drive" }, salva) : null;
}

// ---------- elenco dei bandi ----------
async function _bandiFr(d, ricarica, dire, sezione) {
  const ges = d.gestione, st = stato.faroStato || "aperti", prof = stato.faroProfilo || "";
  let righe;
  try { righe = await api("GET", "/gestione/faro/bandi?sezione=" + sezione + "&stato=" + encodeURIComponent(st) + (prof ? "&profilo=" + prof : "") + (stato.faroCerca ? "&q=" + encodeURIComponent(stato.faroCerca) : "")); }
  catch (e) { return avviso(e.message, "no"); }
  const profiliSez = d.profili.filter(p => sezione === "clienti" ? p.tipo !== "impresa" : p.tipo === "impresa" && (sezione === "mensile" ? p.cadenza === "mensile" : p.cadenza !== "mensile"));
  const selS = h("select", { "aria-label": "Stato", onchange: (e) => { stato.faroStato = e.target.value; ricarica(); } },
    [["aperti", "Aperti (nuovi, interessanti, in candidatura)"], ["nuovo", "Nuovi da guardare"], ["interessante", "Interessanti"], ["candidatura", "In candidatura"], ["scartato", "Scartati"], ["archiviato", "Scaduti"], ["tutti", "Tutti"]]
      .map(([v, t]) => h("option", { value: v, selected: v === st }, t)));
  const selP = h("select", { "aria-label": "Per chi", onchange: (e) => { stato.faroProfilo = e.target.value; ricarica(); } },
    h("option", { value: "" }, "Tutti i profili"), profiliSez.map(p => h("option", { value: String(p.id), selected: String(p.id) === String(prof) }, p.nome + " (" + p.bandi + ")")));
  const cerca = h("input", { type: "search", placeholder: "Cerca nel titolo, nell'ente, nella sintesi", value: stato.faroCerca || "", onkeydown: (e) => { if (e.key === "Enter") { stato.faroCerca = e.target.value.trim(); ricarica(); } } });
  const scad = (b) => {
    if (b.giorni === null) return h("span", { class: "etichetta" }, b.scadenza_nota || "scadenza non indicata");
    const cls = b.giorni < 0 ? "no" : b.giorni <= 7 ? "no" : b.giorni <= d.impostazioni.giorni_avviso ? "avv" : "";
    return h("span", { class: "etichetta " + cls }, "scade il " + _dataFr(b.scadenza) + (b.giorni < 0 ? " (scaduto)" : b.giorni === 0 ? " (oggi)" : " · tra " + b.giorni + " giorni"));
  };
  const setaccio = (b) => {
    if (b.stato === "candidatura" || b.stato === "archiviato") return null;
    const motivo = h("input", { type: "text", maxlength: 1000, placeholder: "Motivo (obbligatorio): perché interessa o perché no", value: "" });
    const passa = async (nuovo) => {
      try {
        const r = await api("PUT", "/gestione/faro/bandi/" + b.id, { stato: nuovo, nota: motivo.value.trim() });
        dire(nuovo === "interessante" ? "Segnato come interessante" + (r.lettura ? ": parte la lettura approfondita del bando." : ".") : nuovo === "scartato" ? "Scartato." : "Rimesso tra i nuovi.");
        ricarica();
      } catch (e) { dire(e.message, "no"); motivo.focus(); }
    };
    return h("div", { class: "fr-setaccio" },
      b.stato === "nuovo" || b.stato === "scartato" || b.stato === "interessante" ? motivo : null,
      h("div", { class: "azioni" },
        b.stato !== "interessante" ? _btnFr("Interessante", () => passa("interessante"), "p") : null,
        b.stato !== "scartato" ? _btnFr("Scarta", () => passa("scartato")) : null,
        b.stato !== "nuovo" ? _btnFr("Rimetti tra i nuovi", () => passa("nuovo")) : null));
  };
  const candidatura = (b) => {
    if (!ges || b.stato === "candidatura" || b.stato === "scartato" || b.stato === "archiviato") return null;
    const pref = (b.profili.find(p => p.azienda_id) || {}).azienda_id;
    const az = h("select", { "aria-label": "Chi si candida" }, d.aziende.map(a => h("option", { value: String(a.id), selected: a.id === pref }, a.nome)));
    return h("details", { class: "fr-candida" }, h("summary", {}, h("b", {}, "Ci candidiamo")),
      h("p", { class: "sotto" }, "Il bando diventa un progetto dell'impresa scelta: scheda compilata con i dati letti, task a ritroso dalla scadenza (requisiti, partner, progetto e costi, documenti, revisione, invio) e la scadenza come milestone." +
        (b.scheda_stato !== "pronta" ? " Conviene prima la lettura approfondita: senza, la scheda del progetto parte dai soli dati della segnalazione." : "")),
      h("div", { class: "riga" }, h("label", {}, "Chi si candida", az),
        _btnFr("Crea il progetto della candidatura", async () => {
          try { const r = await api("POST", "/gestione/faro/bandi/" + b.id + "/candidatura", { azienda_id: Number(az.value) }); dire("Creato il progetto «" + r.nome + "» con " + r.task + " task."); ricarica(); } catch (e) { dire(e.message, "no"); }
        }, "p")));
  };
  const carta = (b) => h("div", { class: "carta fr-bando" },
    h("div", { class: "fr-testa" },
      h("a", { class: "nome", href: b.url, target: "_blank", rel: "noopener" }, b.titolo, " ↗"),
      h("span", { class: "etichetta " + STATI_FR[b.stato][1] }, STATI_FR[b.stato][0])),
    h("div", { class: "sotto" }, [b.ente, b.regione, b.categoria, b.fonte ? "fonte: " + b.fonte : null].filter(Boolean).join(" · ")),
    h("div", {}, scad(b),
      h("span", { class: "etichetta" }, b.importo !== null ? "fino a " + _euroFr(b.importo) : (b.importo_nota || "importo non indicato")),
      b.copertura ? h("span", { class: "etichetta" + (b.profili.some(p => p.esito === "da_valutare") ? " avv" : "") }, "copre il " + b.copertura + "% dei costi") : null,
      b.verifica ? h("span", { class: "etichetta " + VERIFICA_FR[b.verifica][1], title: b.verifica_nota }, VERIFICA_FR[b.verifica][0]) : null),
    b.verifica && b.verifica !== "confermato" ? h("p", { class: "sotto" }, "Controllo sulla pagina: " + b.verifica_nota) : null,
    h("p", {}, b.sintesi),
    b.beneficiari ? h("p", { class: "sotto" }, "Chi può partecipare: " + b.beneficiari) : null,
    b.importo !== null && b.importo_nota ? h("p", { class: "sotto" }, b.importo_nota) : null,
    b.profili.map(p => h("div", { class: "fr-perche" }, h("span", { class: "etichetta " + (p.esito === "da_valutare" ? "avv" : "ok") }, p.profilo + (p.esito === "da_valutare" ? " · da valutare" : "")), " ", p.motivo)),
    b.nota ? h("p", { class: "sotto" }, (b.stato === "scartato" ? "Scartato" : "Motivo") + (b.setaccio_da ? " (" + b.setaccio_da + ")" : "") + ": " + b.nota) : null,
    _driveFr(b, d, ricarica, dire),
    b.progetto ? h("p", {}, "Progetto della candidatura: ", h("a", { href: "#", onclick: (e) => { e.preventDefault(); stato.progettoAperto = b.progetto_id; vai("progetto"); } }, b.progetto)) : null,
    _bloccoSchedaFr(b, d, ricarica, dire),
    setaccio(b), candidatura(b));
  const vuoto = sezione === "mensile" ? "Nessun bando per costituire nuove imprese con questi filtri. Questa sezione si guarda una volta al mese."
    : d.fonti.mai === d.fonti.attive && !d.giri.length ? (ges ? "Faro non ha ancora fatto nessun giro. Premi «Fai un giro adesso», oppure fai il collaudo da «Come lavora»." : "Faro non ha ancora fatto nessun giro.")
    : "Nessun bando con questi filtri.";
  return [sezione === "mensile" ? h("p", { class: "aiuto" }, "Bandi e fondi per COSTITUIRE nuove imprese: una sezione a parte, da guardare una volta al mese (la prima settimana del mese arriva un promemoria). Qui non entrano i bandi per le società esistenti.")
    : sezione === "clienti" ? h("p", { class: "aiuto" }, "Filone clienti: bandi che un cliente o un potenziale cliente può vincere e in cui possiamo lavorare. Nulla parte verso l'esterno senza la tua approvazione.") : null,
    !ges && sezione === "mie" ? h("p", { class: "aiuto" }, "Primo setaccio: per ogni bando nuovo scegli «Interessante» o «Scarta» scrivendo il motivo. Lorenzo decide poi le candidature tra gli interessanti.") : null,
    h("div", { class: "riga fr-filtri" }, selS, selP, cerca),
    righe.length ? righe.map(carta) : h("p", { class: "sotto" }, vuoto)];
}

async function _bollettiniFr(d, ricarica, dire) {
  let righe;
  try { righe = await api("GET", "/gestione/faro/bollettini"); } catch (e) { return avviso(e.message, "no"); }
  return [h("p", { class: "aiuto" }, "Ogni " + GIORNI_FR[d.impostazioni.bollettino_giorno] + " mattina Opifex prepara un bollettino per ogni profilo acceso che ha bandi nuovi (la sezione «Nuove imprese» una volta al mese): bando, scadenza, contributo, che cosa finanzia e perché riguarda quel profilo. " +
      "È scritto con i dati letti da Faro, senza aggiunte. Non viene inviato a nessuno."),
    d.gestione ? h("div", { class: "azioni" }, _btnFr("Prepara adesso il bollettino", async () => {
      try { const r = await api("POST", "/gestione/faro/bollettini"); dire(r.bollettini ? "Bollettini preparati: " + r.bollettini + "." : "Nessun bando nuovo dall'ultimo bollettino.", r.bollettini ? "ok" : "avv"); ricarica(); } catch (e) { dire(e.message, "no"); }
    }, "p")) : null,
    righe.length ? righe.map(b => h("details", { class: "carta" },
      h("summary", {}, h("b", {}, b.profilo), " · " + b.bandi + (b.bandi === 1 ? " bando" : " bandi") + " · dal " + _dataFr(b.dal) + " al " + _dataFr(b.al),
        b.cadenza === "mensile" ? h("span", { class: "etichetta" }, "mensile") : null, b.tipo !== "impresa" ? h("span", { class: "etichetta" }, "per terzi") : null),
      h("pre", { class: "fr-bollettino" }, b.testo),
      h("div", { class: "azioni" }, _btnFr("Copia il testo", async () => { try { await navigator.clipboard.writeText(b.testo); dire("Bollettino copiato."); } catch (e) { dire("Non riesco a copiare: seleziona il testo a mano.", "avv"); } }))))
      : h("p", { class: "sotto" }, "Ancora nessun bollettino.")];
}

// ---------- profili ----------
function _formProfiloFr(p, ricarica, dire, tipoNuovo) {
  const nome = h("input", { type: "text", maxlength: 80, value: p ? p.nome : "" });
  const t0 = p ? p.tipo : (tipoNuovo || "impresa");
  const tipo = h("select", {}, [["impresa", "Una mia società o associazione"], ["cliente", "Un cliente o potenziale cliente"], ["esterno", "Un profilo tipo (bollettino a più destinatari)"]]
    .map(([v, t]) => h("option", { value: v, selected: v === t0 }, t)));
  const cad = h("select", {}, h("option", { value: "settimanale", selected: !p || p.cadenza !== "mensile" }, "Ogni settimana"), h("option", { value: "mensile", selected: p && p.cadenza === "mensile" }, "Sezione a parte, una volta al mese"));
  const descr = h("textarea", { rows: 5, maxlength: 4000, placeholder: "Chi è, dove ha sede, che cosa fa, che cosa cerca nei bandi e che cosa non gli interessa." }, p ? p.descrizione : "");
  const regioni = h("input", { type: "text", maxlength: 300, value: p ? p.regioni : "", placeholder: "Es. Liguria, Toscana, nazionale, europeo" });
  const imin = h("input", { type: "number", min: 0, step: 500, value: p ? p.importo_min : 5000 });
  const cmin = h("input", { type: "number", min: 0, max: 100, value: p ? p.copertura_min : 50 });
  const att = h("input", { type: "checkbox", checked: p ? p.attivo : true });
  return h("div", {},
    h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Tipo", tipo), h("label", {}, "Quando guardarlo", cad)),
    h("label", {}, "Descrizione (Faro la legge a ogni giro)", descr),
    h("div", { class: "riga" }, h("label", {}, "Dove può partecipare", regioni), h("label", {}, "Contributo minimo (€): sotto si scarta", imin), h("label", {}, "Copertura minima (%): sotto è «da valutare»", cmin)),
    h("label", { class: "fr-spunta" }, att, " Faro cerca per questo profilo"),
    h("div", { class: "azioni" },
      _btnFr(p ? "Salva" : "Aggiungi il profilo", async () => {
        const corpo = { nome: nome.value.trim(), tipo: tipo.value, cadenza: tipo.value === "impresa" ? cad.value : "settimanale", descrizione: descr.value.trim(), regioni: regioni.value.trim(),
          importo_min: Number(imin.value || 0), copertura_min: Number(cmin.value || 0), attivo: att.checked, contatto_id: p ? p.contatto_id : null };
        try { await api(p ? "PUT" : "POST", "/gestione/faro/profili" + (p ? "/" + p.id : ""), corpo); dire("Profilo salvato."); ricarica(); } catch (e) { dire(e.message, "no"); }
      }, "p"),
      p ? _btnFr("Elimina", async () => { if (!confirm("Eliminare il profilo «" + p.nome + "»? I bandi restano, spariscono i suoi abbinamenti.")) return; try { await api("DELETE", "/gestione/faro/profili/" + p.id); ricarica(); } catch (e) { dire(e.message, "no"); } }) : null));
}

function _profiliFr(d, ricarica, dire) {
  const voce = (p) => h("details", { class: "carta" },
    h("summary", {}, h("b", {}, p.nome), " ", h("span", { class: "etichetta " + (p.attivo ? "ok" : "") }, p.attivo ? "acceso" : "spento"),
      p.cadenza === "mensile" ? h("span", { class: "etichetta" }, "mensile") : null,
      h("span", { class: "sotto" }, " " + p.bandi + (p.bandi === 1 ? " bando aperto" : " bandi aperti") + " · minimo " + _euroFr(p.importo_min) + " · copertura " + p.copertura_min + "%")),
    _formProfiloFr(p, ricarica, dire));
  const mie = d.profili.filter(p => p.tipo === "impresa"), altri = d.profili.filter(p => p.tipo !== "impresa");
  return [h("h3", {}, "Le mie società"),
    h("p", { class: "aiuto" }, "Per decidere a quali bandi candidarsi. Le soglie le applica il sistema: sotto il contributo minimo il bando non entra, sotto la copertura minima entra come «da valutare». " +
      "Un profilo «una volta al mese» (come Nuove imprese) ha la sua sezione e il suo bollettino mensile."),
    mie.map(voce),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Aggiungi una società")), _formProfiloFr(null, ricarica, dire, "impresa")),
    h("h3", {}, "Clienti e profili tipo ", h("span", { class: "etichetta " + (d.impostazioni.clienti_acceso ? "ok" : "") }, d.impostazioni.clienti_acceso ? "filone acceso" : "filone spento")),
    h("p", { class: "aiuto" }, "Il filone commerciale: «questo ente può vincere questo bando e noi possiamo lavorarci dentro». " +
      (d.impostazioni.clienti_acceso ? "È acceso: Faro cerca anche per questi profili." : "È spento: questi profili restano qui ma Faro non li usa, finché non accendi il filone in «Come lavora».")),
    altri.map(voce),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Aggiungi un cliente o un profilo tipo")), _formProfiloFr(null, ricarica, dire, "esterno"))];
}

// ---------- fonti ----------
async function _fontiFr(d, ricarica, dire) {
  let fonti;
  try { fonti = await api("GET", "/gestione/faro/fonti"); } catch (e) { return avviso(e.message, "no"); }
  const soloRotte = !!stato.faroFontiRotte;
  const gruppi = {}, proposte = fonti.filter(f => f.proposta && !f.scartata);
  for (const f of fonti) if (!f.proposta && !f.scartata && (!soloRotte || f.raggiungibile === false)) (gruppi[f.categoria] = gruppi[f.categoria] || []).push(f);
  const salva = async (f, cambi) => { try { await api("PUT", "/gestione/faro/fonti/" + f.id, { nome: f.nome, url: f.url, categoria: f.categoria, regione: f.regione, attiva: f.attiva, ...cambi }); ricarica(); } catch (e) { dire(e.message, "no"); } };
  const riga = (f) => h("li", { class: "fr-fonte" + (f.attiva ? "" : " spenta") },
    h("div", {}, h("a", { href: f.url, target: "_blank", rel: "noopener" }, f.nome, " ↗"), f.regione ? h("span", { class: "etichetta" }, f.regione) : null,
      f.raggiungibile === false ? h("span", { class: "etichetta no", title: f.controllo_esito }, "non risponde") : null,
      h("div", { class: "sotto" }, "ultimo controllo di Faro: " + _quandoFr(f.ultima_il) + " · bandi trovati: " + f.trovati + (f.controllo_il ? " · indirizzo: " + f.controllo_esito : ""))),
    h("div", { class: "fr-azioni" }, _btnFr(f.attiva ? "Metti in pausa" : "Riattiva", () => salva(f, { attiva: !f.attiva })),
      _btnFr("Togli", async () => { if (!confirm("Togliere «" + f.nome + "» dal registro?")) return; try { await api("DELETE", "/gestione/faro/fonti/" + f.id); ricarica(); } catch (e) { dire(e.message, "no"); } })));
  const nome = h("input", { type: "text", maxlength: 200, placeholder: "Es. Fondazione Carige – Bandi" }), url = h("input", { type: "url", maxlength: 500, placeholder: "https://…" });
  const cat = h("input", { type: "text", maxlength: 60, placeholder: "Es. Fondazioni", list: "fr-categorie" }), reg = h("select", {}, h("option", { value: "" }, "Nazionale o non legata a una regione"), d.regioni.map(r => h("option", { value: r }, r)));
  const elenco = h("textarea", { rows: 8, placeholder: "[Fondazioni bancarie]\n- Fondazione Carige: https://www.fondazionecarige.it/bandi/\n- Fondazione CRT: https://www.fondazionecrt.it/bandi/\n\noppure, da un foglio di calcolo:\nNome;Indirizzo;Categoria;Regione" });
  const proposta = (f) => h("li", { class: "fr-fonte" },
    h("div", {}, h("a", { href: f.url, target: "_blank", rel: "noopener" }, f.nome, " ↗"), h("span", { class: "etichetta" }, f.categoria), f.regione ? h("span", { class: "etichetta" }, f.regione) : null,
      f.motivo ? h("div", { class: "sotto" }, "Perché: " + f.motivo) : null),
    h("div", { class: "fr-azioni" }, _btnFr("Accetta", () => salva(f, { attiva: true }), "p"),
      _btnFr("Scarta", async () => { try { await api("DELETE", "/gestione/faro/fonti/" + f.id); dire("Scartata: Faro non la riproporrà."); ricarica(); } catch (e) { dire(e.message, "no"); } })));
  return [h("p", { class: "aiuto" }, "Qui vive il registro delle fonti: i siti degli enti e delle istituzioni che pubblicano bandi (" + d.fonti.attive + " attive su " + d.fonti.n + "). " +
      "Si amplia in tre modi: le aggiungi tu, le importi da un elenco, oppure le propone Faro quando durante i giri trova un ente che non c'è. A ogni giro Faro ne controlla " + d.impostazioni.fonti_per_giro + ", partendo da quelle che non vede da più tempo" +
      (d.fonti.mai ? " (" + d.fonti.mai + " non ancora controllate)" : "") + "."),
    proposte.length ? h("div", { class: "carta" }, h("div", { class: "nome" }, "Fonti proposte da Faro (" + proposte.length + ")"),
      h("p", { class: "sotto" }, "Enti che Faro ha trovato durante i giri e che non erano nel registro. Accettate, entrano nella rotazione; scartate, non tornano."),
      h("ul", { class: "fr-fonti" }, proposte.map(proposta))) : null,
    h("div", { class: "azioni" },
      _btnFr("Copia il registro su Drive", async () => { try { const r = await api("POST", "/gestione/faro/fonti/drive"); dire("Registro copiato su Drive (Opifex › Bandi), in un foglio Google: " + r.link); ricarica(); } catch (e) { dire(e.message, "no"); } }),
      d.registro_drive ? h("a", { href: "https://docs.google.com/spreadsheets/d/" + d.registro_drive + "/edit", target: "_blank", rel: "noopener" }, "Apri il foglio su Drive ↗") : null,
      _btnFr("Controlla che gli indirizzi rispondano", async () => { try { const r = await api("POST", "/gestione/faro/fonti/controlla"); dire("Controllo avviato su " + r.fonti + " fonti: senza modello, costo zero. Ricarica tra qualche minuto."); } catch (e) { dire(e.message, "no"); } }),
      d.fonti.irraggiungibili ? h("label", { class: "fr-spunta" }, h("input", { type: "checkbox", checked: soloRotte, onchange: (e) => { stato.faroFontiRotte = e.target.checked; ricarica(); } }), " solo le " + d.fonti.irraggiungibili + " che non rispondono") : null),
    h("datalist", { id: "fr-categorie" }, Object.keys(gruppi).map(c => h("option", { value: c }))),
    Object.keys(gruppi).sort().map(c => h("details", { class: "carta", open: Object.keys(gruppi).length === 1 || soloRotte },
      h("summary", {}, h("b", {}, c), h("span", { class: "sotto" }, " " + gruppi[c].filter(f => f.attiva).length + " attive su " + gruppi[c].length)), h("ul", { class: "fr-fonti" }, gruppi[c].map(riga)))),
    h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Aggiungi una fonte")),
      h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Pagina dei bandi", url)), h("div", { class: "riga" }, h("label", {}, "Categoria", cat), h("label", {}, "Regione", reg)),
      h("div", { class: "azioni" }, _btnFr("Aggiungi", async () => { try { await api("POST", "/gestione/faro/fonti", { nome: nome.value.trim(), url: url.value.trim(), categoria: cat.value.trim() || "Altro", regione: reg.value || null }); dire("Fonte aggiunta."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"))),
    h("details", { class: "carta", open: d.fonti.n < 100 },
      h("summary", {}, h("b", {}, "Importa un elenco di fonti (il censimento)")),
      h("p", { class: "sotto" }, "Incolla l'elenco così com'è: una fonte per riga («Nome: indirizzo»), con le righe tra parentesi quadre come categorie, oppure le righe copiate da un foglio di calcolo (Nome; indirizzo; categoria; regione). " +
        "Le fonti già presenti non si duplicano, anche se l'indirizzo è scritto in modo un po' diverso. La regione si riconosce dal nome."),
      elenco,
      h("div", { class: "azioni" },
        _btnFr("Importa l'elenco incollato", async () => { try { const r = await api("POST", "/gestione/faro/fonti/importa", { testo: elenco.value }); dire("Lette " + r.lette + " fonti: " + r.nuove + " nuove, " + r.doppioni + " già nel registro."); elenco.value = ""; ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"),
        _btnFr("Recupera le fonti dai vecchi flussi n8n", async () => { try { const r = await api("POST", "/gestione/faro/fonti/n8n"); dire("Da n8n: " + r.fonti + " fonti nuove, lette in " + r.flussi + " flussi. In n8n non è cambiato nulla."); ricarica(); } catch (e) { dire(e.message, "no"); } })),
      h("p", { class: "sotto" }, "Il recupero da n8n legge soltanto i testi dei vecchi flussi (spenti) per ricavarne gli indirizzi: non li accende e non li modifica."))];
}

// ---------- come lavora, costi e collaudo ----------
async function _resocontoFr(gid, dire) {
  const box = h("div", { class: "fr-resoconto" });
  const disegna = async () => {
    let r;
    try { r = await api("GET", "/gestione/faro/giri/" + gid); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const x = r.riepilogo;
    const giudica = async (b, v) => { try { await api("PUT", "/gestione/faro/bandi/" + b.id + "/giudizio", { giudizio: b.giudizio_umano === v ? "" : v }); disegna(); } catch (e) { dire(e.message, "no"); } };
    riempi(box, [
      h("p", {}, h("b", {}, x.trovati + (x.trovati === 1 ? " bando trovato" : " bandi trovati")), " su " + r.fonti.length + " fonti · scartati dal sistema " + x.scartati_dal_sistema + " · costo " + euro(x.costo)),
      h("p", { class: "sotto" }, "Controllo automatico sulla pagina: " + x.confermati + " ritrovati, " + x.da_controllare + " da controllare, " + x.non_trovati + " non ritrovati. " +
        "Il tuo giudizio: " + x.giusti + " giusti, " + x.sbagliati + " sbagliati, " + x.inventati + " inventati" + (x.da_giudicare ? ", " + x.da_giudicare + " da guardare." : ".")),
      h("div", { class: "sotto" }, "Fonti: ", r.fonti.map((f, i) => [i ? " · " : "", h("a", { href: f.url, target: "_blank", rel: "noopener" }, f.nome)])),
      r.bandi.length ? h("ul", { class: "fr-fonti" }, r.bandi.map(b => h("li", { class: "fr-fonte" },
        h("div", {}, h("a", { href: b.url, target: "_blank", rel: "noopener" }, b.titolo, " ↗"), h("div", { class: "sotto" }, b.ente + (b.scadenza ? " · scade il " + _dataFr(b.scadenza) : "") + (b.importo !== null ? " · fino a " + _euroFr(b.importo) : "")),
          b.verifica ? h("div", { class: "sotto" }, h("span", { class: "etichetta " + VERIFICA_FR[b.verifica][1] }, VERIFICA_FR[b.verifica][0]), " " + b.verifica_nota) : null),
        h("div", { class: "fr-azioni" }, [["giusto", "Giusto"], ["sbagliato", "Sbagliato"], ["inventato", "Inventato"]].map(([v, t]) =>
          h("button", { type: "button", class: b.giudizio_umano === v ? "p" : "s", "aria-pressed": b.giudizio_umano === v ? "true" : "false", onclick: () => giudica(b, v) }, t))))))
        : h("p", { class: "sotto" }, r.giro.stato === "in_corso" ? "Giro in corso…" : "Nessun bando segnalato in questo giro.")]);
  };
  await disegna();
  return box;
}

function _lavoroFr(d, ricarica, dire) {
  const im = d.impostazioni, co = d.costi;
  const num = (v, min, max) => h("input", { type: "number", min, max, value: v });
  const gf = num(im.giorni_fonte, 1, 60), fg = num(im.fonti_per_giro, 1, 12), gg = num(im.giri_al_giorno, 1, 12), ga = num(im.giorni_avviso, 1, 90);
  const bg = h("select", {}, GIORNI_FR.map((g, i) => h("option", { value: String(i), selected: i === im.bollettino_giorno }, g)));
  const lq = h("select", {}, Object.entries(LETTURA_FR).map(([v, t]) => h("option", { value: v, selected: v === im.lettura }, t)));
  const mods = d.modelli.length ? d.modelli : [im.modello_lettura];
  const lm = h("select", {}, mods.map(m => h("option", { value: m, selected: m === im.modello_lettura }, m + (d.stime[m] ? " · ≈ " + euro(d.stime[m].costo) + " a bando" : ""))));
  const rich = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Es. Cerca bandi per mostre d'arte italiana all'estero, in particolare in Cina." });
  const settimana = Math.ceil(d.fonti.attive / Math.max(1, im.fonti_per_giro));
  const salvaTutto = (extra) => api("PUT", "/gestione/faro/impostazioni", { acceso: im.acceso, giorni_fonte: Number(gf.value), fonti_per_giro: Number(fg.value), giri_al_giorno: Number(gg.value),
    giorni_avviso: Number(ga.value), bollettino_giorno: Number(bg.value), lettura: lq.value, modello_lettura: lm.value, setaccio: Number(chi.value), ...extra });
  const chi = h("select", {}, d.setaccio_possibili.map(u => h("option", { value: String(u.id), selected: u.id === im.setaccio }, u.nome + (u.ruolo_globale === "titolare" ? " (titolare)" : " (reparto Bandi)"))));
  const collaudi = d.giri.filter(g => g.collaudo);
  const giriMese = co.giro_medio * Math.min(im.giri_al_giorno, Math.max(1, settimana)) * 30;
  return [
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Collaudo: un giro vero su sei fonti"),
      h("p", { class: "sotto" }, "Faro fa un giro su sei fonti di categorie diverse. Alla fine Opifex riapre la pagina di ogni bando segnalato e controlla che titolo, scadenza e importo ci siano davvero (senza modello). " +
        "Poi tu segni ogni bando come giusto, sbagliato o inventato: il resoconto dice quanti erano giusti e quanto è costato."),
      h("div", { class: "azioni" }, _btnFr("Fai il collaudo", async () => { try { await api("POST", "/gestione/faro/giri", { collaudo: true }); dire("Collaudo avviato: qualche minuto. Il resoconto compare qui sotto."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p")),
      collaudi.map(g => h("details", { class: "carta", ontoggle: async (e) => { if (e.target.open && !e.target.dataset.ok) { e.target.dataset.ok = "1"; e.target.append(await _resocontoFr(g.id, dire)); } } },
        h("summary", {}, h("b", {}, "Collaudo del " + _quandoFr(g.creato_il)), " ", h("span", { class: "etichetta " + (g.stato === "concluso" ? "ok" : g.stato === "errore" ? "no" : "avv") }, g.stato === "in_corso" ? "in corso" : g.stato),
          h("span", { class: "sotto" }, " " + g.segnalati + " bandi · " + euro(g.costo)))))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Lettura approfondita dei bandi"),
      h("p", { class: "sotto" }, "Faro apre la pagina ufficiale e i documenti collegati (avviso, allegati, FAQ in PDF) e compila la scheda: beneficiari, spese ammissibili, intensità di aiuto, importi, dotazione, scadenza e invio, partner, criteri e punteggi, de minimis, cumulabilità. " +
        "Ogni dato ha il documento e il punto da cui è letto, con la citazione: se la citazione non si ritrova nel testo il dato non entra. Ciò che non è scritto resta vuoto. Chiude con il giudizio: candidarsi, valutare o lasciare."),
      h("div", { class: "riga" }, h("label", {}, "Quando farla", lq), h("label", {}, "Con quale modello", lm)),
      h("p", { class: "sotto" }, "Costo stimato a bando con " + im.modello_lettura + ": " + euro(d.stima_lettura.costo) + " (" + d.stima_lettura.base + "). Tetto di sicurezza: 25 letture al giorno."),
      h("div", { class: "azioni" }, _btnFr("Salva", async () => { try { await salvaTutto({}); dire("Salvato."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Quanto costa"),
      h("table", { class: "fr-campi" }, h("tbody", {},
        h("tr", {}, h("th", { scope: "row" }, "Questo mese"), h("td", {}, euro(co.mese) + " — giri " + euro(co.giri_mese) + " (" + co.giri_n + "), letture " + euro(co.letture_mese) + " (" + co.letture_n + ")")),
        h("tr", {}, h("th", { scope: "row" }, "Mese scorso"), h("td", {}, euro(co.mese_scorso))),
        h("tr", {}, h("th", { scope: "row" }, "Un giro, in media"), h("td", {}, co.giro_medio ? euro(co.giro_medio) : "ancora nessun giro concluso")),
        co.giro_medio ? h("tr", {}, h("th", { scope: "row" }, "Ricerca automatica, al mese"), h("td", {}, "≈ " + euro(giriMese) + " con il ritmo attuale (letture escluse)")) : null)),
      h("p", { class: "sotto" }, "È il costo del modello (token). Le ricerche web dei giri hanno un piccolo costo a parte presso Anthropic.")),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Chiedi a Faro una ricerca"),
      h("p", { class: "sotto" }, "Un giro su una richiesta tua, anche fuori dal registro delle fonti. I bandi che trova entrano nell'elenco come gli altri."), rich,
      h("div", { class: "azioni" }, _btnFr("Cerca", async () => { try { await api("POST", "/gestione/faro/giri", { modo: "libero", richiesta: rich.value.trim() }); dire("Ricerca avviata."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"),
        d.agente.portali.length ? _btnFr("Giro sui portali collegati", async () => { try { await api("POST", "/gestione/faro/giri", { modo: "portali" }); dire("Giro sui portali avviato."); ricarica(); } catch (e) { dire(e.message, "no"); } }) : null),
      d.agente.portali.length ? null : h("p", { class: "sotto" }, "Per far entrare Faro in un portale con accesso (per esempio Obiettivo Europa): Impostazioni › Collegamenti, aggiungi il sito con nome utente e password e assegnalo a Faro. " +
        "Il login lo fa il sistema: l'agente non vede le credenziali.")),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Ritmo della ricerca automatica"),
      h("p", { class: "sotto" }, "Con questi numeri servono circa " + settimana + " giri per passare tutte le fonti attive. Ogni giro è una ricerca sul web con il modello " + d.agente.modello + "."),
      h("div", { class: "riga" }, h("label", {}, "Ogni fonte si ricontrolla dopo (giorni)", gf), h("label", {}, "Fonti per giro", fg), h("label", {}, "Giri al giorno, al massimo", gg)),
      h("div", { class: "riga" }, h("label", {}, "Avviso di scadenza (giorni prima)", ga), h("label", {}, "Bollettino e aggiornamento della settimana", bg)),
      h("div", { class: "riga" }, h("label", {}, "Chi fa il primo setaccio", chi)),
      h("p", { class: "sotto" }, "Chi fa il primo setaccio riceve ogni settimana un compito con i bandi nuovi da guardare e, subito, un compito urgente se un bando non ancora guardato scade entro i giorni di avviso. " +
        "Qui compaiono il titolare e chi ha il reparto Bandi (Impostazioni › Utenti)."),
      h("div", { class: "azioni" }, _btnFr("Salva", async () => { try { await salvaTutto({}); dire("Salvato."); ricarica(); } catch (e) { dire(e.message, "no"); } }, "p"))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Il materiale su Drive ", h("span", { class: "etichetta " + (im.drive ? "ok" : "") }, im.drive ? "acceso" : "spento")),
      h("p", { class: "sotto" }, "Per ogni bando trovato (tranne quelli che il controllo non ritrova sulla pagina) Opifex crea una cartella in Drive › Opifex › Bandi, chiamata «scadenza - titolo», " +
        "e ci scarica la pagina ufficiale, l'avviso, gli allegati e le FAQ, con la scheda tecnica da leggere a colpo d'occhio. La scheda si completa da sola dopo la lettura approfondita. Senza modello: costo zero." +
        (d.drive_collegato ? "" : " Drive non è ancora collegato: Impostazioni › Collegamenti.")),
      h("div", { class: "azioni" }, _btnFr(im.drive ? "Spegni il salvataggio su Drive" : "Accendi il salvataggio su Drive", async () => { try { await salvaTutto({ drive: !im.drive }); ricarica(); } catch (e) { dire(e.message, "no"); } }))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Filone clienti ", h("span", { class: "etichetta " + (im.clienti_acceso ? "ok" : "") }, im.clienti_acceso ? "acceso" : "spento")),
      h("p", { class: "sotto" }, "Il filone commerciale (clienti, potenziali clienti, profili tipo come il piccolo museo locale) è predisposto ma resta spento finché non dai il via: spento, Faro non cerca per quei profili e i loro bollettini non si preparano. " +
        "La scheda opportunità e il collegamento al CRM arrivano con la fase 2."),
      h("div", { class: "azioni" }, _btnFr(im.clienti_acceso ? "Spegni il filone clienti" : "Accendi il filone clienti", async () => {
        if (!im.clienti_acceso && !confirm("Accendere il filone clienti? Faro cercherà anche per i clienti e i profili tipo, con un costo in più per giro.")) return;
        try { await salvaTutto({ clienti_acceso: !im.clienti_acceso }); ricarica(); } catch (e) { dire(e.message, "no"); }
      }))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Ultimi giri"),
      d.giri.length ? h("ul", { class: "fr-fonti" }, d.giri.map(g => h("li", { class: "fr-fonte" }, h("div", {},
        h("b", {}, _quandoFr(g.creato_il)), " · " + (g.collaudo ? "collaudo · " : "") + MODI_FR[g.modo] + (g.modo === "fonti" ? " (" + g.fonti + ")" : "") + " · ",
        h("span", { class: "etichetta " + (g.stato === "concluso" ? "ok" : g.stato === "errore" ? "no" : "avv") }, g.stato === "in_corso" ? "in corso" : g.stato),
        h("span", { class: "sotto" }, " segnalati " + g.segnalati + ", scartati dal sistema " + g.scartati + " · costo " + euro(g.costo)),
        g.esito ? h("details", {}, h("summary", { class: "sotto" }, "Che cosa ha riferito"), h("p", { class: "fr-esito" }, g.esito)) : null,
        g.segnalati ? h("details", { ontoggle: async (e) => { if (e.target.open && !e.target.dataset.ok) { e.target.dataset.ok = "1"; e.target.append(await _resocontoFr(g.id, dire)); } } },
          h("summary", { class: "sotto" }, "Resoconto e controllo dei bandi")) : null))))
        : h("p", { class: "sotto" }, "Nessun giro ancora."))];
}
