"use strict";
// Dossier di competenza, biblioteca di Padre Casati, Cerimoniere e pollici su/giù. I testi degli agenti sono inseriti come testo.

const NOME_LIVELLO = { supervisionato: "Supervisionato", a_campione: "A campione", autonomo: "Autonomo (solo azioni interne)" };
const TIPO_DOC = { studio: "Studio", dispensa: "Dispensa", documento: "Documento" };

// Pollice su/giù sul lavoro di un agente. oggetto: task | chat | briefing. Il giù chiede un motivo (diventa un «errore da evitare» proposto).
function pollici(agenteId, oggetto, oggettoId) {
  const box = h("span", { class: "pollici" });
  const msg = h("span", { class: "sotto" });
  const invia = async (voto, nota) => {
    try {
      await api("POST", "/valutazioni", { oggetto, oggetto_id: oggettoId || null, agente_id: agenteId || null, voto, nota: nota || null });
      box.replaceChildren(h("span", { class: "sotto" }, voto > 0 ? "👍 Grazie, registrato." : "👎 Registrato" + (nota ? ": entra tra le proposte del dossier." : ".")));
    } catch (e) { msg.textContent = e.message; }
  };
  const su = h("button", { class: "s", type: "button", title: "Buon lavoro", onclick: () => invia(1) }, "👍");
  const giu = h("button", { class: "s", type: "button", title: "Da migliorare", onclick: () => {
    const nota = h("input", { maxlength: 400, placeholder: "Cosa non andava? (facoltativo, diventa una lezione da approvare)", style: "min-width:260px" });
    box.replaceChildren(nota, h("button", { class: "p", type: "button", onclick: () => invia(-1, nota.value.trim()) }, "Invia"), msg);
    nota.focus();
  } }, "👎");
  box.append(su, " ", giu, " ", msg);
  return box;
}

function vistaDossier() {
  const corpo = h("div"), dettaglio = h("div");
  const apri = async (id) => {
    try {
      const f = await api("GET", "/dossier/" + id), x = f.fiducia;
      riempi(dettaglio, h("div", { class: "carta" },
        h("h3", { style: "margin-top:0" }, "Fascicolo di " + f.agente.nome),
        h("div", { class: "sotto" }, [f.agente.ruolo, f.agente.divisione].filter(Boolean).join(" · ")),
        avviso((NOME_LIVELLO[x.livello_suggerito] || x.livello_suggerito) + " — " + x.descrizione_livello + ". " +
          (x.dati_sufficienti ? "Approvazione " + Math.round(x.tasso_approvazione * 100) + "% su " + x.casi + " casi negli ultimi " + x.giorni + " giorni (👍 " + x.pollici_su + ", 👎 " + x.pollici_giu + ", task approvati " + x.approvati + ", respinti " + x.respinti + ")."
            : "Servono almeno " + x.minimo_casi + " valutazioni o approvazioni per un suggerimento affidabile (finora " + x.casi + ")."), x.livello_suggerito === "autonomo" ? "ok" : "avv"),
        h("p", { class: "aiuto" }, "Il livello è un suggerimento calcolato sui risultati: non cambia da solo i permessi. Le azioni verso l'esterno restano sempre approvate da una persona."),
        f.voci_da_riverificare ? avviso(f.voci_da_riverificare + " voci del dossier sono da riverificare (data scaduta): le trovi in Memoria di lavoro.", "avv") : null,
        h("div", { class: "sotto" }, "Token usati questo mese: " + f.token_mese + (f.agente.budget_token_mensile ? " su " + f.agente.budget_token_mensile : "")),
        f.voci_reparto_per_tipo.length ? h("div", { class: "sotto" }, "Dossier di reparto e trasversale: " + f.voci_reparto_per_tipo.map(t => t.n + " " + (TIPO_MEM[t.tipo] || t.tipo).toLowerCase()).join(", ")) : null,
        h("h4", {}, "Voci personali"),
        f.voci_personali.length ? f.voci_personali.map(v => h("div", { class: "voce" },
          h("div", { class: "sotto" }, (TIPO_MEM[v.tipo] || v.tipo) + (v.tema ? " · " + v.tema : "") + " · " + (v.stato === "proposta" ? "da approvare" : "approvata") + (v.casi ? " · " + v.casi + " casi" : "")),
          h("div", {}, v.testo))) : h("p", { class: "sotto" }, "Ancora nessuna voce personale: nascono dalle valutazioni negative con motivo e dalle proposte dell'agente."),
        f.ultime_segnalazioni.length ? [h("h4", {}, "Ultime segnalazioni"), f.ultime_segnalazioni.map(n => h("div", { class: "sotto" }, "👎 " + n.nota))] : null));
      dettaglio.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) { dettaglio.replaceChildren(avviso(e.message, "no")); }
  };
  (async () => {
    try {
      const d = await api("GET", "/dossier");
      riempi(corpo, d.agenti.length ? h("table", { class: "tabella" },
        h("thead", {}, h("tr", {}, ["Agente", "Dipartimento", "Voci personali", "Casi (60 gg)", "Approvazione", "Livello suggerito", ""].map(t => h("th", {}, t)))),
        h("tbody", {}, d.agenti.map(a => h("tr", {},
          h("td", {}, a.nome), h("td", {}, a.divisione || "—"), h("td", {}, String(a.voci_personali)), h("td", {}, String(a.casi)),
          h("td", {}, a.tasso_approvazione == null ? "—" : Math.round(a.tasso_approvazione * 100) + "%"),
          h("td", {}, NOME_LIVELLO[a.livello_suggerito] || a.livello_suggerito),
          h("td", {}, h("button", { class: "s", onclick: () => apri(a.id) }, "Fascicolo")))))) : h("p", { class: "sotto" }, "Nessun agente."));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  })();
  return [h("h2", {}, "Dossier e fiducia"),
    h("p", { class: "aiuto" }, "Ogni agente ha un fascicolo di competenza: le sue voci personali, il dossier del suo reparto e i risultati del suo lavoro (👍/👎 che dai nelle chat e nei task, task approvati o respinti). Dal fascicolo vedi il livello di fiducia suggerito: supervisionato, a campione o autonomo sulle azioni interne."),
    corpo, dettaglio];
}

function vistaBiblioteca() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/biblioteca");
      const bozze = d.documenti.filter(x => x.stato_dispensa === "bozza");
      const proposti = d.coda.filter(c => c.stato === "proposto");
      const decidiCoda = async (c, azione) => {
        if (azione === "approva" && !confirm("Scarico «" + c.titolo + "» da " + new URL(c.url).hostname + "?")) return;
        try { const r = await api("POST", "/gestione/biblioteca/coda/" + c.id + "/decisione", { azione }); msg.replaceChildren(r.stato === "errore" ? avviso("Download non riuscito: " + r.errore, "no") : avviso(r.stato === "scaricato" ? "Scaricato e aggiunto alla biblioteca." : "Respinto.", "ok")); await carica(); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      const decidiDisp = async (x, azione) => {
        try { const r = await api("POST", "/gestione/biblioteca/dispense/" + x.id + "/decisione", { azione }); msg.replaceChildren(avviso(r.stato === "approvata" ? "Dispensa approvata: arriva a " + r.destinatari + "." : "Dispensa ritirata.", "ok")); await carica(); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      const url = h("input", { type: "url", maxlength: 1000, placeholder: "https://… link a un PDF ad accesso aperto" });
      const titolo = h("input", { maxlength: 250, placeholder: "Titolo" });
      const licenza = h("input", { maxlength: 120, placeholder: "Licenza (es. CC BY)" });
      riempi(corpo, [
        d.formatore_id ? null : avviso("Padre Casati non è presente tra gli agenti: viene creato dall'aggiornamento 1.16.0.", "avv"),
        h("h3", {}, "Da approvare" + (d.da_approvare ? " (" + d.da_approvare + ")" : "")),
        !proposti.length && !bozze.length ? h("p", { class: "sotto" }, "Niente in attesa.") : null,
        proposti.length > 1 ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (e) => {
          const siti = [...new Set(proposti.map(c => { try { return new URL(c.url).hostname; } catch (x) { return "?"; } }))];
          if (!confirm("Scarico tutti i " + proposti.length + " documenti in attesa da: " + siti.join(", ") + "?")) return;
          e.currentTarget.disabled = true;
          try { const r = await api("POST", "/gestione/biblioteca/coda/approva-tutti"); msg.replaceChildren(avviso("Scarico di " + r.avviati + " documenti avviato: vanno uno alla volta, la lista si aggiorna da sola.", "ok"));
            const giro = async () => { await carica(); const n = (await api("GET", "/gestione/biblioteca")).coda.filter(c => c.stato === "proposto").length; if (n && stato.vista === "impostazioni") setTimeout(giro, 4000); }; setTimeout(giro, 4000); }
          catch (er) { msg.replaceChildren(avviso(er.message, "no")); e.currentTarget.disabled = false; } } }, "Scarica tutto (" + proposti.length + ")")) : null,
        proposti.map(c => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, c.titolo),
          h("div", { class: "sotto" }, [c.autori, c.anno, c.archivio, c.licenza ? "licenza: " + c.licenza : "licenza non indicata", c.proposto_da ? "proposto da " + c.proposto_da : "indicato da te"].filter(Boolean).join(" · ")),
          c.motivo ? h("div", {}, "Perché: " + c.motivo) : null,
          h("div", { class: "sotto" }, "Indirizzo: " + c.url),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidiCoda(c, "approva") }, "Scarica"), h("button", { class: "s", onclick: () => decidiCoda(c, "respingi") }, "Respingi")))),
        bozze.map(x => {
          const anteprima = h("pre", { style: "white-space:pre-wrap;display:none;max-height:360px;overflow:auto" });
          return h("div", { class: "carta", style: "margin-bottom:8px" },
            h("div", { class: "nome" }, x.nome + " (versione " + x.versione + ")"),
            h("div", { class: "sotto" }, ["bozza di " + (x.preparata_da || "?"), "per " + (x.reparto || "tutti gli agenti"), x.caratteri + " caratteri"].join(" · ")),
            anteprima,
            h("div", { class: "azioni" },
              h("button", { class: "s", onclick: async () => { if (anteprima.style.display === "none") { try { const t = await api("GET", "/gestione/biblioteca/dispense/" + x.id); anteprima.textContent = t.testo; anteprima.style.display = "block"; } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } else anteprima.style.display = "none"; } }, "Leggi"),
              h("button", { class: "p", onclick: () => decidiDisp(x, "approva") }, "Approva e distribuisci"), h("button", { class: "s", onclick: () => decidiDisp(x, "respingi") }, "Ritira")));
        }),
        h("h3", {}, "Proponi un documento"),
        h("p", { class: "aiuto" }, "Incolla il link diretto a un PDF ad accesso aperto (da un archivio universitario, OpenAlex, arXiv…). Entra nella coda e si scarica solo quando premi «Scarica». Academia.edu non si usa in automatico: i suoi termini vietano accessi e download automatici e l'uso dei contenuti per l'IA."),
        h("div", { class: "riga" }, h("label", {}, "Indirizzo", url), h("label", {}, "Titolo", titolo), h("label", {}, "Licenza", licenza)),
        h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
          try { await api("POST", "/gestione/biblioteca/coda", { url: url.value.trim(), titolo: titolo.value.trim(), licenza: licenza.value.trim() || null }); url.value = titolo.value = licenza.value = ""; await carica(); }
          catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi alla coda")),
        h("h3", {}, "In biblioteca"),
        d.documenti.filter(x => x.stato_dispensa !== "bozza" && x.stato_dispensa !== "ritirata").length ? h("table", { class: "tabella" },
          h("thead", {}, h("tr", {}, ["Documento", "Tipo", "Anno", "Licenza", "Riservatezza", "Fonte"].map(t => h("th", {}, t)))),
          h("tbody", {}, d.documenti.filter(x => x.stato_dispensa !== "bozza" && x.stato_dispensa !== "ritirata").map(x => h("tr", {},
            h("td", {}, x.nome + (x.autori ? " — " + x.autori : "")), h("td", {}, (TIPO_DOC[x.tipo_doc] || x.tipo_doc) + (x.tipo_doc === "dispensa" ? " v" + x.versione + (x.reparto ? " · " + x.reparto : "") : "")),
            h("td", {}, x.anno ? String(x.anno) : "—"), h("td", {}, x.licenza || "—"), h("td", {}, x.fascia_dati), h("td", {}, x.fonte_url ? new URL(x.fonte_url).hostname : "caricato da te")))))
          : h("p", { class: "sotto" }, "La biblioteca è vuota: chiedi a Padre Casati di cercare fonti, oppure aggiungi un link qui sopra."),
        d.coda.filter(c => c.stato === "errore").length ? [h("h3", {}, "Download non riusciti"), d.coda.filter(c => c.stato === "errore").slice(0, 5).map(c => h("div", { class: "sotto" }, c.titolo + ": " + c.errore))] : null,
      ]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Biblioteca di Padre Casati"),
    h("p", { class: "aiuto" }, "Padre Casati è il formatore di tutti i reparti: custodisce gli studi, prepara le dispense e risponde alle domande tecniche dei colleghi citando i documenti. Cerca fonti ad accesso aperto (Wikipedia, OpenAlex, Semantic Scholar, arXiv) ma non scarica nulla senza il tuo via libera, e le dispense arrivano agli agenti solo dopo la tua approvazione. Parlagli dalla Chat come a qualsiasi agente."),
    msg, corpo];
}

function vistaCerimoniere() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/cerimoniere");
      const decidi = async (p, azione) => { try { await api("POST", "/gestione/cerimoniere/proposte/" + p.id + "/decisione", { azione }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
      riempi(corpo, [
        d.schede_vaghe.length ? avviso("Schede di competenza da completare (rendono l'agente difficile da trovare): " + d.schede_vaghe.join(", ") + ". Le completi in Agenti.", "avv") : null,
        h("h3", {}, "Ruoli proposti" + (d.aperte ? " (" + d.aperte + ")" : "")),
        d.proposte_ruoli.length ? d.proposte_ruoli.map(p => h("div", { class: "carta", style: "margin-bottom:8px" },
          h("div", { class: "nome" }, p.titolo + (p.stato !== "aperta" ? " — " + (p.stato === "presa_in_carico" ? "presa in carico" : "scartata") : "")),
          h("div", {}, p.descrizione), p.motivo ? h("div", { class: "sotto" }, "Perché: " + p.motivo) : null,
          p.stato === "aperta" ? h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => decidi(p, "presa_in_carico") }, "Prendo in carico"), h("button", { class: "s", onclick: () => decidi(p, "scartata") }, "Scarta")) : null))
          : h("p", { class: "sotto" }, "Nessun ruolo proposto: il Cerimoniere ne propone uno quando nessuno copre un bisogno."),
        h("h3", {}, "Instradamenti recenti" + (d.totali.tutti ? " (utili " + d.totali.utili + ", non utili " + d.totali.non_utili + " su " + d.totali.tutti + ")" : "")),
        d.instradamenti.length ? d.instradamenti.map(i => h("div", { class: "voce" },
          h("div", { class: "sotto" }, new Date(i.creata_il).toLocaleString("it-IT") + " · " + (i.richiedente || "un collega") + " → " + (i.destinatario || "?") + " · " + (i.esito ? (i.esito === "utile" ? "utile" : "non utile") : "esito non noto")),
          h("div", {}, i.bisogno))) : h("p", { class: "sotto" }, "Ancora nessun instradamento."),
      ]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Cerimoniere"),
    h("p", { class: "aiuto" }, "Il maestro delle cerimonie legge l'organizzazione dal vivo (schede di competenza, dipartimenti, aziende): quando aggiungi un ruolo non serve aggiornare nulla. Un manager gli espone un bisogno e lui indica a chi rivolgersi, presenta il richiedente e, se nessuno copre l'esigenza, ti propone un nuovo ruolo. Non svolge il lavoro: instrada."),
    msg, corpo];
}

const ORIGINE_STUDIO = { bando: "bando caricato", discussione: "argomento discusso", lacuna: "lacuna rilevata", iniziativa: "approfondimento di Padre Casati", manuale: "richiesto da te" };
const STATO_STUDIO = { proposto: "da approvare", approvato: "in partenza", in_corso: "in corso…", completato: "concluso", scartato: "scartato", errore: "non riuscito" };

function vistaStudi() {
  const corpo = h("div"), msg = h("div");
  let timer = null, firma = null;
  const testi = new Map();    // schede gia' aperte: restano aperte e allo stesso punto anche quando la pagina si aggiorna
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/studi");
      const f = JSON.stringify(d);
      if (f === firma && corpo.firstChild) return;      // nulla di nuovo: non si ridisegna, cosi' non si perde il punto di lettura
      firma = f;
      const decidi = async (s, azione) => {
        try { await api("POST", "/gestione/studi/" + s.id + "/decisione", { azione }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      };
      const tema = h("input", { maxlength: 200, placeholder: "Es. Regole di rendicontazione dei bandi PNRR" });
      const motivo = h("textarea", { style: "min-height:56px", maxlength: 1500, placeholder: "Perché serve (facoltativo)" });
      const rep = h("select", {}, h("option", { value: "" }, "Per tutti i reparti"), d.divisioni.map(x => h("option", { value: x.id }, x.nome)));
      riempiConservando(corpo, [
        h("p", { class: "aiuto" }, "Padre Casati studia quando c'è un motivo: un bando caricato, una domanda dei colleghi che la biblioteca non copre, un agente che riceve molti 👎, un approfondimento che vuole fare lui o che chiedi tu. Ogni studio parte solo dopo la tua approvazione, consulta biblioteca e archivi aperti e si chiude con una scheda e una voce di dossier da approvare in «Memoria di lavoro»."),
        h("h3", {}, "Studi" + (d.da_approvare ? " da approvare (" + d.da_approvare + ")" : "")),
        d.studi.length ? d.studi.map(s => {
          const sch = h("pre", { style: "white-space:pre-wrap;max-height:380px;overflow:auto;display:" + (testi.has(s.id) ? "block" : "none") }, testi.get(s.id) || "");
          return h("div", { class: "carta", style: "margin-bottom:8px" },
            h("div", { class: "nome" }, s.tema),
            h("div", { class: "sotto" }, [STATO_STUDIO[s.stato], ORIGINE_STUDIO[s.origine], s.reparto, s.richiesto_da ? "per " + s.richiesto_da : "", s.riferimento,
              s.token_usati ? s.token_usati + " token" : "", s.memoria_id ? "voce di dossier: " + (s.stato_voce === "approvata" ? "approvata" : "da approvare") : ""].filter(Boolean).join(" · ")),
            s.motivo ? h("div", {}, "Perché: " + s.motivo) : null,
            s.errore ? avviso(s.errore, "no") : null, sch,
            h("div", { class: "azioni" },
              s.stato === "proposto" ? [h("button", { class: "p", onclick: () => decidi(s, "approva") }, "Approva lo studio"), h("button", { class: "s", onclick: () => decidi(s, "scarta") }, "Scarta")] : null,
              s.ha_scheda ? h("button", { class: "s", onclick: async () => { if (sch.style.display === "none") { try { sch.textContent = (await api("GET", "/gestione/studi/" + s.id)).scheda; testi.set(s.id, sch.textContent); sch.style.display = "block"; } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } else { sch.style.display = "none"; testi.delete(s.id); } } }, "Leggi la scheda") : null));
        }) : h("p", { class: "sotto" }, "Nessuno studio ancora."),
        h("h3", {}, "Chiedi uno studio"),
        h("div", { class: "riga" }, h("label", {}, "Tema", tema), h("label", {}, "Reparto", rep)), motivo,
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try { await api("POST", "/gestione/studi", { tema: tema.value.trim(), motivo: motivo.value.trim() || null, divisione_id: rep.value ? Number(rep.value) : null });
            tema.value = motivo.value = ""; msg.replaceChildren(avviso("Studio avviato: Padre Casati ci sta lavorando.", "ok")); await carica(); }
          catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Avvia lo studio"))]);
      if (d.studi.some(s => s.stato === "in_corso" || s.stato === "approvato") && !timer) timer = setInterval(() => { if (!document.body.contains(corpo)) { clearInterval(timer); return; } carica(); }, 8000);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return h("div", {}, h("h2", {}, "Studi di Padre Casati"), pannelloFormazioneAuto(), msg, corpo);
}

function pannelloFormazioneAuto() {
  const box = h("div"), msg = h("div");
  const studi = h("input", { type: "checkbox" }), minimo = h("input", { type: "checkbox" }), giorni = h("input", { type: "number", min: 0, max: 90, style: "width:70px" });
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/formazione-auto");
      studi.checked = d.studi_automatici; minimo.checked = d.minimo_attivo; if (document.activeElement !== giorni) giorni.value = d.giorni;
      riempi(box, [
        d.ginnasio_attivo ? null : avviso("Il Ginnasio è spento: le richieste di formazione restano in coda finché non lo accendi (Impostazioni → Conoscenza → Ginnasio).", "avv"),
        h("p", { class: "sotto" }, "Studi in coda o in corso: " + d.studi_in_coda + (d.giri.length ? " · ultimo giro di formazione: " + ({ in_corso: "in corso…", concluso: "concluso", errore: "errore " + (d.giri[0].errore || "") })[d.giri[0].stato] + (d.giri[0].stato === "concluso" ? " (" + d.giri[0].interrogati + " agenti, " + d.giri[0].richieste + " richieste)" : "") : " · nessun giro ancora")),
        d.minimi_mancanti.length ? h("details", {}, h("summary", {}, d.minimi_mancanti.length + " competenze necessarie ancora al livello zero (formazione prioritaria)"), d.minimi_mancanti.map(m => h("div", { class: "sotto" }, m.agente + " → " + m.competenza))) : h("p", { class: "sotto" }, "Nessuna competenza necessaria è al livello zero.")]);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const salva = async () => { try { await api("PUT", "/gestione/formazione-auto/impostazioni", { studi_automatici: studi.checked, giorni: Number(giorni.value), minimo_attivo: minimo.checked }); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
  const giroOra = h("button", { class: "s", type: "button" }, "Fai il giro di formazione ora");
  giroOra.addEventListener("click", async () => { giroOra.disabled = true; try { await api("POST", "/gestione/formazione-auto/giro"); msg.replaceChildren(avviso("Giro avviato: Padre Casati interroga gli agenti in sottofondo.", "ok")); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } giroOra.disabled = false; });
  const salvaB = h("button", { class: "s", type: "button" }, "Salva"); salvaB.addEventListener("click", salva);
  carica();
  const t = setInterval(() => { if (!document.body.contains(box)) clearInterval(t); else carica(); }, 20000);
  return h("details", { class: "carta", style: "margin-bottom:12px" }, h("summary", {}, "Coda e formazione automatiche"),
    h("p", { class: "aiuto" }, "Gli studi approvati partono da soli, uno dopo l'altro. Quando la coda è finita, Padre Casati chiede a ogni agente quali competenze gli servono e quali vorrebbe approfondire: le richieste vanno in Ginnasio. Chi non ha almeno il livello 1 in una competenza necessaria viene formato per primo."),
    h("label", { class: "interruttore" }, studi, h("span", {}, "Le proposte di studio entrano da sole in coda (senza la tua approvazione)")),
    h("label", { class: "interruttore" }, minimo, h("span", {}, "Livello minimo 1 sulle competenze necessarie, con precedenza")),
    h("label", {}, "Giro di formazione ogni quanti giorni (0 = mai in automatico)", giorni), h("div", { class: "azioni" }, salvaB, giroOra), msg, box);
}
