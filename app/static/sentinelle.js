"use strict";
// Sentinelle: coda di proposte da approvare e casi di prova per agente (confronto prima/dopo).

const NOME_SENT = { qualita: "Qualità", costi: "Costi", fonti: "Fonti", evoluzione: "Evoluzione", usabilita: "Usabilità" };

function vistaSentinelle() {
  const coda = h("div"), prove = h("div"), msg = h("div");
  const caricaCoda = async () => {
    try {
      const el = await api("GET", "/gestione/sentinelle/proposte");
      riempi(coda, el.length ? el.map(p => {
        const decidi = async (approva) => { try { const r = await api("POST", "/gestione/sentinelle/proposte/" + p.id + "/decisione", { approva }); msg.replaceChildren(avviso(r.esito, "ok")); caricaCoda(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
        return h("div", { class: "carta" }, h("div", { class: "nome" }, h("span", { class: "etichetta" }, NOME_SENT[p.sentinella]), " " + p.titolo),
          h("div", { class: "sotto" }, p.motivazione),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidi(true) }, "Approva"), h("button", { class: "s", onclick: () => decidi(false) }, "Respingi")));
      }) : h("p", { class: "sotto" }, "Nessuna proposta in attesa."));
    } catch (e) { coda.replaceChildren(avviso(e.message, "no")); }
  };
  const bScan = h("button", { class: "s", onclick: async () => { bScan.disabled = true; try { const r = await api("POST", "/gestione/sentinelle/scansiona"); msg.replaceChildren(avviso("Scansione fatta: " + Object.entries(r).map(([k, v]) => NOME_SENT[k] + " " + v).join(", "), "ok")); caricaCoda(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } bScan.disabled = false; } }, "Cerca nuove proposte ora");
  const scelta = h("select", {}, (stato.agenti || []).filter(a => a.attivo).map(a => h("option", { value: a.id }, a.nome + " — " + a.ruolo)));
  let timer = null;
  const caricaProve = async () => {
    clearTimeout(timer);
    const id = scelta.value; if (!id) return;
    try {
      const r = await api("GET", "/gestione/prove/" + id);
      const inCorso = r.lotti.find(l => l.stato === "in_corso");
      const c = r.confronto;
      riempi(prove, [
        h("div", { class: "azioni" },
          h("button", { class: "s", onclick: async () => { try { const x = await api("POST", "/gestione/prove/" + id + "/genera", { quanti: 10 }); msg.replaceChildren(avviso(x.creati + " casi creati. Controllali e disattiva quelli che non servono.", "ok")); caricaProve(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Genera 10 casi"),
          h("button", { class: "p", disabled: !!inCorso || !r.casi.some(k => k.attivo), onclick: async () => { const et = prompt("Etichetta della prova (es. «prima della modifica»)", "") ; if (et === null) return; try { await api("POST", "/gestione/prove/" + id + "/lancia", { etichetta: et }); caricaProve(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, inCorso ? "Prova in corso " + inCorso.fatti + "/" + inCorso.totale : "Lancia la prova")),
        c.differenza !== null ? avviso("Ultime due prove: " + c.lotti[1].media + " → " + c.lotti[0].media + " (" + (c.differenza >= 0 ? "+" : "") + c.differenza + ")" + (c.cambiato ? " · istruzioni o modello cambiati nel frattempo" : " · nessuna modifica rilevata"), c.differenza < -0.5 ? "avv" : "ok")
          : h("p", { class: "sotto" }, "Servono due prove concluse per il confronto prima/dopo."),
        ...c.casi.filter(x => x.prima !== x.dopo).map(x => h("div", { class: "sotto" }, (x.prima ?? "–") + " → " + (x.dopo ?? "–") + " · " + x.richiesta.slice(0, 90))),
        h("h4", {}, "Casi (" + r.casi.filter(k => k.attivo).length + " attivi)"),
        ...r.casi.map(k => h("div", { class: "carta" }, h("div", { class: "nome" }, k.richiesta), h("div", { class: "sotto" }, "Criteri: " + k.criteri),
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { await api("PUT", "/gestione/prove/casi/" + k.id + "?attivo=" + !k.attivo); caricaProve(); } }, k.attivo ? "Disattiva" : "Riattiva"),
            h("button", { class: "s", onclick: async () => { if (confirm("Eliminare il caso?")) { await api("DELETE", "/gestione/prove/casi/" + k.id); caricaProve(); } } }, "Elimina"))))]);
      if (inCorso) timer = setTimeout(caricaProve, 5000);
    } catch (e) { prove.replaceChildren(avviso(e.message, "no")); }
  };
  scelta.addEventListener("change", caricaProve);
  caricaCoda(); caricaProve();
  return [h("h2", {}, "Sentinelle e casi di prova"),
    h("p", { class: "aiuto" }, "Le sentinelle (Qualità, Costi, Fonti, Evoluzione, Usabilità: l'Osservatore dell'uso guarda solo quali pagine apri e dove compaiono errori, mai cosa scrivi) cercano ogni giorno cose da migliorare e te le propongono qui: non cambiano nulla senza il tuo via libera. I casi di prova sono richieste tipiche per ogni agente: lanciali prima e dopo una modifica per vedere se è migliorato. Ogni prova consuma qualche token."),
    msg, h("h3", {}, "Proposte in attesa"), h("div", { class: "azioni" }, bScan), coda,
    h("h3", {}, "Casi di prova"), h("label", {}, "Agente", scelta), prove];
}
