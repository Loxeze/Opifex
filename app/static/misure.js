"use strict";
// Consumi: dove vanno i token, per chi, per quale motivo, con indicazioni per risparmiare.

function vistaMisure() {
  const corpo = h("div"), msg = h("div");
  const periodo = h("select", {}, [["1", "Ultime 24 ore"], ["7", "Ultimi 7 giorni"], ["30", "Ultimi 30 giorni"], ["90", "Ultimi 90 giorni"]].map(([v, t]) => h("option", { value: v, selected: v === "7" }, t)));
  const usd = (x) => euro(x);
  const num = (x) => Number(x).toLocaleString("it-IT");
  const tab = (teste, righe) => h("div", { class: "tabscorri" }, h("table", { class: "tabella" }, h("thead", {}, h("tr", {}, teste.map(t => h("th", {}, t)))), h("tbody", {}, righe.map(r => h("tr", {}, r.map(c => h("td", {}, c)))))));
  const barra = (quota) => h("div", { class: "barra" }, h("div", { style: "width:" + Math.min(100, quota) + "%;height:8px;background:var(--accento,#3b6fd4);border-radius:4px" }));
  const carica = async () => {
    corpo.replaceChildren(h("p", { class: "sotto" }, "Calcolo…"));
    try {
      const r = await api("GET", "/gestione/misure?giorni=" + periodo.value);
      const t = r.totali;
      if (!t.chiamate) { corpo.replaceChildren(h("p", { class: "sotto" }, r.suggerimenti[0].testo)); return; }
      const blocchi = [
        h("div", { class: "griglia-numeri" },
          [["Spesa", usd(t.costo)], ["Risposte", num(t.chiamate)], ["Token in ingresso", num(t.token_input)], ["Token in uscita", num(t.token_output)],
           ["Passi medi per risposta", t.passi_medi], ["Secondi medi", t.secondi_medi]].map(([k, v]) => h("div", { class: "carta" }, h("div", { class: "sotto" }, k), h("div", { class: "nome" }, String(v))))),
        h("h3", {}, "Dove si può risparmiare"),
        ...(r.suggerimenti.length ? r.suggerimenti.map(s => h("div", { class: "carta" }, h("div", { class: "nome" }, s.titolo + (s.risparmio ? " — circa " + usd(s.risparmio) + " risparmiabili" : "")), h("div", { class: "sotto" }, s.testo)))
          : [h("p", { class: "sotto" }, "Nessuna anomalia evidente in questo periodo.")]),
        h("h3", {}, "Che cosa mandiamo al modello, in media, a ogni risposta"),
        h("p", { class: "sotto" }, "Stima in token (3,5 caratteri per token). Le istruzioni e gli strumenti si ripetono identici a ogni risposta."),
        tab(["Parte", "Token", "Quota", ""], r.composizione.map(c => [c.voce, num(c.token), c.quota + "%", barra(c.quota)])),
        h("h3", {}, "Per motivo"),
        tab(["Origine", "Risposte", "Spesa", "Token in medi", "Token out medi", "Passi"], r.per_origine.map(o => [o.origine, num(o.chiamate), usd(o.costo), num(o.token_input_medi), num(o.token_output_medi), o.passi_medi])),
        h("h3", {}, "Per agente (i 15 più costosi)"),
        tab(["Agente", "Modello", "Risposte", "Spesa", "Token in medi", "Strumenti", "Passi", "Istruzioni (tk)"], r.per_agente.map(a => [a.nome, a.modello || "", num(a.chiamate), usd(a.costo), num(a.token_input_medi), a.strumenti_medi, a.passi_medi, num(Math.round(a.car_istruzioni / 3.5))])),
        h("h3", {}, "Per modello"),
        tab(["Modello", "Risposte", "Spesa", "Token in", "Token out"], r.per_modello.map(m => [m.modello || "", num(m.chiamate), usd(m.costo), num(m.token_input), num(m.token_output)])),
        h("h3", {}, "Le 10 risposte più costose"),
        tab(["Quando", "Agente", "Motivo", "Token in/out", "Passi", "Spesa"], r.piu_costose.map(c => [c.quando.replace("T", " "), c.agente, c.origine, num(c.token_input) + " / " + num(c.token_output), c.passi, usd(c.costo)])),
        h("h3", {}, "Spesa per giorno"),
        tab(["Giorno", "Risposte", "Spesa"], r.per_giorno.map(g => [g.giorno, num(g.chiamate), usd(g.costo)])),
      ];
      corpo.replaceChildren(...blocchi);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  periodo.onchange = carica;
  carica();
  return [h("h2", {}, "Consumi: dove vanno i token"),
    h("p", { class: "sotto" }, "Ogni risposta degli agenti viene misurata: quanti token, quanti passaggi con gli strumenti, da che cosa è composto ciò che si manda al modello. Le misure partono da questa versione e si riempiono man mano che gli agenti lavorano."),
    h("div", { class: "azioni" }, periodo), msg, corpo];
}
