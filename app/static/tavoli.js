"use strict";
// Tavoli di lavoro: riunioni fra agenti con moderatore e verbale.

function vistaTavoli() {
  const corpo = h("div"), msg = h("div");
  const titolo = h("input", { maxlength: 200, placeholder: "Titolo del tavolo" });
  const odg = h("textarea", { style: "min-height:100px", placeholder: "Ordine del giorno: di che cosa devono discutere e che cosa ti serve in uscita." });
  const part = h("input", { placeholder: "Partecipanti separati da virgola, es. Marco, Dario, Elena" });
  const mod = h("input", { placeholder: "Moderatore (se vuoto, Aurora)" });
  const turni = h("select", {}, [1, 2, 3].map(n => h("option", { value: n }, n + (n === 1 ? " giro" : " giri")))); turni.value = "2";
  const dettaglio = async (id, box) => {
    const t = await api("GET", "/gestione/tavoli/" + id);
    riempi(box, [t.verbale ? [h("h4", {}, "Verbale (" + t.moderatore + ")"), h("div", { class: "risposta", style: "white-space:pre-wrap" }, t.verbale)] : h("p", { class: "sotto" }, t.stato === "errore" ? "Errore: " + (t.errore || "") : "Il verbale non è ancora pronto."),
      h("details", {}, h("summary", {}, "Interventi (" + t.interventi.length + ")"), t.interventi.map(i => h("div", { class: "risposta", style: "white-space:pre-wrap;margin-bottom:6px" }, h("b", {}, "Giro " + i.turno + " · " + i.nome + ": "), i.testo)))]);
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/tavoli");
      riempi(corpo, d.tavoli.length ? d.tavoli.map(t => {
        const box = h("div", { style: "display:none" });
        return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, t.titolo),
          h("div", { class: "sotto" }, [{ in_corso: "In corso", conclusa: "Concluso", errore: "Errore" }[t.stato], t.partecipanti, t.interventi + " interventi"].join(" · ")),
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { if (box.style.display === "none") { await dettaglio(t.id, box); box.style.display = ""; } else box.style.display = "none"; } }, "Apri")), box);
      }) : h("p", { class: "sotto" }, "Nessun tavolo ancora."));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Tavoli di lavoro"),
    h("p", { class: "aiuto" }, "Convoca più agenti su un tema: intervengono in ordine, ciascuno dalla propria specializzazione, poi il moderatore scrive il verbale con sintesi, decisioni, disaccordi, azioni e cosa manca. Le azioni non partono da sole."),
    titolo, odg, part, h("div", { class: "riga" }, h("label", {}, "Moderatore", mod), h("label", {}, "Giri", turni)),
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      try { const r = await api("POST", "/gestione/tavoli", { titolo: titolo.value.trim(), ordine_del_giorno: odg.value.trim(), partecipanti: part.value.split(",").map(x => x.trim()).filter(Boolean), moderatore: mod.value.trim() || null, turni: Number(turni.value) });
        msg.replaceChildren(avviso(r.sintesi, "ok")); titolo.value = odg.value = part.value = ""; await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Convoca il tavolo")),
    msg, h("div", { class: "azioni" }, h("button", { class: "s", onclick: carica }, "Aggiorna l'elenco")), corpo);
}
