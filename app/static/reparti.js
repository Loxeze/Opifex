// Reparti pronti (Legale, Sviluppo software, Casa editrice) e Sandbox. Solo titolare.
function vistaReparti() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/reparti");
      riempi(corpo, [
        h("p", { class: "aiuto" }, "Reparti già impostati con manager, ruoli e istruzioni. Si attivano una volta sola e puoi poi modificare ogni agente dalle impostazioni come gli altri. Nel reparto Legale ogni materia ha una figura sola (nessun doppio controllo) e i pareri sono bozze da verificare con un professionista; nello Sviluppo software ogni ruolo ha un agente Claude e un controllore ChatGPT per i compiti complessi."),
        d.reparti.map(r => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, r.nome + (r.attivo ? "  🟢 attivo (" + r.agenti + " agenti)" : "  ⚪ non attivo")), h("div", { class: "sotto" }, r.descrizione),
          h("div", { class: "azioni" }, h("button", { class: r.attivo ? "s" : "p", onclick: async () => {
            try { const x = await api("POST", "/gestione/reparti/" + r.chiave + "/attiva"); msg.replaceChildren(avviso(x.creati.length ? "Creati " + x.creati.length + " agenti." : "Era già tutto a posto.", "ok")); await carica(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, r.attivo ? "Completa / ricontrolla" : "Attiva il reparto"))))]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Reparti pronti"), msg, corpo);
}

function vistaSandbox() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/sandbox");
      const err = e => msg.replaceChildren(avviso(e.message, "no"));
      const ST = { in_attesa: "in attesa di approvazione", ok: "riuscita", errore: "con errore", timeout: "tempo scaduto", rifiutata: "rifiutata", non_disponibile: "non disponibile" };
      const L = d.limiti;
      riempi(corpo, [
        h("p", { class: "aiuto" }, "Qui gli agenti di sviluppo provano il codice che scrivono, in un contenitore usa-e-getta: nessuna rete, nessun dato né chiave di Opifex, " + L.memoria + " di memoria, " + L.tempo_s + " secondi, " + L.processi + " processi, utente senza privilegi e file system in sola lettura. Opifex non installa né scarica nulla: serve Docker o Podman con l'immagine già presente sul server. La rete la approvi tu, caso per caso."),
        d.motore ? avviso("Motore: " + d.motore + (d.motore_pronto ? " (pronto)" : " (non risponde: controlla che il servizio sia attivo)"), d.motore_pronto ? "ok" : "no") : avviso("Sul server non c'è né Docker né Podman: finché non ne installi uno la sandbox resta non disponibile. Dimmi pure e lo prepariamo insieme.", "no"),
        Object.entries(d.immagini).map(([k, i]) => h("div", { class: "sotto" }, k + ": " + i.nome + (i.presente ? " ✓ presente" : " ✗ assente (da scaricare una volta: docker pull " + i.nome + ")"))),
        h("div", { class: "azioni" }, h("button", { class: d.attiva ? "s" : "p", onclick: async () => { try { await api("POST", "/gestione/sandbox/impostazioni", { attiva: !d.attiva }); await carica(); } catch (e) { err(e); } } }, d.attiva ? "Spegni la sandbox" : "Accendi la sandbox")),
        h("div", { class: "sotto" }, "Doppi controlli Claude/ChatGPT negli ultimi 7 giorni: " + d.revisioni.n + " (riusciti " + d.revisioni.ok + ")"),
        h("h3", {}, "Ultime prove"),
        d.esecuzioni.length ? d.esecuzioni.map(e => {
          const det = h("pre", { style: "white-space:pre-wrap;display:none;max-height:300px;overflow:auto" }, "CODICE\n" + e.codice + "\n\nUSCITA\n" + (e.uscita || "(nessuna)"));
          return h("div", { class: "carta", style: "margin-bottom:8px" },
            h("div", { class: "nome" }, "#" + e.id + " " + e.linguaggio + " · " + (e.agente || "—") + " · " + ST[e.stato] + (e.rete ? " · CON RETE" : "")),
            h("div", { class: "sotto" }, [e.durata_ms != null ? e.durata_ms + " ms" : "", e.motivo_rete ? "motivo rete: " + e.motivo_rete : "", new Date(e.creata_il).toLocaleString("it-IT")].filter(Boolean).join(" · ")), det,
            h("div", { class: "azioni" }, e.stato === "in_attesa" ? [h("button", { class: "p", onclick: async () => { try { await api("POST", "/gestione/sandbox/" + e.id + "/decisione", { approva: true }); await carica(); } catch (x) { err(x); } } }, "Approva la rete ed esegui"),
              h("button", { class: "s", onclick: async () => { try { await api("POST", "/gestione/sandbox/" + e.id + "/decisione", { approva: false }); await carica(); } catch (x) { err(x); } } }, "Rifiuta")] : null,
              h("button", { class: "s", onclick: () => { det.style.display = det.style.display === "none" ? "block" : "none"; } }, "Codice e output")));
        }) : h("p", { class: "sotto" }, "Nessuna prova ancora.")]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Sandbox del codice"), msg, corpo);
}
