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
