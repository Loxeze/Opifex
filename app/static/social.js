"use strict";
// Social: collegamento a Buffer e coda dei post preparati dagli agenti, da approvare prima della pubblicazione.
// Tutti i testi arrivano dall'API e vengono inseriti come testo, mai come HTML.

const STATI_POST = { da_approvare: ["Da approvare", "avv"], inviato: ["Inviato a Buffer", "ok"], rifiutato: ["Rifiutato", "no"], errore: ["Errore", "no"] };
const quandoS = (t) => t ? new Date(t).toLocaleString("it-IT", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "alla prima occasione libera in coda";
const perInput = (t) => { const d = new Date(t); const p = (n) => String(n).padStart(2, "0"); return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes()); };

function vistaSocial() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const [bf, lista] = await Promise.all([api("GET", "/gestione/social/buffer"), api("GET", "/gestione/social/post")]);
      riempi(corpo, [schedaBuffer(bf, carica), h("h3", {}, "Post preparati dagli agenti"), listaPost(lista, carica)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  const riepilogo = h("div", { class: "bt-plancia", style: "margin-bottom:18px" });
  riassuntoSocial(riepilogo);
  return [h("h2", {}, "Social"), riepilogo, corpo];
}

function boxCanali(ricarica) {
  const box = h("div"); const msg = h("div");
  (async () => {
    try {
      const d = await api("GET", "/gestione/social/canali");
      riempi(box, [h("h4", {}, "A chi serve ogni canale"),
        h("p", { class: "aiuto" }, "Assegna ogni canale alle aziende e ai progetti che lo usano: gli agenti vedono e usano solo i canali del loro ambito. Un canale senza assegnazioni resta libero per tutti gli agenti social."),
        d.canali.map(c => {
          const az = d.aziende.map(a => { const x = h("input", { type: "checkbox" }); x.checked = c.aziende.includes(a.id); return [a, x]; });
          const pr = d.progetti.map(a => { const x = h("input", { type: "checkbox" }); x.checked = c.progetti.includes(a.id); return [a, x]; });
          const m2 = h("div");
          return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, c.name + " · " + c.service),
            h("div", { class: "sotto" }, "Aziende"), h("div", { class: "spunte" }, az.map(([a, x]) => h("label", { class: "spunta" }, x, a.nome))),
            h("div", { class: "sotto" }, "Progetti"), h("div", { class: "spunte" }, pr.map(([a, x]) => h("label", { class: "spunta" }, x, a.nome))), m2,
            h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
              try { await api("PUT", "/gestione/social/canali/" + encodeURIComponent(c.id), { aziende: az.filter(([, x]) => x.checked).map(([a]) => a.id), progetti: pr.filter(([, x]) => x.checked).map(([a]) => a.id) });
                m2.replaceChildren(avviso("Salvato", "ok")); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
        }), msg]);
    } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
  })();
  return box;
}

function schedaBuffer(bf, ricarica) {
  const msg = h("div");
  if (bf.collegato) {
    return h("div", { class: "carta" }, h("div", { class: "nome" }, "Buffer collegato"),
      bf.errore ? avviso(bf.errore, "no") : null,
      bf.canali.length ? boxCanali(ricarica)
        : h("p", { class: "aiuto" }, "Nessun canale: collegali dentro Buffer (Instagram, Facebook, LinkedIn, TikTok…)."),
      h("p", { class: "aiuto" }, "Per far preparare post a un agente, accendi «Può preparare post per i social» nella sua scheda. I post restano qui in attesa del tuo OK."),
      msg, h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
        if (!confirm("Scollegare Buffer?")) return;
        try { await api("DELETE", "/gestione/social/buffer"); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Scollega Buffer")));
  }
  const chiave = h("input", { type: "password", autocomplete: "off", placeholder: "Chiave API di Buffer" });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Collega Buffer"),
    h("p", { class: "aiuto" }, "Non basta il login a Buffer: serve una chiave API. In Buffer clicca l'icona del profilo in basso a sinistra → «API» (oppure vai su publish.buffer.com/settings/api) → scheda «Personal Access» → «+ New Key» (la crea il proprietario dell'organizzazione). Incollala qui sotto: viene cifrata e non verrà più mostrata. Gli agenti non pubblicano mai da soli."),
    h("label", {}, "Chiave API", chiave), msg,
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (ev) => {
      const b = ev.currentTarget; b.disabled = true; msg.replaceChildren();
      try { await api("PUT", "/gestione/social/buffer", { chiave: chiave.value.trim() }); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); b.disabled = false; } } }, "Collega e verifica")));
}

function listaPost(lista, ricarica) {
  if (!lista.length) return h("p", { class: "sotto" }, "Nessun post ancora.");
  return lista.map(p => {
    const [t, cl] = STATI_POST[p.stato] || [p.stato, ""];
    const msg = h("div");
    const testo = h("textarea", { style: "min-height:110px" }); testo.value = p.testo;
    const quando = h("input", { type: "datetime-local" }); if (p.programmato_il) quando.value = perInput(p.programmato_il);
    const modificabile = p.stato === "da_approvare" || p.stato === "errore";
    const azione = async (az) => {
      msg.replaceChildren();
      try {
        if (az === "approva") {
          await api("PUT", "/gestione/social/post/" + p.id, quando.value ? { testo: testo.value, programmato_il: new Date(quando.value).toISOString() } : { testo: testo.value, senza_orario: true });
        }
        await api("POST", "/gestione/social/post/" + p.id + "/decisione", { azione: az });
        ricarica();
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    };
    return h("div", { class: "carta", style: "margin-top:12px" },
      h("div", { class: "nome" }, p.canale_nome + " · " + p.servizio),
      h("div", { class: "sotto" }, (p.agente ? "Preparato da " + p.agente + " · " : "") + "pubblicazione: " + quandoS(p.programmato_il)),
      h("div", {}, h("span", { class: "etichetta " + cl }, t)),
      modificabile ? [h("label", {}, "Testo", testo), h("label", {}, "Data e ora (vuoto = prima occasione libera in coda di Buffer)", quando)]
        : h("div", { class: "risposta", style: "margin-top:8px" }, p.testo),
      (p.media || []).length ? h("div", { class: "sotto" }, "File: " + p.media.map(m => m.tipo + " " + m.url).join(", ")) : null,
      p.errore ? avviso(p.errore, "no") : null, msg,
      modificabile ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => azione("rifiuta") }, "Rifiuta"),
        h("button", { class: "p", onclick: () => azione("approva") }, "Approva e programma")) : null);
  });
}

// Riepilogo mese su mese: mese in corso fino a oggi contro lo stesso numero di giorni del mese scorso.
async function riassuntoSocial(box) {
  try {
    const d = await api("GET", "/gestione/plancia/social");
    const v = (a, b) => { const x = variazione(a, b); return x ? h("span", { class: "bt-var" }, " " + x.testo) : null; };
    const T = d.totali;
    const kpi = (tit, n, prima, nota) => h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, tit), h("div", { class: "bt-num" }, String(n)), h("div", { class: "bt-sotto" }, "scorso mese: " + prima, v(n, prima)), nota ? h("div", { class: "bt-sotto" }, nota) : null);
    const mx = Math.max(1, ...d.canali.map(c => Math.max(c.creati, c.creati_prima)));
    const righe = d.canali.length ? d.canali.map(c => h("div", { class: "bt-confronto" }, h("div", { class: "bt-bl" }, c.canale),
      h("div", {}, h("div", { class: "bt-bt" }, h("i", { style: "width:" + (100 * c.creati / mx) + "%" })), h("div", { class: "bt-bt prima" }, h("i", { style: "width:" + (100 * c.creati_prima / mx) + "%" }))),
      h("div", { class: "bt-bv" }, c.creati + " / " + c.creati_prima))) : h("p", { class: "bt-sotto" }, "Ancora nessun post: appena gli agenti ne preparano, il confronto compare qui.");
    const prof = d.profili.length ? d.profili.map(p => h("tr", {}, h("td", {}, p.nome, h("span", { class: "bt-sotto" }, " · " + p.piattaforma)), h("td", {}, p.seguaci == null ? "—" : nIt(p.seguaci)),
      h("td", {}, p.seguaci != null && p.seguaci_prima != null ? (p.seguaci - p.seguaci_prima >= 0 ? "+" : "") + nIt(p.seguaci - p.seguaci_prima) : "—"), h("td", {}, p.visualizzazioni == null ? "—" : compatto(p.visualizzazioni)))) : null;
    riempi(box, [h("section", { class: "bt-griglia bt-kpis tre" }, kpi("Post preparati", T.creati, T.creati_prima), kpi("Post inviati", T.inviati, T.inviati_prima), h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, "Da approvare"), h("div", { class: "bt-num" }, String(d.da_approvare)), h("div", { class: "bt-sotto" }, "in attesa del tuo OK"))),
      h("section", { class: "bt-griglia" }, h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "Post per canale")), righe,
        h("div", { class: "bt-leg2" }, h("i", { style: "background:#1E8466" }), h("span", {}, "mese in corso"), h("i", { style: "background:#CFE3DA" }), h("span", {}, "stesso periodo del mese scorso"))),
        h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "I tuoi profili")), prof ? h("table", { class: "bt-tab" }, h("thead", {}, h("tr", {}, h("th", {}, "Profilo"), h("th", {}, "Seguaci"), h("th", {}, "4 sett."), h("th", {}, "Visualizzazioni"))), h("tbody", {}, prof))
          : h("p", { class: "bt-sotto" }, "Nessun profilo tuo monitorato. Aggiungilo in Impostazioni, Profili social monitorati, e qui vedrai seguaci e visualizzazioni a confronto.")),
      ),
      h("p", { class: "bt-nota" }, "Mi piace e commenti per singolo post non sono ancora disponibili: Buffer non li restituisce. Qui contano i post preparati dagli agenti e i dati dei profili monitorati.")]);
  } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
}
