"use strict";
// Fornitori AI: chiavi (cifrate), stato di funzionamento e registrazione di nuovi modelli.

function blocchiFornitori() {
  const corpo = h("div");
  const verifica = h("div");
  const NOMI = { anthropic: "Anthropic (Claude)", openai: "OpenAI (ChatGPT)", xai: "xAI (Grok)" };
  const ORIGINE = { app: "chiave inserita nell'app", server: "chiave nel file .env del server", mancante: "chiave mancante" };
  const carica = async () => {
    let origini = {};
    try { origini = await api("GET", "/gestione/fornitori/chiavi"); } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); return; }
    const schede = Object.keys(NOMI).map(n => {
      const campo = h("input", { type: "password", autocomplete: "off", placeholder: "Incolla qui la chiave API (non viene mai mostrata dopo il salvataggio)" });
      const msg = h("div");
      return h("div", { class: "carta" }, h("div", { class: "nome" }, NOMI[n]),
        h("div", { class: "sotto" }, "Stato: " + ORIGINE[origini[n]]),
        h("label", {}, "Chiave API", campo), msg,
        h("div", { class: "azioni" },
          h("button", { class: "p", onclick: async () => {
            try { await api("PUT", "/gestione/fornitori/" + n + "/chiave", { chiave: campo.value }); campo.value = ""; await carica(); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva chiave"),
          origini[n] === "app" ? h("button", { class: "s", onclick: async () => {
            if (!confirm("Rimuovere la chiave inserita nell'app?")) return;
            try { await api("PUT", "/gestione/fornitori/" + n + "/chiave", { chiave: null }); await carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Rimuovi") : null));
    });
    // nuovo modello
    const forn = h("select", {}, Object.keys(NOMI).map(n => h("option", { value: n }, NOMI[n])));
    const nome = h("input", { type: "text", maxlength: 80, placeholder: "Nome esatto del modello, es. gpt-4.1" });
    const fascia = h("select", {}, ["economico", "standard", "avanzato"].map(f => h("option", { value: f }, f))); fascia.value = "standard";
    const ci = h("input", { type: "number", min: 0, step: "any", placeholder: "facoltativo" });
    const co = h("input", { type: "number", min: 0, step: "any", placeholder: "facoltativo" });
    const msgM = h("div");
    riempi(corpo, [
      h("div", { class: "griglia" }, schede),
      h("p", { class: "aiuto" }, "La chiave salvata qui è cifrata e ha la precedenza su quella del file .env. Le chiavi API sono a pagamento a consumo e separate dagli abbonamenti (ChatGPT Plus, Grok)."),
      h("h4", {}, "Modelli registrati"),
      h("p", { class: "sotto" }, (stato.opzioni.modelli || []).map(m => m.nome + " (" + m.fornitore + ")").join(" · ")),
      h("div", { class: "carta" }, h("div", { class: "nome" }, "Registra un modello"),
        h("div", { class: "riga" }, h("label", {}, "Fornitore", forn), h("label", {}, "Nome del modello", nome), h("label", {}, "Livello", fascia)),
        h("div", { class: "riga" }, h("label", {}, "Costo input per milione di token", ci), h("label", {}, "Costo output per milione di token", co)), msgM,
        h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
          try { await api("POST", "/gestione/modelli", { fornitore: forn.value, nome: nome.value.trim(), fascia: fascia.value,
              costo_input_per_milione: ci.value === "" ? null : Number(ci.value), costo_output_per_milione: co.value === "" ? null : Number(co.value) });
            await ricarica(); } catch (e) { msgM.replaceChildren(avviso(e.message, "no")); } } }, "Registra"))),
    ]);
  };
  carica();
  const bVer = h("button", { class: "p", onclick: async (e) => {
    const b = e.currentTarget; b.disabled = true; b.textContent = "Verifica in corso…"; verifica.replaceChildren();
    try {
      const r = await api("POST", "/gestione/fornitori/verifica");
      verifica.replaceChildren(h("div", { class: "griglia" }, r.map(x => h("div", { class: "carta" },
        h("div", { class: "nome" }, (x.ok ? "🟢 " : "🔴 ") + NOMI[x.fornitore]),
        h("div", { class: "sotto" }, x.modello ? "Modello provato: " + x.modello : "Nessun modello registrato"),
        h("div", { class: "sotto" }, x.ok ? "Attivo · risposta in " + x.ms + " ms" : "Non funziona: " + x.dettaglio)))));
    } catch (er) { verifica.replaceChildren(avviso(er.message, "no")); }
    b.disabled = false; b.textContent = "Verifica ora";
  } }, "Verifica ora");
  return [h("h3", {}, "Stato dei sistemi AI"),
    h("p", { class: "aiuto" }, "Fa una richiesta minima a ciascun fornitore con il suo modello più economico: costa una frazione di centesimo."),
    h("div", { class: "azioni" }, bVer), verifica,
    h("h3", {}, "Chiavi e modelli"), corpo];
}

// Posta generica (IMAP, es. Aruba): l'agente legge e prepara bozze, non invia mai.
function bloccoPosta() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/posta");
      const et = h("input", { type: "text", maxlength: 60, placeholder: "Es. Posta Logos" });
      const em = h("input", { type: "email", maxlength: 200, placeholder: "nome@tuodominio.it" });
      const host = h("input", { type: "text", value: "imaps.aruba.it", maxlength: 253 });
      const porta = h("input", { type: "number", value: 993 });
      const ut = h("input", { type: "text", maxlength: 200, placeholder: "Di solito è l'indirizzo email completo" });
      const pw = h("input", { type: "password", autocomplete: "off", placeholder: "Password della casella" });
      const msg = h("div");
      const STATO = { attiva: "attiva", errore: "errore", da_provare: "da provare" };
      riempi(corpo, [
        d.caselle.length ? d.caselle.map(c => {
          const opz = a => h("option", { value: a.id }, a.nome + (a.dipartimento ? " (" + a.dipartimento + ")" : ""));
          const sel = h("select", {}, h("option", { value: "" }, "— nessun agente —"),
            h("optgroup", { label: "Dipartimenti che gestiscono la posta" }, d.agenti.filter(a => a.naturale).map(opz)),
            h("optgroup", { label: "Altri agenti (es. l'agente dei verbali)" }, d.agenti.filter(a => !a.naturale).map(opz)));
          sel.value = c.agenti.length ? String(c.agenti[0]) : "";
          const m2 = h("div");
          return h("div", { class: "carta", style: "margin-bottom:12px" },
            h("div", { class: "nome" }, c.etichetta + " — " + c.email),
            h("div", { class: "sotto" }, c.host + ":" + c.porta + " · stato: " + STATO[c.stato]),
            c.ultimo_errore ? avviso(c.ultimo_errore, "no") : null,
            h("div", { class: "sotto" }, "Agente a cui è affidata in esclusiva (legge e prepara bozze, mai invio; nessun altro agente la vede):"),
            sel, m2,
            h("div", { class: "azioni" },
              h("button", { class: "s", onclick: async () => { try { const r = await api("PUT", "/gestione/posta/" + c.id + "/agente", { agente_id: sel.value ? Number(sel.value) : null }); m2.replaceChildren(avviso("Salvato", "ok"), r.avviso ? avviso(r.avviso, "avv") : null); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
              h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/gestione/posta/" + c.id + "/prova"); m2.replaceChildren(avviso(r.esito, r.ok ? "ok" : "no")); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Prova"),
              h("button", { class: "r", onclick: async () => { if (!confirm("Scollegare questa casella?")) return; try { await api("DELETE", "/gestione/posta/" + c.id); carica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Scollega")));
        }) : h("p", { class: "sotto" }, "Nessuna casella collegata."),
        h("div", { class: "carta" }, h("div", { class: "nome" }, "Collega una casella email (Aruba o altro)"),
          h("div", { class: "riga" }, h("label", {}, "Nome", et), h("label", {}, "Indirizzo email", em)),
          h("div", { class: "riga" }, h("label", {}, "Server IMAP", host), h("label", {}, "Porta", porta)),
          h("div", { class: "riga" }, h("label", {}, "Utente", ut), h("label", {}, "Password", pw)),
          h("p", { class: "aiuto" }, "La password viene cifrata e non è più visibile. Gli agenti possono cercare, leggere e preparare bozze nella cartella Bozze; non inviano e non cancellano. Per le caselle Aruba il server è imaps.aruba.it, porta 993." ), msg,
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { const r = await api("POST", "/gestione/posta", { etichetta: et.value, email: em.value, host: host.value, porta: Number(porta.value), utente: ut.value || null, password: pw.value });
              await carica(); if (!r.ok) corpo.prepend(avviso(r.esito, "no")); }
            catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Collega e prova")))]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h3", {}, "Posta (IMAP, es. Aruba)"), corpo];
}

// Backup cifrato, tetto di spesa e allarmi
function vistaSistema() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/sistema");
      const b = d.backup, s = d.spesa;
      const msg = h("div");
      const giorno = h("input", { type: "number", min: 0, step: "any", value: s.limiti.giorno || "", placeholder: "nessun limite" });
      const mese = h("input", { type: "number", min: 0, step: "any", value: s.limiti.mese || "", placeholder: "nessun limite" });
      const KB = (n) => (n / 1024 / 1024).toFixed(1) + " MB";
      const u = b.ultimo;
      riempi(corpo, [
        h("h2", {}, "Backup e costi"),
        h("h3", {}, "Backup automatico"),
        h("div", { class: "carta" },
          !b.chiave_creata ? avviso("Prima di tutto crea la chiave di backup: senza, il backup non parte.", "avv") : null,
          u ? avviso((u.ok ? "Ultimo backup riuscito: " : "Ultimo tentativo FALLITO: ") + new Date(u.quando).toLocaleString("it-IT") + " · " + (u.ok ? KB(u.dimensione) + " · " + (u.drive || "") : u.dettaglio), u.ok ? "ok" : "no")
            : h("p", { class: "sotto" }, "Nessun backup ancora."),
          h("p", { class: "aiuto" }, "Ogni giorno Opifex salva il database e il file .env (con la chiave della cassaforte) in un archivio cifrato: una copia sul server (ultime " + b.conserva + ") e una su Drive, nella cartella Backup. L'archivio si apre solo con la chiave di backup. Su Drive i vecchi file non vengono cancellati: pulisci tu ogni tanto."),
          h("div", { class: "interruttore" }, (() => { const c = h("input", { type: "checkbox" }); c.checked = b.attivo; c.addEventListener("change", async () => { try { await api("PUT", "/gestione/sistema/backup", { attivo: c.checked }); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } }); return c; })(), h("span", {}, "Backup automatico attivo")),
          msg,
          h("div", { class: "azioni" },
            h("button", { class: "p", onclick: async (e) => { const bt = e.currentTarget; bt.disabled = true; bt.textContent = "Backup in corso…"; msg.replaceChildren();
              try { const r = await api("POST", "/gestione/sistema/backup/ora"); msg.replaceChildren(avviso(r.ok ? "Backup fatto (" + KB(r.dimensione) + "). " + (r.drive || "") : r.dettaglio, r.ok ? "ok" : "no")); }
              catch (x) { msg.replaceChildren(avviso(x.message, "no")); } bt.disabled = false; bt.textContent = "Esegui un backup adesso"; carica(); } }, "Esegui un backup adesso"),
            h("button", { class: "s", onclick: async () => {
              const rigenera = b.chiave_creata;
              if (rigenera && !confirm("Rigenerare la chiave? I backup già fatti si apriranno solo con la VECCHIA chiave.")) return;
              try { const r = await api("POST", "/gestione/sistema/backup/chiave" + (rigenera ? "?rigenera=true" : "")); 
                msg.replaceChildren(avviso("CHIAVE DI BACKUP (si vede una volta sola, conservala in un posto sicuro fuori dal server, per esempio nel tuo gestore di password): " + r.chiave, "avv")); carica(); }
              catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, b.chiave_creata ? "Rigenera la chiave" : "Crea la chiave di backup")),
          (() => { const r = b.ripristino; const bt = h("button", { class: "s", onclick: async () => { bt.disabled = true; bt.textContent = "Provo il ripristino…";
            try { const e = await api("POST", "/gestione/sistema/backup/prova-ripristino"); msg.replaceChildren(avviso(e.ok ? "Prova riuscita: " + e.dettaglio : "Prova FALLITA: " + e.dettaglio, e.ok ? "ok" : "no")); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); }
            bt.disabled = false; bt.textContent = "Prova il ripristino adesso"; carica(); } }, "Prova il ripristino adesso");
            return h("div", {}, r ? avviso((r.ok ? "Ultima prova di ripristino riuscita: " : "Ultima prova di ripristino FALLITA: ") + new Date(r.quando).toLocaleString("it-IT") + " · " + r.metodo + " · " + r.dettaglio, r.ok ? "ok" : "no")
              : h("p", { class: "sotto" }, "Il ripristino non è ancora stato provato: Opifex lo prova da solo ogni settimana."), h("div", { class: "azioni" }, bt)); })(),
          b.locali.length ? h("div", { class: "sotto" }, "Sul server (" + b.cartella + "): " + b.locali.slice(0, 5).map(x => x.nome.replace("opifex-backup-", "").replace(".enc", "") + " (" + KB(x.dimensione) + ")").join(" · ")) : null,
          h("p", { class: "aiuto" }, "Ripristino: copia il file .enc sul server e usa  python -m app.ripristina FILE.enc LA_TUA_CHIAVE CARTELLA  dalla cartella /opt/agenti: ottieni database.sql e env.txt. Poi psql con l'indirizzo del database < database.sql, e rimetti il .env.")),
        h("h3", {}, "Tetto di spesa"),
        h("div", { class: "carta" },
          h("p", { class: "aiuto" }, "Limite al costo stimato delle chiamate AI (nella valuta dei prezzi che hai inserito per i modelli, di solito dollari). All'80% ricevi un avviso su Telegram; al 100% gli agenti si fermano finché non alzi il limite o cambia il periodo. Lascia vuoto per nessun limite."),
          h("div", { class: "riga" }, h("label", {}, "Limite giornaliero", giorno), h("label", {}, "Limite mensile", mese)),
          h("div", { class: "sotto" }, "Speso oggi: " + s.consumo.giorno.toFixed(2) + " · questo mese: " + s.consumo.mese.toFixed(2)),
          s.modelli_senza_prezzo.length ? avviso("Questi modelli sono in uso ma senza prezzo: la loro spesa non viene contata. Inserisci i prezzi in Sicurezza e garanzie → Registra un modello: " + s.modelli_senza_prezzo.join(", "), "avv") : null,
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { await api("PUT", "/gestione/sistema/spesa", { giorno: giorno.value === "" ? null : Number(giorno.value), mese: mese.value === "" ? null : Number(mese.value) }); msg.replaceChildren(avviso("Limiti salvati", "ok")); carica(); }
            catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Salva i limiti"))),
        h("h3", {}, "Allarmi"),
        h("div", { class: "carta" },
          h("p", { class: "aiuto" }, "Ogni 10 minuti Opifex controlla disco del server, errori ripetuti dei fornitori AI e stato del backup. Se qualcosa non va ricevi un messaggio urgente su Telegram (e lo stesso allarme non si ripete prima di 6 ore)."),
          h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/gestione/sistema/allarmi/prova"); msg.replaceChildren(avviso(r.inviati.length ? "Allarmi inviati: " + r.inviati.join(" · ") : "Controllo fatto: nessun problema.", r.inviati.length ? "avv" : "ok")); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Controlla adesso"))),
      ]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}


function bloccoCanva() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const s = await api("GET", "/gestione/canva");
      const cid = h("input", { type: "text", value: s.client_id || "", maxlength: 300, placeholder: "ID client dell'app Canva" });
      const sec = h("input", { type: "password", autocomplete: "off", placeholder: s.client_configurato ? "•••••• (già salvato)" : "Segreto client" });
      const msg = h("div");
      const mostra = (t, tipo) => msg.replaceChildren(avviso(t, tipo));
      if (s.esito && s.esito.startsWith("ok:")) mostra("Canva collegato: " + s.esito.slice(3), "ok");
      else if (s.esito) mostra(s.esito, "no");
      if (s.errore) mostra(s.errore, "no");
      corpo.replaceChildren(h("div", { class: "carta" },
        h("p", { class: "sotto" }, s.collegato ? "Collegato" + (s.nome ? " come " + s.nome : "") + "." : "Non collegato."),
        msg,
        s.collegato ? h("div", { class: "azioni" },
          h("button", { class: "s", onclick: async () => { try { mostra((await api("POST", "/gestione/canva/prova")).esito, "ok"); } catch (x) { mostra(x.message, "no"); } } }, "Prova"),
          h("button", { class: "s", onclick: async () => { if (!confirm("Scollegare Canva?")) return; try { await api("DELETE", "/gestione/canva"); carica(); } catch (x) { mostra(x.message, "no"); } } }, "Scollega")) : null,
        h("p", { class: "aiuto" }, "1. Su canva.com/developers crea un'integrazione (Connect API) e attiva i permessi: design:meta:read, design:content:read, design:content:write, asset:read, asset:write, profile:read. 2. Come URL di reindirizzamento inserisci: " + s.redirect + " 3. Incolla qui ID e segreto (il segreto viene cifrato), poi premi «Collega Canva». Serve un account Canva a pagamento; i design si creano e si esportano, non si riempiono in automatico. Poi abilita Canva sugli agenti che devono usarlo, nella loro scheda."),
        h("label", {}, "ID client", cid), h("label", {}, "Segreto client", sec),
        h("div", { class: "azioni" },
          h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/canva/client", { client_id: cid.value.trim(), client_secret: sec.value.trim() || null }); carica(); } catch (x) { mostra(x.message, "no"); } } }, "Salva credenziali"),
          s.client_configurato ? h("button", { class: "p", onclick: async () => { try { window.location.href = (await api("POST", "/gestione/canva/autorizza")).url; } catch (x) { mostra(x.message, "no"); } } }, s.collegato ? "Ricollega Canva" : "Collega Canva") : null)));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}


function bloccoCosti() {
  const corpo = h("div");
  const carica = async () => {
    try {
      const q = await api("GET", "/gestione/costi");
      const msg = h("div");
      const campo = (f, nome) => {
        const i = h("input", { type: "password", autocomplete: "off", placeholder: q.chiavi[f] ? "•••••• (già salvata)" : "Chiave admin " + nome });
        return h("label", {}, "Chiave admin " + nome, i, h("div", { class: "azioni" },
          h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/costi/chiavi", { fornitore: f, chiave: i.value.trim() || null }); carica(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, i.value ? "Salva" : "Salva / rimuovi")));
      };
      corpo.replaceChildren(h("div", { class: "carta" },
        h("pre", { class: "sotto", style: "white-space:pre-wrap" }, q.testo),
        h("p", { class: "aiuto" }, "Per vedere la spesa reale (non solo la stima) inserisci le chiavi ADMIN dei fornitori: Anthropic (console → Settings → Admin keys) e OpenAI (Organization → Admin keys). Sono diverse dalle chiavi normali, sono solo di lettura sui costi e vengono cifrate. Aurora e le sentinelle le usano per consultare i costi."),
        msg, campo("anthropic", "Anthropic"), campo("openai", "OpenAI")));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return corpo;
}
