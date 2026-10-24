"use strict";
// Progetti (con cartelle su Google Drive) e account Google collegati.

function vistaProgetti() {
  const corpo = h("div");
  const msg = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/progetti");
      const nome = h("input", { type: "text", maxlength: 100, placeholder: "Es. Bando Interreg 2027" });
      const desc = h("input", { type: "text", maxlength: 500, placeholder: "Di cosa si tratta (facoltativo)" });
      const tutti = h("input", { type: "checkbox" }); tutti.checked = true;
      const scelte = d.agenti.map(a => ({ a, c: h("input", { type: "checkbox" }) }));
      const lista = h("div", { class: "riga", style: "display:none" }, scelte.map(({ a, c }) => h("label", { style: "flex:0 0 auto;margin-right:12px" }, c, " " + a.nome)));
      tutti.addEventListener("change", () => { lista.style.display = tutti.checked ? "none" : ""; });
      const attivi = d.progetti.filter(p => !p.archiviato), archiviati = d.progetti.filter(p => p.archiviato);
      const scheda = (p) => h("div", { class: "carta", style: "margin-bottom:12px" },
        h("div", { class: "nome" }, p.nome),
        p.descrizione ? h("div", { class: "sotto" }, p.descrizione) : null,
        h("div", { class: "sotto" }, "Agenti coinvolti: " + p.agenti.length + " · Drive: " + ({ ok: "cartelle create", da_sincronizzare: "da creare", errore: "errore" })[p.drive_stato]),
        p.drive_errore && p.drive_stato === "errore" ? avviso(p.drive_errore, "no") : null,
        h("div", { class: "azioni" },
          p.drive_url ? h("a", { href: p.drive_url, target: "_blank", rel: "noopener noreferrer" }, h("button", { class: "s", type: "button" }, "Apri su Drive")) : null,
          h("button", { class: "s", onclick: async (e) => { e.currentTarget.disabled = true; msg.replaceChildren();
            try { const r = await api("POST", "/gestione/progetti/" + p.id + "/sincronizza"); msg.replaceChildren(r.ok ? avviso("Cartelle aggiornate su Drive.", "ok") : avviso(r.errore, "no")); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); }
            carica(); } }, "Crea/aggiorna cartelle su Drive"),
          h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/progetti/" + p.id + "/archivia", { archiviato: !p.archiviato }); carica(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, p.archiviato ? "Riattiva" : "Archivia")));
      riempi(corpo, [
        d.drive_pronto ? null : avviso("Per creare le cartelle su Drive collega prima un account Google con Drive nella scheda Collegamenti: i progetti si creano comunque e le cartelle si generano dopo.", "avv"),
        attivi.length ? attivi.map(scheda) : h("p", { class: "sotto" }, "Nessun progetto."),
        archiviati.length ? [h("h3", {}, "Archiviati"), archiviati.map(scheda)] : null,
        msg,
        h("h3", {}, "Nuovo progetto"),
        h("div", { class: "carta" }, h("label", {}, "Nome", nome), h("label", {}, "Descrizione", desc),
          h("label", {}, tutti, " Coinvolgi tutti gli agenti attivi"), lista,
          h("p", { class: "aiuto" }, "Su Drive nasce Opifex → nome del progetto → agent (una cartella per ogni agente) e repository (documenti per tutta l'organizzazione). Gli output aggiornati stanno nella cartella del progetto. Archiviare un progetto non cancella mai nulla su Drive."),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async (e) => {
            msg.replaceChildren(); e.currentTarget.disabled = true;
            try { const r = await api("POST", "/gestione/progetti", { nome: nome.value, descrizione: desc.value, agenti: tutti.checked ? null : scelte.filter(x => x.c.checked).map(x => x.a.id) });
              await carica(); msg.replaceChildren(r.drive.ok ? avviso("Progetto creato e cartelle pronte su Drive.", "ok") : avviso("Progetto creato. Drive: " + r.drive.errore, "avv")); }
            catch (x) { msg.replaceChildren(avviso(x.message, "no")); e.currentTarget.disabled = false; } } }, "Crea progetto")))]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Progetti"), corpo];
}

function vistaCollegamenti() {
  const corpo = h("div");
  const msg = h("div");
  const mostra = (t, tipo) => msg.replaceChildren(avviso(t, tipo));
  const carica = async () => {
    try {
      const s = await api("GET", "/gestione/google");
      const cid = h("input", { type: "text", value: s.client_id || "", maxlength: 300, placeholder: "xxxx.apps.googleusercontent.com" });
      const sec = h("input", { type: "password", autocomplete: "off", placeholder: s.client_configurato ? "Segreto già salvato (scrivi solo per sostituirlo)" : "GOCSPX-…" });
      const etic = h("input", { type: "text", maxlength: 60, placeholder: "Nome per riconoscerlo, es. Xenia, Renovatio, Logos" });
      const serv = Object.entries(s.servizi).map(([k, t]) => ({ k, c: h("input", { type: "checkbox" }), t }));
      serv.forEach(x => { x.c.checked = true; });
      const radice = h("input", { type: "text", value: s.drive_radice_id || "", maxlength: 200 });
      const conDrive = s.account.filter(a => a.servizi.includes("drive"));
      const sceltaDrive = h("select", {}, h("option", { value: "" }, "— nessuno —"), conDrive.map(a => h("option", { value: a.id }, a.etichetta + " (" + a.email + ")")));
      sceltaDrive.value = s.drive_account_id || "";
      const esito = s.esito ? (s.esito.startsWith("ok:") ? avviso("Account collegato: " + s.esito.slice(3), "ok") : avviso(s.esito, "no")) : null;
      riempi(corpo, [
        esito,
        h("h3", {}, "Account Google collegati"),
        s.account.length ? s.account.map(a => h("div", { class: "carta", style: "margin-bottom:12px" },
          h("div", { class: "nome" }, a.etichetta + " — " + a.email),
          h("div", { class: "sotto" }, "Servizi: " + a.servizi.map(x => s.servizi[x] || x).join(", ")),
          a.ultimo_errore ? avviso(a.ultimo_errore, "no") : null,
          h("div", { class: "azioni" },
            h("button", { class: "s", onclick: async () => { msg.replaceChildren(); try { mostra((await api("POST", "/gestione/google/account/" + a.id + "/prova")).esito, "ok"); } catch (x) { mostra(x.message, "no"); } } }, "Prova"),
            h("button", { class: "s", onclick: async () => { if (!confirm("Scollegare " + a.email + "?")) return; try { await api("DELETE", "/gestione/google/account/" + a.id); carica(); } catch (x) { mostra(x.message, "no"); } } }, "Scollega"))))
          : h("p", { class: "sotto" }, "Nessun account collegato."),
        msg,
        s.client_configurato ? [
          h("h3", {}, "Collega un altro account"),
          h("div", { class: "carta" }, h("label", {}, "Nome", etic),
            h("div", { class: "sotto" }, "Cosa può usare Opifex di questo account:"),
            h("div", { class: "riga" }, serv.map(x => h("label", { style: "flex:0 0 auto;margin-right:14px" }, x.c, " " + x.t))),
            h("p", { class: "aiuto" }, "Google ti chiederà di scegliere l'account e di accettare i permessi. Gmail: gli agenti possono leggere e preparare bozze, mai inviare da soli. Puoi collegare quanti account vuoi, ripetendo l'operazione."),
            h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
              try { const r = await api("POST", "/gestione/google/autorizza", { etichetta: etic.value, servizi: serv.filter(x => x.c.checked).map(x => x.k) }); window.location.href = r.url; }
              catch (x) { mostra(x.message, "no"); } } }, "Collega con Google"))),
          h("h3", {}, "Drive per i progetti"),
          h("div", { class: "carta" }, h("label", {}, "Account che crea le cartelle", sceltaDrive),
            h("label", {}, "ID della cartella «Opifex» su Drive", radice),
            h("p", { class: "aiuto" }, "L'ID è la parte finale dell'indirizzo della cartella su Drive. Opifex vi crea dentro una cartella per ogni progetto."),
            h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("PUT", "/gestione/google/drive", { account_id: Number(sceltaDrive.value) || 0, radice_id: radice.value.trim() }); mostra("Salvato.", "ok"); } catch (x) { mostra(x.message, "no"); } } }, "Salva")))] : null,
        h("h3", {}, s.client_configurato ? "Credenziali Google (già inserite)" : "Prima configurazione (una volta sola)"),
        h("div", { class: "carta" },
          h("p", { class: "aiuto" }, "1. Su console.cloud.google.com crea un progetto e abilita le API Google Drive, Gmail e Google Calendar. 2. Schermata consenso OAuth: tipo «Esterno», aggiungi le tue email come utenti di test, poi pubblica l'app («In produzione»): in modalità test Google fa scadere il collegamento ogni 7 giorni. 3. Credenziali → ID client OAuth → «Applicazione web», con questo URI di reindirizzamento autorizzato: " + s.redirect + " 4. Incolla qui ID e segreto: il segreto viene cifrato e nessuno lo rivede."),
          h("label", {}, "ID client", cid), h("label", {}, "Segreto client", sec),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => { try { await api("PUT", "/gestione/google/client", { client_id: cid.value.trim(), client_secret: sec.value.trim() || null }); carica(); } catch (x) { mostra(x.message, "no"); } } }, "Salva credenziali"))),
        h("h3", {}, "Altri servizi"),
        h("div", { class: "carta" }, h("div", { class: "sotto" }, "Prossimi: Brevo (email marketing) e altri tramite chiave API, GitHub, Canva, Excel.")),
      ]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Collegamenti"), corpo];
}
