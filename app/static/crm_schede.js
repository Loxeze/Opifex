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
          h("div", { class: "riga" }, h("label", {}, "Nome", f.nome), h("label", {}, "Ente", f.ente)), h("div", { class: "riga" }, h("label", {}, "Email", f.email), h("label", {}, "Telefono", f.telefono)), h("label", {}, "Note", f.note),
          h("div", { class: "riga" }, h("label", {}, "Prossimo passo", passo), h("label", {}, "Entro il", passoIl), h("label", {}, "Responsabile", resp)),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("PUT", "/gestione/crm/contatti/" + c.id, { nome: f.nome.value, ente: f.ente.value, email: f.email.value, telefono: f.telefono.value, note: f.note.value,
              prossimo_passo: passo.value || null, prossimo_passo_il: passoIl.value || null, responsabile_utente_id: resp.value ? Number(resp.value) : null }); msg.replaceChildren(avviso("Salvato.", "ok")); await carica(); } catch (e) { err(e); } } }, "Salva la scheda"),
            h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare il contatto con tutta la sua storia?")) return; try { await api("DELETE", "/gestione/crm/contatti/" + c.id); vai("crm"); } catch (e) { err(e); } } }, "Elimina"))),
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
