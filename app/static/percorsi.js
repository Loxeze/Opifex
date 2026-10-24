"use strict";
// Percorsi di lavoro a fasi: avvio di un lavoro per un agente con fasi, risultati fase per fase, decisioni.
// Tutti i testi arrivano dall'API e vengono inseriti come testo, mai come HTML.

const STATI_PERCORSO = {
  in_elaborazione: ["L'agente sta lavorando…", "avv"], in_attesa: ["Attende la tua decisione", "ok"],
  completato: ["Completato", ""], annullato: ["Annullato", "no"], errore: ["Errore", "no"],
};
const quandoP = (t) => t ? new Date(t).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

function vistaPercorsi() {
  const corpo = h("div");
  const aperto = stato.percorsoAperto || null;
  const carica = async () => {
    try {
      if (aperto) {
        const p = await api("GET", "/percorsi/" + aperto);
        riempi(corpo, dettaglioPercorso(p));
        if (p.stato === "in_elaborazione") stato.timer = setInterval(async () => {
          try {
            const q = await api("GET", "/percorsi/" + aperto);
            if (q.stato !== "in_elaborazione") { clearInterval(stato.timer); stato.timer = null; riempi(corpo, dettaglioPercorso(q)); }
          } catch (e) { /* riprova al prossimo giro */ }
        }, 4000);
      } else {
        const [lista, opz] = await Promise.all([api("GET", "/percorsi"), api("GET", "/percorsi/opzioni")]);
        riempi(corpo, [nuovoPercorso(opz), listaPercorsi(lista)]);
        if (lista.some(x => x.stato === "in_elaborazione")) stato.timer = setInterval(async () => {
          try {
            const l2 = await api("GET", "/percorsi");
            if (!l2.some(x => x.stato === "in_elaborazione")) { clearInterval(stato.timer); stato.timer = null; if (stato.vista === "percorsi" && !stato.percorsoAperto) disegna(); }
          } catch (e) { /* ignora */ }
        }, 4000);
      }
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Percorsi di lavoro"), corpo];
}

function listaPercorsi(lista) {
  if (!lista.length) return h("p", { class: "sotto" }, "Nessun percorso ancora.");
  return [h("h3", {}, "I percorsi"), lista.map(p => {
    const [testo, cl] = STATI_PERCORSO[p.stato] || [p.stato, ""];
    return h("div", { class: "carta agente", style: "margin-top:10px", tabindex: 0, role: "button",
        onclick: () => { stato.percorsoAperto = p.id; disegna(); }, onkeydown: (e) => { if (e.key === "Enter") { stato.percorsoAperto = p.id; disegna(); } } },
      h("div", { class: "nome" }, p.titolo),
      h("div", { class: "sotto" }, p.agente + (p.progetto ? " · " + p.progetto : "") + " · fase " + p.fase_corrente + " di " + p.n_fasi + " · " + quandoP(p.aggiornato_il)),
      h("span", { class: "etichetta " + cl }, testo));
  })];
}

function nuovoPercorso(opz) {
  if (!opz.agenti.length) return avviso("Nessun agente ha fasi di lavoro. Aggiungile dalla scheda dell'agente (sezione «Fasi di lavoro»): così potrai avviare qui un lavoro da svolgere a tappe.", "avv");
  const ag = h("select", {}, opz.agenti.map(a => h("option", { value: a.id }, a.nome + " — " + a.n_fasi + " fasi")));
  const titolo = h("input", { type: "text", maxlength: 150, placeholder: "Es. Bando Borghi 2026 per Renovatio" });
  const brief = h("textarea", { style: "min-height:120px", placeholder: "Cosa dovrà ottenere, per quale azienda, link o riferimenti del bando, vincoli, scadenze…" });
  const fascia = h("select", {}, Object.entries(ETICHETTA_FASCIA).map(([v, t]) => h("option", { value: v }, t))); fascia.value = "interno";
  const prog = h("select", {}, h("option", { value: "" }, "Nessun progetto"), opz.progetti.map(x => h("option", { value: x.id }, x.nome)));
  const msg = h("div");
  const btn = h("button", { class: "p" }, "Avvia il percorso");
  btn.addEventListener("click", async () => {
    msg.replaceChildren(); btn.disabled = true;
    try {
      const r = await api("POST", "/percorsi", { agente_id: Number(ag.value), titolo: titolo.value.trim(), brief: brief.value.trim(), fascia_dati: fascia.value, progetto_id: prog.value ? Number(prog.value) : null });
      stato.percorsoAperto = r.id; disegna();
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); btn.disabled = false; }
  });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Nuovo percorso"),
    h("div", { class: "riga" }, h("label", {}, "Agente", ag), h("label", {}, "Progetto", prog), h("label", {}, "Tipo di dati", fascia)),
    h("label", {}, "Titolo", titolo), h("label", {}, "Cosa deve fare", brief), msg, h("div", { class: "azioni" }, btn));
}

function dettaglioPercorso(p) {
  const [testoStato, cl] = STATI_PERCORSO[p.stato] || [p.stato, ""];
  const msg = h("div");
  const nota = h("textarea", { style: "min-height:90px", placeholder: "Le tue indicazioni: quale proposta scegliere, cosa cambiare, cosa approfondire…" });
  const decidi = async (azione) => {
    msg.replaceChildren();
    if (azione === "annulla" && !confirm("Annullare il percorso?")) return;
    try { await api("POST", "/percorsi/" + p.id + "/decisione", { azione, nota: nota.value.trim() }); disegna(); }
    catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const tappe = h("div", { class: "sotto" }, p.fasi.map((f, i) => {
    const n = i + 1;
    const fatta = p.esiti.some(e => e.posizione === n && e.decisione === "approvata") || p.stato === "completato" && n <= p.fase_corrente;
    return h("span", { class: "etichetta " + (fatta ? "ok" : n === p.fase_corrente && p.stato !== "completato" ? "avv" : "") }, n + ". " + f.titolo);
  }));
  const ultimo = p.esiti.length ? p.esiti[p.esiti.length - 1] : null;
  return [
    h("div", { class: "azioni", style: "justify-content:flex-start" }, h("button", { class: "s", onclick: () => { stato.percorsoAperto = null; disegna(); } }, "← Tutti i percorsi")),
    h("div", { class: "carta" },
      h("div", { class: "nome" }, p.titolo),
      h("div", { class: "sotto" }, p.agente + (p.progetto ? " · " + p.progetto : "") + " · dati " + p.fascia_dati + " · avviato " + quandoP(p.creato_il)),
      h("div", {}, h("span", { class: "etichetta " + cl }, testoStato)), tappe,
      h("div", { class: "sotto", style: "margin-top:10px" }, "Lavoro richiesto"), h("div", { class: "risposta" }, p.brief),
      p.errore ? avviso(p.errore, "no") : null,
      p.stato === "errore" ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidi("riprova") }, "Riprova la fase")) : null),
    p.stato === "in_elaborazione" ? avviso("L'agente sta svolgendo la fase " + p.fase_corrente + " («" + p.fasi[p.fase_corrente - 1].titolo + "»). Puoi lasciare la pagina: ti avviso quando è pronta.", "avv") : null,
    p.esiti.slice().reverse().map(e => h("div", { class: "carta", style: "margin-top:12px" },
      h("div", { class: "nome" }, "Fase " + e.posizione + ": " + (p.fasi[e.posizione - 1]?.titolo || "") + (e.tentativo > 1 ? " (versione " + e.tentativo + ")" : "")),
      h("div", { class: "sotto" }, quandoP(e.creato_il) + (e.decisione ? " · " + (e.decisione === "approvata" ? "approvata" : "modifiche richieste") + (e.deciso_da ? " da " + e.deciso_da : "") : " · in attesa di decisione")),
      h("div", { class: "risposta", style: "margin-top:8px" }, e.testo),
      e.parere_superiore ? [h("div", { class: "sotto", style: "margin-top:12px" }, "Parere del superiore"), h("div", { class: "risposta" }, e.parere_superiore)] : null,
      e.nota ? [h("div", { class: "sotto", style: "margin-top:12px" }, "Le tue indicazioni"), h("div", { class: "risposta" }, e.nota)] : null)),
    p.stato === "in_attesa" && ultimo ? h("div", { class: "carta", style: "margin-top:12px;border-color:var(--ok)" },
      h("div", { class: "nome" }, "La tua decisione sulla fase " + p.fase_corrente),
      h("label", {}, "Indicazioni (obbligatorie se chiedi modifiche; se approvi, scrivi quale strada scegliere)", nota), msg,
      h("div", { class: "azioni" },
        h("button", { class: "s", onclick: () => decidi("annulla") }, "Annulla il percorso"),
        h("button", { class: "s", onclick: () => decidi("modifiche") }, "Chiedi modifiche"),
        h("button", { class: "p", onclick: () => decidi("approva") }, p.fase_corrente >= p.n_fasi ? "Approva e chiudi" : "Approva e passa alla fase " + (p.fase_corrente + 1)))) : msg,
    p.stato === "in_elaborazione" ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => decidi("annulla") }, "Annulla il percorso")) : null,
  ];
}
