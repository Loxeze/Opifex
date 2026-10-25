// «Quando lavora» (trigger per agente) e «Smistamento» (regole e consegne tra manager). Solo titolare.
const EVENTO_NOME = { documento_caricato: "Viene caricato un documento", task_assegnato: "Gli viene assegnata una task", consegna_ricevuta: "Riceve una consegna da un manager", studio_concluso: "Padre Casati conclude uno studio" };
const GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

function descriviTrigger(t) {
  if (t.tipo === "manuale") return "Solo a mano";
  if (t.tipo === "evento") return (EVENTO_NOME[t.evento] || t.evento) + (t.parole ? " · parole: " + t.parole : "");
  if (t.frequenza === "ogni_ore") return "Ogni " + t.ogni_ore + " ore";
  const ora = (t.ora || "").slice(0, 5);
  return t.frequenza === "giornaliero" ? "Ogni giorno alle " + ora : "Ogni " + (t.giorni || []).map(g => GIORNI[g]).join(", ") + " alle " + ora;
}

function vistaQuando() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/quando");
      const ag = h("select", {}, d.agenti.map(a => h("option", { value: a.id }, a.nome)));
      const nome = h("input", { maxlength: 80, placeholder: "Es. Ricerca bandi del mattino" });
      const compito = h("textarea", { style: "min-height:70px", maxlength: 3000, placeholder: "Cosa deve fare quando scatta (almeno 10 caratteri)" });
      const tipo = h("select", {}, [["manuale", "Solo a mano"], ["orario", "A un orario"], ["evento", "Quando succede qualcosa"]].map(([v, t]) => h("option", { value: v }, t)));
      const freq = h("select", {}, [["giornaliero", "Ogni giorno"], ["settimanale", "Alcuni giorni della settimana"], ["ogni_ore", "Ogni N ore"]].map(([v, t]) => h("option", { value: v }, t)));
      const ora = h("input", { type: "time", value: "08:00" }), ore = h("input", { type: "number", min: 1, max: 24, value: 6, style: "width:70px" });
      const giorni = GIORNI.map((g, i) => { const c = h("input", { type: "checkbox", value: i }); return h("label", { class: "inline" }, c, " " + g); });
      const evento = h("select", {}, d.eventi.map(e => h("option", { value: e }, EVENTO_NOME[e] || e)));
      const parole = h("input", { maxlength: 200, placeholder: "Parole da cercare (facoltativo): bando cultura" });
      const tok = h("input", { type: "number", min: 500, max: 8000, value: 2500, style: "width:90px" }), gg = h("input", { type: "number", min: 1, max: 24, value: 3, style: "width:70px" });
      const sezOrario = h("div", { class: "riga" }, freq, ora, ore, h("div", {}, giorni)), sezEvento = h("div", { class: "riga" }, evento, parole);
      const aggiorna = () => {
        sezOrario.style.display = tipo.value === "orario" ? "" : "none"; sezEvento.style.display = tipo.value === "evento" ? "" : "none";
        ora.style.display = freq.value === "ogni_ore" ? "none" : ""; ore.style.display = freq.value === "ogni_ore" ? "" : "none";
        giorni.forEach(g => g.style.display = freq.value === "settimanale" ? "" : "none");
      };
      tipo.onchange = freq.onchange = aggiorna; aggiorna();
      const per = {};
      d.trigger.forEach(t => (per[t.agente] = per[t.agente] || []).push(t));
      const err = e => msg.replaceChildren(avviso(e.message, "no"));
      riempi(corpo, [
        h("p", { class: "aiuto" }, "Qui decidi quando ogni agente si mette al lavoro da solo: a un orario, quando succede qualcosa (un documento caricato, una task assegnata, una consegna, uno studio concluso) oppure solo a mano. Ogni trigger nasce spento; ha un tetto di token per esecuzione e un massimo di esecuzioni al giorno. L'agente lavora con i dati interni e ogni azione verso l'esterno resta soggetta alla tua approvazione."),
        Object.keys(per).length ? Object.entries(per).map(([a, lista]) => h("div", {}, h("h3", {}, a), lista.map(t => {
          const reg = h("pre", { style: "white-space:pre-wrap;display:none;max-height:300px;overflow:auto" });
          return h("div", { class: "carta", style: "margin-bottom:8px" },
            h("div", { class: "nome" }, t.nome + (t.attivo ? "  🟢 acceso" : "  ⚪ spento")),
            h("div", { class: "sotto" }, [descriviTrigger(t), "max " + t.max_token + " token", t.oggi + "/" + t.max_al_giorno + " oggi", t.ultimo_esito ? "ultimo esito: " + t.ultimo_esito : ""].filter(Boolean).join(" · ")),
            h("div", {}, t.compito), reg,
            h("div", { class: "azioni" },
              h("button", { class: t.attivo ? "s" : "p", onclick: async () => { try { await api("POST", "/gestione/quando/" + t.id + "/attivo", { attivo: !t.attivo }); await carica(); } catch (e) { err(e); } } }, t.attivo ? "Spegni" : "Accendi"),
              h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/quando/" + t.id + "/esegui"); msg.replaceChildren(avviso("Avviato: l'agente sta lavorando.", "ok")); } catch (e) { err(e); } } }, "Esegui ora"),
              h("button", { class: "s", onclick: async () => {
                if (reg.style.display !== "none") { reg.style.display = "none"; return; }
                try { const r = await api("GET", "/gestione/quando/" + t.id + "/esecuzioni"); reg.textContent = r.esecuzioni.length ? r.esecuzioni.map(e => new Date(e.creato_il).toLocaleString("it-IT") + " · " + e.causa + " · " + e.esito + (e.token ? " · " + e.token + " token" : "") + (e.risultato ? "\n" + e.risultato.slice(0, 600) : "")).join("\n\n") : "Nessuna esecuzione."; reg.style.display = "block"; } catch (e) { err(e); } } }, "Cronologia"),
              h("button", { class: "s", onclick: async () => { if (!confirm("Eliminare il trigger «" + t.nome + "»?")) return; try { await api("DELETE", "/gestione/quando/" + t.id); await carica(); } catch (e) { err(e); } } }, "Elimina")));
        }))) : h("p", { class: "sotto" }, "Nessun trigger ancora."),
        h("h3", {}, "Nuovo trigger"),
        h("div", { class: "riga" }, h("label", {}, "Agente", ag), h("label", {}, "Nome", nome), h("label", {}, "Quando", tipo)), sezOrario, sezEvento, compito,
        h("div", { class: "riga" }, h("label", {}, "Token massimi", tok), h("label", {}, "Esecuzioni al giorno", gg)),
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try {
            await api("POST", "/gestione/quando", { agente_id: Number(ag.value), nome: nome.value, compito: compito.value, tipo: tipo.value, frequenza: tipo.value === "orario" ? freq.value : null,
              ora: ora.value, giorni: giorni.filter(g => g.firstChild.checked).map(g => Number(g.firstChild.value)), ogni_ore: Number(ore.value), evento: evento.value, parole: parole.value,
              max_token: Number(tok.value), max_al_giorno: Number(gg.value) });
            nome.value = compito.value = ""; msg.replaceChildren(avviso("Trigger creato, spento: accendilo quando sei pronto.", "ok")); await carica();
          } catch (e) { err(e); } } }, "Crea (spento)"))]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Quando lavora"), msg, corpo);
}

function vistaSmistamento() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/quando/smistamento");
      const err = e => msg.replaceChildren(avviso(e.message, "no"));
      const stato = async (r, s) => { try { await api("POST", "/gestione/quando/regole/" + r.id + "/stato", { stato: s }); await carica(); } catch (e) { err(e); } };
      const quando = h("input", { maxlength: 400, placeholder: "Es. un bando o un avviso del settore cultura" });
      const dest = h("select", {}, d.manager.map(m => h("option", { value: m.id }, m.nome)));
      const ST = { proposta: "da approvare", attiva: "attiva", disattivata: "disattivata" }, SC = { inviata: "in corso", elaborata: "elaborata", errore: "errore", non_elaborata: "non elaborata" };
      riempi(corpo, [
        h("p", { class: "aiuto" }, "Quando un manager trova qualcosa che spetta a un altro manager, lo passa con una consegna: nasce una task per il destinatario, che la esamina subito. Le regole qui sotto dicono ai manager dove mandare cosa. Il Cerimoniere può proporne di nuove: valgono solo dopo la tua approvazione."),
        h("h3", {}, "Regole"),
        d.regole.length ? d.regole.map(r => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, "Quando " + r.quando + " → " + r.destinatario),
          h("div", { class: "sotto" }, [ST[r.stato], r.da_agente ? "solo per " + r.da_agente : "per tutti i manager", r.proposta_da ? "proposta da " + r.proposta_da : ""].filter(Boolean).join(" · ")),
          h("div", { class: "azioni" }, r.stato === "attiva" ? h("button", { class: "s", onclick: () => stato(r, "disattivata") }, "Disattiva") : h("button", { class: "p", onclick: () => stato(r, "attiva") }, r.stato === "proposta" ? "Approva" : "Riattiva"),
            r.stato === "proposta" ? h("button", { class: "s", onclick: () => stato(r, "disattivata") }, "Scarta") : null))) : h("p", { class: "sotto" }, "Nessuna regola ancora."),
        h("div", { class: "riga" }, h("label", {}, "Quando", quando), h("label", {}, "Passa a", dest)),
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try { await api("POST", "/gestione/quando/regole", { quando: quando.value.trim(), a_agente_id: Number(dest.value) }); quando.value = ""; await carica(); } catch (e) { err(e); } } }, "Aggiungi regola")),
        h("h3", {}, "Ultime consegne"),
        d.consegne.length ? d.consegne.map(c => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, c.titolo), h("div", { class: "sotto" }, [c.da + " → " + c.a, SC[c.stato], c.task_id ? "task #" + c.task_id : "", new Date(c.creata_il).toLocaleString("it-IT")].filter(Boolean).join(" · ")),
          c.esito ? h("div", {}, c.esito.slice(0, 500)) : null)) : h("p", { class: "sotto" }, "Nessuna consegna ancora.")]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Smistamento e consegne"), msg, corpo);
}
