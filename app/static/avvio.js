"use strict";
// Opifex 3.0: primo accesso e avvio guidato in nove passi. Ogni passo si puo' saltare e riprendere, e mostra se funziona davvero.

// Pagina di accesso della 3.0 appena installata: nessun utente ancora, si crea il proprio con il codice d'avvio dato dall'installatore.
function moduloPrimoAccesso() {
  const nome = h("input", { type: "text", autocomplete: "name", required: true, maxlength: 80 });
  const email = h("input", { type: "email", autocomplete: "username", required: true });
  const pw = h("input", { type: "password", autocomplete: "new-password", required: true, minlength: 10 });
  const pw2 = h("input", { type: "password", autocomplete: "new-password", required: true, minlength: 10 });
  const codice = h("input", { type: "text", autocomplete: "off", required: true, spellcheck: "false" });
  const msg = h("div");
  const invia = async (ev) => {
    ev.preventDefault(); msg.replaceChildren();
    if (pw.value !== pw2.value) { msg.replaceChildren(avviso("Le due password non coincidono.", "no")); return; }
    try {
      await api("POST", "/avvio/primo-utente", { nome: nome.value, email: email.value, password: pw.value, codice: codice.value });
      await proseguiAccesso(await api("POST", "/login", { email: email.value, password: pw.value }));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  radice.replaceChildren(h("div", { class: "accesso" },
    h("h2", {}, "Opifex 3.0"),
    h("p", { class: "sotto" }, "Benvenuto. Questa è un'installazione nuova: crea il tuo accesso. Poi l'avvio guidato ti accompagna nel resto."),
    h("form", { onsubmit: invia, class: "carta" },
      h("label", {}, "Il tuo nome", nome), h("label", {}, "Email", email),
      h("label", {}, "Password (almeno 10 caratteri)", pw), h("label", {}, "Ripeti la password", pw2),
      h("label", {}, "Codice d'avvio", codice), h("p", { class: "aiuto" }, "Il codice d'avvio è nell'ultimo messaggio dell'installazione sul server. Serve una volta sola."),
      msg, h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Crea l'accesso ed entra")))));
}

const AVVIO_AIUTO = {
  benvenuto: "Questa è la tua Opifex 3.0: parte vuota, accanto alla 2, che resta com'è. Puoi copiare dalla 2 ciò che hai già configurato.",
  ia: "Le chiavi dei fornitori AI e i computer con il modello locale. Aurora lavora su Claude; Posta sul modello locale, con Claude per i controlli e gli invii.",
  chi: "Chi sei, che cosa offri e a chi. Aurora lo usa per capire che cosa conta, il Radar per cercare clienti e collaboratori.",
  posta: "La casella che legge Posta. Le risposte che prepara restano da approvare: non parte nulla senza di te.",
  calendario: "Calendario e Drive dallo stesso collegamento Google.",
  memoria: "L'app per il computer indicizza i tuoi dischi e il NAS. Collegata qui, Aurora e Posta possono cercare nella tua memoria. I file non lasciano mai il computer: ad Aurora arrivano solo i risultati delle ricerche.",
  telefono: "Opifex sul telefono e su Telegram, per avvisi e conversazioni a voce.",
  radar: "Il Radar cerca ogni giorno notizie, potenziali clienti e collaboratori sui temi che scegli.",
  squadra: "Aurora e Posta. Gli altri agenti si aggiungono quando servono.",
};

function vistaAvvio() {
  const corpo = h("div", { class: "avvio" });
  let dati = null;
  if (!stato.passoAvvio) stato.passoAvvio = "benvenuto";
  const segna = async (id, esito, avanti) => {
    try { await api("PUT", "/gestione/avvio/passo/" + id, { esito }); } catch (e) { /* si ripete con il prossimo clic */ }
    if (avanti) { const i = dati.passi.findIndex(p => p.id === id); if (i >= 0 && i < dati.passi.length - 1) stato.passoAvvio = dati.passi[i + 1].id; }
    carica();
  };
  const spia = (p) => { const fatto = (p.verifica && p.verifica.pronto) || p.esito === "fatto";
    return h("span", { class: "pallino" + (fatto ? " ok" : p.esito === "saltato" ? " salta" : ""), title: fatto ? "A posto" : p.esito === "saltato" ? "Saltato" : "Da fare", "aria-hidden": "true" }); };
  const pulsante = (testo, fn, cls) => h("button", { class: cls || "s", type: "button", onclick: fn }, testo);

  const dettaglio = (p) => {
    const v = p.verifica || {}, msg = h("div"), out = [];
    const ok = (t) => msg.replaceChildren(avviso(t, "ok")), no = (t) => msg.replaceChildren(avviso(t, "no"));
    const okPoi = (t) => { stato.avvioEsito = t; carica(); };   // si ridisegna con le verifiche nuove, e il messaggio resta
    if (stato.avvioEsito) { ok(stato.avvioEsito); stato.avvioEsito = null; }
    if (p.id === "benvenuto") {
      const box = h("div");
      out.push(box);
      if (dati.importabile) {
        api("GET", "/gestione/avvio/dalla-2").then(a => {
          if (!a.disponibile) { riempi(box, avviso(a.motivo || "La 2 non è raggiungibile", "avv")); return; }
          const det = { chiavi: a.chiavi.length ? "trovate: " + a.chiavi.join(", ") : "nessuna nella 2",
            computer: a.computer.length ? a.computer.map(c => c.nome + (c.modello ? " (" + c.modello + ")" : "")).join(", ") : "nessuno",
            garanzie: a.garanzie.map(g => g.nome + (g.complete ? " ✓" : "")).join(", "),
            google: a.google.length ? a.google.map(g => g.email).join(", ") : "nessun account",
            aggiornamenti: a.aggiornamenti ? "dalla stessa fonte della 2" : "non impostati" };
          const scelte = Object.keys(a.cose).map(k => { const c = h("input", { type: "checkbox", value: k }); c.checked = !(dati.importato || []).includes(k);
            return h("label", { class: "spunta" }, c, h("span", {}, h("b", {}, a.cose[k]), " — " + det[k] + ((dati.importato || []).includes(k) ? " (già copiato)" : ""))); });
          riempi(box, [h("h3", {}, "Copia dalla 2"), h("p", { class: "sotto" }, "Si copia e basta: nella 2 non cambia nulla. I segreti restano cifrati."), scelte,
            pulsante("Copia le voci scelte", async () => {
              const cose = scelte.map(l => l.querySelector("input")).filter(c => c.checked).map(c => c.value);
              try { const r = await api("POST", "/gestione/avvio/dalla-2", { cose }); okPoi("Copiato: " + Object.entries(r.copiato).map(([k, n]) => a.cose[k] + " (" + n + ")").join(", ")); }
              catch (e) { no(e.message); }
            }, "p")]);
        }).catch(e => riempi(box, avviso(e.message, "no")));
      } else box.append(h("p", { class: "sotto" }, "Questa installazione non è collegata a una 2: si parte da zero."));
    }
    if (p.id === "ia") {
      out.push(h("ul", {}, Object.entries(v.chiavi || {}).map(([n, c]) => h("li", {}, (c ? "✓ " : "— ") + { anthropic: "Claude (Anthropic)", openai: "OpenAI", xai: "Grok" }[n] + (c ? " collegato" : " senza chiave"))),
        h("li", {}, (v.computer || []).length ? "✓ Computer locali: " + v.computer.join(", ") : "— Nessun computer locale")),
        h("div", { class: "azioni" }, pulsante("Chiavi, modelli e garanzie", () => vai("impostazioni", "sicurezza")), pulsante("Computer locali e prova", () => vai("computer"))));
      if (!(v.chiavi || {}).anthropic) out.push(avviso("Aurora ha bisogno della chiave di Claude (Anthropic).", "avv"));
    }
    if (p.id === "chi") {
      const nome = h("input", { type: "text", maxlength: 120, placeholder: "es. Logos di Lorenzo Zeppa" }), terr = h("input", { type: "text", maxlength: 200, placeholder: "es. Liguria, Italia, Europa" });
      const prof = h("textarea", { rows: 4, maxlength: 3000, placeholder: "Che cosa fai e che cosa offri, in poche righe." }), cli = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Clienti e collaboratori ideali: chi sono, dove, di che dimensione." });
      out.push(h("p", { class: "sotto" }, v.attivita ? "Attività già descritte: " + v.attivita + ". Puoi aggiungerne un'altra." : "Descrivi la tua prima attività (le altre le aggiungi dopo, da Lavoro › Schede d'impresa)."),
        h("label", {}, "Nome dell'attività", nome), h("label", {}, "Zona in cui lavori", terr), h("label", {}, "Che cosa fai e che cosa offri", prof), h("label", {}, "Clienti e collaboratori ideali", cli),
        h("div", { class: "azioni" }, pulsante("Salva l'attività", async () => {
          try { await api("POST", "/gestione/avvio/attivita", { nome: nome.value, territorio: terr.value, profilo: prof.value, clienti: cli.value }); okPoi("Salvata."); } catch (e) { no(e.message); }
        }, "p")));
    }
    if (p.id === "posta") {
      out.push(h("ul", {}, h("li", {}, (v.caselle || []).length ? "✓ Gmail collegato: " + v.caselle.join(", ") : "— Nessuna casella Gmail collegata"),
        h("li", {}, v.affidata ? "✓ Posta legge la casella" : "— Posta non ha ancora una casella"), h("li", {}, "Invio: con la tua approvazione (le email restano in Posta › Da approvare)")),
        avviso("Se nella 2 ci sono agenti che leggono o rispondono alla stessa casella, spegni la posta lì (scheda di ciascun agente) per non avere due agenti sulle stesse email.", "avv"),
        h("div", { class: "azioni" }, pulsante("Collega Google o altre caselle", () => vai("sez", "collegamenti")), pulsante("Scheda di Posta", () => vai("agenti"))));
    }
    if (p.id === "calendario") {
      out.push(h("ul", {}, h("li", {}, (v.calendar ? "✓ " : "— ") + "Calendario"), h("li", {}, (v.drive ? "✓ " : "— ") + "Drive (cartella Opifex con la regola d'ordine)")),
        h("div", { class: "azioni" }, pulsante("Apri il collegamento Google", () => vai("sez", "collegamenti"))));
    }
    if (p.id === "memoria") {
      const indirizzo = location.origin;
      out.push(h("ol", { class: "passi-avvio" },
        h("li", {}, "Sul computer con l'archivio apri l'app ", h("b", {}, "Opifex-Archivio"), ". Se non ce l'hai: ", h("a", { href: "/desktop/IndiceArchivio.exe", download: "Opifex-Archivio.exe" }, "scarica l'app per Windows"), "."),
        h("li", {}, "Nell'app apri la scheda ", h("b", {}, "Opifex"), " e come indirizzo scrivi ", h("code", { class: "copiabile" }, indirizzo), "."),
        h("li", {}, "Entra con la stessa email e password che usi qui."),
        h("li", {}, "Lascia l'app aperta: quando il computer è acceso, Aurora può cercare nella tua memoria.")),
        v.collegata ? avviso("✓ L'app è collegata: la memoria è raggiungibile.", "ok") : avviso("L'app non risulta ancora collegata. Questa pagina si aggiorna da sola.", "avv"),
        h("p", { class: "aiuto" }, "L'app si collega a un Opifex alla volta: se la colleghi qui, la 2 non userà più questo computer per le Finestre."),
        h("div", { class: "azioni" }, pulsante("Dai ad Aurora e Posta l'accesso alla memoria", async () => {
          try { const r = await api("POST", "/gestione/avvio/memoria-agenti", {}); ok(r.collegata ? "Fatto: Aurora e Posta possono cercare nella tua memoria." : "Fatto. Appena l'app sarà collegata, potranno usarla."); } catch (e) { no(e.message); }
        }, "p")));
      if (!v.collegata) stato.attesa = setTimeout(() => { if (stato.vista === "avvio" && stato.passoAvvio === "memoria") carica(); }, 6000);
    }
    if (p.id === "telefono") {
      out.push(h("ul", {}, h("li", {}, (v.app ? "✓ " : "— ") + "App sul telefono" + (v.app ? " (" + v.app + " dispositivi)" : "")), h("li", {}, (v.telegram ? "✓ " : "— ") + "Telegram")),
        h("div", { class: "azioni" }, pulsante("App sul telefono", () => vai("impostazioni", "app")), pulsante("Telegram", () => vai("impostazioni", "canali"))));
    }
    if (p.id === "radar") {
      out.push(h("p", { class: "sotto" }, v.temi ? "Temi del Radar: " + v.temi + "." : "Nessun tema ancora. Te ne propongo uno a partire dalle tue attività: lo trovi spento, da controllare e accendere."),
        h("div", { class: "azioni" }, pulsante("Attiva il Radar e proponi un tema", async () => {
          try { await api("POST", "/gestione/avvio/radar", {}); okPoi("Fatto. Controlla il tema in Contatti › Radar e accendilo."); } catch (e) { no(e.message); }
        }, "p"), pulsante("Apri il Radar", () => { stato.crmTab = "radar"; vai("crm"); })));
    }
    if (p.id === "squadra") {
      out.push(h("ul", {}, (v.agenti || []).map(a => h("li", {}, h("b", {}, a.nome), " — " + a.modello))),
        h("p", { class: "sotto" }, "Prima prova: apri la chat e chiedi ad Aurora «Che cosa c'è di importante nella mia posta?»."),
        h("div", { class: "azioni" }, pulsante("Apri la chat con Aurora", () => vai("chat"), "p"), pulsante("Vedi la squadra", () => vai("agenti"))));
    }
    const i = dati.passi.findIndex(x => x.id === p.id);
    return h("div", { class: "carta avvio-passo" },
      h("div", { class: "sotto" }, "Passo " + (i + 1) + " di " + dati.passi.length),
      h("h3", {}, p.titolo), h("p", {}, AVVIO_AIUTO[p.id] || ""), out, msg,
      h("div", { class: "azioni avvio-piede" },
        pulsante(i === dati.passi.length - 1 ? "Ho finito" : "Fatto, avanti", () => segna(p.id, "fatto", true), "p"),
        pulsante("Salta per ora", () => segna(p.id, "saltato", true)),
        p.esito ? pulsante("Riapri il passo", () => segna(p.id, "", false)) : null));
  };

  const disegnaTutto = () => {
    const p = dati.passi.find(x => x.id === stato.passoAvvio) || dati.passi[0];
    riempi(corpo, [
      h("h2", {}, "Avvio guidato"),
      h("p", { class: "sotto" }, "Completati " + dati.completati + " di " + dati.totale + ". Puoi tornare qui quando vuoi da Oggi › Avvio guidato."),
      h("div", { class: "avvio-griglia" },
        h("nav", { class: "avvio-elenco", "aria-label": "Passi dell'avvio" }, dati.passi.map((x, k) => h("button", { type: "button", class: x.id === p.id ? "attivo" : "", "aria-current": x.id === p.id ? "step" : null,
          onclick: () => { stato.passoAvvio = x.id; disegnaTutto(); } }, spia(x), h("span", {}, (k + 1) + ". " + x.titolo)))),
        dettaglio(p))]);
  };
  const carica = async () => {
    if (stato.attesa) { clearTimeout(stato.attesa); stato.attesa = null; }
    try { dati = await api("GET", "/gestione/avvio"); stato.avvioFatti = dati.completati; disegnaTutto(); }
    catch (e) { riempi(corpo, avviso(e.message, "no")); }
  };
  corpo.append(h("p", { class: "sotto" }, "Carico…"));
  carica();
  return corpo;
}
