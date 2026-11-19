"use strict";
// Campagne email a blocchi (2.64): partenza dal foglio Google o dal CRM, il Redattore studia i siti e scrive email personali, Lorenzo approva
// (finché non accende l'invio automatico), solleciti, e la Posta smista le risposte: interessati → opportunità con il link per la call.

const STATI_DEST = { in_attesa: "da preparare", in_studio: "il Redattore ci lavora", da_approvare: "da approvare", approvata: "approvata, in partenza", inviata: "inviata",
  scartata: "scartata", errore: "errore", risposto: "ha risposto (in lettura)", interessato: "interessato", non_interessato: "non interessato",
  rimosso: "non vuole altre email", nessuna_risposta: "chiuso: nessuna risposta" };
const STATI_CP = { bozza: "da avviare", in_corso: "in corso", in_pausa: "in pausa", chiusa: "chiusa" };
const CAMPI_BRIEF = [["destinatari", "Destinatari", "chi sono (es. hotel 4-5 stelle a Sharm, direttori o proprietari)"], ["occasione", "Occasione", "perché scrivi adesso (es. a marzo siamo in zona per…)"],
  ["offerta", "Cosa offri", "partecipare, servizi a prezzo ridotto perché siete in zona…"], ["cercare", "Cosa cercare sui siti", "novità, eventi, servizi, cosa manca…"],
  ["angoli", "Angoli preferiti", "gli agganci che ti interessano"], ["evitare", "Da evitare", "cosa non dire"], ["tono", "Tono", "es. personale, prima persona, frasi brevi"]];

const _btnCp = (testo, fn, cls) => h("button", { class: cls || "s", type: "button", onclick: async (ev) => { const b = ev.currentTarget; b.disabled = true; try { await fn(); } finally { b.disabled = false; } } }, testo);
const _euroCp = (n) => (Number(n) || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function vistaCampagne() { return [h("h2", {}, "Campagne email"), ...[].concat(crmCampagne())]; }

function crmCampagne() {
  const corpo = h("div", {}, h("p", { class: "sotto" }, "Carico…"));
  const carica = async () => {
    if (stato.campagnaAperta) { apriCampagna(corpo, stato.campagnaAperta, carica); return; }
    let d; try { d = await api("GET", "/gestione/campagne"); } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); return; }
    const nuova = h("div");
    const bNuova = h("button", { class: "p", type: "button", onclick: () => { nuova.firstChild ? nuova.replaceChildren() : nuova.replaceChildren(formNuovaCampagna(d, (id) => { stato.campagnaAperta = id; carica(); })); } }, "+ Nuova campagna");
    const riga = (c) => {
      const n = c.numeri;
      return h("button", { class: "mq-riga", type: "button", onclick: () => { stato.campagnaAperta = c.id; carica(); } },
        h("span", { class: "mq-pos" }, c.stato === "chiusa" ? "✓" : "•"),
        h("span", { class: "mq-nome" }, h("b", {}, c.nome)),
        h("span", { class: "mq-barra", "aria-hidden": "true" }, h("span", { style: "width:" + Math.round(100 * n.partite / Math.max(1, n.totale)) + "%;background:var(--ok,#1F6B52)" })),
        h("span", { class: "mq-num" }, h("b", {}, n.partite + "/" + n.totale), " inviate"),
        h("span", { class: "mq-dett" }, [c.impresa || "nessuna impresa", c.categoria, STATI_CP[c.stato], c.da_foglio ? "dal foglio Google" : null,
          n.da_approvare ? n.da_approvare + " da approvare" : null, n.interessato ? n.interessato + (n.interessato === 1 ? " interessato" : " interessati") : null,
          n.risposte ? n.risposte + (n.risposte === 1 ? " risposta" : " risposte") + (n.tasso_risposta != null ? " (" + n.tasso_risposta + "%)" : "") : null,
          c.invio_automatico ? "invio automatico" : null].filter(Boolean).join(" · ")));
    };
    riempi(corpo, [
      h("p", { class: "aiuto" }, "Ogni campagna è un flusso a blocchi: i contatti arrivano dal tuo foglio Google o dal CRM, il Redattore delle campagne legge il sito di ciascuno e scrive un'email personale, tu la leggi e la approvi, e dopo l'invio la Posta smista le risposte: gli interessati diventano opportunità, a chi non risponde parte un sollecito. Nulla parte senza il tuo sì, finché non decidi tu di accendere l'invio automatico."),
      h("div", { class: "azioni" }, bNuova), nuova,
      d.campagne.length ? h("div", { class: "mq-classifica" }, d.campagne.map(riga)) : h("p", { class: "sotto" }, "Nessuna campagna ancora.")]);
  };
  carica();
  return corpo;
}

function _opz(lista, vuota, cosa, scelto) {
  return h("select", {}, [vuota ? h("option", { value: "" }, vuota) : null].concat(lista.map(x => { const o = h("option", { value: x.id }, cosa(x)); if (String(x.id) === String(scelto)) o.selected = true; return o; })).filter(Boolean));
}

function formNuovaCampagna(d, dopo) {
  if (!d.mittenti.length) return avviso("Prima collega una casella: un account Google con Gmail (Impostazioni › Google) o una casella IMAP con invio (Posta › Caselle).", "avv");
  const nome = h("input", { type: "text", placeholder: "Nome della campagna (es. Hotel Sharm - visite primavera 2027)", maxlength: 120 });
  const obiettivo = h("textarea", { rows: 3, placeholder: "Obiettivo: a chi scrivi, che cosa proponi, che cosa vuoi ottenere (es. fissare una call)…" });
  const categoria = h("input", { type: "text", placeholder: "categoria: hotel, musei, sponsor…", maxlength: 40 });
  const impresa = _opz(d.aziende, "— a nome di quale impresa —", z => z.nome);
  const mitt = _opz(d.mittenti, null, m => m.email + " (" + m.tipo + ")");
  const fonteFoglio = h("input", { type: "radio", name: "fonte", checked: true }), fonteCrm = h("input", { type: "radio", name: "fonte" });
  const foglio = h("input", { type: "url", placeholder: "Link del foglio Google (https://docs.google.com/spreadsheets/d/…)" });
  const segm = _opz(d.segmenti, "— tutti i contatti con email —", s => "Segmento: " + s.nome);
  const tipo = h("input", { type: "text", placeholder: "tipo (es. museo, hotel)" }), regione = h("input", { type: "text", placeholder: "regione" });
  const crmBox = h("div", {}, h("div", { class: "azioni" }, segm, tipo, regione)); crmBox.hidden = true;
  const foglioBox = h("div", {}, foglio, h("p", { class: "sotto" }, "Opifex legge il foglio ogni 10 minuti e non ci scrive mai. Prima riga: le intestazioni. Colonne riconosciute: nome (o hotel, ente, struttura), sito, email, località (o comune), provincia, regione, note."));
  fonteFoglio.onchange = fonteCrm.onchange = () => { foglioBox.hidden = !fonteFoglio.checked; crmBox.hidden = fonteFoglio.checked; };
  const personalizza = h("input", { type: "checkbox", checked: true });
  const msg = h("div");
  return h("div", { class: "carta" }, h("h3", {}, "Nuova campagna"),
    h("label", {}, "Nome", nome), h("label", {}, "Obiettivo", obiettivo),
    h("div", { class: "azioni" }, impresa, mitt, categoria),
    h("div", { class: "azioni" }, h("label", { class: "spunta" }, fonteFoglio, h("span", {}, "I contatti arrivano da un foglio Google")), h("label", { class: "spunta" }, fonteCrm, h("span", {}, "Li scelgo dal CRM"))),
    foglioBox, crmBox,
    h("label", { class: "spunta" }, personalizza, h("span", {}, "Il Redattore studia il sito di ognuno e personalizza l'email (senza sito: testo standard)")),
    _btnCp("Crea la campagna", async () => {
      const filtri = {};
      if (fonteCrm.checked) { if (tipo.value.trim()) filtri.tipo = tipo.value.trim(); if (regione.value.trim()) filtri.regione = regione.value.trim(); }
      try {
        const r = await api("POST", "/gestione/campagne", { nome: nome.value, obiettivo: obiettivo.value, azienda_id: impresa.value ? Number(impresa.value) : null, mittente: mitt.value,
          segmento_id: fonteCrm.checked && segm.value ? Number(segm.value) : null, filtri, foglio: fonteFoglio.checked ? foglio.value.trim() : "",
          categoria: categoria.value.trim(), personalizza: personalizza.checked });
        dopo(r.id);
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    }, "p"), msg);
}

// Il flusso, blocco per blocco: ogni blocco dice cosa fa Opifex e si regola lì.
function _blocchiFlusso(c, salva) {
  const n = c.numeri;
  const campo = (el, chiave, conv) => { el.onchange = async () => { const v = conv ? conv(el) : el.value; try { await salva({ [chiave]: v }); } catch (e) { alert(e.message); } }; return el; };
  const blocco = (tipo, titolo, testo, controlli, numero) => h("div", { class: "fl-blocco fl-" + tipo },
    h("div", { class: "fl-tipo" }, ({ partenza: "Partenza", azione: "Azione", attesa: "Attesa", decisione: "Decisione", uscita: "Uscita" })[tipo]),
    h("div", { class: "fl-corpo" }, h("b", {}, titolo), h("div", { class: "sotto" }, testo), controlli ? h("div", { class: "fl-controlli" }, controlli) : null),
    numero != null ? h("div", { class: "fl-numero" }, String(numero)) : null);
  const freccia = () => h("div", { class: "fl-freccia", "aria-hidden": "true" }, "↓");
  // partenza
  const foglio = campo(h("input", { type: "url", value: c.foglio || "", placeholder: "Link del foglio Google" }), "foglio");
  const accDrive = c.account_drive.length > 1 ? campo(_opz(c.account_drive, "— account Google —", a => "letto con " + a.email, c.foglio_account_id), "foglio_account_id", el => el.value ? Number(el.value) : null) : null;
  const leggiOra = c.foglio ? _btnCp("Leggi il foglio adesso", async () => { try { const r = await api("POST", "/gestione/campagne/" + c.id + "/foglio"); alert(r.righe + " righe lette: " + r.nuove + " contatti nuovi, " + r.destinatari + " destinatari aggiunti" + (r.senza_email ? ", " + r.senza_email + " senza email" : "") + "."); salva({}); } catch (e) { alert(e.message); } }, "s piccolo") : null;
  const statoFoglio = c.foglio ? (c.foglio_errore ? avviso(c.foglio_errore, "no") : h("span", { class: "sotto" }, c.foglio_letto_il ? c.foglio_righe + " righe · letto " + new Date(c.foglio_letto_il).toLocaleString("it-IT") : "non ancora letto")) : null;
  // studio
  const pers = h("input", { type: "checkbox" }); pers.checked = c.personalizza; campo(pers, "personalizza", el => el.checked);
  const modello = campo(h("select", {}, [["claude-haiku-5-5", "Claude Haiku (economico)"], ["claude-sonnet-5-5", "Claude Sonnet (più bravo, costa di più)"]].map(([v, t]) => { const o = h("option", { value: v }, t); if (v === c.modello) o.selected = true; return o; })), "modello");
  const tetto = campo(h("input", { type: "number", min: 0, max: 1000, step: 0.5, value: c.tetto_spesa, style: "width:90px" }), "tetto_spesa", el => Number(el.value));
  // approvazione
  const a = c.autonomia;
  const auto = h("input", { type: "checkbox", disabled: !a.puo && !c.invio_automatico }); auto.checked = c.invio_automatico; campo(auto, "invio_automatico", el => el.checked);
  // invio, attesa, solleciti
  const ritmo = campo(h("input", { type: "number", min: 1, max: 120, value: c.per_ora, style: "width:70px" }), "per_ora", el => Number(el.value));
  const giorni = campo(h("input", { type: "number", min: 3, max: 60, value: c.sollecito_giorni, style: "width:70px" }), "sollecito_giorni", el => Number(el.value));
  const soll = campo(h("select", {}, [[0, "nessun sollecito"], [1, "solo la seconda email"], [2, "seconda email, e la terza se c'è una novità"]].map(([v, t]) => { const o = h("option", { value: v }, t); if (v === c.solleciti) o.selected = true; return o; })), "solleciti", el => Number(el.value));
  const link = campo(h("input", { type: "url", value: c.link_prenotazione || "", placeholder: "https://calendar.app.google/… (pagina di prenotazione, slot da 20 minuti)" }), "link_prenotazione");
  const opp = Object.fromEntries((c.opportunita || []).map(x => [x.stato, x.n]));
  return h("div", { class: "fl-flusso" },
    blocco("partenza", "Contatti", c.foglio ? "Righe nuove del foglio Google → contatti nel CRM (senza doppioni) e destinatari. Il foglio resta tuo: Opifex lo legge e basta." : "Contatti scelti dal CRM. Puoi collegare anche un foglio Google: le righe nuove entreranno da sole.",
      [foglio, accDrive, leggiOra, statoFoglio].filter(Boolean), n.totale), freccia(),
    blocco("azione", "Studio del sito", "Il Redattore legge il sito (o le note già raccolte, se hanno meno di 6 mesi), verifica la zona con il CRM e sceglie l'angolo d'attacco seguendo il brief. Riceve solo dati pubblici: mai email o nomi delle persone.",
      [h("label", { class: "spunta" }, pers, h("span", {}, "Personalizza con il sito")), h("label", {}, "Modello ", modello), h("label", {}, "Tetto di spesa ", tetto), h("span", { class: "sotto" }, "speso " + _euroCp(c.spesa) + " su " + _euroCp(c.tetto_spesa))],
      n.in_studio || null), freccia(),
    blocco("azione", "Bozza", "Email personale con angolo e motivo; senza sito, il testo standard della campagna.", null, n.da_approvare), freccia(),
    blocco("decisione", "Approvazione", c.invio_automatico ? "Invio automatico acceso: le bozze partono senza passare da te. Le risposte agli interessati le approvi sempre tu." : "Approvi tu ogni email. L'invio automatico si può accendere dopo " + a.serve + " bozze di fila approvate senza correzioni.",
      [h("label", { class: "spunta" }, auto, h("span", {}, "Invio automatico")), h("span", { class: "sotto" }, a.di_fila + " di " + a.serve + " approvate di fila senza correzioni")], null), freccia(),
    blocco("azione", "Invio", "Dalla casella " + (c.mittente_email || "?") + ", piano, per non finire nello spam. Entra nella storia del contatto.", [h("label", {}, "Email all'ora ", ritmo)], n.partite), freccia(),
    blocco("attesa", "Attesa della risposta", "La Posta legge le risposte con il modello del portatile (restano in casa) e le smista da sola.", [h("label", {}, "Giorni prima del sollecito ", giorni), h("label", {}, "Solleciti ", soll)], n.inviata), freccia(),
    h("div", { class: "fl-uscite" },
      blocco("uscita", "Interessato", "Opportunità al primo gradino, notifica, e la bozza di risposta con il link per prenotare la call. Anche i «mi richiami più avanti» contano come interessati.", [link], n.interessato),
      blocco("uscita", "Non interessato", "Chiuso senza avvisarti, mai cancellato: resta nelle statistiche.", null, n.non_interessato + n.rimosso),
      blocco("uscita", "Nessuna risposta", "Dopo i solleciti il contatto si chiude come «nessuna risposta».", null, n.nessuna_risposta)),
    (opp.interessato || opp.call_fissata || opp.call_fatta || opp.proposta || opp.vinta) ? h("p", { class: "sotto" }, "Opportunità nate da questa campagna: " +
      [["interessato", "interessati", "interessato"], ["call_fissata", "call fissate", "call fissata"], ["call_fatta", "call fatte", "call fatta"], ["proposta", "proposte", "proposta"], ["vinta", "vinte", "vinta"], ["persa", "perse", "persa"]].filter(([k]) => opp[k]).map(([k, t, t1]) => opp[k] + " " + (opp[k] === 1 ? t1 : t)).join(" · ")) : null);
}

async function apriCampagna(corpo, cid, torna) {
  let c; try { c = await api("GET", "/gestione/campagne/" + cid); } catch (e) { stato.campagnaAperta = null; corpo.replaceChildren(avviso(e.message, "no")); return; }
  const ricarica = () => apriCampagna(corpo, cid, torna);
  const n = c.numeri, msg = h("div");
  const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
  const salva = async (dati) => { if (Object.keys(dati).length) await api("PUT", "/gestione/campagne/" + cid, dati); ricarica(); };
  const indietro = h("button", { class: "s", type: "button", onclick: () => { stato.campagnaAperta = null; torna(); } }, "← Tutte le campagne");
  const chiusa = c.stato === "chiusa";
  // comandi
  const conferma = h("div");
  const avvia = c.stato === "bozza" ? _btnCp(c.personalizza || c.foglio ? "Avvia la campagna" : "Avvia", async () => {
    if (!c.testo.trim()) { err(new Error("Scrivi prima il testo standard: serve per chi non ha il sito.")); return; }
    await api("PUT", "/gestione/campagne/" + cid, { stato: "in_corso" }); msg.replaceChildren(avviso("Campagna avviata: il Redattore prepara le bozze a gruppi di 5 ogni 5 minuti. Ti avviso quando ce ne sono da approvare.", "ok")); ricarica();
  }, "p") : null;
  const approvaTutte = h("button", { class: "p", type: "button" }, n.da_approvare === 1 ? "Approva l'email da approvare" : "Approva tutte le " + n.da_approvare + " email");
  approvaTutte.hidden = !n.da_approvare;
  approvaTutte.onclick = () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, (n.da_approvare === 1 ? "Approvi 1 email?" : "Approvi " + n.da_approvare + " email?") + " Partiranno piano, circa " + c.per_ora + " all'ora. Approvarle tutte insieme non conta per l'invio automatico se non le hai lette. Le risposte agli interessati restano da approvare una per una."),
    h("div", { class: "azioni" }, _btnCp("Sì, approva e invia", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/approva", { tutte: true }); ricarica(); } catch (e) { err(e); } }, "p"),
      h("button", { class: "s", type: "button", onclick: () => conferma.replaceChildren() }, "Annulla"))));
  const statoBtn = chiusa || c.stato === "bozza" ? null : c.stato === "in_pausa"
    ? _btnCp("Riprendi", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "in_corso" }); ricarica(); }, "s")
    : _btnCp("Metti in pausa", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "in_pausa" }); ricarica(); }, "s");
  const duplica = _btnCp("Duplica", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/duplica"); stato.campagnaAperta = r.id; torna(); } catch (e) { err(e); } }, "s");
  const chiudi = chiusa ? null : h("button", { class: "s", type: "button" }, "Chiudi la campagna");
  if (chiudi) chiudi.onclick = () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, "Chiudere la campagna? Le email non ancora partite vengono scartate."),
    h("div", { class: "azioni" }, _btnCp("Sì, chiudi", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "chiusa" }); ricarica(); }, "p"), h("button", { class: "s", type: "button", onclick: () => conferma.replaceChildren() }, "Annulla"))));
  // brief
  const b = c.brief || {};
  const campiB = Object.fromEntries(CAMPI_BRIEF.map(([k, , ph]) => [k, h("textarea", { rows: 2, placeholder: ph }, b[k] || "")]));
  const categoria = h("input", { type: "text", value: c.categoria || "", maxlength: 40, placeholder: "hotel, musei, sponsor…" });
  const appunti = h("textarea", { rows: 3, placeholder: "Scrivi a ruota libera cosa vuoi ottenere, a chi, con quale occasione: il Redattore ne ricava il brief qui sotto." });
  const bloccoBrief = h("details", { class: "carta", open: !b.occasione && !chiusa }, h("summary", {}, h("b", {}, "Il brief"), h("span", { class: "sotto" }, " — la carta d'identità della campagna: il Redattore lo legge prima di ogni contatto")),
    h("label", {}, "Appunti per il brief", appunti),
    _btnCp("Proponi il brief dagli appunti", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/brief", { appunti: appunti.value }); for (const [k] of CAMPI_BRIEF) if (r[k]) campiB[k].value = r[k]; if (r.categoria && !categoria.value) categoria.value = r.categoria; msg.replaceChildren(avviso("Ecco la proposta: correggila e salva il brief.", "ok")); } catch (e) { err(e); } }, "s"),
    h("label", {}, "Categoria", categoria),
    CAMPI_BRIEF.map(([k, et]) => h("label", {}, et, campiB[k])),
    _btnCp("Salva il brief", async () => { try { await api("PUT", "/gestione/campagne/" + cid, { brief: Object.fromEntries(CAMPI_BRIEF.map(([k]) => [k, campiB[k].value])), categoria: categoria.value }); msg.replaceChildren(avviso("Brief salvato.", "ok")); } catch (e) { err(e); } }, "p"));
  // testo standard
  const obiettivo = h("textarea", { rows: 3 }, c.obiettivo);
  const oggetto = h("input", { type: "text", value: c.oggetto, maxlength: 200, placeholder: "Oggetto" });
  const testo = h("textarea", { rows: 10, placeholder: "Testo: usa {saluto}, {nome}, {ente}" }, c.testo);
  const salvaTesto = async () => api("PUT", "/gestione/campagne/" + cid, { obiettivo: obiettivo.value, oggetto: oggetto.value, testo: testo.value });
  const bloccoTesto = h("details", { class: "carta", open: !c.testo }, h("summary", {}, h("b", {}, "Il testo standard"), h("span", { class: "sotto" }, " — per chi non ha il sito, o se la personalizzazione è spenta")),
    h("p", { class: "sotto" }, "Da " + (c.mittente_email || "?") + (c.impresa ? " a nome di " + c.impresa : "") + ". {saluto} diventa «Gentile Nome Cognome,» oppure «Buongiorno,»; {ente} il nome dell'organizzazione. In fondo Opifex aggiunge la riga per chi non vuole altre email."),
    h("label", {}, "Obiettivo", obiettivo), h("label", {}, "Oggetto", oggetto), h("label", {}, "Testo", testo),
    chiusa ? null : h("div", { class: "azioni" },
      _btnCp("Fallo scrivere alla Posta", async () => { try { await api("PUT", "/gestione/campagne/" + cid, { obiettivo: obiettivo.value }); const r = await api("POST", "/gestione/campagne/" + cid + "/modello"); oggetto.value = r.oggetto; testo.value = r.testo; msg.replaceChildren(avviso("Ecco la proposta: correggila e salva.", "ok")); } catch (e) { err(e); } }, "s"),
      _btnCp("Salva il testo", async () => { try { await salvaTesto(); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { err(e); } }, "s"),
      !c.personalizza && !c.foglio && n.in_attesa ? _btnCp("Prepara subito le email (" + n.in_attesa + ")", async () => { try { await salvaTesto(); const r = await api("POST", "/gestione/campagne/" + cid + "/prepara"); msg.replaceChildren(avviso(r.preparate + " email pronte da leggere e approvare, qui sotto.", "ok")); ricarica(); } catch (e) { err(e); } }, "s") : null,
      c.foglio ? null : _btnCp("Ricalcola i destinatari dal CRM", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/destinatari"); msg.replaceChildren(avviso(r.nuovi + " nuovi destinatari (" + r.totale + " in tutto, " + r.esclusi + " esclusi).", "ok")); ricarica(); } catch (e) { err(e); } }, "s")));
  // correzioni proposte dal Redattore
  const correzioni = c.correzioni.length ? h("div", { class: "carta" }, h("h3", {}, "Correzioni proposte al CRM"), h("p", { class: "sotto" }, "Il Redattore non può modificare il CRM: ti propone le località che ha trovato sui siti."),
    c.correzioni.map(x => h("div", { class: "azioni", style: "align-items:center" }, h("span", {}, (x.ente || "Contatto") + ": " + x.campo + " → «" + x.valore + "»" + (x.comune ? " (ora: " + x.comune + ")" : "")),
      _btnCp("Accetta", async () => { await api("POST", "/gestione/campagne/correzioni/" + x.id, { accetta: true }); ricarica(); }, "s piccolo"),
      _btnCp("No", async () => { await api("POST", "/gestione/campagne/correzioni/" + x.id, { accetta: false }); ricarica(); }, "s piccolo")))) : null;
  // destinatari
  const dest = (x) => {
    const box = h("div", { class: "carta cp-dest" });
    box.append(h("div", { class: "mq-titolo" }, h("b", {}, x.ente || x.nome || x.email), x.nome && x.ente ? h("span", { class: "sotto" }, x.nome) : null,
      h("span", { class: "sotto" }, x.email), x.localita ? h("span", { class: "sotto" }, x.localita) : null, h("span", { class: "cp-stato cp-" + x.stato }, STATI_DEST[x.stato] || x.stato),
      x.passo > 1 ? h("span", { class: "sotto" }, "sollecito " + (x.passo - 1)) : null,
      x.inviata_il ? h("span", { class: "sotto" }, "inviata " + new Date(x.inviata_il).toLocaleDateString("it-IT")) : null,
      x.prossimo_il && x.stato === "inviata" ? h("span", { class: "sotto" }, "prossimo passo il " + new Date(x.prossimo_il).toLocaleDateString("it-IT")) : null));
    if (x.angolo) box.append(h("div", { class: "cp-angolo" }, h("b", {}, "Angolo: "), x.angolo, x.angolo_motivo ? h("span", { class: "sotto" }, " — " + x.angolo_motivo) : null));
    if (x.zona) box.append(h("div", { class: "sotto" + (/Attenzione|controllalo/.test(x.zona) ? " cp-avviso" : "") }, x.zona));
    if (x.nota) box.append(h("div", { class: "sotto" }, x.nota));
    if (x.risposta_oggetto || x.risposta_sintesi) box.append(h("div", { class: "sotto" }, "Risposta" + (x.risposta_oggetto ? ": «" + x.risposta_oggetto + "»" : "") + (x.risposta_sintesi ? " — " + x.risposta_sintesi : "")));
    if (x.errore && x.email_id) box.append(avviso(x.errore, "no"));
    const editor = (email_id, ogg, tes, titolo, aperto) => {
      const o = h("input", { type: "text", value: ogg || "", maxlength: 200 }), t = h("textarea", { rows: 9 }, tes || "");
      return h("details", { open: aperto }, h("summary", {}, titolo), h("label", {}, "Oggetto", o), h("label", {}, "Testo", t),
        h("div", { class: "azioni" },
          _btnCp("Approva", async () => { try { if (o.value !== ogg || t.value !== tes) await api("PUT", "/gestione/email-uscita/" + email_id, { oggetto: o.value, testo: t.value }); await api("POST", "/gestione/campagne/" + cid + "/approva", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "p"),
          _btnCp("Scarta", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/scarta", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "s")));
    };
    if (x.email_id && (x.stato === "da_approvare" || x.stato === "errore")) box.append(editor(x.email_id, x.oggetto, x.testo, x.tipo === "sollecito" ? "Leggi e correggi il sollecito" : "Leggi e correggi", false));
    if (x.risposta && (x.risposta.stato === "da_approvare" || x.risposta.stato === "errore")) box.append(editor(x.risposta.email_id, x.risposta.oggetto, x.risposta.testo, "La risposta per fissare la call (da approvare)", true));
    else if (x.risposta) box.append(h("div", { class: "sotto" }, "Risposta per la call: " + ({ approvata: "in partenza", inviata: "inviata", rifiutata: "scartata" })[x.risposta.stato]));
    if (["inviata", "risposto", "interessato", "non_interessato", "nessuna_risposta"].includes(x.stato)) {
      const es = (st, et, affare) => h("button", { class: "s piccolo", type: "button", onclick: async () => { try { const r = await api("POST", "/gestione/campagne/destinatari/" + x.id + "/esito", { stato: st, crea_affare: !!affare }); if (r.affare) msg.replaceChildren(avviso("Aperta l'opportunità nel CRM e preparata la risposta con il link per la call.", "ok")); ricarica(); } catch (e) { err(e); } } }, et);
      box.append(h("div", { class: "azioni" }, x.contatto_id ? h("button", { class: "s piccolo", type: "button", onclick: () => apriContatto(x.contatto_id) }, "Scheda nel CRM") : null,
        x.stato !== "interessato" ? es("interessato", "Interessato + opportunità", true) : null, x.stato !== "non_interessato" ? es("non_interessato", "Non interessato") : null, es("rimosso", "Non scrivergli più")));
    }
    return box;
  };
  const filtro = h("select", { "aria-label": "Mostra", class: "si-periodo" }, [["", "Tutti"], ["da_approvare", "Da approvare"], ["interessato", "Interessati"], ["inviata", "In attesa di risposta"], ["errore", "Con errori"], ["chiusi", "Chiusi"]].map(([v, t]) => { const o = h("option", { value: v }, t); if (v === (stato.campagnaFiltro || "")) o.selected = true; return o; }));
  const lista = h("div");
  const mostra = () => {
    const f = filtro.value; stato.campagnaFiltro = f;
    const sel = c.destinatari.filter(x => !f || (f === "chiusi" ? ["non_interessato", "rimosso", "nessuna_risposta", "scartata"].includes(x.stato) : x.stato === f || (f === "interessato" && x.stato === "risposto")));
    riempi(lista, sel.length ? sel.slice(0, 200).map(dest) : h("p", { class: "sotto" }, c.destinatari.length ? "Nessuno in questo gruppo." : "Nessun destinatario ancora: aggiungi righe al foglio o scegli i contatti dal CRM."));
  };
  filtro.onchange = mostra; mostra();
  riempi(corpo, [h("div", { class: "azioni" }, indietro), h("h2", { class: "cp-nome" }, c.nome, h("span", { class: "cp-stato" }, STATI_CP[c.stato])),
    h("div", { class: "azioni" }, avvia, approvaTutte, statoBtn, duplica, chiudi), conferma, msg,
    bloccoBrief, bloccoTesto,
    h("details", { class: "carta", open: true }, h("summary", {}, h("b", {}, "Il flusso")), _blocchiFlusso(c, salva)),
    correzioni,
    h("div", { class: "azioni", style: "align-items:center" }, h("h3", { style: "margin:0" }, "Destinatari"), filtro), lista]);
}

function apriContatto(id) { stato.contattoAperto = id; vai("contatto"); }
