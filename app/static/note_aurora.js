"use strict";
// Note di Aurora: dettate o scritte, Aurora le trasforma in documento e propone a quale manager affidarle; l'affidamento parte solo col tuo comando.

const STATO_NOTA = { bozza: "Bozza", proposta: "Proposta di Aurora", affidata: "Affidata", archiviata: "Archiviata" };

function vistaNoteAurora() {
  const corpo = h("div"), msg = h("div");
  const t = h("textarea", { style: "min-height:110px", placeholder: "Detta o scrivi qui la tua nota: Aurora la scrive in ordine e propone a quale manager affidarla." });
  const dettaglio = async (id, box) => {
    const n = await api("GET", "/note-aurora/" + id);
    const analisi = h("textarea", { style: "min-height:60px" }); analisi.value = n.analisi || "";
    const man = h("input", { maxlength: 80, placeholder: "Nome del manager" }); man.value = n.manager || "";
    const agisci = async (fn) => { try { const r = await fn(); msg.replaceChildren(avviso(r || "Fatto.", "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
    riempi(box, [
      h("div", { class: "risposta", style: "white-space:pre-wrap" }, n.documento || n.testo),
      n.punti ? [h("h4", {}, "Punti d'azione"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, n.punti)] : null,
      n.stato !== "affidata" ? [
        n.motivo ? h("p", { class: "aiuto" }, "Perché: " + n.motivo) : null,
        h("div", { class: "riga" }, h("label", {}, "Manager", man)), h("label", {}, "Analisi richiesta", analisi),
        h("div", { class: "azioni" },
          h("button", { class: "s", onclick: () => agisci(async () => { await api("POST", "/note-aurora/" + id + "/suggerisci"); return "Aurora sta rivedendo la nota: ricarica fra qualche istante."; }) }, "Chiedi ad Aurora"),
          h("button", { class: "p", onclick: () => agisci(async () => (await api("POST", "/note-aurora/" + id + "/affida", { manager: man.value.trim() || null, analisi: analisi.value.trim() || null })).sintesi) }, "Affida al manager"),
          h("button", { class: "r", onclick: () => agisci(async () => { await api("POST", "/note-aurora/" + id + "/archivia"); return "Archiviata."; }) }, "Archivia"))]
        : [h("p", { class: "aiuto" }, "Affidata a " + n.manager + " · " + (n.esito_stato === "elaborata" ? "esaminata" : n.esito_stato || "")),
           n.esito ? h("div", { class: "risposta", style: "white-space:pre-wrap" }, n.esito) : null,
           (n.commenti || []).map(c => h("div", { class: "risposta", style: "white-space:pre-wrap" }, h("b", {}, (c.agente || "Lorenzo") + ": "), c.testo))]]);
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/note-aurora");
      riempi(corpo, d.note.length ? d.note.map(n => {
        const box = h("div", { style: "display:none" });
        return h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, n.titolo),
          h("div", { class: "sotto" }, [STATO_NOTA[n.stato], n.manager ? "→ " + n.manager : "", new Date(n.creata_il).toLocaleDateString("it-IT")].filter(Boolean).join(" · ")),
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { if (box.style.display === "none") { await dettaglio(n.id, box); box.style.display = ""; } else box.style.display = "none"; } }, "Apri")), box);
      }) : h("p", { class: "sotto" }, "Nessuna nota."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Note di Aurora"),
    h("p", { class: "aiuto" }, "Detta una nota: Aurora la scrive come documento, con i punti d'azione, e ti propone il manager a cui affidarla per l'analisi. Non parte nulla finché non premi «Affida»: il manager poi spezzetta il lavoro tra i suoi operativi."),
    t, h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      if (!t.value.trim()) return;
      try { const r = await api("POST", "/note-aurora", { testo: t.value.trim() }); t.value = ""; msg.replaceChildren(avviso(r.sintesi, "ok")); setTimeout(carica, 1500); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva e passa ad Aurora")), msg, corpo);
}
