"use strict";
// CRM: elenco dei contatti, scheda del singolo contatto (storia, opportunità, prossimo passo) e pipeline delle opportunità.

const CANALI_CRM = { email: "Email", telefono: "Telefono", incontro: "Incontro", riunione: "Riunione", messaggio: "Messaggio", social: "Social", altro: "Altro" };
const ESITI_CRM = { nessuna_risposta: "Nessuna risposta", risposto: "Ha risposto", interessato: "Interessato", non_interessato: "Non interessato", da_richiamare: "Da richiamare", altro: "—" };
const STATI_OPP = { nuova: "Nuova", contattato: "Contattato", in_trattativa: "In trattativa", vinta: "Vinta", persa: "Persa", in_pausa: "In pausa" };
const TIPI_OPP = { bando: "Bando", cliente: "Cliente", partnership: "Partnership", sponsor: "Sponsor", consulenza: "Consulenza", altro: "Altro" };
const dataIt = (d) => d ? new Date(d).toLocaleDateString("it-IT") : "—";

function crmSchede(filtro) {
  const corpo = h("div"), msg = h("div");
  const q = h("input", { type: "search", placeholder: "Cerca per nome, ente, email o telefono", maxlength: 100 });
  let ultimo = null;
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/crm/contatti?filtro=" + filtro + (q.value.trim().length >= 2 ? "&q=" + encodeURIComponent(q.value.trim()) : ""));
      ultimo = d;
      const c = d.conteggi;
      const nome = h("input", { type: "text", maxlength: 200, placeholder: "Nome e cognome" }), ente = h("input", { type: "text", maxlength: 200, placeholder: "Ente / azienda" });
      const email = h("input", { type: "email", maxlength: 200 }), tel = h("input", { type: "text", maxlength: 60 }), note = h("textarea", { style: "min-height:56px", maxlength: 5000 });
      riempi(corpo, [
        h("p", { class: "sotto" }, c.totale.toLocaleString("it-IT") + " contatti · " + c.da_ricontattare + " da ricontattare · " + c.mai_contattati + " mai contattati"),
        h("div", { class: "riga" }, h("label", {}, "Cerca", q)),
        d.contatti.length ? d.contatti.map(x => h("div", { class: "carta", style: "margin-bottom:8px;cursor:pointer", onclick: () => { stato.contattoAperto = x.id; vai("contatto"); } },
          h("div", { class: "nome" }, x.nome || x.ente || x.email || ("Contatto #" + x.id)),
          h("div", { class: "sotto" }, [x.nome && x.ente ? x.ente : "", x.email, x.tipo !== "altro" ? x.tipo : "", x.provincia, "ultimo contatto: " + dataIt(x.ultimo_contatto), x.opp_aperte ? x.opp_aperte + " opportunità aperte" : ""].filter(Boolean).join(" · ")),
          x.prossimo_passo ? h("div", { class: "sotto", style: "color:" + (x.prossimo_passo_il && x.prossimo_passo_il <= new Date().toISOString().slice(0, 10) ? "var(--avv)" : "var(--tenue)") }, "➜ " + x.prossimo_passo + (x.prossimo_passo_il ? " (entro " + dataIt(x.prossimo_passo_il) + ")" : "")) : null))
          : h("p", { class: "sotto" }, filtro ? "Nessun contatto da ricontattare." : "Nessun contatto."),
        filtro ? null : h("details", { class: "carta" }, h("summary", {}, "+ Nuovo contatto"),
          h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Ente", ente)), h("div", { class: "riga" }, h("label", {}, "Email", email), h("label", {}, "Telefono", tel)), h("label", {}, "Note", note),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { const r = await api("POST", "/gestione/crm/contatti", { nome: nome.value, ente: ente.value, email: email.value, telefono: tel.value, note: note.value }); stato.contattoAperto = r.id; vai("contatto"); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea e apri la scheda"))), msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") carica(); });
  carica();
  return corpo;
}

function crmPipeline() {
  const corpo = h("div");
  api("GET", "/gestione/crm/pipeline").then(d => {
    const eur = (n) => n ? n.toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }) : "";
    riempi(corpo, [h("p", { class: "aiuto" }, "Le opportunità aperte e quelle chiuse negli ultimi 60 giorni. Si creano e si aggiornano dalla scheda di ogni contatto."),
      h("div", { class: "riga", style: "align-items:flex-start" }, Object.keys(STATI_OPP).map(s => h("div", { class: "carta", style: "flex:1 1 210px;min-width:0" },
        h("div", { class: "nome" }, STATI_OPP[s] + " (" + d.colonne[s].length + ")"), d.totali[s] ? h("div", { class: "sotto" }, eur(d.totali[s])) : null,
        d.colonne[s].map(o => h("div", { class: "sotto", style: "padding:8px 0;border-top:1px solid var(--bordo);cursor:pointer", onclick: () => { stato.contattoAperto = o.contatto_id; vai("contatto"); } },
          h("div", { style: "color:var(--testo)" }, o.titolo), [o.contatto, TIPI_OPP[o.tipo], eur(o.valore_euro), o.progetto, o.scadenza ? "entro " + dataIt(o.scadenza) : ""].filter(Boolean).join(" · "),
          o.prossima_azione ? h("div", {}, "➜ " + o.prossima_azione) : null)))))]);
  }).catch(e => corpo.replaceChildren(avviso(e.message, "no")));
  return corpo;
}

function vistaContatto() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/crm/contatti/" + stato.contattoAperto);
      const c = d.contatto;
      const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
      const sel = (obj, val) => { const s = h("select", {}, Object.entries(obj).map(([k, t]) => h("option", { value: k }, t))); s.value = val; return s; };
      const opz = (lista, vuoto) => [h("option", { value: "" }, vuoto)].concat(lista.map(x => h("option", { value: x.id }, x.nome)));
      // dati del contatto
      const f = { nome: h("input", { type: "text", value: c.nome, maxlength: 200 }), ente: h("input", { type: "text", value: c.ente, maxlength: 200 }), email: h("input", { type: "email", value: c.email, maxlength: 200 }),
        telefono: h("input", { type: "text", value: c.telefono, maxlength: 60 }), note: h("textarea", { style: "min-height:60px", maxlength: 5000 }, c.note) };
      const m = d.modello;
      f.genere = sel({ organizzazione: "Organizzazione", persona: "Persona" }, m.genere);
      f.tipo = h("input", { type: "text", value: c.tipo === "altro" ? "" : c.tipo, maxlength: 40, list: "tipi-crm", placeholder: "Es. comune, albergo, università" });
      f.comune = h("input", { type: "text", value: c.comune || "", maxlength: 100 });
      const passo = h("input", { type: "text", value: c.prossimo_passo || "", maxlength: 300, placeholder: "Es. Richiamare per il bando" }), passoIl = h("input", { type: "date", value: c.prossimo_passo_il || "" });
      const resp = h("select", {}, opz(d.utenti, "— nessuno —")); resp.value = c.responsabile_utente_id || "";
      // nuova interazione
      const ic = sel(CANALI_CRM, "email"), id = sel({ uscita: "L'abbiamo contattato noi", entrata: "Ci ha contattato lui" }, "uscita"), ie = sel(ESITI_CRM, "altro");
      const io = h("input", { type: "text", maxlength: 200, placeholder: "Oggetto (facoltativo)" }), inote = h("textarea", { style: "min-height:56px", maxlength: 5000, placeholder: "Cosa è stato detto / risposto" });
      const ip = h("select", {}, opz(d.progetti, "— nessun progetto —")), iq = h("input", { type: "datetime-local" });
      // nuova opportunità
      const ot = h("input", { type: "text", maxlength: 200, placeholder: "Es. Co-finanziamento Interreg" }), otipo = sel(TIPI_OPP, "altro"), ost = sel(STATI_OPP, "nuova");
      const ov = h("input", { type: "number", min: 0, step: 100, placeholder: "Valore €" }), osc = h("input", { type: "date" }), oaz = h("input", { type: "text", maxlength: 300, placeholder: "Prossima azione" });
      const opr = h("select", {}, opz(d.progetti, "— nessun progetto —"));
      riempi(corpo, [
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => vai("crm") }, "← CRM")),
        h("div", { class: "carta" }, h("div", { class: "nome" }, c.nome || c.ente || c.email), h("div", { class: "sotto" }, [c.lista.nome, "relazione: " + c.relazione, "ultimo contatto: " + dataIt(c.ultimo_contatto)].join(" · ")),
          h("div", { class: "riga" }, h("label", {}, "Nome", f.nome), h("label", {}, "Ente", f.ente)), h("div", { class: "riga" }, h("label", {}, "Email", f.email), h("label", {}, "Telefono", f.telefono)),
          h("div", { class: "riga" }, h("label", {}, "È una", f.genere), h("label", {}, "Tipo", f.tipo), h("label", {}, "Comune", f.comune)),
          h("datalist", { id: "tipi-crm" }, m.tipi_in_uso.map(t => h("option", { value: t }))), h("label", {}, "Note", f.note),
          h("div", { class: "riga" }, h("label", {}, "Prossimo passo", passo), h("label", {}, "Entro il", passoIl), h("label", {}, "Responsabile", resp)),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("PUT", "/gestione/crm/contatti/" + c.id, { nome: f.nome.value, ente: f.ente.value, email: f.email.value, telefono: f.telefono.value, note: f.note.value, genere: f.genere.value, tipo: f.tipo.value || "altro", comune: f.comune.value,
              prossimo_passo: passo.value || null, prossimo_passo_il: passoIl.value || null, responsabile_utente_id: resp.value ? Number(resp.value) : null }); msg.replaceChildren(avviso("Salvato.", "ok")); await carica(); } catch (e) { err(e); } } }, "Salva la scheda"),
            h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare il contatto con tutta la sua storia?")) return; try { await api("DELETE", "/gestione/crm/contatti/" + c.id); vai("crm"); } catch (e) { err(e); } } }, "Elimina"))),
        ...modelloScheda(d, c, carica, err),
        h("h3", {}, "Opportunità"),
        d.opportunita.length ? d.opportunita.map(o => {
          const st = sel(STATI_OPP, o.stato);
          return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, o.titolo),
            h("div", { class: "sotto" }, [TIPI_OPP[o.tipo], o.valore_euro ? Number(o.valore_euro).toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }) : "", o.progetto, o.azienda, o.scadenza ? "entro " + dataIt(o.scadenza) : ""].filter(Boolean).join(" · ")),
            o.prossima_azione ? h("div", {}, "➜ " + o.prossima_azione) : null, o.note ? h("div", { class: "sotto" }, o.note) : null,
            h("div", { class: "azioni" }, st, h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/crm/opportunita/" + o.id, { stato: st.value }); await carica(); } catch (e) { err(e); } } }, "Aggiorna stato"),
              h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare l'opportunità?")) return; try { await api("DELETE", "/gestione/crm/opportunita/" + o.id); await carica(); } catch (e) { err(e); } } }, "Elimina")));
        }) : h("p", { class: "sotto" }, "Nessuna opportunità aperta per questo contatto."),
        h("details", { class: "carta" }, h("summary", {}, "+ Nuova opportunità"),
          h("div", { class: "riga" }, h("label", {}, "Titolo", ot), h("label", {}, "Tipo", otipo), h("label", {}, "Stato", ost)),
          h("div", { class: "riga" }, h("label", {}, "Valore", ov), h("label", {}, "Scadenza", osc), h("label", {}, "Progetto", opr)), h("label", {}, "Prossima azione", oaz),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("POST", "/gestione/crm/contatti/" + c.id + "/opportunita", { titolo: ot.value, tipo: otipo.value, stato: ost.value,
              valore_euro: ov.value ? Number(ov.value) : null, scadenza: osc.value || null, progetto_id: opr.value ? Number(opr.value) : null, prossima_azione: oaz.value || null }); await carica(); } catch (e) { err(e); } } }, "Aggiungi"))),
        h("h3", {}, "Storia dei contatti"),
        h("details", { class: "carta" }, h("summary", {}, "+ Registra un contatto avvenuto"),
          h("div", { class: "riga" }, h("label", {}, "Canale", ic), h("label", {}, "Chi ha iniziato", id), h("label", {}, "Esito", ie), h("label", {}, "Quando (vuoto = ora)", iq)),
          h("label", {}, "Oggetto", io), h("label", {}, "Note", inote), h("label", {}, "Progetto collegato", ip),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("POST", "/gestione/crm/contatti/" + c.id + "/interazioni", { canale: ic.value, direzione: id.value, esito: ie.value,
              oggetto: io.value || null, note: inote.value || null, progetto_id: ip.value ? Number(ip.value) : null, quando: iq.value ? new Date(iq.value).toISOString() : null }); await carica(); } catch (e) { err(e); } } }, "Registra"))),
        d.interazioni.length ? d.interazioni.map(i => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, (i.direzione === "uscita" ? "➡ " : "⬅ ") + CANALI_CRM[i.canale] + (i.oggetto ? " · " + i.oggetto : "")),
          h("div", { class: "sotto" }, [new Date(i.quando).toLocaleString("it-IT"), i.da ? "da " + i.da : "", ESITI_CRM[i.esito] !== "—" ? ESITI_CRM[i.esito] : "", i.progetto, i.riunione ? "riunione «" + i.riunione + "»" : ""].filter(Boolean).join(" · ")),
          i.note ? h("div", {}, i.note) : null)) : h("p", { class: "sotto" }, "Ancora nessun contatto registrato."), msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Scheda contatto"), corpo];
}


// ---- modello dei dati: campi personalizzati, categorie, relazioni, recapiti, fonte e verifica, storico ----
function modelloScheda(d, c, carica, err) {
  const m = d.modello, base = "/gestione/crm";
  const ok = async (f) => { try { await f(); await carica(); } catch (e) { err(e); } };
  // campi personalizzati del tipo
  const val = {};
  const campi = m.definizioni.map(df => {
    let inp;
    const cur = m.attributi[df.chiave];
    if (df.dato === "scelta") { inp = h("select", {}, [h("option", { value: "" }, "—")].concat(df.scelte.map(x => h("option", { value: x }, x)))); inp.value = cur ?? ""; }
    else if (df.dato === "si_no") { inp = h("select", {}, [h("option", { value: "" }, "—"), h("option", { value: "si" }, "Sì"), h("option", { value: "no" }, "No")]); inp.value = cur === true ? "si" : cur === false ? "no" : ""; }
    else inp = h("input", { type: df.dato === "numero" ? "number" : df.dato === "data" ? "date" : "text", value: cur ?? "", maxlength: 500, step: "any" });
    val[df.chiave] = inp;
    return h("label", {}, df.etichetta + (df.tipo ? "" : " (per tutti)"), inp);
  });
  const orfani = Object.keys(m.attributi_orfani || {});
  const blocchiAttr = h("div", { class: "carta" }, h("div", { class: "nome" }, "Campi personalizzati"),
    campi.length ? [h("div", { class: "riga" }, campi), h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => ok(async () => { await api("PUT", base + "/contatti/" + c.id + "/attributi", { valori: Object.fromEntries(Object.entries(val).map(([k, i]) => [k, i.value])) }); }) }, "Salva i campi"))]
      : h("p", { class: "sotto" }, "Per il tipo «" + (c.tipo || "altro") + "» non ci sono campi: li definisci in CRM → Campi e categorie. Restano vuoti dove non servono."),
    orfani.length ? h("p", { class: "sotto" }, "Valori di campi non più previsti per questo tipo: " + orfani.join(", ")) : null);
  // categorie
  const cat = h("input", { type: "text", list: "categorie-crm", placeholder: "Categoria", maxlength: 60 }), mot = h("input", { type: "text", placeholder: "Perché rientra in questa categoria", maxlength: 300 });
  const blocchiCat = h("div", { class: "carta" }, h("div", { class: "nome" }, "Categorie"),
    m.categorie.length ? m.categorie.map(x => h("div", { class: "sotto" }, h("b", {}, x.categoria), " — " + x.motivazione + " ", h("button", { class: "s", onclick: () => ok(() => api("DELETE", base + "/contatti/" + c.id + "/categorie/" + encodeURIComponent(x.categoria))) }, "Togli"))) : h("p", { class: "sotto" }, "Nessuna categoria."),
    h("datalist", { id: "categorie-crm" }, (d.categorie_ammesse || []).map(x => h("option", { value: x.nome }))),
    h("div", { class: "riga" }, h("label", {}, "Categoria", cat), h("label", {}, "Motivazione", mot)),
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => ok(() => api("POST", base + "/contatti/" + c.id + "/categorie", { categoria: cat.value, motivazione: mot.value })) }, "Assegna")));
  // relazioni
  const rAltro = h("select", {}, [h("option", { value: "" }, m.genere === "persona" ? "— scegli l'organizzazione —" : "— scegli la persona —")].concat((d.possibili_relazioni || []).map(x => h("option", { value: x.id }, x.nome))));
  const rRuolo = h("input", { type: "text", placeholder: "Ruolo (es. direttore)", maxlength: 120 }), rDal = h("input", { type: "date" }), rAl = h("input", { type: "date" });
  const blocchiRel = h("div", { class: "carta" }, h("div", { class: "nome" }, m.genere === "persona" ? "Dove lavora" : "Chi ci lavora"),
    m.relazioni.length ? m.relazioni.map(x => h("div", { class: "sotto", style: x.attuale ? "" : "opacity:.7" },
      h("a", { href: "#", onclick: (e) => { e.preventDefault(); stato.contattoAperto = x.altro_id; carica_altro(); } }, x.altro), " · " + (x.ruolo || "—") + " · " + (x.attuale ? "attuale" : "PASSATO") + " (" + dataIt(x.dal) + " → " + (x.al ? dataIt(x.al) : "oggi") + ")" + (x.fonte ? " · fonte: " + x.fonte : "") + " ",
      x.attuale ? h("button", { class: "s", onclick: () => ok(() => api("PUT", base + "/relazioni/" + x.id + "/termina", {})) }, "Chiudi incarico") : null,
      h("button", { class: "s", onclick: () => { if (confirm("Eliminare la relazione?")) ok(() => api("DELETE", base + "/relazioni/" + x.id)); } }, "Elimina"))) : h("p", { class: "sotto" }, "Nessuna relazione."),
    h("div", { class: "riga" }, h("label", {}, m.genere === "persona" ? "Organizzazione" : "Persona", rAltro), h("label", {}, "Ruolo", rRuolo), h("label", {}, "Dal", rDal), h("label", {}, "Al", rAl)),
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => ok(() => {
      if (!rAltro.value) throw new Error("Scegli con chi collegarlo");
      const a = Number(rAltro.value), body = m.genere === "persona" ? { persona_id: c.id, organizzazione_id: a } : { persona_id: a, organizzazione_id: c.id };
      return api("POST", base + "/relazioni", { ...body, ruolo: rRuolo.value || null, dal: rDal.value || null, al: rAl.value || null });
    }) }, "Collega")));
  // recapiti aggiuntivi
  const tipoR = h("select", {}, [["email", "Email"], ["telefono", "Telefono"], ["sito", "Sito"], ["indirizzo", "Indirizzo"]].map(([k, t]) => h("option", { value: k }, t))), vR = h("input", { type: "text", maxlength: 300 }), fR = h("input", { type: "text", placeholder: "Fonte (facoltativa)", maxlength: 300 });
  const blocchiRec = h("div", { class: "carta" }, h("div", { class: "nome" }, "Altri recapiti"),
    m.recapiti.length ? m.recapiti.map(x => h("div", { class: "sotto" }, x.tipo + ": " + x.valore + (x.fonte ? " · fonte: " + x.fonte : "") + (x.verificato_il ? " · verificato il " + dataIt(x.verificato_il) : "") + " ",
      h("button", { class: "s", onclick: () => ok(() => api("DELETE", base + "/recapiti/" + x.id)) }, "Togli"))) : h("p", { class: "sotto" }, "Nessun recapito aggiuntivo."),
    h("div", { class: "riga" }, h("label", {}, "Tipo", tipoR), h("label", {}, "Valore", vR), h("label", {}, "Fonte", fR)),
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => ok(() => api("POST", base + "/contatti/" + c.id + "/recapiti", { tipo: tipoR.value, valore: vR.value, fonte: fR.value || null })) }, "Aggiungi")));
  // fonte e verifica
  const fe = h("input", { type: "text", value: m.fonte.fonte_editore || "", maxlength: 300 }), fl = h("input", { type: "text", value: m.fonte.fonte_licenza || "", maxlength: 300 }), fu = h("input", { type: "text", value: m.fonte.fonte_url || "", maxlength: 300 }), fd = h("input", { type: "date", value: m.fonte.fonte_data || "" });
  const vn = h("input", { type: "text", placeholder: "Nota (es. telefonato, risponde)", maxlength: 300 });
  const blocchiFonte = h("details", { class: "carta" }, h("summary", {}, "Fonte e verifica · " + (m.verificato_il ? "verificato il " + dataIt(m.verificato_il) : "mai verificato") + (m.fonte.fonte_editore ? " · " + m.fonte.fonte_editore : "")),
    h("div", { class: "riga" }, h("label", {}, "Editore della fonte", fe), h("label", {}, "Licenza", fl)), h("div", { class: "riga" }, h("label", {}, "Indirizzo della fonte", fu), h("label", {}, "Data della fonte", fd)),
    m.fonte.importato_il ? h("p", { class: "sotto" }, "Importato il " + dataIt(m.fonte.importato_il)) : null,
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => ok(() => api("PUT", base + "/contatti/" + c.id + "/fonte", { fonte_editore: fe.value, fonte_licenza: fl.value, fonte_url: fu.value, fonte_data: fd.value || null })) }, "Salva la fonte")),
    h("div", { class: "riga" }, h("label", {}, "Verifica", vn)), m.verifica_nota ? h("p", { class: "sotto" }, "Ultima nota: " + m.verifica_nota) : null,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => ok(() => api("POST", base + "/contatti/" + c.id + "/verifica", { nota: vn.value || null })) }, "Segna come verificato oggi")));
  // storico
  const st = h("div");
  const blocchiStorico = h("details", { class: "carta", ontoggle: async (e) => { if (!e.target.open || st.childNodes.length) return; try { const r = await api("GET", base + "/contatti/" + c.id + "/storico");
      st.replaceChildren(...(r.storico.length ? r.storico.map(x => h("div", { class: "sotto" }, new Date(x.quando).toLocaleString("it-IT") + " · " + (x.da || "sistema") + " · " + x.campo + (x.prima || x.dopo ? ": " + (x.prima || "—") + " → " + (x.dopo || "—") : "") + (x.fonte ? " · fonte: " + x.fonte : ""))) : [h("p", { class: "sotto" }, "Nessuna modifica registrata.")])); } catch (x) { err(x); } } },
    h("summary", {}, "Storico delle modifiche"), st);
  return [blocchiAttr, blocchiCat, blocchiRel, blocchiRec, blocchiFonte, blocchiStorico];
}

function carica_altro() { vai("contatto"); }

function campiPersonalizzati() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const [d, k] = await Promise.all([api("GET", "/gestione/crm/campi"), api("GET", "/gestione/crm/categorie")]);
      const tipo = h("input", { type: "text", list: "tipi-campi", placeholder: "Es. comune (vuoto = per tutti)", maxlength: 40 }), chiave = h("input", { type: "text", placeholder: "nome tecnico, es. abitanti", maxlength: 40 }),
        et = h("input", { type: "text", placeholder: "Etichetta, es. Abitanti", maxlength: 60 }), dato = h("select", {}, [["testo", "Testo"], ["numero", "Numero"], ["data", "Data"], ["si_no", "Sì / No"], ["scelta", "Scelta tra voci"]].map(([v, t]) => h("option", { value: v }, t))),
        scelte = h("input", { type: "text", placeholder: "Voci separate da virgola (solo per «scelta»)", maxlength: 500 }), nc = h("input", { type: "text", placeholder: "Nuova categoria", maxlength: 60 });
      const per = {}; d.campi.forEach(x => (per[x.tipo || ""] = per[x.tipo || ""] || []).push(x));
      riempi(corpo, [
        h("p", { class: "aiuto" }, "I campi personalizzati servono dove servono: «abitanti» per i comuni, «stelle» per gli alberghi. Nelle schede degli altri tipi quel campo non compare e resta vuoto. Il tipo è quello che scrivi nella scheda del contatto."),
        Object.keys(per).length ? Object.entries(per).map(([t, lista]) => h("div", { class: "carta" }, h("div", { class: "nome" }, t ? "Tipo: " + t : "Per tutti i tipi"),
          lista.map(x => h("div", { class: "sotto" }, x.etichetta + " (" + x.chiave + ", " + x.dato + (x.dato === "scelta" ? ": " + x.scelte.join(", ") : "") + ") ",
            h("button", { class: "s", onclick: async () => { if (!confirm("Eliminare il campo «" + x.etichetta + "»?")) return; try { await api("DELETE", "/gestione/crm/campi/" + x.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina"))))) : h("p", { class: "sotto" }, "Nessun campo personalizzato ancora."),
        h("datalist", { id: "tipi-campi" }, d.tipi_in_uso.map(t => h("option", { value: t }))),
        h("details", { class: "carta" }, h("summary", {}, "+ Nuovo campo"), h("div", { class: "riga" }, h("label", {}, "Per il tipo", tipo), h("label", {}, "Nome tecnico", chiave), h("label", {}, "Etichetta", et)),
          h("div", { class: "riga" }, h("label", {}, "Che dato è", dato), h("label", {}, "Voci", scelte)),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("POST", "/gestione/crm/campi", { tipo: tipo.value, chiave: chiave.value, etichetta: et.value, dato: dato.value, scelte: scelte.value.split(",").map(x => x.trim()).filter(Boolean) }); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea il campo"))),
        h("h3", {}, "Categorie"), h("p", { class: "sotto" }, k.categorie.map(x => x.nome + " (" + x.usate + ")").join(" · ")),
        h("div", { class: "riga" }, h("label", {}, "Nuova categoria", nc), h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/crm/categorie", { nome: nc.value }); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi"))), msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}
