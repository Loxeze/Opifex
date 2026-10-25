"use strict";
// Iniziative: opportunita' aperte dai manager. Le sopra-soglia aspettano qui il via libera. Testi inseriti come testo.

const STATI_INIZ = { da_approvare: ["Da approvare", "avv"], in_corso: ["In corso", "ok"], conclusa: ["Sintesi pronta", "ok"], rifiutata: ["Rifiutata", "no"] };

function vistaIniziative() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/iniziative");
      riempi(corpo, [schedaSoglie(d, carica), d.iniziative.length ? d.iniziative.map(i => cartaIniziativa(i, carica)) : h("p", { class: "sotto" }, "Nessuna iniziativa ancora. Le apre un manager quando trova un'opportunità che coinvolge più agenti.")]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Iniziative"), corpo];
}

function schedaSoglie(d, ricarica) {
  const msg = h("div");
  const soglia = h("input", { type: "number", min: 1000, step: 1000, value: d.soglia_token });
  const rami = h("input", { type: "number", min: 1, max: 12, value: d.max_rami });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Quando il manager può partire da solo"),
    h("p", { class: "aiuto" }, "Un manager apre da solo un'iniziativa se la stima di token è entro la soglia e i rami non superano il massimo. Sopra la soglia compare qui «Da approvare» e non parte nulla senza il tuo OK."),
    h("label", {}, "Soglia di token stimati", soglia), h("label", {}, "Massimo rami per iniziativa", rami), msg,
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
      try { await api("PUT", "/gestione/iniziative/impostazioni", { soglia_token: Number(soglia.value), max_rami: Number(rami.value) }); msg.replaceChildren(avviso("Salvato.", "ok")); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
}

function cartaIniziativa(i, ricarica) {
  const [t, cl] = STATI_INIZ[i.stato] || [i.stato, ""];
  const msg = h("div");
  const decidi = async (azione) => { msg.replaceChildren(); try { await api("POST", "/gestione/iniziative/" + i.id + "/decisione", { azione }); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
  return h("div", { class: "carta" }, h("div", { class: "nome" }, i.titolo), h("span", { class: "etichetta " + cl }, t),
    h("div", { class: "sotto" }, "Aperta da " + (i.aperta_da || "?") + " · " + i.rami_fatti + "/" + i.rami + " task fatte" + (i.budget_token ? " · stima " + i.budget_token.toLocaleString("it-IT") + " token" : "")),
    i.descrizione ? h("p", {}, i.descrizione) : null,
    (i.dettaglio_rami || []).map(r => h("div", { class: "sotto" }, "• " + r.titolo + " — " + (r.agente || "?") + " [" + r.stato.replace("_", " ") + "]")),
    i.sintesi ? h("div", { class: "carta" }, h("div", { class: "nome" }, "Sintesi del manager"), h("p", { style: "white-space:pre-wrap" }, i.sintesi)) : null, msg,
    i.stato === "da_approvare" ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidi("approva") }, "Approva e avvia"), h("button", { class: "s", onclick: () => decidi("rifiuta") }, "Rifiuta")) : null);
}
