"use strict";
// Contatti (CRM): liste, importazione CSV, riepilogo aggregato e ricerca. I dati personali sono cifrati sul server; gli agenti vedono solo conteggi.

function vistaCrm() {
  const TAB = [["cruscotto", "Cruscotto"], ["schede", "Contatti"], ["ricontattare", "Da ricontattare"], ["pipeline", "Opportunità"], ["campi", "Campi e categorie"], ["liste", "Liste"]];
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
