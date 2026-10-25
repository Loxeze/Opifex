// Salute degli agenti: prova tutti gli agenti accesi con una domanda breve e mostra chi risponde.
function vistaSalute() {
  const esito = h("div"); const msg = h("div");
  const ETI = { ok: ["ok", "Risponde"], vuota: ["avv", "Risposta vuota"], errore: ["no", "Errore"], bloccato: ["avv", "Bloccato"], spento: ["", "Spento"] };
  const b = h("button", { class: "p", onclick: async () => {
    b.disabled = true; b.textContent = "Provo gli agenti…"; msg.replaceChildren(); esito.replaceChildren();
    try {
      const r = await api("POST", "/gestione/salute-agenti");
      const c = r.conteggio;
      msg.replaceChildren(avviso(c.ok + " rispondono · " + c.vuota + " vuoti · " + c.errore + " con errore · " + c.bloccato + " bloccati · " + c.spento + " spenti",
        c.vuota + c.errore + c.bloccato === 0 ? "ok" : "avv"));
      esito.replaceChildren(...r.agenti.map(a => h("div", { class: "carta" },
        h("div", { class: "nome" }, a.nome + " ", h("span", { class: "etichetta " + ETI[a.stato][0] }, ETI[a.stato][1])),
        h("div", { class: "sotto" }, [a.divisione || "Sistema", a.ruolo, a.modello].filter(Boolean).join(" · ") + (a.secondi != null ? " · " + a.secondi + " s · " + a.token + " token" : "")),
        a.anteprima ? h("div", { class: "sotto" }, "«" + a.anteprima + "»") : null,
        a.errore ? h("div", { class: "sotto" }, a.errore) : null,
        a.dettagli ? h("div", { class: "sotto" }, "Dettagli: " + JSON.stringify(a.dettagli)) : null)));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false; b.textContent = "Prova di nuovo";
  } }, "Prova tutti gli agenti");
  return [h("h2", {}, "Salute degli agenti"),
    h("p", { class: "aiuto" }, "Manda a ogni agente acceso una domanda breve e mostra chi risponde, chi risponde vuoto e chi è bloccato (budget, garanzie, sospensione). Ci vuole qualche minuto e costa qualche migliaio di token in tutto."),
    h("div", { class: "azioni" }, b), msg, esito];
}
