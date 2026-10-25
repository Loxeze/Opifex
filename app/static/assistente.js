"use strict";
// Assistente prompt: dialogo per scrivere o migliorare il prompt di un agente. Il testo proposto si inserisce nel campo solo se lo scegli.

function assistentePrompt(campoPrompt, leggiScheda) {
  const storia = [];
  const dialogo = h("div", { class: "sotto" });
  const richiesta = h("textarea", { style: "min-height:70px", maxlength: 4000, placeholder: "Es. Scrivimi il prompt per un agente che cerca bandi per piccoli comuni e li passa al manager; oppure: rendi più chiaro cosa NON deve fare." });
  const msg = h("div");
  const proposta = h("textarea", { style: "min-height:140px;display:none", readonly: true });
  const usa = h("button", { class: "p", type: "button", style: "display:none", onclick: () => { campoPrompt.value = proposta.value; usa.style.display = "none"; msg.replaceChildren(avviso("Inserito nel campo «Cosa deve fare»: controlla e salva l'agente.", "ok")); } }, "Inserisci nel campo del prompt");
  const invia = h("button", { class: "s", type: "button", onclick: async (ev) => {
    const b = ev.currentTarget; const testo = richiesta.value.trim(); if (!testo) return;
    b.disabled = true; b.textContent = "Scrivo…"; msg.replaceChildren();
    try {
      const r = await api("POST", "/gestione/assistente-prompt", { richiesta: testo, scheda: { ...leggiScheda(), istruzioni: campoPrompt.value }, conversazione: storia });
      storia.push({ ruolo: "utente", testo }); storia.push({ ruolo: "assistente", testo: r.risposta + (r.prompt ? "\n[Prompt proposto inserito a parte]" : "") });
      dialogo.append(h("p", {}, h("strong", {}, "Tu: "), testo), h("p", { style: "white-space:pre-wrap" }, h("strong", {}, "Assistente: "), r.risposta));
      richiesta.value = "";
      if (r.prompt) { proposta.value = r.prompt; proposta.style.display = ""; usa.style.display = ""; }
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false; b.textContent = "Chiedi all'assistente";
  } }, "Chiedi all'assistente");
  return h("details", { class: "carta" }, h("summary", {}, "✨ Assistente prompt: scrivi o migliora il prompt con l'aiuto di Claude"),
    h("p", { class: "aiuto" }, "Descrivi cosa vuoi che faccia l'agente (o come migliorare il prompt che c'è). L'assistente vede la scheda dell'agente e l'elenco degli altri agenti, non i tuoi documenti né le chat."),
    dialogo, richiesta, invia, proposta, usa, msg);
}
