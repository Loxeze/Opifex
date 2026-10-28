"use strict";
// CRM: contatti con filtri combinabili, segmenti salvati (liste intelligenti), esportazione CSV e nuova opportunità dalla bacheca.

const FILTRI_MENU = [["genere", "Persone / enti"], ["tipo", "Tipo"], ["regione", "Regione"], ["provincia", "Provincia"], ["settore", "Settore"], ["relazione", "Relazione"], ["categoria", "Categoria"], ["lista_id", "Lista"]];
const FILTRI_FLAG = [["con_email", "Ha l'email"], ["con_telefono", "Ha il telefono"], ["da_ricontattare", "Da ricontattare"], ["mai_contattati", "Mai contattati"], ["con_opportunita", "Con opportunità aperte"], ["senza_responsabile", "Senza responsabile"]];

function crmContatti() {
  const corpo = h("div"), msg = h("div"), risultati = h("div"), segmentiBox = h("div");
  let valori = null, pagina = 1, ultimo = null;
  const campi = {};
  const filtri = () => {
    const f = {};
    FILTRI_MENU.forEach(([k]) => { if (campi[k] && campi[k].value) f[k] = k === "lista_id" ? Number(campi[k].value) : campi[k].value; });
    FILTRI_FLAG.forEach(([k]) => { if (campi[k] && campi[k].checked) f[k] = true; });
    if (campi.q.value.trim().length >= 2) f.q = campi.q.value.trim();
    return f;
  };
  const imposta = (f) => {
    FILTRI_MENU.forEach(([k]) => { campi[k].value = f[k] !== undefined ? String(f[k]) : ""; });
    FILTRI_FLAG.forEach(([k]) => { campi[k].checked = !!f[k]; });
    campi.q.value = f.q || "";
  };
  const cerca = async (p) => {
    pagina = p || 1;
    try {
      const d = await api("POST", "/gestione/crm/contatti/cerca", { filtri: filtri(), pagina, per_pagina: 50 });
      ultimo = d; msg.replaceChildren();
      const pagine = Math.max(1, Math.ceil(d.totale / d.per_pagina));
      riempi(risultati, [h("p", { class: "sotto" }, d.totale.toLocaleString("it-IT") + " contatti" + (Object.keys(d.filtri).length ? " con questi filtri" : "") + (pagine > 1 ? " · pagina " + d.pagina + " di " + pagine : "")),
        d.contatti.length ? d.contatti.map(x => h("div", { class: "carta", style: "margin-bottom:8px;cursor:pointer", onclick: () => { stato.contattoAperto = x.id; vai("contatto"); } },
          h("div", { class: "nome" }, x.nome || x.ente || x.email || ("Contatto #" + x.id)),
          h("div", { class: "sotto" }, [x.nome && x.ente ? x.ente : "", x.email, x.tipo !== "altro" ? x.tipo : "", x.regione, x.provincia, "ultimo contatto: " + dataIt(x.ultimo_contatto), x.opp_aperte ? x.opp_aperte + " opportunità aperte" : ""].filter(Boolean).join(" · ")),
          x.prossimo_passo ? h("div", { class: "sotto" }, "➜ " + x.prossimo_passo + (x.prossimo_passo_il ? " (entro " + dataIt(x.prossimo_passo_il) + ")" : "")) : null)) : h("p", { class: "sotto" }, "Nessun contatto con questi filtri."),
        pagine > 1 ? h("div", { class: "azioni" }, h("button", { class: "s", disabled: d.pagina <= 1, onclick: () => cerca(d.pagina - 1) }, "← Precedente"), h("button", { class: "s", disabled: d.pagina >= pagine, onclick: () => cerca(d.pagina + 1) }, "Successiva →")) : null]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const caricaSegmenti = async () => {
    try {
      const d = await api("GET", "/gestione/crm/segmenti");
      riempi(segmentiBox, d.segmenti.length ? [h("div", { class: "sotto" }, "Segmenti salvati (si aggiornano da soli)"), h("div", { class: "azioni", style: "flex-wrap:wrap" }, d.segmenti.map(s => h("span", { class: "chip-segmento" },
        h("button", { class: "s", onclick: () => { imposta(s.filtri); cerca(1); } }, s.nome + " · " + s.contatti),
        h("button", { class: "s", title: "Elimina il segmento", "aria-label": "Elimina il segmento " + s.nome, onclick: async () => { if (!confirm("Eliminare il segmento «" + s.nome + "»? I contatti non vengono toccati.")) return; try { await api("DELETE", "/gestione/crm/segmenti/" + s.id); caricaSegmenti(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "×"))))] : null);
    } catch (e) { segmentiBox.replaceChildren(); }
  };
  const costruisci = async () => {
    try { valori = await api("GET", "/gestione/crm/filtri/valori"); } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); return; }
    campi.q = h("input", { type: "search", placeholder: "Cerca per nome, ente, email o telefono", maxlength: 100 });
    campi.q.addEventListener("keydown", (e) => { if (e.key === "Enter") cerca(1); });
    FILTRI_MENU.forEach(([k, etichetta]) => {
      const opz = k === "genere" ? [["persona", "Persone"], ["organizzazione", "Enti"]] : k === "lista_id" ? valori.liste.map(l => [l.id, l.nome]) : (valori[k] || []).map(v => [v, v]);
      campi[k] = h("select", { onchange: () => cerca(1) }, h("option", { value: "" }, etichetta + ": tutti"), opz.map(([v, t]) => h("option", { value: v }, t)));
    });
    FILTRI_FLAG.forEach(([k, etichetta]) => { campi[k] = h("input", { type: "checkbox", onchange: () => cerca(1) }); });
    const nome = h("input", { type: "text", maxlength: 80, placeholder: "Nome del segmento, es. Comuni toscani da ricontattare" });
    riempi(corpo, [
      segmentiBox,
      h("div", { class: "carta" }, h("label", {}, "Cerca", campi.q),
        h("div", { class: "griglia", style: "margin-top:8px" }, FILTRI_MENU.map(([k]) => campi[k])),
        h("div", { class: "azioni", style: "flex-wrap:wrap;margin-top:8px" }, FILTRI_FLAG.map(([k, e]) => h("label", { class: "casella" }, campi[k], " " + e))),
        h("div", { class: "azioni", style: "flex-wrap:wrap" },
          h("button", { class: "p", onclick: () => cerca(1) }, "Cerca"),
          h("button", { class: "s", onclick: () => { imposta({}); cerca(1); } }, "Azzera i filtri"),
          h("button", { class: "s", onclick: async () => {
            try {
              const r = await fetch("/gestione/crm/contatti/esporta", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token }, body: JSON.stringify({ filtri: filtri() }) });
              if (!r.ok) throw new Error(messaggioErrore(await r.json().catch(() => null)));
              const a = h("a", { href: URL.createObjectURL(await r.blob()), download: "contatti-crm.csv" }); document.body.append(a); a.click(); a.remove();
            } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Esporta in CSV")),
        h("div", { class: "riga", style: "margin-top:8px" }, h("label", {}, "Salva questi filtri come segmento", nome),
          h("button", { class: "s", style: "align-self:flex-end", onclick: async () => {
            try { await api("POST", "/gestione/crm/segmenti", { nome: nome.value, filtri: filtri() }); nome.value = ""; msg.replaceChildren(avviso("Segmento salvato.", "ok")); caricaSegmenti(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva segmento"))),
      msg, risultati,
      h("details", { class: "carta" }, h("summary", {}, "+ Nuovo contatto a mano"), nuovoContattoForm())]);
    caricaSegmenti(); cerca(1);
  };
  costruisci();
  return corpo;
}

function nuovoContattoForm() {
  const msg = h("div");
  const nome = h("input", { type: "text", maxlength: 200, placeholder: "Nome e cognome" }), ente = h("input", { type: "text", maxlength: 200, placeholder: "Ente / azienda" });
  const email = h("input", { type: "email", maxlength: 200 }), tel = h("input", { type: "text", maxlength: 60 }), note = h("textarea", { style: "min-height:56px", maxlength: 5000 });
  return h("div", {}, h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Ente", ente)), h("div", { class: "riga" }, h("label", {}, "Email", email), h("label", {}, "Telefono", tel)), h("label", {}, "Note", note), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      try { const r = await api("POST", "/gestione/crm/contatti", { nome: nome.value, ente: ente.value, email: email.value, telefono: tel.value, note: note.value }); stato.contattoAperto = r.id; vai("contatto"); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea e apri la scheda")));
}

// nuova opportunità direttamente dalla bacheca: si cerca il contatto e si compila il minimo
function nuovaOpportunitaDaBacheca(ricarica) {
  const msg = h("div"), trovati = h("div");
  let scelto = null;
  const q = h("input", { type: "search", maxlength: 100, placeholder: "Cerca il contatto (nome, ente, email)…" });
  const titolo = h("input", { type: "text", maxlength: 200, placeholder: "Es. Co-finanziamento Interreg" });
  const tipo = h("select", {}, Object.entries(TIPI_OPP).map(([k, t]) => h("option", { value: k }, t))), fase = h("select", {}, Object.entries(STATI_OPP).map(([k, t]) => h("option", { value: k }, t)));
  const valore = h("input", { type: "number", min: 0, step: 100, placeholder: "Valore €" }), scad = h("input", { type: "date" });
  const etichetta = h("p", { class: "sotto" }, "Nessun contatto scelto");
  const cerca = async () => {
    try {
      const d = await api("POST", "/gestione/crm/contatti/cerca", { filtri: { q: q.value.trim() }, per_pagina: 8 });
      riempi(trovati, d.contatti.map(x => h("div", { class: "sotto riga-clic", onclick: () => { scelto = x; etichetta.textContent = "Contatto: " + (x.nome || x.ente || x.email); trovati.replaceChildren(); } }, (x.nome || x.ente || x.email) + (x.nome && x.ente ? " · " + x.ente : ""))));
      if (!d.contatti.length) trovati.replaceChildren(h("p", { class: "sotto" }, "Nessun contatto trovato: crealo prima in Contatti."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") cerca(); });
  return h("details", { class: "carta" }, h("summary", {}, "+ Nuova opportunità"),
    h("label", {}, "Contatto", q), h("div", { class: "azioni" }, h("button", { class: "s", onclick: cerca }, "Cerca")), trovati, etichetta,
    h("label", {}, "Titolo", titolo), h("div", { class: "riga" }, h("label", {}, "Tipo", tipo), h("label", {}, "Fase", fase)), h("div", { class: "riga" }, h("label", {}, "Valore", valore), h("label", {}, "Scadenza", scad)), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      if (!scelto) { msg.replaceChildren(avviso("Cerca e scegli il contatto.", "avv")); return; }
      try { await api("POST", "/gestione/crm/contatti/" + scelto.id + "/opportunita", { titolo: titolo.value, tipo: tipo.value, stato: fase.value, valore_euro: valore.value ? Number(valore.value) : null, scadenza: scad.value || null }); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea opportunità")));
}
