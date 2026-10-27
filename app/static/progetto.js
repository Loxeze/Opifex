"use strict";
// Dashboard del singolo progetto e elenco dei progetti per i collaboratori.

function vistaProgettiMiei() {
  const corpo = h("div");
  api("GET", "/progetti-miei").then(d => {
    riempi(corpo, d.progetti.length ? d.progetti.map(p => h("div", { class: "carta", style: "margin-bottom:10px;border-left:5px solid " + (p.colore || "#f3b54a") },
      h("div", { class: "nome" }, p.nome), h("div", { class: "sotto" }, [p.azienda, p.aperte + " task aperte su " + p.totali, p.archiviato ? "archiviato" : ""].filter(Boolean).join(" · ")),
      p.descrizione ? h("div", { class: "sotto" }, p.descrizione) : null,
      h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => { stato.progettoAperto = p.id; vai("progetto"); } }, "Apri la dashboard"))))
      : h("p", { class: "sotto" }, "Non hai ancora progetti: il titolare ti assegna le imprese di cui occuparti."));
  }).catch(e => corpo.replaceChildren(avviso(e.message, "no")));
  return [h("h2", {}, "Progetti"), corpo];
}

function vistaProgetto() {
  const corpo = h("div"), msg = h("div");
  const STATO = { da_fare: "Da fare", in_corso: "In corso", in_attesa: "In attesa", completata: "Completate" };
  const parla = (id) => { stato.chatAgente = id; vai("chat"); };
  const carica = async () => {
    try {
      const d = await api("GET", "/progetti/" + stato.progettoAperto + "/dashboard");
      const p = d.progetto, col = p.colore || "#f3b54a", tot = d.task.length, fatte = d.conteggi.completata;
      const perc = tot ? Math.round(100 * fatte / tot) : 0;
      const tit = d.puo_modificare;
      const nuovaMs = h("input", { type: "text", maxlength: 200, placeholder: "Nuova milestone" }), scadMs = h("input", { type: "date" });
      const colonne = ["da_fare", "in_corso", "in_attesa", "completata"].map(s => h("div", { class: "carta", style: "flex:1 1 220px;min-width:0" },
        h("div", { class: "nome" }, STATO[s] + " (" + d.conteggi[s] + ")"),
        d.task.filter(t => t.stato === s).slice(0, 12).map(t => h("div", { class: "sotto", style: "padding:6px 0;border-top:1px solid var(--bordo)" },
          h("div", { style: "color:var(--testo)" }, t.titolo + (t.in_ritardo ? " ⚠" : "")),
          [t.agente ? "🤖 " + t.agente : "", t.persona ? "👤 " + t.persona : "", t.scadenza ? "entro " + new Date(t.scadenza).toLocaleDateString("it-IT") : "", t.priorita !== "normale" ? t.priorita : ""].filter(Boolean).join(" · "))),
        d.conteggi[s] > 12 ? h("div", { class: "sotto" }, "…e altre " + (d.conteggi[s] - 12)) : null));
      riempi(corpo, [
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => vai("progetti") }, "← Tutti i progetti")),
        h("div", { class: "carta", style: "border-left:6px solid " + col },
          h("div", { class: "nome" }, h("span", { class: "punto-col", style: "background:" + col }), p.nome + (p.archiviato ? " (archiviato)" : "")),
          h("div", { class: "sotto" }, "Impresa: " + (p.azienda || "—")), p.descrizione ? h("div", {}, p.descrizione) : null,
          h("div", { style: "margin:10px 0 4px;height:8px;border-radius:99px;background:var(--bordo);overflow:hidden" }, h("div", { style: "height:100%;width:" + perc + "%;background:linear-gradient(90deg,#f3b54a,#e58bd0)" })),
          h("div", { class: "sotto" }, perc + "% completato · " + fatte + " task chiuse su " + tot + (d.in_ritardo ? " · ⚠ " + d.in_ritardo + " in ritardo" : "")),
          p.allineamento ? h("details", { style: "margin-top:8px" }, h("summary", {}, "Documento di allineamento"), h("pre", { style: "white-space:pre-wrap" }, p.allineamento)) : null),
        bloccoScheda(p.id),
        bloccoSquadra(p.id),
        tit ? [h("h3", {}, "Manager di riferimento"),
          h("div", { class: "riga" }, [d.pm ? { ambito: "Project management", id: d.pm.id, nome: d.pm.nome } : null, ...d.manager].filter(Boolean).map(m => h("div", { class: "carta", style: "flex:0 1 220px" },
            h("div", { class: "sotto" }, m.ambito), h("div", { class: "nome" }, m.nome), h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => parla(m.id) }, "Parla con lui"))))),
          !d.pm ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/progetti/" + p.id + "/project-manager"); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea il project manager")) : null] : null,
        h("h3", {}, "Task"), h("div", { class: "riga", style: "align-items:flex-start" }, colonne),
        h("h3", {}, "Chi ci lavora"),
        h("div", { class: "riga", style: "align-items:flex-start" },
          d.agenti.map(a => h("div", { class: "carta", style: "flex:0 1 240px" }, h("div", { class: "nome" }, "🤖 " + a.nome), h("div", { class: "sotto" }, [a.ambito, a.ruolo].filter(Boolean).join(" · ")),
            h("div", { class: "sotto" }, a.aperte + " aperte · " + a.chiuse + " chiuse · " + a.attivita_7g + " aggiornamenti negli ultimi 7 giorni"),
            tit ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => parla(a.id) }, "Chat")) : null)),
          d.persone.map(x => h("div", { class: "carta", style: "flex:0 1 240px" }, h("div", { class: "nome" }, "👤 " + x.nome), h("div", { class: "sotto" }, x.aperte + " aperte · " + x.chiuse + " chiuse"))),
          !d.agenti.length && !d.persone.length ? h("p", { class: "sotto" }, "Nessuna task assegnata: nessuno ci sta ancora lavorando.") : null),
        h("h3", {}, "Milestone"),
        d.milestone.length ? d.milestone.map(m => h("div", { class: "carta", style: "margin-bottom:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap" },
          h("div", { style: "flex:1" }, h("div", { class: "nome" }, (m.raggiunta_il ? "✅ " : "⬜ ") + m.titolo),
            h("div", { class: "sotto" }, (m.scadenza ? "entro " + new Date(m.scadenza).toLocaleDateString("it-IT") : "senza scadenza") + (m.raggiunta_il ? " · raggiunta il " + new Date(m.raggiunta_il).toLocaleDateString("it-IT") : ""))),
          tit ? [h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/milestone/" + m.id + "/raggiunta", { raggiunta: !m.raggiunta_il }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, m.raggiunta_il ? "Riapri" : "Segna raggiunta"),
            h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare la milestone?")) return; try { await api("DELETE", "/gestione/milestone/" + m.id); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina")] : null))
          : h("p", { class: "sotto" }, "Nessuna milestone ancora."),
        tit ? h("div", { class: "riga" }, h("label", {}, "Nuova milestone", nuovaMs), h("label", {}, "Scadenza", scadMs),
          h("button", { class: "p", style: "align-self:flex-end", onclick: async () => { try { await api("POST", "/gestione/progetti/" + p.id + "/milestone", { titolo: nuovaMs.value.trim(), scadenza: scadMs.value || null }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi")) : null,
        msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Progetto"), corpo];
}


// Scheda del progetto: la memoria condivisa che leggono e aggiornano tutti gli agenti assegnati.
function bloccoScheda(pid) {
  const corpo = h("div");
  const carica = async () => {
    try {
      const s = await api("GET", "/progetti/" + pid + "/scheda");
      const msg = h("div"), mod = s.puo_modificare;
      const campi = Object.entries(s.campi).map(([k, et]) => ({ k, et, t: h("textarea", { style: "min-height:90px", maxlength: 3000, disabled: !mod, placeholder: et }) }));
      campi.forEach(c => { c.t.value = s[c.k] || ""; });
      const nuovaDec = h("input", { type: "text", maxlength: 600, placeholder: "Nuova decisione presa" });
      const file = h("input", { type: "file" });
      const fascia = h("select", {}, ["interno", "pubblico", "riservato"].map(x => h("option", { value: x }, x)));
      const scelta = h("select", {}, h("option", { value: "" }, "— allega un documento già caricato —"));
      if (mod) api("GET", "/gestione/progetti/" + pid + "/documenti-disponibili").then(l => l.forEach(d => scelta.appendChild(h("option", { value: d.id }, d.nome)))).catch(() => {});
      const dec = s.decisioni.filter(d => !d.superata), vecchie = s.decisioni.filter(d => d.superata);
      const chi = x => x.agente ? "🤖 " + x.agente : (x.persona ? "👤 " + x.persona : "");
      const NOMI = s.campi;
      riempi(corpo, [
        h("h3", {}, "Scheda del progetto"),
        h("p", { class: "aiuto" }, "È la memoria condivisa: la leggono a ogni richiesta tutti gli agenti assegnati e la aggiornano loro stessi quando decidono o scoprono qualcosa." + (s.scheda_il ? " Ultimo aggiornamento: " + new Date(s.scheda_il).toLocaleString("it-IT") : "")),
        h("div", { class: "carta" },
          campi.map(c => h("label", {}, c.et, c.t)),
          mod ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { const body = {}; campi.forEach(c => { body[c.k] = c.t.value; }); const r = await api("PUT", "/gestione/progetti/" + pid + "/scheda", body);
              msg.replaceChildren(avviso(r.cambiati.length ? "Scheda salvata." : "Nessuna modifica.", "ok")); if (r.cambiati.length) carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva la scheda")) : null,
          msg),
        h("h3", {}, "Decisioni prese"),
        dec.length ? dec.map(d => h("div", { class: "carta", style: "margin-bottom:6px" }, h("div", {}, d.testo),
          h("div", { class: "sotto" }, new Date(d.creata_il).toLocaleDateString("it-IT") + " · " + chi(d)),
          mod ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("DELETE", "/gestione/progetti/" + pid + "/decisioni/" + d.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Segna come superata")) : null))
          : h("p", { class: "sotto" }, "Nessuna decisione registrata."),
        mod ? h("div", { class: "riga" }, h("label", {}, "Registra una decisione", nuovaDec), h("button", { class: "p", style: "align-self:flex-end", onclick: async () => {
          try { await api("POST", "/gestione/progetti/" + pid + "/decisioni", { testo: nuovaDec.value }); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi")) : null,
        vecchie.length ? h("details", {}, h("summary", { class: "sotto", style: "cursor:pointer" }, "Decisioni superate (" + vecchie.length + ")"), vecchie.map(d => h("div", { class: "sotto", style: "text-decoration:line-through" }, d.testo))) : null,
        h("h3", {}, "Documentazione di base"),
        h("p", { class: "aiuto" }, "I documenti allegati qui li possono leggere e consultare tutti gli agenti assegnati al progetto (PDF, Word, Excel, immagini…). Il livello di riservatezza decide quali modelli possono riceverli."),
        s.documenti.length ? s.documenti.map(d => h("div", { class: "carta", style: "margin-bottom:6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap" },
          h("div", { style: "flex:1" }, h("div", { class: "nome" }, d.nome), h("div", { class: "sotto" }, d.nome_file + " · " + d.caratteri + " caratteri · " + d.fascia_dati)),
          mod ? h("button", { class: "s", onclick: async () => { try { await api("DELETE", "/gestione/progetti/" + pid + "/documenti/" + d.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Stacca dal progetto") : null))
          : h("p", { class: "sotto" }, "Nessun documento allegato."),
        mod ? h("div", { class: "carta" }, h("label", {}, "Carica un documento", file), h("label", {}, "Riservatezza", fascia),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (e) => {
            if (!file.files.length) { msg.replaceChildren(avviso("Scegli un file.", "avv")); return; }
            e.currentTarget.disabled = true;
            try { const fd = new FormData(); fd.append("file", file.files[0]); fd.append("nome", ""); fd.append("fascia_dati", fascia.value); await api("POST", "/gestione/progetti/" + pid + "/documenti", fd); carica(); }
            catch (x) { msg.replaceChildren(avviso(x.message, "no")); e.currentTarget.disabled = false; } } }, "Carica e allega")),
          h("div", { class: "azioni" }, scelta, h("button", { class: "s", onclick: async () => { if (!scelta.value) return;
            try { await api("POST", "/gestione/progetti/" + pid + "/documenti/" + scelta.value); carica(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Allega"))) : null,
        mod && s.versioni && s.versioni.length ? h("details", {}, h("summary", { class: "sotto", style: "cursor:pointer;margin-top:10px" }, "Storico delle modifiche (" + s.versioni.length + ")"),
          s.versioni.map(v => h("div", { class: "sotto", style: "padding:6px 0;border-top:1px solid var(--bordo)" },
            new Date(v.creata_il).toLocaleString("it-IT") + " · " + (v.agente ? "🤖 " + v.agente : "👤 " + (v.persona || "?")) + " · " + (NOMI[v.campo] || v.campo),
            h("div", { style: "white-space:pre-wrap;color:var(--testo)" }, (v.dopo || "").slice(0, 400))))) : null]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}

const ESITI_KPI = { in_linea: "🟢 in linea", a_rischio: "🟠 a rischio", fuori_rotta: "🔴 fuori rotta", raggiunto: "✅ raggiunto" };

function bloccoSquadra(pid) {
  const corpo = h("div");
  const carica = async () => {
    try {
      const s = await api("GET", "/progetti/" + pid + "/squadra"), mod = s.puo_modificare;
      const msg = h("div");
      const brief = h("textarea", { style: "min-height:80px", maxlength: 4000, disabled: !mod, placeholder: "Cosa vuoi ottenere: il project manager ricava da qui le competenze necessarie e propone la squadra" });
      brief.value = s.brief || "";
      const agisci = async (f) => { try { await f(); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
      riempi(corpo, [
        h("h3", {}, "Squadra e KPI"),
        h("p", { class: "aiuto" }, "Il project manager sceglie gli agenti in base alle competenze (e al loro livello), tu approvi. Gli agenti restano dei loro manager d'area, che vengono avvisati e possono richiamarli; dentro il progetto li comanda il PM, che assegna i KPI e li valuta."),
        h("div", { class: "carta" }, h("label", {}, "Brief del progetto", brief),
          mod ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => agisci(() => api("PUT", "/gestione/progetti/" + pid + "/brief", { brief: brief.value })) }, "Salva il brief")) : null),
        s.proposte.map(pr => h("div", { class: "carta", style: "border-left:4px solid var(--accento, #c60)" },
          h("div", { class: "nome" }, "Squadra proposta da " + (pr.proposta_da || "un agente")),
          h("div", { class: "sotto" }, pr.motivazione),
          pr.lacune ? h("div", { class: "sotto" }, "Competenze mancanti: " + pr.lacune) : null,
          pr.membri.map(m => h("div", {}, h("b", {}, m.nome), " (" + (m.reparto || "—") + ") — " + (m.ruolo_progetto || m.ruolo || "") + (m.motivo ? ": " + m.motivo : ""))),
          mod ? h("div", { class: "azioni" },
            h("button", { class: "p", onclick: () => agisci(() => api("POST", "/gestione/squadre/" + pr.id + "/decisione", { approva: true })) }, "Approva la squadra"),
            h("button", { class: "s", onclick: () => { const n = prompt("Perché la respingi? (il PM lo leggerà)") ; if (n !== null) agisci(() => api("POST", "/gestione/squadre/" + pr.id + "/decisione", { approva: false, nota: n })); } }, "Respingi")) : null)),
        s.squadra.length ? s.squadra.map(m => h("div", { class: "carta", style: "margin-bottom:6px" },
          h("div", { class: "nome" }, (m.e_pm ? "🧭 " : "") + m.nome + (m.livello_formazione ? " (" + m.livello_formazione + ")" : ""), h("span", { class: "sotto" }, " · " + (m.ruolo_progetto || m.ruolo || "") + " · " + (m.reparto || ""))),
          m.competenze.length ? h("div", { class: "sotto" }, "Competenze: " + m.competenze.join(", ")) : null,
          h("div", { class: "sotto" }, "Nel progetto: " + m.misure.chiuse + " task chiuse, " + m.misure.aperte + " aperte" + (m.misure.in_ritardo ? ", " + m.misure.in_ritardo + " in ritardo" : "") + " · 👍 " + m.misure.pollici_su + " 👎 " + m.misure.pollici_giu),
          m.kpi.map(k => h("div", { style: "padding:4px 0;border-top:1px solid var(--bordo)" + (k.chiuso ? ";opacity:.6" : "") },
            "🎯 " + k.nome + ": " + (k.valore ?? "—") + (k.valore_obiettivo != null ? " / " + k.valore_obiettivo + " " + (k.unita || "") : "") + (k.esito ? " · " + ESITI_KPI[k.esito] : "") + (k.scadenza ? " · entro " + new Date(k.scadenza).toLocaleDateString("it-IT") : ""),
            k.nota ? h("div", { class: "sotto" }, k.nota) : null)),
          mod && !m.e_pm ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => { if (confirm("Togliere " + m.nome + " dalla squadra?")) agisci(() => api("DELETE", "/gestione/progetti/" + pid + "/squadra/" + m.id)); } }, "Togli dalla squadra")) : null))
          : h("p", { class: "sotto" }, "Nessuna squadra ancora: scrivi il brief e chiedi al project manager di proporla."),
        msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}
