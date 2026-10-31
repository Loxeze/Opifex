"use strict";
// Miglioramento degli agenti: Padre Casati propone istruzioni migliori per chi riceve molti «giù»; qui si leggono e si approvano.

function provaMiglioramento(p) {
  const r = p.prova || {};
  if (p.prova_stato === "in_corso") return h("p", { class: "aiuto" }, "Prova in corso: ricarica fra qualche minuto.");
  if (p.prova_stato === "errore") return h("p", { class: "aiuto" }, "Prova non riuscita: " + (r.errore || ""));
  const d = r.differenza;
  return h("div", { class: "risposta" }, h("b", {}, "Prova sui casi: media " + r.media_prima + " → " + r.media_dopo + (d !== null && d !== undefined ? " (" + (d >= 0 ? "+" : "") + d + ")" : "")),
    (r.casi || []).map(c => h("div", { class: "sotto" }, c.prima + " → " + c.dopo + " · " + c.richiesta.slice(0, 120))));
}

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
          p.prova_stato ? provaMiglioramento(p) : null,
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/gestione/miglioramenti/" + p.id + "/prova"); msg.replaceChildren(avviso(r.sintesi, "ok")); await carica(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Prova prima di applicare"), h("button", { class: "p", onclick: () => decidi("approva") }, "Applica"), h("button", { class: "s", onclick: () => decidi("respingi") }, "Respingi")));
      }) : h("p", { class: "sotto" }, "Nessuna proposta in attesa."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Miglioramento degli agenti"),
    h("p", { class: "aiuto" }, "Quando un agente riceve molti «giù», Padre Casati legge i motivi e propone istruzioni migliori. Non cambia nulla finché non le applichi; le vecchie restano nello storico."),
    msg, cand, corpo, h("h3", {}, "Prove di qualità (dopo ogni aggiornamento)"), proveRegressione());
}

// Compiti di esempio con criteri, rieseguiti quando vuoi: il punteggio per versione mostra se la qualità sale o scende.
function proveRegressione() {
  const box = h("div", { class: "carta" }), msg = h("div");
  const mostra = async () => {
    try {
      const d = await api("GET", "/gestione/prove");
      const nome = h("input", { type: "text", maxlength: 80, placeholder: "Nome della prova" });
      const ag = h("select", {}, d.agenti.map(a => h("option", { value: a.id }, a.nome)));
      const comp = h("textarea", { rows: 3, placeholder: "Il compito da dare all'agente" });
      const cri = h("textarea", { rows: 3, placeholder: "Un criterio per riga: «Cita la fonte dei dati», «Chiude con i prossimi passi»…" });
      riempi(box, [h("p", { class: "aiuto" }, "Ogni prova fa lavorare davvero l'agente (costa token) e controlla la risposta sui criteri. Rilanciala dopo un aggiornamento per vedere l'andamento."),
        d.prove.map(p => h("div", { class: "carta", style: "margin:8px 0" }, h("div", { class: "nome" }, p.nome + " — " + (p.agente || "")),
          h("div", { class: "sotto" }, "Andamento (dal più recente): " + (p.esiti.length ? p.esiti.map(e => "v" + e.versione + " " + Math.round(e.punteggio) + "%" + (e.errore ? " (errore)" : "")).join(" · ") : "mai eseguita")),
          h("div", { class: "azioni" },
            h("button", { class: "p", type: "button", onclick: async (e) => { e.currentTarget.disabled = true; msg.replaceChildren(h("p", { class: "sotto" }, "Prova in corso…"));
              try { const r = await api("POST", "/gestione/prove/" + p.id + "/esegui"); msg.replaceChildren(avviso("Punteggio " + Math.round(r.punteggio) + "% (giudice: " + r.giudice + ")" + (r.errore ? " — " + r.errore : ""), r.errore ? "no" : "ok")); mostra(); }
              catch (x) { msg.replaceChildren(avviso(x.message, "no")); e.currentTarget.disabled = false; } } }, "Esegui ora"),
            h("button", { class: "r", type: "button", onclick: async () => { await api("DELETE", "/gestione/prove/" + p.id); mostra(); } }, "Elimina")))),
        h("div", { class: "nome" }, "Nuova prova"), nome, ag, comp, cri,
        h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: async () => { try { await api("POST", "/gestione/prove", { nome: nome.value, agente_id: Number(ag.value), compito: comp.value, criteri: cri.value }); mostra(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Aggiungi la prova")),
        msg]);
    } catch (x) { box.replaceChildren(avviso(x.message, "no")); }
  };
  mostra();
  return box;
}
