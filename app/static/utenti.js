"use strict";
// Accesso a più passi (password personale, secondo fattore), account personale e gestione dei collaboratori.

function disegnaQr(matrice) {
  const modulo = 6, bordo = 4, n = matrice.length, lato = (n + bordo * 2) * modulo;
  const c = h("canvas", { width: lato, height: lato, role: "img", "aria-label": "Codice QR per l'app di autenticazione", style: "max-width:100%;background:#fff;border-radius:6px" });
  const g = c.getContext("2d");
  g.fillStyle = "#fff"; g.fillRect(0, 0, lato, lato);
  g.fillStyle = "#000";
  matrice.forEach((riga, y) => riga.forEach((v, x) => { if (v) g.fillRect((x + bordo) * modulo, (y + bordo) * modulo, modulo, modulo); }));
  return c;
}

function schermataAccesso(titolo, contenuto) {
  radice.replaceChildren(h("div", { class: "accesso" }, h("h2", {}, "Opifex"), h("div", { class: "carta" }, h("div", { class: "nome" }, titolo), contenuto)));
}

async function proseguiAccesso(r) {
  const msg = h("div");
  const passo = async (f) => { msg.replaceChildren(); try { await proseguiAccesso(await f()); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } };
  if (r.passo === "ok") {
    token = r.token;
    try { sessionStorage.setItem("token", token); } catch (e) { /* ignora */ }
    if (r.codici_recupero) return mostraCodici(r.codici_recupero, () => avvia());
    if (r.recupero_usato) stato.avvisoRecupero = "Hai usato un codice di recupero: te ne restano " + r.codici_rimasti + ". Genera nuovi codici dalla scheda Account.";
    return avvia();
  }
  if (r.passo === "cambia_password") {
    const a = h("input", { type: "password", autocomplete: "new-password", minlength: 10 });
    const b = h("input", { type: "password", autocomplete: "new-password", minlength: 10 });
    return schermataAccesso("Scegli la tua password", h("form", { onsubmit: (ev) => { ev.preventDefault();
      if (a.value !== b.value) { msg.replaceChildren(avviso("Le due password non coincidono", "no")); return; }
      passo(() => api("POST", "/login/password", { sfida: r.sfida, nuova: a.value })); } },
      h("p", { class: "aiuto" }, "Quella che ti hanno dato è temporanea. Scegline una tua, di almeno 10 caratteri."),
      h("label", {}, "Nuova password", a), h("label", {}, "Ripetila", b), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Continua"))));
  }
  if (r.passo === "codice") {
    const cod = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 12, required: true, placeholder: "123456" });
    return schermataAccesso("Codice di verifica", h("form", { onsubmit: (ev) => { ev.preventDefault(); passo(() => api("POST", "/login/2fa", { sfida: r.sfida, codice: cod.value.trim() })); } },
      h("p", { class: "aiuto" }, "Apri l'app di autenticazione e scrivi il codice a 6 cifre. Se hai perso il telefono, usa uno dei codici di recupero."),
      h("label", {}, "Codice", cod), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Entra"), h("button", { class: "s", type: "button", onclick: () => mostraAccesso() }, "Annulla"))));
  }
  if (r.passo === "configura_2fa") {
    schermataAccesso("Attiva il secondo fattore", h("p", { class: "aiuto" }, "Preparo il codice…"));
    let a;
    try { a = await api("POST", "/login/2fa/avvia", { sfida: r.sfida }); } catch (e) { return mostraAccesso(e.message); }
    const cod = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 8, required: true, placeholder: "123456" });
    return schermataAccesso("Attiva il secondo fattore", h("form", { onsubmit: (ev) => { ev.preventDefault(); passo(() => api("POST", "/login/2fa/conferma", { sfida: r.sfida, codice: cod.value.trim() })); } },
      h("p", { class: "aiuto" }, "1. Installa sul telefono un'app di autenticazione (Google Authenticator, Microsoft Authenticator, Aegis, 1Password…). 2. Inquadra il codice QR. 3. Scrivi qui il codice a 6 cifre che mostra."),
      disegnaQr(a.matrice),
      h("p", { class: "aiuto" }, "Se non puoi inquadrarlo, inserisci a mano questa chiave: ", h("code", {}, a.segreto)),
      h("label", {}, "Codice mostrato dall'app", cod), msg,
      h("div", { class: "azioni" }, h("button", { class: "p", type: "submit" }, "Conferma e entra"))));
  }
  mostraAccesso("Risposta non prevista dal server");
}

function mostraCodici(codici, dopo) {
  schermataAccesso("Codici di recupero", h("div", {},
    avviso("Salvali adesso in un posto sicuro (gestore di password, foglio stampato). Non verranno mostrati di nuovo. Ognuno vale una sola volta e serve se perdi il telefono.", "avv"),
    h("pre", { class: "risposta", style: "font-size:1.1em;letter-spacing:.06em" }, codici.join("\n")),
    h("div", { class: "azioni" },
      h("button", { class: "s", onclick: () => { try { navigator.clipboard.writeText(codici.join("\n")); } catch (e) { /* ignora */ } } }, "Copia"),
      h("button", { class: "p", onclick: dopo }, "Li ho salvati, continua"))));
}

function vistaAccount() {
  const corpo = h("div");
  const msg = h("div");
  const carica = async () => {
    try {
      const s = await api("GET", "/account");
      const att = h("input", { type: "password", autocomplete: "current-password" });
      const nuova = h("input", { type: "password", autocomplete: "new-password", minlength: 10 });
      const nuova2 = h("input", { type: "password", autocomplete: "new-password", minlength: 10 });
      const pw2 = h("input", { type: "password", autocomplete: "current-password" });
      const cod = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 8, placeholder: "Codice a 6 cifre" });
      const nuovoToken = (t) => { token = t; try { sessionStorage.setItem("token", t); } catch (e) { /* ignora */ } };
      const mostra = (testo, tipo) => msg.replaceChildren(avviso(testo, tipo));
      const sezione2fa = [];
      if (s.secondo_fattore) {
        sezione2fa.push(avviso("Secondo fattore attivo. Codici di recupero ancora validi: " + s.codici_recupero_rimasti + ".", "ok"),
          h("p", { class: "aiuto" }, "Per generare nuovi codici di recupero" + (s.ruolo === "titolare" ? " o per spegnere il secondo fattore" : "") + " scrivi la password e un codice dell'app."),
          h("label", {}, "Password", pw2), h("label", {}, "Codice", cod),
          h("div", { class: "azioni" },
            h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/account/2fa/nuovi-codici", { password: pw2.value, codice: cod.value.trim() });
              mostraCodici(r.codici_recupero, () => disegna()); } catch (e) { mostra(e.message, "no"); } } }, "Nuovi codici di recupero"),
            s.ruolo === "titolare" ? h("button", { class: "s", onclick: async () => { if (!confirm("Spegnere il secondo fattore?")) return;
              try { const r = await api("POST", "/account/2fa/disattiva", { password: pw2.value, codice: cod.value.trim() }); nuovoToken(r.token); carica(); } catch (e) { mostra(e.message, "no"); } } }, "Spegni il secondo fattore") : null));
      } else {
        sezione2fa.push(avviso("Il secondo fattore non è attivo. Consigliato: protegge l'accesso anche se la password venisse scoperta.", "avv"),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try {
              const a = await api("POST", "/account/2fa/avvia");
              const c2 = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 8, placeholder: "123456" });
              riempi(corpo, [h("div", { class: "carta" }, h("div", { class: "nome" }, "Attiva il secondo fattore"),
                h("p", { class: "aiuto" }, "Inquadra il QR con un'app di autenticazione e scrivi il codice a 6 cifre."), disegnaQr(a.matrice),
                h("p", { class: "aiuto" }, "Chiave manuale: ", h("code", {}, a.segreto)), h("label", {}, "Codice", c2), msg,
                h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try {
                  const r = await api("POST", "/account/2fa/conferma", { codice: c2.value.trim() }); nuovoToken(r.token); mostraCodici(r.codici_recupero, () => disegna()); } catch (e) { mostra(e.message, "no"); } } }, "Conferma"),
                  h("button", { class: "s", onclick: carica }, "Annulla")))]);
            } catch (e) { mostra(e.message, "no"); } } }, "Attiva il secondo fattore")));
      }
      riempi(corpo, [
        stato.avvisoRecupero ? avviso(stato.avvisoRecupero, "avv") : null,
        h("div", { class: "carta" }, h("div", { class: "nome" }, s.nome), h("div", { class: "sotto" }, s.email + " · " + (s.ruolo === "titolare" ? "Titolare" : "Collaboratore"))),
        h("h3", {}, "Password"),
        h("div", { class: "carta" }, h("label", {}, "Password attuale", att), h("label", {}, "Nuova password (almeno 10 caratteri)", nuova), h("label", {}, "Ripeti la nuova", nuova2),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            if (nuova.value !== nuova2.value) return mostra("Le due password non coincidono", "no");
            try { const r = await api("POST", "/account/password", { attuale: att.value, nuova: nuova.value }); nuovoToken(r.token);
              att.value = nuova.value = nuova2.value = ""; mostra("Password cambiata. Le altre sessioni aperte sono state chiuse.", "ok"); } catch (e) { mostra(e.message, "no"); } } }, "Cambia password"))),
        h("h3", {}, "Voce"),
        h("div", { class: "carta" },
          h("div", { class: "interruttore" }, (() => { const c = h("input", { type: "checkbox" }); c.checked = Voce.leggiRisposte; c.addEventListener("change", () => { Voce.leggiRisposte = c.checked; }); return c; })(),
            h("span", {}, "Leggi ad alta voce le risposte degli agenti (su questo dispositivo)")),
          h("p", { class: "aiuto" }, Voce.supportoLettura ? "Nella Chat trovi il pulsante «Parla» per dettare i messaggi e il «Vivavoce» per conversare a voce." : "Questo browser non supporta la lettura vocale.")),
        h("h3", {}, "Secondo fattore"), h("div", { class: "carta" }, sezione2fa),
        Passkey.sezioneAccount(), Vetro.sezioneAccount(), msg]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Il mio account"), corpo];
}

function vistaUtenti() {
  const corpo = h("div");
  const msg = h("div");
  const quando = (t) => t ? new Date(t).toLocaleString("it-IT") : "mai";
  const mostraTemp = (titolo, pw) => msg.replaceChildren(h("div", { class: "carta" }, avviso(titolo, "ok"),
    h("div", { class: "nome", style: "letter-spacing:.08em" }, pw),
    h("p", { class: "aiuto" }, "Comunicala alla persona con un canale diverso dall'email di invito (di persona o per telefono). Non verrà mostrata di nuovo: al primo accesso dovrà sceglierne una sua e attivare il secondo fattore.")));
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/utenti");
      const nome = h("input", { type: "text", maxlength: 120 });
      const email = h("input", { type: "email", maxlength: 200 });
      const scelte = d.divisioni.map(v => ({ v, c: h("input", { type: "checkbox" }) }));
      const sceltaImp = d.aziende.map(z => ({ z, c: h("input", { type: "checkbox" }) }));
      riempi(corpo, [
        d.utenti.map(u => {
          const caselle = d.divisioni.map(v => { const c = h("input", { type: "checkbox" }); c.checked = u.divisioni.includes(v.id); return { v, c }; });
          const impU = d.aziende.map(z => { const c = h("input", { type: "checkbox" }); c.checked = (u.aziende || []).includes(z.id); return { z, c }; });
          return h("div", { class: "carta", style: "margin-bottom:12px" },
            h("div", { class: "nome" }, u.nome + (u.attivo ? "" : " (disattivato)")),
            h("div", { class: "sotto" }, u.email + " · " + (u.ruolo === "titolare" ? "Titolare" : "Collaboratore") + " · secondo fattore: " + (u.secondo_fattore ? "attivo" : "non ancora") +
              (u.password_temporanea ? " · password temporanea non ancora cambiata" : "") + " · ultimo accesso: " + quando(u.ultimo_accesso)),
            u.ruolo === "titolare" ? null : [
              h("div", { class: "sotto", style: "margin-top:8px" }, "Divisioni a cui può accedere:"),
              h("div", { class: "riga" }, caselle.map(({ v, c }) => h("label", { style: "flex:0 0 auto;margin-right:12px" }, c, " " + v.nome))),
              h("div", { class: "sotto", style: "margin-top:8px" }, "Imprese di cui vede progetti e task:"),
              h("div", { class: "riga" }, impU.map(({ z, c }) => h("label", { style: "flex:0 0 auto;margin-right:12px" }, c, " " + z.nome))),
              h("div", { class: "azioni" },
                h("button", { class: "s", onclick: async () => { msg.replaceChildren(); try { await api("PUT", "/gestione/utenti/" + u.id + "/aziende", { aziende: impU.filter(x => x.c.checked).map(x => x.z.id) }); msg.replaceChildren(avviso("Imprese salvate.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva imprese"),
                h("button", { class: "s", onclick: async () => { msg.replaceChildren(); try { await api("PUT", "/gestione/utenti/" + u.id + "/divisioni", { divisioni: caselle.filter(x => x.c.checked).map(x => x.v.id) }); msg.replaceChildren(avviso("Divisioni salvate.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva divisioni"),
                h("button", { class: "s", onclick: async () => { if (!confirm("Generare una nuova password temporanea per " + u.nome + "? Dovrà anche rifare il secondo fattore.")) return;
                  try { const r = await api("POST", "/gestione/utenti/" + u.id + "/reimposta"); mostraTemp("Nuova password temporanea per " + u.nome + ":", r.password_temporanea); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Reimposta accesso"),
                h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/utenti/" + u.id + "/attivo", { attivo: !u.attivo }); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, u.attivo ? "Disattiva" : "Riattiva"))]);
        }),
        msg,
        h("h3", {}, "Aggiungi un collaboratore"),
        h("div", { class: "carta" },
          h("label", {}, "Nome", nome), h("label", {}, "Email", email),
          h("div", { class: "sotto" }, "Divisioni a cui può accedere:"),
          h("div", { class: "riga" }, scelte.map(({ v, c }) => h("label", { style: "flex:0 0 auto;margin-right:12px" }, c, " " + v.nome))),
          h("div", { class: "sotto" }, "Imprese di cui vede progetti e task:"),
          h("div", { class: "riga" }, sceltaImp.map(({ z, c }) => h("label", { style: "flex:0 0 auto;margin-right:12px" }, c, " " + z.nome))),
          h("p", { class: "aiuto" }, "Riceverà una password temporanea da cambiare al primo accesso, e dovrà attivare l'app di autenticazione (obbligatoria per i collaboratori). Vede solo Chat e il proprio account, limitati alle divisioni scelte."),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            try { const r = await api("POST", "/gestione/utenti", { nome: nome.value.trim(), email: email.value.trim(), divisioni: scelte.filter(x => x.c.checked).map(x => x.v.id), aziende: sceltaImp.filter(x => x.c.checked).map(x => x.z.id) });
              await carica(); mostraTemp("Collaboratore creato. Password temporanea:", r.password_temporanea); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Crea collaboratore")))]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Utenti"), corpo];
}
