// Posta: da leggere (filtrata dal modello locale), situazioni (memoria dei dialoghi), caselle da sfogliare, email da approvare, filtro.
// Il testo delle email lo legge solo il modello locale: qui si vede, non si manda a nessun modello online.

function _dataPosta(iso) {
  if (!iso) return "";
  const d = new Date(iso), oggi = new Date();
  return d.toDateString() === oggi.toDateString() ? d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}
function _mittente(da) { return String(da || "").replace(/\s*<[^>]*>/, "").replace(/"/g, "") || da || ""; }
const _URGENZA = ["", "da guardare", "presto", "oggi"];

// Lettore: apre un'email in una carta sotto la riga cliccata
function _apriEmail(chiave, msgId, dove) {
  if (dove._aperto) { dove._aperto.remove(); dove._aperto = null; return; }
  const box = h("div", { class: "posta-lettore" }, h("p", { class: "sotto" }, "Apro l'email…"));
  dove._aperto = box; dove.after(box);
  api("GET", "/gestione/posta-in/caselle/" + chiave + "/" + encodeURIComponent(msgId))
    .then(r => riempi(box, [h("pre", { class: "posta-testo" }, r.testo), h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => { box.remove(); dove._aperto = null; } }, "Chiudi"))]))
    .catch(e => riempi(box, avviso(e.message, "no")));
}

function _pannelloDaLeggere() {
  const box = h("div"); let tutte = false;
  const carica = async () => {
    let d;
    try { d = await api("GET", "/gestione/posta-in?tutte=" + (tutte ? "1" : "0")); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const st = d.stato || {};
    const statoRiga = !d.caselle ? avviso("Nessuna casella collegata: collegale nella scheda «Collegamenti».", "avv")
      : !d.attivo ? avviso("Il filtro è spento: accendilo nella scheda «Filtro».", "avv")
      : st.esito && st.esito !== "ok" ? avviso("Filtro " + st.esito + (st.errore ? ": " + st.errore : "") + ". Le email nuove aspettano: il testo non va mai a un modello online.", "avv")
      : h("p", { class: "sotto" }, "Filtrate dal modello locale (" + d.modello + ")" + (st.quando ? " · ultimo giro " + _dataPosta(st.quando) : "") + ".");
    const lavora = h("button", { class: "s", type: "button" }, "Controlla adesso");
    lavora.onclick = async () => { lavora.disabled = true; lavora.textContent = "Il modello locale sta leggendo…";
      try { const r = await api("POST", "/gestione/posta-in/vaglia", undefined, { scadenzaMs: 600000 }); if (r.errore) alertBox(r.errore); } catch (e) { alertBox(e.message); }
      carica(); };
    const alertBox = (t) => box.prepend(avviso(t, "no"));
    const voce = (x) => {
      const riga = h("div", { class: "posta-voce" + (x.urgenza >= 2 ? " urgente" : ""), role: "button", tabindex: "0" },
        h("div", { class: "posta-testa" }, h("strong", {}, _mittente(x.mittente)), h("span", { class: "sotto" }, _dataPosta(x.data) + " · " + x.casella)),
        h("div", { class: "posta-oggetto" }, x.oggetto || "(senza oggetto)"),
        x.riassunto ? h("div", {}, x.riassunto) : null,
        h("div", { class: "posta-etichette" },
          x.urgenza ? h("span", { class: "etichetta urg" + x.urgenza }, _URGENZA[x.urgenza]) : null,
          x.motivo ? h("span", { class: "sotto" }, x.motivo) : null,
          x.situazione ? h("button", { class: "collegamento", type: "button", onclick: (ev) => { ev.stopPropagation(); stato.postaScheda = 1; stato.postaSituazione = x.situazione_id; disegna(); } }, "↳ " + x.situazione) : null));
      const letta = h("button", { class: "s piccolo", type: "button", title: "Segna come letta", onclick: async (ev) => { ev.stopPropagation(); try { await api("POST", "/gestione/posta-in/" + x.id + "/letta"); riga.parentNode.remove(); } catch (e) { alertBox(e.message); } } }, "✓ Letta");
      const apri = () => _apriEmail(x.origine + "-" + x.casella_id, x.msg_id, contenitore);
      riga.onclick = apri; riga.onkeydown = (ev) => { if (ev.key === "Enter") apri(); };
      const contenitore = h("div", { class: "posta-riga" }, riga, letta);
      return h("div", {}, contenitore);
    };
    const c = d.conteggi || {};
    const filtro = h("label", { class: "sotto", style: "display:flex;gap:6px;align-items:center" }, h("input", { type: "checkbox", checked: tutte, onchange: (ev) => { tutte = ev.target.checked; carica(); } }), "Mostra anche quelle normali");
    const tutteLette = d.email.length ? h("button", { class: "s", type: "button", onclick: async () => { await api("POST", "/gestione/posta-in/tutte-lette"); carica(); } }, "Segna tutte come lette") : null;
    riempi(box, [statoRiga,
      h("p", { class: "sotto" }, "Ultimi 14 giorni: " + (c.importante || 0) + " importanti, " + (c.normale || 0) + " normali, " + (c.scartabile || 0) + " scartate dal filtro."),
      h("div", { class: "azioni" }, lavora, tutteLette, filtro),
      d.email.length ? d.email.map(voce) : h("p", { class: "sotto" }, tutte ? "Nessuna email da leggere." : "Nessuna email importante da leggere.")]);
  };
  carica();
  return box;
}

function _pannelloSituazioni() {
  const box = h("div"), dett = h("div");
  const quadro = h("div");
  const mostraQuadro = (q) => riempi(quadro, q && q.testo ? h("div", { class: "carta posta-quadro" }, h("h3", {}, "Il punto della situazione"),
    h("div", { class: "sotto" }, q.quando ? "preparato " + _dataPosta(q.quando) : ""), h("pre", { class: "posta-testo" }, q.testo)) : null);
  const bq = h("button", { class: "p", type: "button" }, "Fammi il punto della situazione");
  bq.onclick = async () => { bq.disabled = true; bq.textContent = "Il modello locale sta riassumendo…";
    try { const r = await api("POST", "/gestione/posta-in/quadro", undefined, { scadenzaMs: 600000 }); mostraQuadro({ testo: r.testo, quando: new Date().toISOString() }); }
    catch (e) { riempi(quadro, avviso(e.message, "no")); }
    bq.disabled = false; bq.textContent = "Fammi il punto della situazione"; };
  const apri = async (id) => {
    let s; try { s = await api("GET", "/gestione/posta-in/situazioni/" + id); } catch (e) { riempi(dett, avviso(e.message, "no")); return; }
    const titolo = h("input", { value: s.titolo, style: "width:100%" });
    riempi(dett, h("div", { class: "carta" },
      h("label", {}, "Titolo", titolo),
      h("div", { class: "sotto" }, (s.interlocutori || "") + " · " + s.email_n + " email · aggiornata " + _dataPosta(s.aggiornata_il)),
      h("pre", { class: "posta-testo" }, s.riassunto || "Il riassunto arriva con la prossima email."),
      h("div", { class: "azioni" },
        h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { titolo: titolo.value }); carica(); } }, "Salva titolo"),
        h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { aperta: !s.aperta }); riempi(dett, null); carica(); } }, s.aperta ? "Chiudi la situazione" : "Riapri")),
      h("h3", {}, "Email"),
      s.email.map(e => { const r = h("div", { class: "posta-voce", role: "button", tabindex: "0" },
        h("div", { class: "posta-testa" }, h("strong", {}, _mittente(e.mittente)), h("span", { class: "sotto" }, _dataPosta(e.data))),
        h("div", { class: "posta-oggetto" }, e.oggetto), e.riassunto ? h("div", { class: "sotto" }, e.riassunto) : null);
        r.onclick = () => _apriEmail(e.origine + "-" + e.casella_id, e.msg_id, r); return r; })));
    dett.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  let chiuse = false;
  const carica = async () => {
    let l; try { l = await api("GET", "/gestione/posta-in/situazioni?chiuse=" + (chiuse ? "1" : "0")); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    riempi(box, [h("label", { class: "sotto", style: "display:flex;gap:6px;align-items:center" }, h("input", { type: "checkbox", checked: chiuse, onchange: (ev) => { chiuse = ev.target.checked; carica(); } }), "Mostra anche le chiuse"),
      l.length ? h("div", { class: "posta-situazioni" }, l.map(s => h("button", { type: "button", class: "carta posta-sit" + (s.aperta ? "" : " chiusa"), onclick: () => apri(s.id) },
        h("strong", {}, s.titolo), h("div", { class: "sotto" }, (s.interlocutori || "").slice(0, 80)),
        h("div", { class: "posta-riassunto" }, (s.riassunto || "").slice(0, 220) + ((s.riassunto || "").length > 220 ? "…" : "")),
        h("div", { class: "sotto" }, _dataPosta(s.aggiornata_il) + " · " + s.email_n + " email" + (s.da_leggere ? " · " + s.da_leggere + " da leggere" : "")))))
        : h("p", { class: "sotto" }, "Ancora nessuna situazione: nascono da sole quando il filtro trova email che fanno parte di un dialogo da seguire.")]);
  };
  api("GET", "/gestione/posta-in").then(d => mostraQuadro(d.quadro)).catch(() => {});
  carica();
  if (stato.postaSituazione) { apri(stato.postaSituazione); stato.postaSituazione = null; }
  return [h("p", { class: "sotto" }, "Ogni dialogo che vale la pena seguire (una trattativa, una pratica, un progetto) diventa una situazione: il modello locale ne tiene il riassunto e lo aggiorna a ogni email nuova."),
    h("div", { class: "azioni" }, bq), quadro, box, dett];
}

function _pannelloCaselle() {
  const box = h("div"), lista = h("div"), cerca = h("input", { type: "search", placeholder: "Cerca in questa casella…", style: "flex:1;min-width:0" });
  let scelta = null;
  const sfoglia = async () => {
    if (!scelta) return;
    riempi(lista, h("p", { class: "sotto" }, "Leggo la casella…"));
    let l; try { l = await api("GET", "/gestione/posta-in/caselle/" + scelta + "?cerca=" + encodeURIComponent(cerca.value.trim())); } catch (e) { riempi(lista, avviso(e.message, "no")); return; }
    riempi(lista, l.length ? l.map(e => { const r = h("div", { class: "posta-voce" + (e.non_letta ? " nonletta" : ""), role: "button", tabindex: "0" },
      h("div", { class: "posta-testa" }, h("strong", {}, _mittente(e.da)), h("span", { class: "sotto" }, _dataPosta(e.data) + (e.categoria && e.categoria !== "da_vagliare" ? " · " + e.categoria : ""))),
      h("div", { class: "posta-oggetto" }, e.oggetto || "(senza oggetto)"), h("div", { class: "sotto" }, e.riassunto || e.anteprima));
      r.onclick = () => _apriEmail(scelta, e.id, r); r.onkeydown = (ev) => { if (ev.key === "Enter") r.click(); }; return r; }) : h("p", { class: "sotto" }, "Nessuna email."));
  };
  api("GET", "/gestione/posta-in/caselle").then(cc => {
    if (!cc.length) { riempi(box, [avviso("Nessuna casella collegata.", "avv"), h("button", { class: "s", type: "button", onclick: () => vai("sez", "collegamenti") }, "Collega una casella")]); return; }
    const sel = h("select", { onchange: (ev) => { scelta = ev.target.value; sfoglia(); } }, cc.map(c => h("option", { value: c.chiave }, c.etichetta + " · " + c.email + (c.errore ? " (errore)" : ""))));
    scelta = cc[0].chiave;
    cerca.onkeydown = (ev) => { if (ev.key === "Enter") sfoglia(); };
    riempi(box, [h("div", { class: "azioni" }, sel, cerca, h("button", { class: "s", type: "button", onclick: sfoglia }, "Cerca")), lista]);
    sfoglia();
  }).catch(e => riempi(box, avviso(e.message, "no")));
  return [h("p", { class: "sotto" }, "Le tue caselle, Gmail e le altre (Hostinger, Aruba…): ultime due settimane, oppure cerca. Leggere qui non coinvolge nessun modello."), box];
}

function _pannelloFiltro() {
  const box = h("div");
  api("GET", "/gestione/posta-in").then(d => {
    const attivo = h("input", { type: "checkbox", checked: d.attivo }), solo = h("input", { type: "checkbox", checked: d.solo_locale });
    const reg = h("textarea", { style: "min-height:140px;width:100%", placeholder: "Es.: sempre importanti le email di Comuni, Regione, università e partner dei progetti; scadenze dei bandi; Arianna, Matteo, Giuseppe, Fabio. Scarta le newsletter di software e le notifiche dei social." }, d.regole || "");
    const msg = h("div");
    riempi(box, [
      h("label", { style: "display:flex;gap:8px;align-items:center" }, attivo, "Filtro acceso: ogni 5 minuti il modello locale legge le email nuove e le smista"),
      h("label", { style: "display:flex;gap:8px;align-items:center" }, solo, "La posta passa solo dai modelli locali: gli agenti con un modello online non leggono le caselle"),
      h("label", {}, "Cosa conta per te (il filtro lo segue)", reg),
      h("p", { class: "sotto" }, "Modello usato: " + d.modello + " (quello dell'agente Posta se è locale). Se nessun computer locale risponde, il filtro aspetta: non ripiega mai su un modello online."),
      h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: async () => { msg.replaceChildren();
        try { await api("PUT", "/gestione/posta-in/impostazioni", { attivo: attivo.checked, solo_locale: solo.checked, regole: reg.value }); msg.replaceChildren(avviso("Salvato.", "ok")); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
        h("button", { class: "s", type: "button", onclick: () => vai("sez", "collegamenti") }, "Collega o controlla le caselle")), msg]);
  }).catch(e => riempi(box, avviso(e.message, "no")));
  return box;
}

function vistaPosta() {
  const elenco = [["Da leggere", _pannelloDaLeggere()], ["Situazioni", _pannelloSituazioni()], ["Le caselle", _pannelloCaselle()],
    ["Da approvare", [h("p", { class: "sotto" }, "Le email che gli agenti hanno preparato e aspettano il tuo via libera."), codaEmailUscita()]], ["Filtro", _pannelloFiltro()]];
  const s = schede(elenco, stato.postaScheda || 0);
  s.querySelectorAll(".scheda-tab").forEach((b, i) => b.addEventListener("click", () => { stato.postaScheda = i; }));
  return [h("h2", {}, "Posta"), s];
}
