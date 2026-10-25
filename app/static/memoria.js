"use strict";
// Memoria di lavoro: proposte da approvare (nella Chat) e archivio completo (Impostazioni > Memoria di lavoro).

const TIPO_MEM = { decisione: "Decisione", fatto: "Fatto", preferenza: "Preferenza", lezione: "Lezione", sintesi: "Sintesi" };
const FASCIA_MEM = { pubblico: "Pubblico", interno: "Interno", riservato: "Riservato" };

function ambitoMem(v) {
  return [v.divisione, v.azienda, v.progetto].filter(Boolean).join(" · ") || "Generale";
}

function schedaMemoria(v, ricarica, msg) {
  const testo = h("textarea", { style: "min-height:64px", maxlength: 1200 }); testo.value = v.testo;
  const decidi = async (azione) => {
    try { await api("POST", "/memoria/" + v.id + "/decisione", { azione, testo: azione === "approva" && testo.value.trim() !== v.testo ? testo.value.trim() : null }); await ricarica(); }
    catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const origine = v.proposta_da_agente ? "proposta da " + v.proposta_da_agente : v.proposta_da_utente ? "inserita da " + v.proposta_da_utente : "";
  return h("div", { class: "carta", style: "margin-bottom:8px" },
    h("div", { class: "nome" }, (TIPO_MEM[v.tipo] || v.tipo) + " · " + ambitoMem(v)),
    h("div", { class: "sotto" }, [new Date(v.creata_il).toLocaleDateString("it-IT"), origine, v.fonte, FASCIA_MEM[v.fascia_dati]].filter(Boolean).join(" · ")),
    v.stato === "proposta" && v.puo_approvare ? [testo, h("div", { class: "azioni" },
      h("button", { class: "p", onclick: () => decidi("approva") }, "Approva"), h("button", { class: "s", onclick: () => decidi("scarta") }, "Scarta"))]
      : h("div", { class: "risposta" }, v.testo));
}

// pannello compatto per la pagina Chat: solo le proposte in attesa
function pannelloMemoria() {
  const box = h("div", { class: "carta", style: "margin-bottom:14px" });
  const msg = h("div");
  let firma = null;
  const carica = async (forza) => {
    let d;
    try { d = await api("GET", "/memoria?stato=proposta"); } catch (e) { return; }
    const f = d.voci.map(v => v.id).join(",");
    if (!forza && (f === firma || [...box.querySelectorAll("textarea")].some(t => t.value !== t.defaultValue))) return;
    firma = f;
    riempi(box, [
      h("div", { class: "riga", style: "align-items:center;justify-content:space-between" },
        h("h3", { style: "margin:0" }, d.voci.length ? "Memoria da approvare (" + d.voci.length + ")" : "Nessuna voce di memoria da approvare"),
        h("button", { class: "s", onclick: () => { stato.sezione = "memoria"; vai("impostazioni", "memoria"); } }, "Apri la memoria")),
      d.voci.length ? h("p", { class: "aiuto" }, "Decisioni e fatti che gli agenti ricorderanno in futuro: approvale, correggile o scartale.") : null,
      d.voci.slice(0, 5).map(v => schedaMemoria(v, () => carica(true), msg)),
      d.voci.length > 5 ? h("p", { class: "sotto" }, "…e altre " + (d.voci.length - 5) + ": le trovi in Impostazioni > Memoria di lavoro.") : null, msg]);
  };
  carica(true);
  const t = setInterval(() => { if (!document.body.contains(box)) { clearInterval(t); return; } carica(false); }, 15000);
  return box;
}

function vistaMemoria() {
  const corpo = h("div"), msg = h("div");
  let filtro = "proposta";
  const sel = h("select", {}, [["proposta", "Da approvare"], ["approvata", "Approvate"], ["superata", "Superate"], ["scartata", "Scartate"], ["tutte", "Tutte"]].map(([v, n]) => h("option", { value: v }, n)));
  const q = h("input", { type: "search", maxlength: 100, placeholder: "Cerca nel testo…" });
  const nuova = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/memoria?stato=" + filtro + "&q=" + encodeURIComponent(q.value.trim()));
      riempi(corpo, d.voci.length ? d.voci.map(v => {
        const s = schedaMemoria(v, carica, msg);
        if (v.puo_approvare && v.stato !== "proposta") s.append(h("div", { class: "azioni" },
          h("button", { class: "s", onclick: async () => { const t = prompt("Correggi il testo", v.testo); if (t === null || !t.trim()) return;
            try { await api("PUT", "/memoria/" + v.id, { testo: t.trim() }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Modifica"),
          h("button", { class: "r", onclick: async () => { if (!confirm("Cancellare questa voce?")) return;
            try { await api("DELETE", "/memoria/" + v.id); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Cancella")));
        return s;
      }) : h("p", { class: "sotto" }, "Nessuna voce."));
      if (!nuova.dataset.pronto) {
        nuova.dataset.pronto = "1";
        const t = h("textarea", { style: "min-height:64px", maxlength: 1200, placeholder: "Es. Per il Castello di Montarrenti non partecipiamo ai bandi sotto i 20.000 euro." });
        const tipo = h("select", {}, d.tipi.filter(x => x !== "sintesi").map(x => h("option", { value: x }, TIPO_MEM[x])));
        const fa = h("select", {}, Object.entries(FASCIA_MEM).map(([v, n]) => h("option", { value: v }, n))); fa.value = "interno";
        const di = h("select", {}, h("option", { value: "" }, "Generale"), d.opzioni.divisioni.map(x => h("option", { value: x.id }, x.nome)));
        const az = h("select", {}, h("option", { value: "" }, "Tutte le aziende"), d.opzioni.aziende.map(x => h("option", { value: x.id }, x.nome)));
        const pr = h("select", {}, h("option", { value: "" }, "Nessun progetto"), d.opzioni.progetti.map(x => h("option", { value: x.id }, x.nome)));
        const m2 = h("div");
        nuova.append(h("h3", {}, "Aggiungi una voce"),
          h("p", { class: "aiuto" }, "Una sola informazione, breve. Niente password o chiavi. Gli agenti dell'ambito scelto la ritroveranno quando serve."), t,
          h("div", { class: "riga" }, h("label", {}, "Tipo", tipo), h("label", {}, "Dipartimento", di), h("label", {}, "Azienda", az)),
          h("div", { class: "riga" }, h("label", {}, "Progetto", pr), h("label", {}, "Riservatezza", fa)), m2,
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { await api("POST", "/memoria", { testo: t.value.trim(), tipo: tipo.value, fascia_dati: fa.value, divisione_id: di.value ? Number(di.value) : null,
              azienda_id: az.value ? Number(az.value) : null, progetto_id: pr.value ? Number(pr.value) : null });
              t.value = ""; m2.replaceChildren(avviso("Registrata.", "ok")); await carica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Registra")));
      }
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  sel.addEventListener("change", () => { filtro = sel.value; carica(); });
  q.addEventListener("input", () => { clearTimeout(q._t); q._t = setTimeout(carica, 300); });
  carica();
  return h("div", {}, h("h2", {}, "Memoria di lavoro"),
    h("p", { class: "aiuto" }, "Quello che gli agenti ricordano: decisioni, fatti, preferenze e lezioni. Le voci nascono come proposte (dalle tue risposte agli agenti, dalle approvazioni dei percorsi, dai suggerimenti degli agenti e dalle sintesi settimanali) e valgono solo dopo l'approvazione. Ogni agente riceve soltanto le voci del suo ambito e solo se la riservatezza lo consente."),
    h("div", { class: "riga" }, sel, q), msg, corpo, nuova);
}
