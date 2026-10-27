"use strict";
// Siti e hosting: schede con credenziali custodite sul server (mai mostrate), prova di connessione, agenti autorizzati, modifiche da approvare.

const TIPI_SITO = { sftp: "SFTP / SSH", ftp: "FTPS (FTP su TLS)", wordpress: "WordPress (password applicazione)", pannello: "Pannello hosting (solo custodia)", api: "Chiave API (solo custodia)" };

function vistaSiti() {
  const lista = h("div"), attesa = h("div"), msg = h("div"), tutti = h("div");
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/siti");
      const w = await api("GET", "/gestione/siti/scritture");
      riempi(attesa, w.length ? [h("h3", {}, "Modifiche ai siti da approvare (" + w.length + ")"), ...w.map(x => {
        const decidi = async (approva, btn) => { btn.disabled = true; try { const r = await api("POST", "/gestione/siti/scritture/" + x.id + "/decisione", { approva }); msg.replaceChildren(avviso(approva ? (r.stato === "applicata" ? "Modifica applicata" + (r.con_copia ? " (copia di sicurezza conservata)." : ".") : "Non riuscita: " + r.errore) : "Modifica respinta.", r.stato === "errore" ? "no" : "ok")); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); btn.disabled = false; } };
        return h("div", { class: "carta" }, h("div", { class: "nome" }, x.sito + " · " + x.percorso), h("div", { class: "sotto" }, "Proposta da " + (x.agente || "?") + " · " + x.lunghezza + " caratteri"),
          x.motivo ? h("div", {}, "Perché: " + x.motivo) : null,
          h("details", {}, h("summary", {}, "Vedi il nuovo contenuto"), h("pre", { style: "white-space:pre-wrap;max-height:300px;overflow:auto" }, x.contenuto)),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: (e) => decidi(true, e.currentTarget) }, "Approva e applica"), h("button", { class: "s", onclick: (e) => decidi(false, e.currentTarget) }, "Respingi")));
      })] : []);
      const cust = d.custode ? d.custode.nome : "il Maestro di chiavi";
      riempi(tutti, [h("div", { class: "carta" },
        h("label", { style: "display:flex;gap:8px;align-items:flex-start" }, h("input", { type: "checkbox", checked: d.solo_custode, onchange: async (e) => { try { await api("PUT", "/gestione/siti/solo-custode", { attivo: e.target.checked }); carica(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }),
          h("span", {}, h("b", {}, "Solo " + cust + " opera sui siti"), h("div", { class: "sotto" }, "Gli altri agenti non toccano mai l'hosting: glielo chiedono (prova del collegamento, lettura, proposta di modifica). Le modifiche in produzione aspettano sempre il tuo via libera. Se lo spegni tornano valide le assegnazioni ai singoli agenti qui sotto."))),
        d.custode && !d.custode.attivo ? h("div", { class: "sotto", style: "color:#c44" }, cust + " è spento: nessun agente può usare i siti.") : null),
        ...(d.solo_custode ? [] : [blocchiTutti(d.accesso_totale || [], msg, carica)])]);
      riempi(lista, d.siti.length ? d.siti.map(s => schedaSito(s, carica, msg)) : h("p", { class: "sotto" }, "Nessun sito ancora. Aggiungi il primo qui sotto."));
    } catch (e) { lista.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Siti e hosting"),
    h("p", { class: "aiuto" }, "Le password e le chiavi sono cifrate sul server e non vengono mai mostrate, nemmeno a te: puoi solo sostituirle. Gli agenti autorizzati lavorano sul sito tramite strumenti (elenca, leggi, scrivi) senza vedere il segreto. Sui siti in produzione ogni modifica aspetta il tuo via libera e prima si conserva una copia. Meglio usare chiavi SSH o utenti FTP limitati, e la «password applicazione» di WordPress."),
    tutti, msg, attesa, lista, formSito(null, carica, msg)];
}

function blocchiTutti(ids, msg, ricarica) {
  const sel = (stato.agenti || []).filter(a => a.attivo);
  const caselle = sel.map(a => { const c = h("input", { type: "checkbox" }); c.checked = ids.includes(a.id); return [a.id, c, h("label", { style: "display:inline-block;margin-right:12px" }, c, " " + a.nome)]; });
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Agenti che vedono tutti i siti"),
    h("p", { class: "sotto" }, "Questi agenti conoscono tutti i siti salvati qui (anche quelli che aggiungerai dopo), senza doverli assegnare uno per uno. Di solito basta il Capo sviluppo."),
    h("div", {}, caselle.map(c => c[2])),
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/siti/accesso-totale", { agenti: caselle.filter(c => c[1].checked).map(c => c[0]) }); msg.replaceChildren(avviso("Salvato.", "ok")); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
}

function schedaSito(s, ricarica, msg) {
  const sel = (stato.agenti || []).filter(a => a.attivo);
  const caselle = sel.map(a => { const c = h("input", { type: "checkbox" }); c.checked = s.agenti.includes(a.id); return [a.id, c, h("label", { style: "display:inline-block;margin-right:12px" }, c, " " + a.nome)]; });
  return h("div", { class: "carta" },
    h("div", { class: "nome" }, s.nome + " ", h("span", { class: "etichetta" }, TIPI_SITO[s.tipo].split(" (")[0]), s.produzione ? h("span", { class: "etichetta avv" }, "produzione") : null, s.attivo ? null : h("span", { class: "etichetta no" }, "spento")),
    h("div", { class: "sotto" }, [s.url, s.host ? s.host + ":" + s.porta : null, s.utente ? "utente " + s.utente : null, s.ha_segreto ? "segreto custodito 🔒" : "SEGRETO MANCANTE"].filter(Boolean).join(" · ")),
    s.esito_prova ? h("div", { class: "sotto" }, "Ultima prova: " + s.esito_prova) : null,
    s.impronta_host ? h("div", { class: "sotto" }, "Impronta del server: " + s.impronta_host) : null,
    ["sftp", "ftp", "wordpress"].includes(s.tipo) ? [h("div", { class: "sotto" }, "Agenti autorizzati:"), h("div", {}, caselle.map(c => c[2])),
      h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => { try { await api("PUT", "/gestione/siti/" + s.id + "/agenti", { agenti: caselle.filter(c => c[1].checked).map(c => c[0]) }); msg.replaceChildren(avviso("Agenti salvati.", "ok")); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva agenti"),
        h("button", { class: "p", onclick: async (e) => { e.currentTarget.disabled = true; try { const r = await api("POST", "/gestione/siti/" + s.id + "/prova"); msg.replaceChildren(avviso(r.messaggio, r.ok ? "ok" : "no")); ricarica(); } catch (er) { msg.replaceChildren(avviso(er.message, "no")); } } }, "Prova connessione"))] : h("p", { class: "sotto" }, "Solo custodia: nessuna operazione automatica."),
    h("details", {}, h("summary", {}, "Modifica o elimina"), formSito(s, ricarica, msg),
      s.impronta_host ? h("button", { class: "s", onclick: async () => { if (confirm("Dimenticare l'impronta? Alla prossima prova verrà fissata quella del server attuale.")) { await api("POST", "/gestione/siti/" + s.id + "/dimentica-impronta"); ricarica(); } } }, "Dimentica impronta del server") : null,
      h("button", { class: "s", onclick: async () => { if (confirm("Eliminare «" + s.nome + "» e il suo segreto?")) { await api("DELETE", "/gestione/siti/" + s.id); ricarica(); } } }, "Elimina sito")));
}

function formSito(s, ricarica, msg) {
  const nome = h("input", { type: "text", maxlength: 80, value: s ? s.nome : "", placeholder: "Es. Sito Renovatio" });
  const tipo = h("select", {}, Object.entries(TIPI_SITO).map(([v, t]) => h("option", { value: v }, t))); if (s) tipo.value = s.tipo;
  const url = h("input", { type: "url", maxlength: 300, value: s?.url || "", placeholder: "https://… (WordPress e riferimento)" });
  const host = h("input", { type: "text", maxlength: 253, value: s?.host || "", placeholder: "server.esempio.it (SFTP/FTPS)" });
  const porta = h("input", { type: "number", min: 1, max: 65535, value: s?.porta || "", placeholder: "22 / 21" });
  const utente = h("input", { type: "text", maxlength: 200, value: s?.utente || "", autocomplete: "off" });
  const segreto = h("textarea", { style: "min-height:60px", autocomplete: "off", placeholder: s ? "Lascia vuoto per non cambiarlo" : "Password, password applicazione o chiave privata (senza passphrase)" });
  const base = h("input", { type: "text", maxlength: 300, value: s?.percorso_base || "/", placeholder: "/public_html" });
  const prod = h("input", { type: "checkbox" }); prod.checked = s ? s.produzione : true;
  const att = h("input", { type: "checkbox" }); att.checked = s ? s.attivo : true;
  const note = h("input", { type: "text", maxlength: 1000, value: s?.note || "", placeholder: "Note (non segrete)" });
  return h("div", { class: s ? "" : "carta" }, s ? null : h("div", { class: "nome" }, "Aggiungi un sito"),
    h("div", { class: "riga" }, h("label", {}, "Nome", nome), h("label", {}, "Tipo di accesso", tipo)),
    h("div", { class: "riga" }, h("label", {}, "Indirizzo", url), h("label", {}, "Host", host), h("label", {}, "Porta", porta)),
    h("div", { class: "riga" }, h("label", {}, "Utente", utente), h("label", {}, "Cartella base (SFTP/FTPS)", base)),
    h("label", {}, "Segreto", segreto), h("label", {}, "Note", note),
    h("div", { class: "interruttore" }, prod, h("span", {}, "In produzione: ogni modifica chiede il mio via libera")),
    h("div", { class: "interruttore" }, att, h("span", {}, "Attivo")),
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
      const corpo = { nome: nome.value.trim(), tipo: tipo.value, url: url.value.trim() || null, host: host.value.trim() || null, porta: porta.value ? Number(porta.value) : null,
        utente: utente.value.trim() || null, segreto: segreto.value || null, percorso_base: base.value.trim() || "/", produzione: prod.checked, attivo: att.checked, note: note.value.trim() || null };
      try { await api(s ? "PUT" : "POST", "/gestione/siti" + (s ? "/" + s.id : ""), corpo); segreto.value = ""; msg.replaceChildren(avviso("Salvato.", "ok")); ricarica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, s ? "Salva modifiche" : "Aggiungi")));
}
