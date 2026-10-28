"use strict";
// CRM: cruscotto (numeri, imbuto di vendita, scadenze), opportunità a colonne trascinabili e importazione guidata dei contatti.

const eurCrm = (n) => (n || n === 0) ? Number(n).toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }) : "";
const CANALI_ICONA = { email: "✉️", telefono: "📞", incontro: "🤝", riunione: "👥", messaggio: "💬", social: "🌐", altro: "•" };

function crmCruscotto() {
  const corpo = h("div", { class: "crm-cruscotto" });
  const apri = (id) => () => { stato.contattoAperto = id; vai("contatto"); };
  const tessera = (titolo, valore, sotto, azione) => h("div", { class: "tessera" + (azione ? " cliccabile" : ""), onclick: azione || null },
    h("div", { class: "sotto" }, titolo), h("div", { class: "valore" }, valore), sotto ? h("div", { class: "sotto" }, sotto) : null);
  const elencoCarta = (titolo, righe, vuoto) => h("div", { class: "carta" }, h("div", { class: "nome" }, titolo), righe.length ? righe : h("p", { class: "sotto" }, vuoto));
  api("GET", "/gestione/crm/dashboard").then(d => {
    const o = d.opportunita, c = d.contatti;
    const massimo = Math.max(1, ...d.imbuto.map(f => f.n));
    const imbuto = h("div", { class: "carta" }, h("div", { class: "nome" }, "Imbuto di vendita"),
      h("p", { class: "aiuto" }, "Le opportunità per fase (le vinte sono quelle degli ultimi 90 giorni)."),
      d.imbuto.map(f => h("div", { class: "imbuto-riga" },
        h("div", { class: "imbuto-nome" }, STATI_OPP[f.stato]),
        h("div", { class: "imbuto-barra" }, h("div", { class: "imbuto-pieno stato-" + f.stato, style: "width:" + Math.max(f.n ? 4 : 0, Math.round(100 * f.n / massimo)) + "%" }, String(f.n))),
        h("div", { class: "sotto imbuto-dati" }, eurCrm(f.valore)))),
      d.per_tipo.length ? h("div", { class: "sotto", style: "margin-top:8px" }, "Aperte per tipo: " + d.per_tipo.map(t => (TIPI_OPP[t.tipo] || t.tipo) + " " + t.n + (t.valore ? " (" + eurCrm(t.valore) + ")" : "")).join(" · ")) : null);
    riempi(corpo, [
      h("div", { class: "tessere" },
        tessera("Contatti", c.totale.toLocaleString("it-IT"), c.persone + " persone · " + c.organizzazioni + " enti", () => { stato.crmTab = "schede"; disegna(); }),
        tessera("Nuovi (30 giorni)", String(c.nuovi_30g)),
        tessera("Da ricontattare", String(c.da_ricontattare), c.mai_contattati + " mai contattati", () => { stato.crmTab = "ricontattare"; disegna(); }),
        tessera("Opportunità aperte", String(o.aperte), eurCrm(o.valore_aperto), () => { stato.crmTab = "pipeline"; disegna(); }),
        tessera("Valore previsto", eurCrm(o.valore_pesato), "pesato sulla fase"),
        tessera("Vinte (90 giorni)", String(o.vinte_90g), o.valore_vinto_90g ? eurCrm(o.valore_vinto_90g) : ""),
        tessera("Tasso di vittoria", o.tasso_vittoria === null ? "—" : o.tasso_vittoria + "%", o.perse_90g + " perse")),
      imbuto,
      h("div", { class: "griglia" },
        elencoCarta("Opportunità in scadenza (14 giorni)", d.scadenze.map(s => h("div", { class: "sotto riga-clic", onclick: apri(s.contatto_id) },
          h("span", { style: "color:var(--testo)" }, s.titolo), " · " + s.contatto + " · entro " + dataIt(s.scadenza) + (s.valore ? " · " + eurCrm(s.valore) : ""))), "Nessuna scadenza imminente."),
        elencoCarta("Da ricontattare (7 giorni)", d.da_ricontattare.map(s => h("div", { class: "sotto riga-clic", onclick: apri(s.contatto_id) },
          h("span", { style: "color:var(--testo)" }, s.contatto), " · " + (s.passo || "ricontattare") + " · " + dataIt(s.data))), "Nessun ricontatto in programma."),
        elencoCarta("Attività recente", d.attivita.map(a => h("div", { class: "sotto riga-clic", onclick: apri(a.contatto_id) },
          (CANALI_ICONA[a.canale] || "•") + " ", h("span", { style: "color:var(--testo)" }, a.contatto), " · " + (a.oggetto || CANALI_CRM[a.canale]) + " · " + dataIt(a.quando))), "Nessuna interazione registrata."),
        d.regioni.length ? elencoCarta("Contatti per regione", d.regioni.map(r => h("div", { class: "sotto" }, r.valore + ": " + r.n)), "") : null,
        d.categorie.length ? elencoCarta("Contatti per categoria", d.categorie.map(r => h("div", { class: "sotto" }, r.valore + ": " + r.n)), "") : null)]);
  }).catch(e => corpo.replaceChildren(avviso(e.message, "no")));
  return corpo;
}

// ---- opportunità a colonne: si trascinano da una fase all'altra (oppure si cambia fase dal menu della scheda)
function crmBacheca() {
  const corpo = h("div"), msg = h("div");
  const sposta = async (id, nuovo) => {
    try { await api("PUT", "/gestione/crm/opportunita/" + id, { stato: nuovo }); carica(); }
    catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const carica = () => api("GET", "/gestione/crm/pipeline").then(d => {
    riempi(corpo, [nuovaOpportunitaDaBacheca(carica), h("p", { class: "aiuto" }, "Trascina le opportunità da una colonna all'altra per cambiare fase, oppure usa il menu su ogni scheda. Si creano dalla scheda di ogni contatto. Aperte e chiuse negli ultimi 60 giorni."), msg,
      h("div", { class: "bacheca" }, Object.keys(STATI_OPP).map(s => {
        const col = h("div", { class: "bacheca-col stato-" + s, ondragover: (e) => { e.preventDefault(); col.classList.add("sopra"); }, ondragleave: () => col.classList.remove("sopra"),
          ondrop: (e) => { e.preventDefault(); col.classList.remove("sopra"); const id = Number(e.dataTransfer.getData("text/plain")); if (id) sposta(id, s); } },
          h("div", { class: "nome" }, STATI_OPP[s] + " (" + d.colonne[s].length + ")"), d.totali[s] ? h("div", { class: "sotto" }, eurCrm(d.totali[s])) : null);
        d.colonne[s].forEach(o => {
          const scad = o.scadenza && o.scadenza < new Date().toISOString().slice(0, 10) && !["vinta", "persa"].includes(s);
          const menu = h("select", { class: "bacheca-menu", "aria-label": "Cambia fase", onchange: () => sposta(o.id, menu.value), onclick: (e) => e.stopPropagation() },
            Object.keys(STATI_OPP).map(x => h("option", { value: x, selected: x === s }, STATI_OPP[x])));
          col.append(h("div", { class: "bacheca-scheda", draggable: "true", ondragstart: (e) => e.dataTransfer.setData("text/plain", String(o.id)),
            onclick: () => { stato.contattoAperto = o.contatto_id; vai("contatto"); } },
            h("div", { style: "color:var(--testo)" }, o.titolo),
            h("div", { class: "sotto" }, [o.contatto, TIPI_OPP[o.tipo], eurCrm(o.valore_euro), o.progetto].filter(Boolean).join(" · ")),
            o.scadenza ? h("div", { class: "sotto", style: scad ? "color:var(--avv)" : "" }, (scad ? "scaduta il " : "entro ") + dataIt(o.scadenza)) : null,
            o.prossima_azione ? h("div", { class: "sotto" }, "➜ " + o.prossima_azione) : null, menu));
        });
        return col;
      }))]);
  }).catch(e => corpo.replaceChildren(avviso(e.message, "no")));
  carica();
  return corpo;
}

// ---- importazione guidata: file → anteprima e abbinamento colonne → controllo doppioni → report
function importazioneGuidata(chiudi) {
  const radice = h("div", { class: "carta crm-importa" }), msg = h("div");
  let file = null, listeDati = null, anteprima = null;
  const passo1 = async () => {
    try { listeDati = await api("GET", "/gestione/crm/liste"); } catch (e) { radice.replaceChildren(avviso(e.message, "no")); return; }
    const sel = h("select", {}, h("option", { value: "" }, "+ Nuova lista…"), listeDati.liste.map(l => h("option", { value: l.id }, l.nome + " (" + l.contatti + ")")));
    const nome = h("input", { type: "text", maxlength: 120, placeholder: "Nome della nuova lista, es. Musei della Toscana" });
    const natura = h("select", {}, h("option", { value: "pubblico" }, "Dati pubblici (enti, PA)"), h("option", { value: "personale" }, "Dati di persone (clienti, visitatori)"));
    const base = h("input", { type: "text", maxlength: 200, placeholder: "Solo per dati di persone: consenso, contratto, interesse legittimo…" });
    const nuova = h("div", {}, h("label", {}, "Nome", nome), h("label", {}, "Natura dei dati", natura), h("label", {}, "Base giuridica", base));
    sel.addEventListener("change", () => { nuova.style.display = sel.value ? "none" : ""; });
    const f = h("input", { type: "file", accept: ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    riempi(radice, [h("div", { class: "nome" }, "Importa contatti · 1 di 3 — scegli il file"),
      h("p", { class: "aiuto" }, "Excel (.xlsx) o CSV. Nel passaggio dopo vedi un'anteprima e decidi tu quali colonne diventano nome, email, telefono… Nulla viene salvato finché non confermi."),
      h("label", {}, "Dove li metto", sel), nuova, h("label", {}, "File", f), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (ev) => {
        if (!f.files.length) { msg.replaceChildren(avviso("Scegli un file Excel o CSV.", "avv")); return; }
        if (!sel.value && nome.value.trim().length < 2) { msg.replaceChildren(avviso("Dai un nome alla nuova lista.", "avv")); return; }
        const b = ev.currentTarget; b.disabled = true; msg.replaceChildren(avviso("Leggo il file…", "avv"));
        try {
          file = f.files[0];
          const fd = new FormData(); fd.append("file", file);
          anteprima = await api("POST", "/gestione/crm/importa/anteprima", fd);
          let lista = sel.value ? Number(sel.value) : null;
          passo2({ lista, nuova: lista ? null : { nome: nome.value.trim(), natura: natura.value, base_giuridica: base.value.trim() || null } });
        } catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Leggi il file"), h("button", { class: "s", onclick: chiudi }, "Annulla"))]);
  };
  const passo2 = (dest) => {
    const msg2 = h("div"), esito = h("div");
    const selezioni = {};
    anteprima.campi.forEach(c => {
      const s = h("select", {}, h("option", { value: "" }, "— non importare —"), anteprima.intestazioni.map((x, i) => h("option", { value: i }, (x || "(senza titolo)") + " · colonna " + (i + 1))));
      if (anteprima.mappa[c.chiave] !== undefined) s.value = String(anteprima.mappa[c.chiave]);
      selezioni[c.chiave] = s;
    });
    const mappa = () => { const m = {}; Object.entries(selezioni).forEach(([k, s]) => { if (s.value !== "") m[k] = Number(s.value); }); return m; };
    const modo = h("select", {}, h("option", { value: "salta" }, "Salta i doppioni (consigliato)"), h("option", { value: "aggiorna" }, "Completa i contatti già presenti con i dati nuovi"), h("option", { value: "importa" }, "Importa comunque anche i doppioni"));
    const dove = h("select", {}, h("option", { value: "tutte" }, "in tutte le liste"), h("option", { value: "lista" }, "solo nella lista scelta"));
    const tabella = h("div", { style: "overflow:auto;max-height:200px" }, h("table", { class: "anteprima" },
      h("tr", {}, anteprima.intestazioni.map(x => h("th", {}, x || "—"))), anteprima.esempio.map(r => h("tr", {}, anteprima.intestazioni.map((_, i) => h("td", {}, r[i] || ""))))));
    const lancia = async (simula, btn) => {
      const m = mappa();
      if (!m.nome && !m.ente && !m.email) { msg2.replaceChildren(avviso("Abbina almeno una colonna a Nome, Ente o Email.", "avv")); return; }
      btn.disabled = true; msg2.replaceChildren(avviso(simula ? "Controllo in corso…" : "Importazione in corso…", "avv"));
      try {
        let lid = dest.lista;
        if (!lid && !simula) { const r = await api("POST", "/gestione/crm/liste", dest.nuova); lid = r.id; dest.lista = lid; }
        if (!lid) lid = (listeDati.liste[0] || {}).id;
        if (!lid) { msg2.replaceChildren(avviso("Per il controllo serve almeno una lista: importa direttamente, i doppioni saranno comunque saltati.", "avv")); btn.disabled = false; return; }
        const fd = new FormData(); fd.append("file", file); fd.append("mappa", JSON.stringify(m)); fd.append("doppioni", modo.value); fd.append("controlla_in", dove.value);
        fd.append("simula", simula ? "true" : "false"); fd.append("foglio", String(anteprima.foglio));
        const r = await api("POST", "/gestione/crm/liste/" + lid + "/importa", fd);
        msg2.replaceChildren();
        if (simula) { esito.replaceChildren(avviso("Controllo fatto, nulla è stato salvato: " + r.importati + " nuovi contatti, " + r.doppioni + " doppioni" + (r.aggiornati ? ", " + r.aggiornati + " da completare" : "") + ", " + r.righe_vuote + " righe vuote.", "ok")); btn.disabled = false; }
        else passo3(r);
      } catch (e) { msg2.replaceChildren(avviso(e.message, "no")); btn.disabled = false; }
    };
    const bCtrl = h("button", { class: "s", onclick: (ev) => lancia(true, ev.currentTarget) }, "Controlla senza salvare");
    const bImp = h("button", { class: "p", onclick: (ev) => lancia(false, ev.currentTarget) }, "Importa " + anteprima.righe_totali.toLocaleString("it-IT") + " righe");
    riempi(radice, [h("div", { class: "nome" }, "Importa contatti · 2 di 3 — abbina le colonne"),
      h("p", { class: "sotto" }, anteprima.origine + " · " + anteprima.righe_totali.toLocaleString("it-IT") + " righe" + (anteprima.riconosciute ? "" : " · non ho riconosciuto le intestazioni: abbina tu le colonne")),
      anteprima.fogli.length > 1 ? h("p", { class: "sotto" }, "Fogli nel file: " + anteprima.fogli.join(", ") + ". Uso quello indicato sopra.") : null,
      tabella, h("div", { class: "griglia", style: "margin-top:10px" }, anteprima.campi.map(c => h("label", {}, c.etichetta, selezioni[c.chiave]))),
      h("div", { class: "riga" }, h("label", {}, "Se un contatto esiste già (stessa email)", modo), h("label", {}, "Cerca i doppioni", dove)),
      esito, msg2, h("div", { class: "azioni" }, bCtrl, bImp, h("button", { class: "s", onclick: chiudi }, "Annulla"))]);
  };
  const passo3 = (r) => {
    riempi(radice, [h("div", { class: "nome" }, "Importa contatti · 3 di 3 — fatto"),
      avviso(r.importati + " contatti importati" + (r.aggiornati ? ", " + r.aggiornati + " completati" : "") + ", " + r.doppioni + " doppioni saltati, " + r.righe_vuote + " righe vuote.", "ok"),
      r.colonne_ignorate && r.colonne_ignorate.length ? avviso("Colonne non importate: " + r.colonne_ignorate.join(", "), "avv") : null,
      r.saltate && r.saltate.length ? h("details", { class: "carta" }, h("summary", {}, "Righe saltate (prime " + r.saltate.length + ")"), r.saltate.map(x => h("div", { class: "sotto" }, "riga " + x.riga + " · " + x.motivo + (x.valore ? " · " + x.valore : "")))) : null,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => { chiudi(); stato.crmTab = "schede"; disegna(); } }, "Vai ai contatti"), h("button", { class: "s", onclick: () => { file = null; anteprima = null; passo1(); } }, "Importa un altro file"))]);
  };
  passo1();
  return radice;
}
