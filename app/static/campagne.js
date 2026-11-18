"use strict";
// Campagne email della Posta, legate al CRM: si scelgono i destinatari con i filtri del CRM, la Posta scrive il testo, Lorenzo legge e approva,
// le email partono piano e ogni invio e ogni risposta entrano nella storia del contatto.

const STATI_DEST = { in_attesa: "da preparare", da_approvare: "da approvare", approvata: "approvata, in partenza", inviata: "inviata", scartata: "scartata",
  errore: "errore", risposto: "ha risposto", interessato: "interessato", non_interessato: "non interessato", rimosso: "non vuole altre email" };

const _btnCp = (testo, fn, cls) => h("button", { class: cls || "s", type: "button", onclick: async (ev) => { const b = ev.currentTarget; b.disabled = true; try { await fn(); } finally { b.disabled = false; } } }, testo);

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
        h("span", { class: "mq-dett" }, (c.impresa || "nessuna impresa") + " · " + ({ bozza: "bozza", in_corso: "in corso", in_pausa: "in pausa", chiusa: "chiusa" })[c.stato]
          + (n.da_approvare ? " · " + n.da_approvare + " da approvare" : "") + (n.approvata ? " · " + n.approvata + " in partenza" : "")
          + (n.risposte ? " · " + n.risposte + (n.risposte === 1 ? " risposta" : " risposte") + (n.tasso_risposta != null ? " (" + n.tasso_risposta + "%)" : "") : "")));
    };
    riempi(corpo, [
      h("p", { class: "aiuto" }, "Scegli i destinatari con i filtri del CRM, fai scrivere il testo alla Posta e correggilo. Poi Opifex prepara un'email per ognuno: le leggi e le approvi. Nulla parte senza il tuo sì. Le approvate partono piano (al ritmo che scegli, al massimo " + d.max_giorno + " al giorno) e ogni invio entra nella storia del contatto. Le risposte arrivate in posta si segnano da sole; chi chiede di non ricevere altre email non viene più incluso."),
      h("div", { class: "azioni" }, bNuova), nuova,
      d.campagne.length ? h("div", { class: "mq-classifica" }, d.campagne.map(riga)) : h("p", { class: "sotto" }, "Nessuna campagna ancora.")]);
  };
  carica();
  return corpo;
}

function formNuovaCampagna(d, dopo) {
  const nome = h("input", { type: "text", placeholder: "Nome della campagna (es. Musei liguri - visite Montarrenti 2027)", maxlength: 120 });
  const obiettivo = h("textarea", { rows: 4, placeholder: "Obiettivo: a chi scrivi, che cosa proponi, che cosa vuoi ottenere (es. fissare una telefonata)…" });
  const opz = (lista, vuota, cosa) => h("select", {}, [vuota ? h("option", { value: "" }, vuota) : null].concat(lista.map(x => h("option", { value: x.id }, cosa(x)))).filter(Boolean));
  const impresa = opz(d.aziende, "— a nome di quale impresa —", z => z.nome);
  const mitt = opz(d.mittenti, null, m => m.email + " (" + m.tipo + ")");
  const segm = opz(d.segmenti, "— tutti i contatti con email —", s => "Segmento: " + s.nome);
  const tipo = h("input", { type: "text", placeholder: "tipo (es. museo, comune)" }), regione = h("input", { type: "text", placeholder: "regione" }), categoria = h("input", { type: "text", placeholder: "categoria (es. potenziale cliente)" });
  const soloImpresa = h("input", { type: "checkbox" });
  const mai = h("input", { type: "checkbox" });
  const ritmo = h("input", { type: "number", min: 1, max: 120, value: 20, style: "width:80px" });
  const msg = h("div");
  if (!d.mittenti.length) return avviso("Prima collega una casella: un account Google con Gmail (Impostazioni › Google) o una casella IMAP con invio (Posta › Caselle).", "avv");
  return h("div", { class: "carta" }, h("h3", {}, "Nuova campagna"),
    h("label", {}, "Nome", nome), h("label", {}, "Obiettivo", obiettivo),
    h("div", { class: "azioni" }, impresa, mitt),
    h("div", { class: "sotto" }, "Destinatari dal CRM (solo contatti con email; chi ha negato il consenso o ha chiesto di non ricevere altre email è escluso):"),
    h("div", { class: "azioni" }, segm, tipo, regione, categoria),
    h("div", { class: "azioni" }, h("label", { class: "spunta" }, soloImpresa, h("span", {}, "solo i contatti già associati a questa impresa")), h("label", { class: "spunta" }, mai, h("span", {}, "solo mai contattati"))),
    h("label", {}, "Email all'ora (per non finire nello spam) ", ritmo),
    _btnCp("Crea e calcola i destinatari", async () => {
      const filtri = {};
      if (tipo.value.trim()) filtri.tipo = tipo.value.trim();
      if (regione.value.trim()) filtri.regione = regione.value.trim();
      if (categoria.value.trim()) filtri.categoria = categoria.value.trim();
      if (soloImpresa.checked && impresa.value) filtri.impresa_id = Number(impresa.value);
      if (mai.checked) filtri.mai_contattati = true;
      try {
        const r = await api("POST", "/gestione/campagne", { nome: nome.value, obiettivo: obiettivo.value, azienda_id: impresa.value ? Number(impresa.value) : null, mittente: mitt.value,
          segmento_id: segm.value ? Number(segm.value) : null, filtri, per_ora: Number(ritmo.value) || 20 });
        dopo(r.id);
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    }, "p"), msg);
}

async function apriCampagna(corpo, cid, torna) {
  let c; try { c = await api("GET", "/gestione/campagne/" + cid); } catch (e) { stato.campagnaAperta = null; corpo.replaceChildren(avviso(e.message, "no")); return; }
  const ricarica = () => apriCampagna(corpo, cid, torna);
  const n = c.numeri, msg = h("div");
  const indietro = h("button", { class: "s", type: "button", onclick: () => { stato.campagnaAperta = null; torna(); } }, "← Tutte le campagne");
  const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
  // testo
  const obiettivo = h("textarea", { rows: 3 }, c.obiettivo);
  const oggetto = h("input", { type: "text", value: c.oggetto, maxlength: 200, placeholder: "Oggetto" });
  const testo = h("textarea", { rows: 12, placeholder: "Testo: usa {saluto}, {nome}, {ente}" }, c.testo);
  const salva = async () => api("PUT", "/gestione/campagne/" + cid, { obiettivo: obiettivo.value, oggetto: oggetto.value, testo: testo.value });
  const chiusa = c.stato === "chiusa";
  const bloccoTesto = h("div", { class: "carta" }, h("h3", {}, "Il testo"),
    h("p", { class: "sotto" }, "Da " + (c.mittente_email || "?") + (c.impresa ? " a nome di " + c.impresa : "") + ". {saluto} diventa «Gentile Nome Cognome,» oppure «Buongiorno,»; {ente} il nome dell'organizzazione. In fondo Opifex aggiunge la riga per chi non vuole altre email."),
    h("label", {}, "Obiettivo", obiettivo), h("label", {}, "Oggetto", oggetto), h("label", {}, "Testo", testo),
    chiusa ? null : h("div", { class: "azioni" },
      _btnCp("Fallo scrivere alla Posta", async () => { try { await api("PUT", "/gestione/campagne/" + cid, { obiettivo: obiettivo.value }); const r = await api("POST", "/gestione/campagne/" + cid + "/modello"); oggetto.value = r.oggetto; testo.value = r.testo; msg.replaceChildren(avviso("Ecco la proposta della Posta: correggila e salva.", "ok")); } catch (e) { err(e); } }, "s"),
      _btnCp("Salva il testo", async () => { try { await salva(); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { err(e); } }, "s"),
      n.in_attesa ? _btnCp("Prepara le email (" + n.in_attesa + ")", async () => { try { await salva(); const r = await api("POST", "/gestione/campagne/" + cid + "/prepara"); msg.replaceChildren(avviso(r.preparate + " email pronte da leggere e approvare, qui sotto.", "ok")); ricarica(); } catch (e) { err(e); } }, "p") : null,
      _btnCp("Ricalcola i destinatari", async () => { try { const r = await api("POST", "/gestione/campagne/" + cid + "/destinatari"); msg.replaceChildren(avviso(r.nuovi + " nuovi destinatari (" + r.totale + " in tutto, " + r.esclusi + " esclusi).", "ok")); ricarica(); } catch (e) { err(e); } }, "s")));
  // numeri e comandi
  const conferma = h("div");
  const approvaTutte = h("button", { class: "p", type: "button" }, n.da_approvare === 1 ? "Approva l'email da approvare" : "Approva tutte le " + n.da_approvare + " email");
  approvaTutte.hidden = !n.da_approvare;
  approvaTutte.onclick = () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, (n.da_approvare === 1 ? "Approvi 1 email?" : "Approvi " + n.da_approvare + " email?") + " Partiranno piano, circa " + c.per_ora + " all'ora. Puoi sempre mettere in pausa."),
    h("div", { class: "azioni" }, _btnCp("Sì, approva e invia", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/approva", { tutte: true }); ricarica(); } catch (e) { err(e); } }, "p"),
      h("button", { class: "s", type: "button", onclick: () => conferma.replaceChildren() }, "Annulla"))));
  const statoBtn = chiusa ? null : c.stato === "in_pausa"
    ? _btnCp("Riprendi gli invii", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "in_corso" }); ricarica(); }, "s")
    : _btnCp("Metti in pausa", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "in_pausa" }); ricarica(); }, "s");
  const chiudi = chiusa ? null : h("button", { class: "s", type: "button" }, "Chiudi la campagna");
  if (chiudi) chiudi.onclick = () => riempi(conferma, h("div", { class: "carta" }, h("p", {}, "Chiudere la campagna? Le email non ancora partite vengono scartate."),
    h("div", { class: "azioni" }, _btnCp("Sì, chiudi", async () => { await api("PUT", "/gestione/campagne/" + cid, { stato: "chiusa" }); ricarica(); }, "p"), h("button", { class: "s", type: "button", onclick: () => conferma.replaceChildren() }, "Annulla"))));
  const numeri = h("div", { class: "mq-numeri" }, [["destinatari", n.totale], ["da preparare", n.in_attesa], ["da approvare", n.da_approvare], ["in partenza", n.approvata], ["inviate", n.partite], ["risposte", n.risposte + (n.tasso_risposta != null ? " (" + n.tasso_risposta + "%)" : "")], ["interessati", n.interessato], ["errori", n.errore]]
    .map(([et, v]) => h("div", { class: "pb-tessera" }, h("div", { class: "sotto" }, et), h("b", {}, String(v)))));
  // destinatari
  const dest = (x) => {
    const box = h("div", { class: "carta cp-dest" });
    const testa = h("div", { class: "mq-titolo" }, h("b", {}, x.nome || x.ente || x.email), x.nome && x.ente ? h("span", { class: "sotto" }, x.ente) : null,
      h("span", { class: "sotto" }, x.email), h("span", { class: "cp-stato cp-" + x.stato }, STATI_DEST[x.stato] || x.stato),
      x.inviata_il ? h("span", { class: "sotto" }, "inviata " + new Date(x.inviata_il).toLocaleString("it-IT")) : null);
    box.append(testa);
    if (x.risposta_oggetto) box.append(h("div", { class: "sotto" }, "Risposta: «" + x.risposta_oggetto + "»"));
    if (x.errore) box.append(avviso(x.errore, "no"));
    if (x.stato === "da_approvare" || x.stato === "errore") {
      const o = h("input", { type: "text", value: x.oggetto || "", maxlength: 200 }), t = h("textarea", { rows: 8 }, x.testo || "");
      box.append(h("details", {}, h("summary", {}, "Leggi e correggi"), h("label", {}, "Oggetto", o), h("label", {}, "Testo", t),
        h("div", { class: "azioni" },
          _btnCp("Approva", async () => { try { await api("PUT", "/gestione/email-uscita/" + x.email_id, { oggetto: o.value, testo: t.value }); await api("POST", "/gestione/campagne/" + cid + "/approva", { ids: [x.email_id] }); ricarica(); } catch (e) { err(e); } }, "p"),
          _btnCp("Scarta", async () => { try { await api("POST", "/gestione/campagne/" + cid + "/scarta", { ids: [x.email_id] }); ricarica(); } catch (e) { err(e); } }, "s"))));
    }
    if (["inviata", "risposto", "interessato", "non_interessato"].includes(x.stato)) {
      const es = (st, et, affare) => h("button", { class: "s piccolo", type: "button", onclick: async () => { try { const r = await api("POST", "/gestione/campagne/destinatari/" + x.id + "/esito", { stato: st, crea_affare: !!affare }); if (r.affare) msg.replaceChildren(avviso("Aperto un affare nel CRM.", "ok")); ricarica(); } catch (e) { err(e); } } }, et);
      box.append(h("div", { class: "azioni" }, x.contatto_id ? h("button", { class: "s piccolo", type: "button", onclick: () => apriContatto(x.contatto_id) }, "Scheda nel CRM") : null,
        es("interessato", "Interessato"), es("interessato", "Interessato + apri affare", true), es("non_interessato", "Non interessato"), es("rimosso", "Non scrivergli più")));
    }
    return box;
  };
  riempi(corpo, [h("div", { class: "azioni" }, indietro), h("h2", { class: "cp-nome" }, c.nome),
    numeri, h("div", { class: "azioni" }, approvaTutte, statoBtn, chiudi), conferma, msg, bloccoTesto,
    h("h3", {}, "Destinatari"), c.destinatari.length ? c.destinatari.map(dest) : h("p", { class: "sotto" }, "Nessun destinatario: cambia i filtri o ricalcola.")]);
}

function apriContatto(id) { stato.contattoAperto = id; vai("contatto"); }
