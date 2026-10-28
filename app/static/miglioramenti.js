"use strict";
// Miglioramento degli agenti: Padre Casati propone istruzioni migliori per chi riceve molti «giù»; qui si leggono e si approvano.

function vistaMiglioramenti() {
  const corpo = h("div"), msg = h("div"), cand = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/miglioramenti");
      riempi(cand, d.candidati.length ? [h("h3", {}, "Agenti con molti «giù» (almeno " + d.soglia + " in 30 giorni)"),
        d.candidati.map(c => h("div", { class: "riga", style: "align-items:center;justify-content:space-between" }, h("span", {}, c.nome + " · " + c.giu + " giù"),
          h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/miglioramenti/analizza", { agente_id: c.id }); msg.replaceChildren(avviso("Proposta pronta.", "ok")); await carica(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Chiedi a Padre Casati")))] : null);
      riempi(corpo, d.proposte.length ? d.proposte.map(p => {
        const decidi = async (azione) => { try { const r = await api("POST", "/gestione/miglioramenti/" + p.id + "/decisione", { azione }); msg.replaceChildren(avviso(r.sintesi, "ok")); await carica(); }
          catch (e) { msg.replaceChildren(avviso(e.message, "no")); await carica(); } };
        return h("div", { class: "carta", style: "margin-bottom:10px" }, h("div", { class: "nome" }, p.agente),
          h("div", { class: "sotto" }, new Date(p.creata_il).toLocaleDateString("it-IT")),
          h("div", { class: "risposta", style: "white-space:pre-wrap" }, p.sintesi),
          h("details", {}, h("summary", {}, "Perché (voti e note)"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, p.evidenze || "")),
          h("details", {}, h("summary", {}, "Nuove istruzioni complete"), h("div", { class: "risposta", style: "white-space:pre-wrap;max-height:320px;overflow:auto" }, p.proposta)),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidi("approva") }, "Applica"), h("button", { class: "s", onclick: () => decidi("respingi") }, "Respingi")));
      }) : h("p", { class: "sotto" }, "Nessuna proposta in attesa."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Miglioramento degli agenti"),
    h("p", { class: "aiuto" }, "Quando un agente riceve molti «giù», Padre Casati legge i motivi e propone istruzioni migliori. Non cambia nulla finché non le applichi; le vecchie restano nello storico."),
    msg, cand, corpo);
}
