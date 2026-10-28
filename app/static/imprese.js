"use strict";
// Schede d'impresa: i fatti stabili di ogni attività, sempre presenti negli agenti di quell'impresa. Le proposte degli agenti si approvano qui.

function vistaImprese() {
  const corpo = h("div"), msg = h("div"), prop = h("div");
  const scheda = async (az, box) => {
    const d = await api("GET", "/gestione/imprese/" + az.id);
    riempi(box, Object.entries(d.scheda).map(([campo, v]) => {
      const t = h("textarea", { style: "min-height:70px", maxlength: 8000 }); t.value = v.testo;
      return h("div", { style: "margin-bottom:10px" }, h("label", {}, v.etichetta, t),
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
          try { await api("PUT", "/gestione/imprese/" + az.id + "/" + campo, { testo: t.value }); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
          v.aggiornato_da ? h("span", { class: "sotto" }, " Ultima modifica: " + v.aggiornato_da) : null));
    }));
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/imprese");
      riempi(corpo, d.imprese.map(az => {
        const box = h("div", { style: "display:none" });
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, az.nome),
          h("div", { class: "sotto" }, az.compilati + " campi su " + d.totale_campi + " compilati" + (az.proposte ? " · " + az.proposte + " proposte degli agenti" : "")),
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { if (box.style.display === "none") { await scheda(az, box); box.style.display = ""; } else box.style.display = "none"; } }, "Apri la scheda")), box);
      }));
      const p = await api("GET", "/gestione/imprese/proposte");
      riempi(prop, p.proposte.length ? [h("h3", {}, "Proposte degli agenti (" + p.proposte.length + ")"), p.proposte.map(x => {
        const dec = async (azione) => { try { const r = await api("POST", "/gestione/imprese/proposte/" + x.id, { azione }); msg.replaceChildren(avviso(r.sintesi, "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, x.impresa + " · " + p.etichette[x.campo]),
          h("div", { class: "sotto" }, (x.agente || "Un agente") + (x.motivo ? " — " + x.motivo : "")),
          x.attuale ? h("details", {}, h("summary", {}, "Testo attuale"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, x.attuale)) : null,
          h("div", { class: "risposta", style: "white-space:pre-wrap" }, x.testo),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => dec("approva") }, "Approva"), h("button", { class: "s", onclick: () => dec("respingi") }, "Respingi")));
      })] : null);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Schede d'impresa"),
    h("p", { class: "aiuto" }, "Per ogni tua attività i fatti stabili — chi siamo, offerta, clienti, tono, regole, numeri, persone, partner, obiettivi. Gli agenti di quell'impresa li hanno sempre presenti; possono solo proporre modifiche, che approvi tu."),
    msg, prop, corpo);
}
