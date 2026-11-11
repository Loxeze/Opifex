"use strict";
// Contatti (CRM): liste, importazione CSV, riepilogo aggregato e ricerca. I dati personali sono cifrati sul server; gli agenti vedono solo conteggi.

function vistaCrm() {
  const TAB = [["cruscotto", "Cruscotto"], ["schede", "Contatti"], ["ricontattare", "Da ricontattare"], ["pipeline", "Opportunità"], ["radar", "Radar"], ["ricerca", "Ricerca contatti"], ["campi", "Campi e categorie"], ["liste", "Liste"]];
  if (!stato.crmTab) stato.crmTab = "cruscotto";
  const corpo = h("div");
  const tabs = h("div", { class: "azioni", style: "margin-bottom:12px;align-items:center" }, TAB.map(([id, nome]) => h("button", { class: stato.crmTab === id ? "p" : "s", onclick: () => { stato.crmTab = id; disegna(); } }, nome)));
  const importa = h("div");
  const pulsanteImporta = h("button", { class: "p", style: "margin-left:auto", onclick: () => {
    if (importa.firstChild) { importa.replaceChildren(); return; }
    importa.replaceChildren(importazioneGuidata(() => importa.replaceChildren()));
  } }, "⬆ Importa contatti");
  tabs.append(h("button", { class: "p", style: "margin-left:auto", onclick: () => crmNuovoContatto() }, "+ Nuovo contatto"));
  pulsanteImporta.style.marginLeft = "0";
  tabs.append(pulsanteImporta);
  if (stato.crmTab === "cruscotto") corpo.append(...[].concat(crmCruscotto()));
  else if (stato.crmTab === "schede") corpo.append(...[].concat(crmContatti()));
  else if (stato.crmTab === "ricontattare") corpo.append(...[].concat(crmSchede("da_ricontattare")));
  else if (stato.crmTab === "pipeline") corpo.append(...[].concat(crmBacheca()));
  else if (stato.crmTab === "ricerca") corpo.append(...[].concat(crmRicerca()));
  else if (stato.crmTab === "radar") corpo.append(...[].concat(crmRadar(), crmRicerca(true)));
  else if (stato.crmTab === "campi") corpo.append(...[].concat(campiPersonalizzati()));
  else corpo.append(...[].concat(crmListe()));
  return [h("h2", {}, "CRM"), tabs, importa, corpo];
}

function crmListe() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/crm/liste");
      riempi(corpo, [h("p", { class: "aiuto" }, "Qui carichi le liste di contatti da file CSV. I nomi, le email e i telefoni sono cifrati nel database. Gli agenti con «può consultare i conteggi del CRM» vedono solo numeri (sotto " + d.minimo + " contatti rispondono «meno di " + d.minimo + "»), mai elenchi o recapiti."),
        formLista(d, carica), d.liste.length ? d.liste.map(l => cartaLista(l, carica)) : h("p", { class: "sotto" }, "Nessuna lista ancora."), riepilogoCrm(), ricercaCrm()]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}

function formLista(d, ricarica) {
  const msg = h("div");
  const nome = h("input", { type: "text", maxlength: 120, placeholder: "Es. Pubbliche amministrazioni" });
  const fonte = h("input", { type: "text", maxlength: 200, placeholder: "Es. database acquistato nel 2024" });
  const natura = h("select", {}, h("option", { value: "pubblico" }, "Dati pubblici (enti, PA)"), h("option", { value: "personale" }, "Dati di persone (clienti, visitatori)"));
  const base = h("input", { type: "text", maxlength: 200, placeholder: "Solo per dati di persone: consenso, contratto, interesse legittimo…" });
  const az = h("select", {}, h("option", { value: "" }, "Nessuna azienda"), d.aziende.map(a => h("option", { value: a.id }, a.nome)));
  return h("details", { class: "carta" }, h("summary", {}, "+ Nuova lista di contatti"),
    h("label", {}, "Nome", nome), h("label", {}, "Fonte", fonte), h("label", {}, "Natura dei dati", natura), h("label", {}, "Base giuridica", base), h("label", {}, "Azienda", az), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      try { await api("POST", "/gestione/crm/liste", { nome: nome.value, fonte: fonte.value || null, natura: natura.value, base_giuridica: base.value || null, azienda_id: az.value ? Number(az.value) : null }); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea lista")));
}

function cartaLista(l, ricarica) {
  const msg = h("div");
  const file = h("input", { type: "file", accept: ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, l.nome), h("span", { class: "etichetta " + (l.natura === "personale" ? "avv" : "ok") }, l.natura === "personale" ? "Dati di persone" : "Dati pubblici"),
    h("div", { class: "sotto" }, l.contatti.toLocaleString("it-IT") + " contatti" + (l.azienda ? " · " + l.azienda : "") + (l.fonte ? " · " + l.fonte : "") + (l.base_giuridica ? " · base: " + l.base_giuridica : "")),
    h("p", { class: "aiuto" }, "File Excel (.xlsx) o CSV con una riga di intestazioni (anche non la prima). Riconosco: nome, ente, email, telefono, tipo (es. comune), regione, provincia, abitanti, settore, relazione, ultimo contatto, consenso, note."),
    file, msg, h("div", { class: "azioni" },
      h("button", { class: "p", onclick: async (ev) => {
        if (!file.files.length) { msg.replaceChildren(avviso("Scegli un file Excel o CSV.", "avv")); return; }
        const b = ev.currentTarget; b.disabled = true; msg.replaceChildren(avviso("Importazione in corso…", "avv"));
        try { const fd = new FormData(); fd.append("file", file.files[0]); const r = await api("POST", "/gestione/crm/liste/" + l.id + "/importa", fd);
          msg.replaceChildren(avviso(r.importati + " importati, " + r.doppioni + " doppioni, " + r.righe_vuote + " righe vuote (" + r.origine + ").", "ok"),
            r.colonne_ignorate && r.colonne_ignorate.length ? avviso("Colonne non riconosciute (ignorate): " + r.colonne_ignorate.join(", "), "avv") : null); setTimeout(ricarica, 1200); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Importa file"),
      h("button", { class: "s", onclick: async () => { if (!confirm("Eliminare la lista e tutti i suoi contatti?")) return; try { await api("DELETE", "/gestione/crm/liste/" + l.id); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina lista")));
}

function riepilogoCrm() {
  const out = h("div"); const per = h("select", {}, ["regione", "tipo", "provincia", "fascia_dimensione", "settore", "relazione"].map(x => h("option", { value: x }, x.replace("_", " "))));
  const vai = async () => { try { const r = await api("GET", "/gestione/crm/riepilogo?per=" + per.value);
    out.replaceChildren(...r.gruppi.map(g => h("div", { class: "sotto" }, g.valore + ": " + g.contatti))); if (!r.gruppi.length) out.replaceChildren(h("p", { class: "sotto" }, "Nessun dato.")); } catch (e) { out.replaceChildren(avviso(e.message, "no")); } };
  per.addEventListener("change", vai); vai();
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Riepilogo (come lo vedono gli agenti)"), h("label", {}, "Raggruppa per", per), out);
}

function ricercaCrm() {
  const q = h("input", { type: "search", placeholder: "Cerca per nome, ente, email o telefono (almeno 3 caratteri)" }); const out = h("div");
  const cerca = async () => { out.replaceChildren(); try { const r = await api("GET", "/gestione/crm/cerca?q=" + encodeURIComponent(q.value));
    out.replaceChildren(...(r.risultati.length ? r.risultati.map(x => h("div", { class: "sotto" }, [x.nome, x.ente, x.email, x.telefono, x.tipo, x.provincia].filter(Boolean).join(" · ") + " (" + x.lista + ")")) : [h("p", { class: "sotto" }, "Nessun risultato.")])); }
    catch (e) { out.replaceChildren(avviso(e.message, "no")); } };
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") cerca(); });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Cerca un contatto (solo tu, ogni ricerca resta registrata)"), q, h("div", { class: "azioni" }, h("button", { class: "s", onclick: cerca }, "Cerca")), out);
}


// Ricerca contatti: il Ricercatore cerca online contatti molto specifici; qui si approvano prima che entrino nel CRM.
function crmRicerca(soloProposte) {
  const box = h("div"), msg = h("div");
  const criteri = h("textarea", { rows: 4, placeholder: "Es.: direttori e conservatori di musei civici in Toscana e Liguria, con email nominativa di lavoro (non info@). Escludi musei privati.", style: "width:100%" });
  const quanti = h("input", { type: "number", min: 1, max: 40, value: 15, style: "width:70px" });
  const va = h("button", { class: "p", type: "button" }, "Avvia la ricerca");
  va.addEventListener("click", async () => {
    if (criteri.value.trim().length < 20) { msg.replaceChildren(avviso("Descrivi i criteri con più precisione (ruolo, tipo di ente, zona, cosa escludere).", "avv")); return; }
    va.disabled = true;
    try { await api("POST", "/gestione/crm-ricerca/ricerche", { criteri: criteri.value, quantita: Number(quanti.value) || 15 }); msg.replaceChildren(avviso("Ricerca avviata: i risultati compaiono qui sotto da approvare.", "ok")); carica(); }
    catch (e) { msg.replaceChildren(avviso(e.message, "no")); } finally { va.disabled = false; }
  });
  const sel = new Set();
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/crm-ricerca");
      const decidi = async (azione) => {
        if (!sel.size) return;
        try { const r = await api("POST", "/gestione/crm-ricerca/decidi", { ids: [...sel], azione }); sel.clear(); msg.replaceChildren(avviso(azione === "approva" ? `Aggiunti al CRM: ${r.importati}` + (r.doppioni ? ` (doppioni scartati: ${r.doppioni})` : "") : `Scartati: ${r.scartate}`, "ok")); carica(); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      const righe = d.proposte.map(p => h("label", { class: "carta", style: "display:block;margin-bottom:8px" },
        h("input", { type: "checkbox", checked: sel.has(p.id), onchange: ev => { ev.target.checked ? sel.add(p.id) : sel.delete(p.id); } }), " ",
        h("strong", {}, p.nome || p.ente), p.nome ? " · " + p.ente : "", p.ruolo ? " · " + p.ruolo : "",
        h("div", { class: "sotto" }, [p.email, p.telefono, [p.provincia, p.regione].filter(Boolean).join(" ")].filter(Boolean).join(" · ")),
        p.tema ? h("div", { class: "sotto" }, "📡 Radar «" + p.tema + "»" + (p.segnale ? ": " + p.segnale : "")) : null,
        h("div", { class: "sotto" }, "Perché: " + p.motivo), h("a", { href: p.fonte_url, target: "_blank", rel: "noopener noreferrer", class: "sotto" }, "Fonte: " + p.fonte_url)));
      const tutte = h("button", { class: "s", type: "button" }, "Seleziona tutte");
      tutte.addEventListener("click", () => { d.proposte.forEach(p => sel.add(p.id)); carica(); });
      const ok = h("button", { class: "p", type: "button" }, "Aggiungi al CRM"), no = h("button", { class: "s", type: "button" }, "Scarta");
      ok.addEventListener("click", () => decidi("approva")); no.addEventListener("click", () => decidi("scarta"));
      riempi(box, [d.attivo ? null : avviso("Il Ricercatore contatti non è attivo.", "avv"),
        h("h3", {}, `Da approvare (${d.proposte.length})`), d.proposte.length ? [h("div", { class: "azioni" }, tutte, ok, no), righe] : h("p", { class: "sotto" }, "Nessuna proposta in attesa."),
        d.ricerche.length ? h("details", {}, h("summary", {}, "Ultime ricerche"), d.ricerche.map(r => h("p", { class: "sotto" }, `#${r.id} ${({ in_corso: "in corso…", conclusa: "conclusa", errore: "errore" })[r.stato]} · ${r.proposte} proposte, ${r.scartate} doppioni · ${r.criteri.slice(0, 120)}`))) : null]);
    } catch (e) { mostraErrore(box, e, carica); }
  };
  carica();
  ticker(box, carica, 15000);
  if (soloProposte) return [msg, box];
  return [h("p", { class: "aiuto" }, "Il Ricercatore contatti (reparto CRM, modello economico) cerca online contatti molto specifici. Nulla entra nel CRM da solo: ogni proposta ha la sua fonte e la approvi tu. Solo dati professionali pubblici; nomi e recapiti sono cifrati."),
    h("label", {}, "Che contatti cerchi? (ruolo preciso, tipo di ente, zona, cosa escludere)", criteri), h("div", { class: "azioni" }, h("label", {}, "Quanti al massimo ", quanti), va), msg, box];
}


// Radar: temi da tenere d'occhio su notizie, articoli e blog; le segnalazioni arrivano nella lista da approvare qui sotto
function crmRadar() {
  const box = h("div"), msg = h("div");
  const TIPI = [["cliente", "Clienti"], ["collaboratore", "Collaboratori"], ["partner", "Partner"], ["opportunita", "Opportunità e bandi"]];
  const OGNI = [[1, "ogni giorno"], [2, "ogni 2 giorni"], [7, "ogni settimana"]];
  const modulo = (t, fatto) => {
    const nome = h("input", { type: "text", maxlength: 80, value: t.nome || "", placeholder: "Es.: Comuni che investono nel turismo culturale" });
    const tipo = h("select", {}, TIPI.map(([v, n]) => h("option", { value: v }, n))); tipo.value = t.tipo || "cliente";
    const descr = h("textarea", { rows: 3, style: "width:100%", placeholder: "Che cosa cerchi e perché ti interessa. Es.: comuni e GAL di Liguria, Toscana e Piemonte che annunciano progetti di valorizzazione di borghi, castelli o musei, o che hanno ottenuto fondi PNRR/FESR per il patrimonio: potrebbero aver bisogno di contenuti digitali, app o video (Renovatio, Logos)." }, t.descrizione || "");
    const ogni = h("select", {}, OGNI.map(([v, n]) => h("option", { value: v }, n))); ogni.value = String(t.giorni || 1);
    const quanti = h("input", { type: "number", min: 1, max: 40, value: t.quantita || 10, style: "width:70px" });
    const salva = h("button", { class: "p", type: "button" }, t.id ? "Salva" : "Aggiungi il tema");
    salva.addEventListener("click", async () => {
      const corpo_ = { nome: nome.value, tipo: tipo.value, descrizione: descr.value, giorni: Number(ogni.value), quantita: Number(quanti.value) || 10, attivo: t.attivo !== false };
      try { await api(t.id ? "PUT" : "POST", "/gestione/radar" + (t.id ? "/" + t.id : ""), corpo_); msg.replaceChildren(avviso("Salvato.", "ok")); fatto(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    });
    return h("div", { class: "carta" }, h("label", {}, "Nome del tema", nome), h("label", {}, "Che cosa cerca", tipo), h("label", {}, "Descrizione (più è precisa, migliori i risultati)", descr),
      h("div", { class: "azioni" }, h("label", {}, "Frequenza ", ogni), h("label", {}, "Segnalazioni al massimo ", quanti), salva));
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/radar");
      const nuovo = h("div");
      riempi(box, [d.attivo ? null : avviso("Il Ricercatore contatti non è attivo: il Radar si appoggia a lui.", "avv"),
        d.temi.length ? d.temi.map(t => {
          const dett = h("div");
          return h("div", { class: "carta", style: "margin-bottom:8px" },
            h("div", { class: "nome" }, (t.attivo ? "📡 " : "⏸ ") + t.nome),
            h("div", { class: "sotto" }, (TIPI.find(x => x[0] === t.tipo) || [0, t.tipo])[1] + " · " + (OGNI.find(x => x[0] === t.giorni) || [0, "ogni " + t.giorni + " giorni"])[1]
              + " · " + t.segnalazioni + " segnalazioni, " + t.approvate + " entrate nel CRM" + (t.ultima_il ? " · ultimo giro " + new Date(t.ultima_il).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : " · mai girato")),
            h("p", { class: "sotto" }, t.descrizione),
            h("div", { class: "azioni" },
              h("button", { class: "s", type: "button", onclick: async () => { try { await api("POST", "/gestione/radar/" + t.id + "/ora"); msg.replaceChildren(avviso("Giro avviato: le segnalazioni compaiono qui sotto in qualche minuto.", "ok")); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Fai un giro adesso"),
              h("button", { class: "s", type: "button", onclick: async () => { try { await api("PUT", "/gestione/radar/" + t.id, { ...t, attivo: !t.attivo }); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, t.attivo ? "Metti in pausa" : "Riattiva"),
              h("button", { class: "s", type: "button", onclick: () => dett.replaceChildren(modulo(t, carica)) }, "Modifica"),
              h("button", { class: "s", type: "button", onclick: async () => { try { await api("DELETE", "/gestione/radar/" + t.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina")),
            dett);
        }) : h("p", { class: "sotto" }, "Nessun tema ancora: aggiungine uno qui sotto."),
        h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: () => nuovo.replaceChildren(modulo({}, () => { nuovo.replaceChildren(); carica(); })) }, "+ Nuovo tema")), nuovo]);
    } catch (e) { mostraErrore(box, e, carica); }
  };
  carica();
  return [h("h3", {}, "Radar"),
    h("p", { class: "aiuto" }, "Il Radar legge notizie, articoli di giornale, blog e comunicati e ti segnala potenziali clienti, collaboratori, partner e opportunità. Ogni tema ha la sua frequenza. Le segnalazioni arrivano qui sotto con l'articolo da cui nascono e il motivo: nulla entra nel CRM senza il tuo sì e nessuno viene contattato."),
    msg, box, h("h3", {}, "Segnalazioni e proposte da valutare")];
}
