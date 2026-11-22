"use strict";
// Campagne email a blocchi (2.64): partenza dal foglio Google o dal CRM, il Redattore studia i siti e scrive email personali, Lorenzo approva
// (finché non accende l'invio automatico), solleciti, e la Posta smista le risposte: interessati → opportunità con il link per la call.

const STATI_DEST = { in_attesa: "da preparare", in_studio: "il Redattore ci lavora", da_approvare: "da approvare", approvata: "approvata, in partenza", inviata: "inviata",
  scartata: "scartata", errore: "errore", risposto: "ha risposto (in lettura)", interessato: "interessato", non_interessato: "non interessato",
  rimosso: "non vuole altre email", nessuna_risposta: "chiuso: nessuna risposta", respinto: "email respinta: indirizzo bloccato" };
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
      d.campagne.length ? h("div", { class: "mq-classifica" }, d.campagne.map(riga)) : h("p", { class: "sotto" }, "Nessuna campagna ancora."),
      d.imbuto && d.imbuto[0].n ? h("div", { class: "carta" }, graficoImbutoCp(d.imbuto, "L'imbuto di tutte le campagne")) : null,
      d.campagne.length ? cartaClassificaCp() : null,
      _quadri(d.quadri), cartaFattureInCloud()]);
  };
  carica();
  return corpo;
}

// L'imbuto: un gradino per riga, la barra in proporzione ai contatti, e quanti passano dal gradino prima
function graficoImbutoCp(gradini, titolo) {
  const max = Math.max(1, ...gradini.map(g => g.n));
  return h("div", { class: "im-imbuto", role: "table", "aria-label": titolo || "Imbuto" },
    titolo ? h("div", { class: "bt-cap" }, titolo) : null,
    gradini.map((g, i) => h("div", { class: "im-riga", role: "row" },
      h("span", { class: "im-nome", role: "cell" }, g.gradino),
      h("span", { class: "im-barra", role: "cell", title: g.gradino + ": " + g.n }, h("span", { style: "width:" + Math.max(g.n ? 2 : 0, Math.round(100 * g.n / max)) + "%;opacity:" + (1 - i * 0.07) })),
      h("span", { class: "im-num", role: "cell" }, h("b", {}, String(g.n)), g.passaggio != null && i ? h("span", { class: "sotto" }, " " + g.passaggio + "%") : null))));
}

function _quadri(quadri) {
  if (!quadri || !quadri.length) return null;
  return h("div", { class: "carta" }, h("h3", {}, "Quadri di settore"),
    h("p", { class: "sotto" }, "Cosa chiedono i clienti, categoria per categoria, ricavato dalle call registrate. Il Redattore lo legge prima di scrivere."),
    quadri.map(q => h("details", {}, h("summary", {}, h("b", {}, q.categoria), h("span", { class: "sotto" }, " — " + q.n_call + (q.n_call === 1 ? " call" : " call") + ", aggiornato " + new Date(q.aggiornato_il).toLocaleDateString("it-IT"))),
      h("div", { class: "im-quadro" }, q.testo))),
    _btnCp("Aggiorna i quadri adesso", async () => { try { const r = await api("POST", "/gestione/campagne/quadri/aggiorna"); alert(r.aggiornati + " quadri aggiornati."); } catch (e) { alert(e.message); } }, "s piccolo"));
}

// Preventivo: bozza dall'analisi della call, prezzi di Lorenzo, poi creazione in Fatture in Cloud
const STATI_PREV = { bozza: "bozza", in_fatture: "in Fatture in Cloud", accettato: "accettato", rifiutato: "rifiutato", errore: "errore" };
function editorPreventivo(p, dopo) {
  const box = h("div", { class: "carta pv-editor" });
  const msg = h("div");
  const modificabile = p.stato === "bozza" || p.stato === "errore";
  const oggetto = h("input", { type: "text", value: p.oggetto || "", maxlength: 200, disabled: !modificabile });
  const note = h("textarea", { rows: 2, disabled: !modificabile }, p.note || "");
  const righe = h("div", { class: "pv-voci" });
  const totale = h("b");
  const voce = (v) => {
    const nome = h("input", { type: "text", value: v.nome || "", placeholder: "Voce", disabled: !modificabile });
    const descr = h("textarea", { rows: 2, placeholder: "Descrizione", disabled: !modificabile }, v.descrizione || "");
    const q = h("input", { type: "number", min: 0.01, step: 0.5, value: v.quantita || 1, disabled: !modificabile, "aria-label": "Quantità" });
    const pr = h("input", { type: "number", min: 0, step: 10, value: v.prezzo == null ? "" : v.prezzo, placeholder: "€ netto", disabled: !modificabile, "aria-label": "Prezzo netto" });
    const riga = h("div", { class: "pv-voce" }, h("div", { class: "pv-testi" }, nome, descr), h("label", {}, "Q.tà", q), h("label", {}, "Prezzo €", pr),
      modificabile ? h("button", { class: "s piccolo", type: "button", onclick: () => { riga.remove(); conta(); }, "aria-label": "Togli la voce" }, "×") : null);
    riga._leggi = () => ({ nome: nome.value, descrizione: descr.value, quantita: Number(q.value) || 1, prezzo: pr.value === "" ? null : Number(pr.value) });
    q.oninput = pr.oninput = conta;
    return riga;
  };
  function leggiVoci() { return [...righe.children].map(r => r._leggi()); }
  function conta() { const t = leggiVoci().reduce((a, v) => a + (v.prezzo || 0) * (v.quantita || 1), 0); totale.textContent = t.toLocaleString("it-IT", { style: "currency", currency: "EUR" }) + " + IVA"; }
  (p.voci || []).forEach(v => righe.append(voce(v)));
  conta();
  const salva = async () => { const r = await api("PUT", "/gestione/preventivi/" + p.id, { oggetto: oggetto.value, voci: leggiVoci(), note: note.value }); return r; };
  const conferma = h("div");
  box.append(...[h("div", { class: "mq-titolo" }, h("b", {}, "Preventivo per " + (p.cliente || "?")), h("span", { class: "cp-stato" }, STATI_PREV[p.stato] + (p.fic_numero ? " n. " + p.fic_numero : ""))),
    p.errore ? avviso(p.errore, "no") : null,
    h("label", {}, "Oggetto", oggetto), righe,
    modificabile ? h("button", { class: "s piccolo", type: "button", onclick: () => { righe.append(voce({ quantita: 1 })); } }, "+ Voce") : null,
    h("div", { class: "pv-totale" }, "Totale: ", totale), h("label", {}, "Note", note),
    modificabile ? h("div", { class: "azioni" },
      _btnCp("Salva", async () => { try { await salva(); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } }, "s"),
      h("button", { class: "p", type: "button", onclick: () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, "Creo il preventivo in Fatture in Cloud con queste voci? Da lì lo invii, lo modifichi e lo trasformi in fattura."),
        h("div", { class: "azioni" }, _btnCp("Sì, crealo", async () => { try { await salva(); const r = await api("POST", "/gestione/preventivi/" + p.id + "/crea"); msg.replaceChildren(avviso("Creato in Fatture in Cloud: preventivo n. " + r.numero + ". L'opportunità è a «proposta inviata».", "ok")); conferma.replaceChildren(); dopo && dopo(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } }, "p"),
          h("button", { class: "s", type: "button", onclick: () => conferma.replaceChildren() }, "Annulla")))) }, "Crea in Fatture in Cloud")) : null,
    p.stato === "in_fatture" ? h("div", { class: "azioni" }, p.fic_url ? h("a", { href: p.fic_url, target: "_blank", rel: "noopener", class: "s" }, "Apri in Fatture in Cloud") : null,
      _btnCp("Accettato (vinta)", async () => { await api("POST", "/gestione/preventivi/" + p.id + "/esito", { accettato: true }); dopo && dopo(); }, "s piccolo"),
      _btnCp("Rifiutato (persa)", async () => { await api("POST", "/gestione/preventivi/" + p.id + "/esito", { accettato: false }); dopo && dopo(); }, "s piccolo")) : null,
    conferma, msg].filter(Boolean));
  return box;
}

function cartaFattureInCloud() {
  const box = h("div", { class: "carta" }, h("p", { class: "sotto" }, "Carico…"));
  const carica = async () => {
    let d; try { d = await api("GET", "/gestione/preventivi"); } catch (e) { box.replaceChildren(avviso(e.message, "no")); return; }
    const c = d.config, msg = h("div");
    if (c.collegato && c.azienda_id) {
      riempi(box, [h("h3", {}, "Fatture in Cloud"), h("p", { class: "sotto" }, "Collegato all'azienda «" + (c.azienda || c.azienda_id) + "»" + (c.iva_id ? ", IVA " + c.iva + "%" : "") + ". I preventivi approvati in Opifex nascono lì; quando un preventivo diventa fattura, l'affare risulta vinto da solo."),
        _btnCp("Scollega", async () => { await api("DELETE", "/gestione/preventivi/fatture-in-cloud"); carica(); }, "s piccolo")]);
      return;
    }
    const tok = h("input", { type: "password", placeholder: "Token di Fatture in Cloud", autocomplete: "off" });
    const aziende = h("div");
    const vai_ = async (azienda_id) => { try { const r = await api("PUT", "/gestione/preventivi/fatture-in-cloud", { token: tok.value, azienda_id }); if (r.serve_scelta) { riempi(aziende, [h("p", {}, "Il token vede più aziende: quale uso?"), r.aziende.map(a => _btnCp(a.nome, () => vai_(a.id), "s"))]); return; } carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
    riempi(box, [h("h3", {}, "Fatture in Cloud"), h("p", { class: "sotto" }, "Per creare i preventivi in Fatture in Cloud: in Fatture in Cloud › Impostazioni › Applicazioni collegate crea il token con i permessi «Documenti emessi» (lettura e scrittura) e «Informazioni» (lettura), poi incollalo qui. Resta cifrato in Opifex."),
      h("div", { class: "azioni" }, tok, _btnCp("Collega", () => vai_(null), "p")), aziende, msg]);
  };
  carica();
  return box;
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
  const leggiOra = c.foglio ? _btnCp("Leggi il foglio adesso", async () => { try { const r = await api("POST", "/gestione/campagne/" + c.id + "/foglio"); alert(r.righe + " righe lette: " + r.nuove + " contatti nuovi, " + r.destinatari + " destinatari aggiunti" + (r.senza_email ? ", " + r.senza_email + " senza email" : "") + "." +
          ((r.fogli || []).length > 1 || (r.fogli || []).some(f => f.nota) ? "\n\nFogli del file:\n" + r.fogli.map(f => "• " + f.nome + ": " + (f.righe ? f.righe + " righe" : "nessun contatto") + (f.nota ? " (" + f.nota + ")" : "")).join("\n") : "")); salva({}); } catch (e) { alert(e.message); } }, "s piccolo") : null;
  // 2.70: altri documenti di contatti, con le stesse impostazioni
  const nuovoDoc = h("input", { type: "url", placeholder: "Link di un altro foglio Google o Excel su Drive" });
  const altriDoc = h("div", { class: "cp-docs" },
    (c.fogli_extra || []).map(x => h("div", { class: "cp-doc" }, h("span", { class: "cp-doc-url", title: x.url }, "📄 " + x.url.replace(/^https?:\/\//, "").slice(0, 60) + (x.url.length > 68 ? "…" : "")),
      x.errore ? avviso(x.errore, "no") : h("span", { class: "sotto" }, x.letto_il ? x.righe + " righe" : "non ancora letto"),
      _btnCp("Togli", async () => { await api("DELETE", "/gestione/campagne/" + c.id + "/fogli/" + x.id); salva({}); }, "s piccolo"))),
    h("div", { class: "cp-doc-nuovo" }, nuovoDoc, _btnCp(c.foglio ? "Aggiungi un altro documento" : "Collega il documento", async () => {
      if (!nuovoDoc.value.trim()) return;
      try { const r = await api("POST", "/gestione/campagne/" + c.id + "/fogli", { url: nuovoDoc.value.trim() }, { scadenzaMs: 180000 });
        alert(r.righe + " righe lette in tutti i documenti: " + r.nuove + " contatti nuovi, " + r.destinatari + " destinatari aggiunti."); salva({}); } catch (e) { alert(e.message); } }, "s piccolo")));
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
  // 2.72: fascia oraria, giorni feriali, periodo da evitare, riscaldamento della casella
  const oreDal = campo(h("input", { type: "number", min: 0, max: 23, value: c.ore_dal ?? "", placeholder: "—", style: "width:60px" }), "ore_dal", el => el.value === "" ? null : Number(el.value));
  const oreAl = campo(h("input", { type: "number", min: 1, max: 24, value: c.ore_al ?? "", placeholder: "—", style: "width:60px" }), "ore_al", el => el.value === "" ? null : Number(el.value));
  const feriali = h("input", { type: "checkbox" }); feriali.checked = !!c.solo_feriali; campo(feriali, "solo_feriali", el => el.checked);
  const evDal = campo(h("input", { type: "text", value: c.evita_dal || "", placeholder: "MM-GG", pattern: "\\d{2}-\\d{2}", style: "width:70px" }), "evita_dal");
  const evAl = campo(h("input", { type: "text", value: c.evita_al || "", placeholder: "MM-GG", pattern: "\\d{2}-\\d{2}", style: "width:70px" }), "evita_al");
  const scalda = h("input", { type: "checkbox" }); scalda.checked = !!c.riscalda_casella; campo(scalda, "riscalda_casella", el => el.checked);
  const ore = c.ore_dal != null && c.ore_al != null ? Math.max(0, c.ore_al - c.ore_dal) : 24;
  const regoleInvio = [h("label", {}, "Fascia oraria dalle ", oreDal, " alle ", oreAl), h("label", { class: "spunta" }, feriali, h("span", {}, "Solo giorni feriali")),
    h("label", {}, "Periodo da evitare dal ", evDal, " al ", evAl),
    h("label", { class: "spunta" }, scalda, h("span", {}, "Casella nuova: riscaldala (20 email il primo giorno, poi sale fino a 300 in 10 giorni)")),
    h("span", { class: "sotto" }, "Oggi da questa casella: " + (c.partite_oggi || 0) + " di " + (c.tetto_oggi || 300) + " · al massimo " + Math.min(c.per_ora * ore, c.tetto_oggi || 300) + " al giorno con questo ritmo e questa fascia"),
    c.non_parte ? h("span", { class: "sotto cp-blocco-fermo" }, "Adesso non parte: " + c.non_parte) : null,
    c.ore_suggerite ? h("span", { class: "sotto" }, "Dai dati di questa categoria: rispondono di più tra le " + c.ore_suggerite.ore_dal + " e le " + c.ore_suggerite.ore_al + " (" + c.ore_suggerite.tasso + "% contro " + c.ore_suggerite.media + "% di media). ",
      _btnCp("Usa questa fascia", () => salva({ ore_dal: c.ore_suggerite.ore_dal, ore_al: c.ore_suggerite.ore_al }), "s piccolo")) : null].filter(Boolean);
  const giorni = campo(h("input", { type: "number", min: 3, max: 60, value: c.sollecito_giorni, style: "width:70px" }), "sollecito_giorni", el => Number(el.value));
  const soll = campo(h("select", {}, [[0, "nessun sollecito"], [1, "solo la seconda email"], [2, "seconda email, e la terza se c'è una novità"]].map(([v, t]) => { const o = h("option", { value: v }, t); if (v === c.solleciti) o.selected = true; return o; })), "solleciti", el => Number(el.value));
  const link = campo(h("input", { type: "url", value: c.link_prenotazione || "", placeholder: "https://calendar.app.google/… (pagina di prenotazione, slot da 20 minuti)" }), "link_prenotazione");
  const cerca = h("input", { type: "checkbox" }); cerca.checked = !!c.cerca_email_nuova; campo(cerca, "cerca_email_nuova", el => el.checked);
  const opp = Object.fromEntries((c.opportunita || []).map(x => [x.stato, x.n]));
  return h("div", { class: "fl-flusso" },
    blocco("partenza", "Contatti", c.foglio ? "Righe nuove del foglio Google → contatti nel CRM (senza doppioni) e destinatari. Il foglio resta tuo: Opifex lo legge e basta." : "Contatti scelti dal CRM. Puoi collegare anche un foglio Google: le righe nuove entreranno da sole.",
      [foglio, accDrive, leggiOra, statoFoglio, altriDoc, _colonneCp(c, salva)].filter(Boolean), n.totale), freccia(),
    blocco("azione", "Studio del sito", "Il Redattore legge il sito (o le note già raccolte, se hanno meno di 6 mesi), verifica la zona con il CRM e sceglie l'angolo d'attacco seguendo il brief. Riceve solo dati pubblici: mai email o nomi delle persone.",
      [h("label", { class: "spunta" }, pers, h("span", {}, "Personalizza con il sito")), h("label", {}, "Modello ", modello), h("label", {}, "Tetto di spesa ", tetto), h("span", { class: "sotto" }, "speso " + _euroCp(c.spesa) + " su " + _euroCp(c.tetto_spesa))],
      n.in_studio || null), freccia(),
    blocco("azione", "Bozza", "Email personale con angolo e motivo; senza sito, il testo standard della campagna, riscritto per ogni contatto." +
      (c.blocco ? " Finché l'invio automatico è spento, il Redattore lavora a blocchi di " + c.blocco.dimensione + ": il blocco dopo parte quando hai approvato o scartato tutte le bozze di questo, così le tue correzioni arrivano prima." : ""),
      c.blocco ? [h("span", { class: "sotto" + (c.blocco.in_attesa && c.blocco.da_approvare ? " cp-blocco-fermo" : "") },
        c.blocco.in_attesa && c.blocco.da_approvare ? "Blocco completo: " + c.blocco.da_approvare + " bozze aspettano te prima delle prossime " + c.blocco.dimensione
          : "Blocco in corso: " + Math.min(c.blocco.fatte, c.blocco.dimensione) + " di " + c.blocco.dimensione + " preparate")] : null, n.da_approvare), freccia(),
    blocco("decisione", "Approvazione", c.invio_automatico ? "Invio automatico acceso: le bozze partono senza passare da te. Le risposte agli interessati le approvi sempre tu." : "Approvi tu ogni email. L'invio automatico si può accendere dopo " + a.serve + " bozze di fila approvate senza correzioni.",
      [h("label", { class: "spunta" }, auto, h("span", {}, "Invio automatico")), h("span", { class: "sotto" }, a.di_fila + " di " + a.serve + " approvate di fila senza correzioni")], null), freccia(),
    blocco("azione", "Invio", "Dalla casella " + (c.mittente_email || "?") + ", piano, per non finire nello spam. Entra nella storia del contatto.", [h("label", {}, "Email all'ora ", ritmo)].concat(regoleInvio), n.partite), freccia(),
    blocco("attesa", "Attesa della risposta", "La Posta legge le risposte con il modello del portatile (restano in casa) e le smista da sola.", [h("label", {}, "Giorni prima del sollecito ", giorni), h("label", {}, "Solleciti ", soll)], n.inviata), freccia(),
    h("div", { class: "fl-uscite" },
      blocco("uscita", "Interessato", "Opportunità al primo gradino, notifica, e la bozza di risposta con il link per prenotare la call. Anche i «mi richiami più avanti» contano come interessati.", [link], n.interessato),
      blocco("uscita", "Non interessato", "Chiuso senza avvisarti, mai cancellato: resta nelle statistiche.", null, n.non_interessato + n.rimosso),
      blocco("uscita", "Nessuna risposta", "Dopo i solleciti il contatto si chiude come «nessuna risposta».", null, n.nessuna_risposta),
      blocco("uscita", "Respinte", "Indirizzo inesistente: bloccato in tutte le campagne, niente solleciti e niente token spesi. La casella resta pulita.",
        [h("label", { class: "spunta" }, cerca, h("span", {}, "Cerca un'email nuova online e rimetti il contatto in coda")),
         h("span", { class: "sotto" }, "Spenta di serie: accendila solo per le liste che valgono la spesa della ricerca." +
           (c.respinte && c.respinte.trovate ? " Email nuove trovate: " + c.respinte.trovate + "." : "") + (c.respinte && c.respinte.in_ricerca ? " In ricerca: " + c.respinte.in_ricerca + "." : ""))], n.respinto)),
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
  const riscriviTutte = c.da_riscrivere ? _btnCp("Fai riscrivere le " + c.da_riscrivere + " bozze", () => riempi(conferma, h("div", { class: "carta" },
    h("p", {}, "Il Redattore riscrive da capo le " + c.da_riscrivere + " prime email non ancora partite, ognuna diversa dalle altre. Quelle che hai corretto a mano restano come sono. Ci vuole qualche minuto per ogni gruppo di 5 email, con un piccolo costo per ciascuna."),
    h("div", { class: "azioni" }, _btnCp("Sì, riscrivile", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/riscrivi", { tutte: true }); msg.replaceChildren(avviso(r.riscritte + " email tornate al Redattore: le nuove bozze arrivano nei prossimi giri.", "ok")); ricarica(); } catch (e) { err(e); } }, "p"),
      _btnCp("Annulla", () => conferma.replaceChildren(), "s")))), "s") : null;
  const riapriTutte = n.approvata ? _btnCp("Rimetti in modifica le " + n.approvata + " approvate", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/riapri", { tutte: true }); msg.replaceChildren(avviso(r.riaperte + " email di nuovo da approvare e modificabili.", "ok")); ricarica(); } catch (e) { err(e); } }, "s") : null;
  approvaTutte.onclick = () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, (n.da_approvare === 1 ? "Approvi 1 email?" : "Approvi " + n.da_approvare + " email?") + " Partiranno piano, circa " + c.per_ora + " all'ora. Approvarle tutte insieme non conta per l'invio automatico se non le hai lette. Le risposte agli interessati restano da approvare una per una."),
    h("div", { class: "azioni" }, _btnCp("Sì, approva e invia", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/approva", { tutte: true }); if (r.da_completare) alert(r.da_completare + (r.da_completare === 1 ? " email non è stata approvata: ha" : " email non sono state approvate: hanno") + " ancora parti tra [ ] da completare. Le trovi in «Da approvare»."); ricarica(); } catch (e) { err(e); } }, "p"),
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
    if (x.richiamo_il) box.append(h("div", { class: "cp-richiamo" }, (x.richiamo_fatto ? "✓ Ricontattato: " : "⏰ Da ricontattare il ") + new Date(x.richiamo_il + "T12:00:00").toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }) + (x.richiamo_nota ? " — «" + x.richiamo_nota + "»" : "")));
    if (x.risposta_oggetto || x.risposta_sintesi) box.append(h("div", { class: "sotto" }, "Risposta" + (x.risposta_oggetto ? ": «" + x.risposta_oggetto + "»" : "") + (x.risposta_sintesi ? " — " + x.risposta_sintesi : "")));
    if (x.errore && x.email_id) box.append(avviso(x.errore, "no"));
    const editor = (email_id, ogg, tes, oggP, tesP, titolo, aperto, html, allegati, tipo) => {
      const zona = h("div", { class: "cp-bozza" });
      const cambiata = tesP != null && (tes !== tesP || ogg !== oggP);
      const conCampagna = (c.allegati || []).filter(a => tipo === "primo" || (tipo === "sollecito" && a.in_solleciti));
      const elencoAllegati = (lista, togli) => (lista.length || conCampagna.length) ? h("div", { class: "cp-allegati" },
        lista.filter(a => !a.inline).map(a => h("span", { class: "cp-allegato" }, "📎 " + a.nome, h("span", { class: "sotto" }, " " + _pesoCp(a.dimensione)),
          togli ? h("button", { type: "button", class: "cp-x", title: "Togli", "aria-label": "Togli " + a.nome, onclick: () => togli(a) }, "×") : null)),
        conCampagna.map(a => h("span", { class: "cp-allegato campagna", title: "Allegato della campagna" }, "📎 " + a.nome, h("span", { class: "sotto" }, " con la campagna")))) : null;
      const leggi = () => {
        const confronto = cambiata ? h("details", { class: "cp-confronto" }, h("summary", {}, "Confronta con la prima versione del Redattore"),
          h("div", { class: "cp-due" }, h("div", {}, h("b", {}, "Redattore"), _diffCp(oggP + "\n\n" + tesP, ogg + "\n\n" + tes, "via")),
            h("div", {}, h("b", {}, "La tua versione"), _diffCp(oggP + "\n\n" + tesP, ogg + "\n\n" + tes, "nuovo")))) : null;
        const corpoTesto = html ? _htmlCp(html, allegati) : h("div", { class: "cp-testo" }, ..._quadreCp(tes));
        zona.replaceChildren(...[
          cambiata ? h("span", { class: "cp-tua" }, "✎ Modificata da te: il Redattore imparerà da questa correzione") : null,
          _QUADRE_CP.test((ogg || "") + (tes || "")) ? avviso("Ci sono ancora parti tra [ ] da completare: premi «Modifica», scrivile e salva. Finché restano, l'email non si può approvare.", "no") : null,
          h("div", { class: "cp-ogg" }, h("span", { class: "sotto" }, "Oggetto: "), ..._quadreCp(ogg)), corpoTesto, elencoAllegati(allegati || []), confronto,
          h("div", { class: "azioni" }, ...[
            _btnCp("Modifica", () => scrivi(), "s"),
            cambiata || x.tipo === "sollecito" || email_id !== x.email_id ? null : _btnCp("Fai riscrivere", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/riscrivi", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "s"),
            _btnCp("Approva", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/approva", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "p"),
            _btnCp("Scarta", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/scarta", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "s")].filter(Boolean))].filter(Boolean));
      };
      const scrivi = () => {
        const o = h("input", { type: "text", value: ogg || "", maxlength: 200 });
        let lista = (allegati || []).slice();
        const ed = _editorRiccoCp(html || _daTestoCp(tes || ""), lista, email_id, (nuovo) => { lista.push(nuovo); disegnaAll(); });
        const zonaAll = h("div");
        const disegnaAll = () => zonaAll.replaceChildren(elencoAllegati(lista, async (a) => { try { await api("DELETE", "/gestione/email-uscita/allegati/" + a.id); lista = lista.filter(y => y.id !== a.id); disegnaAll(); } catch (e) { err(e); } }) || "");
        disegnaAll();
        const salva = _btnCp("Salva", async () => { const v = ed.valore(); if (!o.value.trim() || !ed.testo().trim()) { err(new Error("Oggetto e testo non possono restare vuoti")); return; }
          try { await api("PUT", "/gestione/email-uscita/" + email_id, { oggetto: o.value, html: v }); ricarica(); } catch (e) { err(e); } }, "p");
        zona.replaceChildren(h("label", {}, "Oggetto", o), h("div", { class: "cp-etichetta" }, "Testo"), ed.el, zonaAll,
          h("p", { class: "sotto" }, "Puoi formattare il testo, mettere link, immagini e allegati. Gli indirizzi web scritti nel testo diventano link da soli. Salvi e la bozza resta da approvare; la versione del Redattore resta per il confronto, così impara a scrivere come te."),
          h("div", { class: "azioni" }, salva, _btnCp("Annulla", () => leggi(), "s")));
        ed.fuoco();
      };
      leggi();
      return h("details", { open: aperto }, h("summary", {}, titolo + (cambiata ? " · modificata da te" : "")), zona);
    };
    if (x.email_id && (x.stato === "da_approvare" || x.stato === "errore")) box.append(editor(x.email_id, x.oggetto, x.testo, x.oggetto_proposto, x.testo_proposto, x.tipo === "sollecito" ? "Leggi, modifica o approva il sollecito" : "Leggi, modifica o approva la bozza", true, x.html, x.allegati, x.tipo));
    const inCoda = (email_id, cosa) => h("div", { class: "azioni cp-incoda", style: "align-items:center" }, h("span", { class: "sotto" }, "✓ " + cosa + " approvata, in coda: non è ancora partita."),
      _btnCp("Rimetti in modifica", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/riapri", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "s piccolo"),
      _btnCp("Scarta", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/scarta", { ids: [email_id] }); ricarica(); } catch (e) { err(e); } }, "s piccolo"));
    if (x.email_id && x.email_stato === "approvata") box.append(inCoda(x.email_id, x.tipo === "sollecito" ? "Sollecito" : "Email"));
    if (x.risposta && x.risposta.stato === "approvata") box.append(inCoda(x.risposta.email_id, x.risposta.tipo === "ripresa" ? "Email di ripresa" : "Risposta"));
    else if (x.risposta && (x.risposta.stato === "da_approvare" || x.risposta.stato === "errore")) box.append(editor(x.risposta.email_id, x.risposta.oggetto, x.risposta.testo, x.risposta.oggetto_proposto, x.risposta.testo_proposto, x.risposta.tipo === "ripresa" ? "L'email per riprendere il discorso (da approvare)" : "La risposta per fissare la call (da approvare)", true, x.risposta.html, x.risposta.allegati, x.risposta.tipo));
    else if (x.risposta) box.append(h("div", { class: "sotto" }, (x.risposta.tipo === "ripresa" ? "Email di ripresa: " : "Risposta per la call: ") + ({ approvata: "in partenza", inviata: "inviata", rifiutata: "scartata" })[x.risposta.stato]));
    if (x.opportunita_id && x.stato === "interessato") {
      const zona = h("div");
      if (x.preventivo) {
        box.append(h("details", { ontoggle: async (ev) => { if (ev.currentTarget.open && !zona.firstChild) { const d = await api("GET", "/gestione/preventivi?opportunita_id=" + x.opportunita_id); zona.replaceChildren(editorPreventivo(d.preventivi[0], ricarica)); } } },
          h("summary", {}, "Preventivo " + STATI_PREV[x.preventivo.stato] + (x.preventivo.fic_numero ? " n. " + x.preventivo.fic_numero : "") + (x.preventivo.totale_netto ? " · " + x.preventivo.totale_netto.toLocaleString("it-IT", { style: "currency", currency: "EUR" }) : "")), zona));
      } else {
        box.append(h("div", { class: "azioni" }, _btnCp("Prepara il preventivo", async () => { try { const p = await api("POST", "/gestione/preventivi", { opportunita_id: x.opportunita_id }); zona.replaceChildren(editorPreventivo(p, ricarica)); } catch (e) { err(e); } }, "s piccolo")), zona);
      }
    }
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
    const sel = c.destinatari.filter(x => !f || (f === "chiusi" ? ["non_interessato", "rimosso", "nessuna_risposta", "scartata", "respinto"].includes(x.stato) : x.stato === f || (f === "interessato" && x.stato === "risposto")));
    riempi(lista, sel.length ? sel.slice(0, 200).map(dest) : h("p", { class: "sotto" }, c.destinatari.length ? "Nessuno in questo gruppo." : "Nessun destinatario ancora: aggiungi righe al foglio o scegli i contatti dal CRM."));
  };
  filtro.onchange = mostra; mostra();
  const quadro = c.quadro ? h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Quadro di settore: " + c.categoria), h("span", { class: "sotto" }, " — da " + c.quadro.n_call + " call; il Redattore lo usa")), h("div", { class: "im-quadro" }, c.quadro.testo)) : null;
  const abbinare = c.da_abbinare.length && c.interessati.length ? h("div", { class: "carta" }, h("h3", {}, "Resoconti delle call da abbinare"),
    h("p", { class: "sotto" }, "Resoconti PLAUD arrivati che Opifex non ha saputo abbinare da solo. Scegli con chi era la call: l'opportunità passa a «call fatta» e il modello del portatile ne fa l'analisi."),
    c.da_abbinare.map(r => { const sel = _opz(c.interessati.map(x => ({ id: x.contatto_id, nome: x.ente })), "— con chi era? —", x => x.nome);
      return h("div", { class: "azioni", style: "align-items:center" }, h("span", {}, (r.data ? new Date(r.data).toLocaleDateString("it-IT") + " · " : "") + r.titolo), sel,
        _btnCp("Abbina", async () => { if (!sel.value) return; try { const x = await api("POST", "/gestione/campagne/riunioni/" + r.id + "/abbina", { contatto_id: Number(sel.value) }); if (x.messaggio) alert(x.messaggio); ricarica(); } catch (e) { err(e); } }, "s piccolo")); })) : null;
  riempi(corpo, [h("div", { class: "azioni" }, indietro), h("h2", { class: "cp-nome" }, c.nome, h("span", { class: "cp-stato" }, STATI_CP[c.stato])),
    h("div", { class: "azioni" }, ...[avvia, approvaTutte, riapriTutte, riscriviTutte, statoBtn, duplica, chiudi].filter(Boolean)), conferma, msg,
    c.imbuto && c.imbuto[0].n ? h("div", { class: "carta" }, graficoImbutoCp(c.imbuto, "L'imbuto della campagna")) : null,
    abbinare, cartaDaChiamareCp(c), bloccoBrief, quadro, bloccoTesto, cartaProvaAbCp(c, salva),
    h("details", { class: "carta", open: true }, h("summary", {}, h("b", {}, "Il flusso")), _blocchiFlusso(c, salva)),
    correzioni, cartaAllegatiCp(c, ricarica), cartaStileCp(),
    h("div", { class: "azioni", style: "align-items:center" }, h("h3", { style: "margin:0" }, "Destinatari"), filtro), lista]);
}

function apriContatto(id) { stato.contattoAperto = id; vai("contatto"); }

// Confronto parola per parola fra la bozza del Redattore e la versione di Lorenzo (2.67)
function _diffCp(a, b, lato) {
  const pa = (a || "").split(/(\s+)/), pb = (b || "").split(/(\s+)/), n = pa.length, m = pb.length;
  const box = h("div", { class: "cp-diff" });
  if (n * m > 4000000) { box.textContent = lato === "via" ? a : b; return box; }
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = pa[i] === pb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  let i = 0, j = 0;
  const pezzo = (t, cl) => box.append(cl ? h("span", { class: cl }, t) : document.createTextNode(t));
  while (i < n || j < m) {
    if (i < n && j < m && pa[i] === pb[j]) { pezzo(pa[i]); i++; j++; }
    else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) { if (lato === "nuovo") pezzo(pb[j], /^\s+$/.test(pb[j]) ? null : "cp-agg"); j++; }
    else { if (lato === "via") pezzo(pa[i], /^\s+$/.test(pa[i]) ? null : "cp-tolto"); i++; }
  }
  return box;
}

// «Come scrivo io»: le regole che il Redattore ha ricavato dalle correzioni (2.67)
function cartaStileCp() {
  const corpo = h("div");
  const box = h("details", { class: "carta", ontoggle: async (ev) => {
    if (!ev.currentTarget.open || corpo.firstChild) return;
    try {
      const s = await api("GET", "/gestione/campagne/stile");
      const t = h("textarea", { rows: 10, placeholder: "Ancora nessuna regola. Correggi qualche bozza e approvala: le regole compariranno qui." }, s.regole || "");
      const esito = h("span", { class: "sotto" });
      corpo.replaceChildren(
        h("p", { class: "sotto" }, "Ogni volta che correggi una bozza e la approvi, il Redattore confronta la sua versione con la tua e aggiorna queste regole. " +
          "Le usa, insieme agli ultimi esempi di correzione, per tutte le bozze nuove. Puoi cambiarle anche a mano. Correzioni studiate finora: " + s.correzioni + "."),
        t, h("div", { class: "azioni", style: "align-items:center" }, _btnCp("Salva le regole", async () => { try { const r = await api("PUT", "/gestione/campagne/stile", { regole: t.value }); t.value = r.regole; esito.textContent = "Salvate."; } catch (e) { esito.textContent = e.message; } }, "p"), esito));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  } }, h("summary", {}, h("b", {}, "Come scrivo io"), h("span", { class: "sotto" }, " — quello che il Redattore ha imparato dalle tue correzioni")), corpo);
  return box;
}

// Parti tra [ ] rimaste nel testo: evidenziate (2.67.2)
const _QUADRE_CP = /\[[^\[\]\n]{1,80}\]/;
function _quadreCp(t) {
  return (t || "").split(/(\[[^\[\]\n]{1,80}\])/).map((p, i) => i % 2 ? h("mark", { class: "cp-quadra" }, p) : document.createTextNode(p));
}

// ---------- 2.69: email come in Gmail (testo formattato, link, immagini, allegati) ----------
const _pesoCp = (n) => n >= 1048576 ? (n / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const _escCp = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function _daTestoCp(t) {
  return t.trim().split(/\n\s*\n/).filter(p => p.trim()).map(p => "<p>" + _escCp(p).replace(/\n/g, "<br>") + "</p>").join("");
}
const _immaginiCp = {};   // id allegato -> indirizzo locale dell'immagine (si scarica una volta)
async function _srcCp(a) {
  if (_immaginiCp[a.id]) return _immaginiCp[a.id];
  const r = await fetch("/gestione/email-uscita/allegati/" + a.id, { headers: token ? { Authorization: "Bearer " + token } : {} });
  if (!r.ok) return "";
  return (_immaginiCp[a.id] = URL.createObjectURL(await r.blob()));
}
function _immaginiDaCid(el, allegati) {
  el.querySelectorAll("img[src^='cid:']").forEach(async (img) => {
    const cidImg = img.getAttribute("src").slice(4), a = (allegati || []).find(x => x.cid === cidImg);
    img.setAttribute("data-cid", cidImg); img.removeAttribute("src"); img.alt = img.alt || "immagine";
    if (a) { const u = await _srcCp(a); if (u) img.src = u; }
  });
}
function _htmlCp(html, allegati) {
  const el = h("div", { class: "cp-testo cp-ricco" });
  el.innerHTML = html;   // gia' ripulito dal server: solo formattazione, link e immagini interne
  el.querySelectorAll("a").forEach(a => { a.target = "_blank"; a.rel = "noopener"; });
  _immaginiDaCid(el, allegati);
  return el;
}
function _editorRiccoCp(html, allegati, email_id, aggiunto) {
  const area = h("div", { class: "cp-editor", contenteditable: "true", role: "textbox", "aria-multiline": "true", "aria-label": "Testo dell'email", spellcheck: "true" });
  area.innerHTML = html;
  _immaginiDaCid(area, allegati);
  const cmd = (c, v) => { area.focus(); document.execCommand(c, false, v); };
  const tasto = (et, titolo, fn, cls) => h("button", { type: "button", class: "cp-tasto" + (cls ? " " + cls : ""), title: titolo, "aria-label": titolo, onmousedown: (e) => e.preventDefault(), onclick: fn }, et);
  const carica = async (file, inline) => {
    const fd = new FormData(); fd.append("file", file); fd.append("inline", inline ? "true" : "false");
    return api("POST", "/gestione/email-uscita/" + email_id + "/allegati", fd, { scadenzaMs: 120000 });
  };
  const sceltaImg = h("input", { type: "file", accept: "image/*", style: "display:none", onchange: async () => {
    const f = sceltaImg.files[0]; sceltaImg.value = ""; if (!f) return;
    try { const a = await carica(f, true); allegati.push(a); area.focus();
      document.execCommand("insertHTML", false, '<img data-cid="' + a.cid + '" alt="' + _escCp(a.nome) + '" src="' + await _srcCp(a) + '">'); } catch (e) { alert(e.message); } } });
  const sceltaFile = h("input", { type: "file", multiple: true, style: "display:none", onchange: async () => {
    for (const f of [...sceltaFile.files]) { try { aggiunto(await carica(f, false)); } catch (e) { alert(f.name + ": " + e.message); } }
    sceltaFile.value = ""; } });
  const barra = h("div", { class: "cp-barra", role: "toolbar", "aria-label": "Formattazione" },
    tasto(h("b", {}, "G"), "Grassetto", () => cmd("bold")), tasto(h("i", {}, "C"), "Corsivo", () => cmd("italic")), tasto(h("u", {}, "S"), "Sottolineato", () => cmd("underline")),
    h("span", { class: "cp-sep" }),
    tasto("• Elenco", "Elenco puntato", () => cmd("insertUnorderedList")), tasto("1. Elenco", "Elenco numerato", () => cmd("insertOrderedList")),
    h("span", { class: "cp-sep" }),
    tasto("🔗 Link", "Trasforma il testo selezionato in un link", () => {
      const sel = window.getSelection(); const testo = sel ? String(sel) : "";
      let u = prompt("Indirizzo del link (https://…)", /^(https?:\/\/|www\.)/i.test(testo) ? testo : "https://"); if (!u || u === "https://") return;
      if (/^www\./i.test(u)) u = "https://" + u;
      if (!/^(https?:\/\/|mailto:)/i.test(u)) { alert("Il link deve cominciare con https:// o mailto:"); return; }
      if (testo) cmd("createLink", u); else cmd("insertHTML", '<a href="' + _escCp(u) + '">' + _escCp(u) + "</a>");
    }), tasto("Togli link", "Togli il link", () => cmd("unlink")),
    h("span", { class: "cp-sep" }),
    tasto("🖼 Immagine", "Metti un'immagine nel testo", () => sceltaImg.click()), tasto("📎 Allega", "Allega un file", () => sceltaFile.click()),
    tasto("Tx", "Togli la formattazione", () => cmd("removeFormat"), "cp-tenue"), sceltaImg, sceltaFile);
  return {
    el: h("div", { class: "cp-ricco-box" }, barra, area),
    fuoco: () => area.focus(),
    testo: () => area.innerText || "",
    valore: () => { const copia = area.cloneNode(true); copia.querySelectorAll("img[data-cid]").forEach(i => i.setAttribute("src", "cid:" + i.getAttribute("data-cid"))); return copia.innerHTML; },
  };
}

// Allegati della campagna: partono con ogni prima email (e, se scelto, con i solleciti)
function cartaAllegatiCp(c, ricarica) {
  const scelta = h("input", { type: "file", multiple: true });
  const esito = h("div");
  return h("details", { class: "carta", open: !!(c.allegati && c.allegati.length) },
    h("summary", {}, h("b", {}, "Allegati della campagna"), h("span", { class: "sotto" }, " — " + (c.allegati && c.allegati.length ? c.allegati.length + " file, partono con ogni prima email" : "per esempio una brochure o un portfolio"))),
    h("p", { class: "sotto" }, "Partono con ogni prima email della campagna; se vuoi anche con i solleciti, spunta la casella. Massimo 15 MB a file, 20 MB in tutto: per video o cartelle pesanti meglio un link nel testo."),
    (c.allegati || []).map(a => h("div", { class: "cp-all-riga" }, h("span", {}, "📎 " + a.nome + " ", h("span", { class: "sotto" }, _pesoCp(a.dimensione))),
      h("label", { class: "interruttore" }, h("input", { type: "checkbox", checked: a.in_solleciti, onchange: async (ev) => { await api("PUT", "/gestione/campagne/" + c.id + "/allegati/" + a.id, { in_solleciti: ev.target.checked }); } }), h("span", {}, "anche nei solleciti")),
      _btnCp("Togli", async () => { await api("DELETE", "/gestione/campagne/" + c.id + "/allegati/" + a.id); ricarica(); }, "s piccolo"))),
    h("div", { class: "azioni", style: "align-items:center" }, scelta, _btnCp("Aggiungi", async () => {
      for (const f of [...scelta.files]) { const fd = new FormData(); fd.append("file", f);
        try { await api("POST", "/gestione/campagne/" + c.id + "/allegati", fd, { scadenzaMs: 120000 }); } catch (e) { esito.replaceChildren(avviso(f.name + ": " + e.message, "no")); return; } }
      ricarica(); }, "p")), esito);
}

// 2.70: cosa c'e' in ogni colonna dei fogli (riconosciuto da Opifex, correggibile da Lorenzo)
const RUOLI_COL_CP = [["", "altri dati"], ["ente", "Nome"], ["email", "Email"], ["sito", "Sito"], ["telefono", "Telefono"], ["comune", "Comune / località"],
  ["provincia", "Provincia"], ["regione", "Regione"], ["note", "Note"]];
// 2.74: i contatti piu' promettenti da chiamare per primi
function cartaDaChiamareCp(c) {
  if (!c.da_chiamare || !c.da_chiamare.length) return null;
  return h("div", { class: "carta" }, h("b", {}, "Da chiamare prima"), h("p", { class: "sotto" }, "Chi ha risposto o è interessato, in ordine di punteggio (risposta, gradino dell'opportunità, sito studiato, indirizzo nominativo)."),
    h("div", { class: "cp-chiama" }, c.da_chiamare.map(x => h("div", { class: "cp-chiama-riga" },
      h("span", { class: "cp-punti", title: "punteggio" }, String(x.punteggio)),
      h("span", {}, h("b", {}, x.ente || x.nome || "Contatto"), x.sintesi ? h("span", { class: "sotto" }, " — " + x.sintesi) : null,
        x.opportunita ? h("span", { class: "sotto" }, " · " + x.opportunita.replace("_", " ")) : null)))));
}

// 2.74: prova dei due oggetti
function cartaProvaAbCp(c, salva) {
  const ogB = h("input", { type: "text", value: c.oggetto_b || "", maxlength: 200, placeholder: "Secondo oggetto da provare (lascia vuoto per non fare la prova)" });
  const res = (c.ab || []).map(x => h("div", {}, h("b", {}, "Oggetto " + x.variante + ": "), x.partite + " partite, " + x.risposte + " risposte" + (x.tasso != null ? " (" + x.tasso + "%)" : "") + ", " + x.interessati + " interessati"));
  return h("details", { class: "carta", open: !!c.oggetto_b }, h("summary", {}, h("b", {}, "Prova dei due oggetti"), h("span", { class: "sotto" }, " — metà dei contatti ricevono un oggetto, metà l'altro")),
    h("p", { class: "sotto" }, "Oggetto A è quello della campagna. Il Redattore parte dall'idea dell'oggetto assegnato e la adatta a ogni contatto. Quando ognuna delle due metà ha almeno 50 email partite, Opifex tiene l'oggetto che ottiene più risposte e te lo dice."),
    h("label", {}, "Oggetto B", ogB), _btnCp("Salva", () => salva({ oggetto_b: ogB.value.trim() }), "s piccolo"),
    res.length ? h("div", { class: "cp-ab" }, res) : null, c.ab_esito ? avviso(c.ab_esito, "ok") : null);
}

// 2.74: classifica delle campagne
function cartaClassificaCp() {
  const corpo = h("div", {}, h("p", { class: "sotto" }, "Carico…"));
  api("GET", "/gestione/campagne/classifica").then(d => {
    if (!d.campagne.length) { corpo.replaceChildren(h("p", { class: "sotto" }, "Ancora nessuna email partita.")); return; }
    const euro = v => v == null ? "—" : "€ " + _euroCp(v);
    const tab = (testate, righe) => h("div", { class: "cp-tab-scorre" }, h("table", { class: "tabella" }, h("thead", {}, h("tr", {}, testate.map(t => h("th", {}, t)))), h("tbody", {}, righe)));
    corpo.replaceChildren(
      tab(["Campagna", "Partite", "Risposte", "Interessati", "Call", "Costo modelli", "Per risposta", "Per call", "Tuo tempo"],
        d.campagne.map(x => h("tr", {}, h("td", {}, x.nome), h("td", {}, String(x.partite)), h("td", {}, x.risposte + (x.tasso != null ? " (" + x.tasso + "%)" : "")),
          h("td", {}, String(x.interessati)), h("td", {}, String(x.call)), h("td", {}, euro(x.spesa)), h("td", {}, euro(x.costo_risposta)), h("td", {}, euro(x.costo_call)),
          h("td", { title: "stima: 2 minuti per ogni bozza corretta, 12 secondi per ogni email approvata" }, "~" + x.minuti_tuoi + " min")))),
      d.angoli.length ? h("div", {}, h("h4", {}, "Angoli d'attacco che funzionano"), tab(["Angolo", "Partite", "Risposte", "Interessati"],
        d.angoli.map(x => h("tr", {}, h("td", {}, x.angolo), h("td", {}, String(x.partite)), h("td", {}, x.risposte + " (" + x.tasso + "%)"), h("td", {}, String(x.interessati)))))) : null,
      d.liste.length ? h("div", {}, h("h4", {}, "Liste"), tab(["Lista", "Partite", "Risposte", "Interessati"],
        d.liste.map(x => h("tr", {}, h("td", {}, x.lista), h("td", {}, String(x.partite)), h("td", {}, x.risposte + " (" + x.tasso + "%)"), h("td", {}, String(x.interessati)))))) : null);
  }).catch(e => corpo.replaceChildren(avviso(e.message, "no")));
  return h("details", { class: "carta" }, h("summary", {}, h("b", {}, "Classifica delle campagne"), h("span", { class: "sotto" }, " — quali portano più risposte e call, e quanto costano")), corpo);
}

function _colonneCp(c, salva) {
  const fogli = (c.foglio_resoconto || []).filter(f => f.colonne && f.colonne.length);
  if (!fogli.length) return null;
  return h("details", { class: "cp-colonne" }, h("summary", {}, "Cosa ho capito delle colonne (" + fogli.length + (fogli.length === 1 ? " foglio" : " fogli") + ")"),
    h("p", { class: "sotto" }, "Per ogni foglio: che cosa c'è in ogni colonna. Le colonne senza un ruolo non si perdono: finiscono nelle note del contatto come «altri dati». Se qualcosa è sbagliato (per esempio la prima colonna è un codice e il nome è nella seconda), correggi e salva: il foglio si rilegge subito."),
    fogli.map(f => {
      const scelte = f.colonne.map(col => { const s = h("select", { "aria-label": "Ruolo della colonna " + col.lettera }, RUOLI_COL_CP.map(([v, t]) => h("option", { value: v, selected: col.ruolo === v }, t))); return [col, s]; });
      const esito = h("div");
      return h("div", { class: "cp-col-foglio" }, h("div", {}, h("b", {}, f.etichetta), h("span", { class: "sotto" }, " · " + f.righe + " righe" + (f.corretta ? " · corretto da te" : "") + (f.testa != null ? " · intestazione alla riga " + (f.testa + 1) : " · senza intestazione"))),
        h("div", { class: "cp-col-tab" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Col."), h("th", {}, "Intestazione"), h("th", {}, "Esempio"), h("th", {}, "È…"))),
          h("tbody", {}, scelte.map(([col, s]) => h("tr", {}, h("td", {}, col.lettera), h("td", {}, col.nome || "—"), h("td", { class: "sotto" }, col.esempio || "—"), h("td", {}, s)))))),
        esito, h("div", { class: "azioni" }, _btnCp("Salva le colonne di questo foglio", async () => {
          const mappa = {}; for (const [col, s] of scelte) if (s.value) { if (s.value in mappa) { esito.replaceChildren(avviso("«" + s.selectedOptions[0].text + "» è scelto per due colonne", "no")); return; } mappa[s.value] = col.indice; }
          try { const r = await api("PUT", "/gestione/campagne/" + c.id + "/colonne", { documento: f.documento, foglio: f.foglio, testa: f.testa, mappa }, { scadenzaMs: 180000 });
            alert("Foglio riletto: " + r.nuove + " contatti nuovi, " + r.aggiornate + " aggiornati."); salva({}); } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
        }, "s piccolo")));
    }));
}
