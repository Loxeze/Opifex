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

function _scadenza(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T12:00:00"), giorni = Math.round((d - new Date()) / 86400000);
  const testo = giorni < 0 ? "scaduta il " + d.toLocaleDateString("it-IT", { day: "numeric", month: "short" }) : giorni === 0 ? "scade oggi" : giorni === 1 ? "scade domani"
    : "entro il " + d.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
  return h("span", { class: "etichetta " + (giorni <= 1 ? "urg3" : giorni <= 7 ? "urg2" : "urg1") }, testo);
}
function _chi(s) { return s.tocca_a_te ? h("span", { class: "etichetta urg2" }, "tocca a te") : h("span", { class: "etichetta" }, "aspetti " + (s.ultimo_da && s.ultimo_da !== "Lorenzo" ? "gli altri" : "una risposta")); }
function _ora(iso) { return iso ? new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""; }
// Cosa sta facendo il giro in corso: la fase, quante risposte ha dato il modello locale, quando l'ultima
function _lavoroInCorso(d) {
  const l = d.lavoro || {}, st = d.stato || {};
  const minuti = l.iniziato ? Math.round((Date.now() - new Date(l.iniziato)) / 60000) : 0;
  const fermo = !l.ultima_risposta && minuti >= 6 && /aspetto|legge|riassume/.test(l.fase || "");
  return h("div", { class: "messaggio " + (fermo ? "no" : "avv") },
    h("strong", {}, "Al lavoro" + (l.fase ? ": " + l.fase : "…")),
    h("div", { class: "sotto" }, "Iniziato alle " + _ora(l.iniziato) + " · risposte del modello locale: " + (l.risposte || 0) + (l.ultima_risposta ? " (l'ultima alle " + _ora(l.ultima_risposta) + ")" : "")
      + (st.vagliate ? " · email lette: " + st.vagliate : "") + ". La pagina si aggiorna da sola; puoi anche chiuderla."),
    fermo ? h("div", {}, "Il modello locale non ha ancora risposto dopo " + minuti + " minuti: controlla che il computer con Ollama sia acceso e collegato (Impostazioni → Computer locali).") : null);
}
function _apriConversazione(id) { stato.postaScheda = 2; stato.postaSituazione = id; disegna(); }

// Il punto: cosa tocca a Lorenzo nelle conversazioni in corso, l'analisi delle ultime settimane, il punto della situazione
function _pannelloCosaFare() {
  const box = h("div"); let seguiva = false, attesa = null, messaggio = null;
  const carica = async () => {
    clearTimeout(attesa);
    let d; try { d = await api("GET", "/gestione/posta-in"); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const st = d.stato || {};
    if (seguiva && !d.in_corso) messaggio = st.esito === "ok"
      ? avviso("Fatto: " + (st.nuove || 0) + " email nuove, " + (st.vagliate || 0) + " lette, " + (st.situazioni || 0) + " conversazioni riassunte.", "ok")
      : avviso("Non è riuscito: " + (st.esito || "") + (st.errore ? " — " + st.errore : "") + ". Quello che manca si fa al prossimo giro, sempre in locale.", "no");
    seguiva = !!d.in_corso;
    if (d.in_corso) attesa = setTimeout(() => { if (box.isConnected) carica(); }, 5000);
    const giorni = h("select", { style: "width:auto;flex:0 0 auto" }, [["14", "ultime 2 settimane"], ["30", "ultimo mese"], ["60", "ultimi 2 mesi"]].map(([v, t]) => h("option", { value: v, selected: v === "30" }, t)));
    const analizza = h("button", { class: d.situazioni_aperte ? "s" : "p", type: "button", disabled: !!d.in_corso }, "Analizza");
    analizza.onclick = async () => { analizza.disabled = true; messaggio = null;
      try { await api("POST", "/gestione/posta-in/analizza", { giorni: Number(giorni.value) }); seguiva = true; } catch (e) { messaggio = avviso(e.message, "no"); }
      carica(); };
    const lavoro = d.in_corso ? _lavoroInCorso(d) : null;
    const quadro = h("div");
    const mostraQuadro = (q) => riempi(quadro, q && q.testo ? h("div", { class: "carta posta-quadro" }, h("h3", {}, "Il punto della situazione"),
      h("div", { class: "sotto" }, q.quando ? "preparato " + _dataPosta(q.quando) + " dal modello locale" : ""), h("pre", { class: "posta-testo" }, q.testo)) : null);
    mostraQuadro(d.quadro);
    const bq = h("button", { class: "s", type: "button", disabled: !d.situazioni_aperte }, "Fammi il punto della situazione");
    bq.onclick = async () => { bq.disabled = true; bq.textContent = "Il modello locale sta scrivendo…";
      try { const r = await api("POST", "/gestione/posta-in/quadro", undefined, { scadenzaMs: 600000 }); mostraQuadro({ testo: r.testo, quando: new Date().toISOString() }); }
      catch (e) { riempi(quadro, avviso(e.message, "no")); }
      bq.disabled = false; bq.textContent = "Fammi il punto della situazione"; };
    const fatto = (f, el) => h("button", { class: "s piccolo", type: "button", title: "Non tocca più a te", onclick: async (ev) => { ev.stopPropagation();
      try { await api("PUT", "/gestione/posta-in/situazioni/" + f.id, { tocca_a_te: false }); el().remove(); } catch (e) { box.prepend(avviso(e.message, "no")); } } }, "✓ Fatto");
    const voce = (f) => { let riga;
      const scheda = h("div", { class: "posta-voce", role: "button", tabindex: "0", onclick: () => _apriConversazione(f.id) },
        h("div", { class: "posta-testa" }, h("strong", {}, f.titolo), h("span", { class: "sotto" }, "ultimo messaggio di " + (f.ultimo_da || "?") + (f.ultimo_il ? " · " + _dataPosta(f.ultimo_il) : ""))),
        f.prossimo_passo ? h("div", { class: "posta-passo" }, "→ " + f.prossimo_passo) : h("div", { class: "sotto" }, "Ti ha scritto " + (f.ultimo_da || "qualcuno") + " e non hai ancora risposto."),
        h("div", { class: "posta-etichette" }, _scadenza(f.scadenza), h("span", { class: "sotto" }, f.interlocutori || "")));
      riga = h("div", { class: "posta-riga" }, scheda, fatto(f, () => riga)); return riga; };
    const vuoto = !d.situazioni_aperte
      ? h("div", { class: "carta" }, h("h3", {}, "Ancora nessuna conversazione analizzata"),
          h("p", {}, "Il filtro ha guardato solo le ultime email. Fagli rileggere le ultime settimane, comprese le risposte che hai mandato tu: ricostruisce le conversazioni in corso e ti dice dove tocca a te."),
          h("div", { class: "azioni" }, giorni, analizza), h("p", { class: "sotto" }, "Con il modello locale può volerci da qualche minuto a mezz'ora, secondo quanta posta hai. Il testo delle email non esce dai tuoi computer."))
      : null;
    riempi(box, [messaggio, lavoro, vuoto,
      d.situazioni_aperte ? [h("h3", {}, d.da_fare.length ? "Tocca a te (" + d.da_fare.length + ")" : "Niente in sospeso: nelle conversazioni in corso non tocca a te"),
        d.da_fare.map(voce),
        h("div", { class: "azioni", style: "margin-top:16px;align-items:center" }, bq),
        h("div", { class: "azioni", style: "align-items:center" }, h("span", { class: "sotto" }, d.situazioni_aperte + " conversazioni in corso. Rileggi la posta di:"), giorni, analizza)] : null,
      quadro]);
  };
  carica();
  return box;
}

function _pannelloDaLeggere() {
  const box = h("div"); let tutte = false, messaggio = null, seguiva = false, attesa = null;
  const carica = async () => {
    clearTimeout(attesa);
    let d;
    try { d = await api("GET", "/gestione/posta-in?tutte=" + (tutte ? "1" : "0")); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const st = d.stato || {};
    if (seguiva && !d.in_corso) {   // il controllo chiesto e' finito: il risultato resta sullo schermo finche' non ne chiedi un altro
      messaggio = st.esito === "ok" ? avviso("Controllo finito: " + (st.nuove || 0) + " email nuove, " + (st.vagliate || 0) + " lette dal modello locale.", "ok")
        : avviso("Il controllo non è riuscito: " + (st.esito || "") + (st.errore ? " — " + st.errore : "") + ". Le email restano in attesa e verranno lette al prossimo giro.", "no");
    }
    seguiva = !!d.in_corso;
    if (d.in_corso && box.isConnected !== false) attesa = setTimeout(() => { if (box.isConnected) carica(); }, 5000);
    const statoRiga = !d.caselle ? avviso("Nessuna casella collegata: collegale nella scheda «Collegamenti».", "avv")
      : d.in_corso ? _lavoroInCorso(d)
      : !d.attivo ? avviso("Il filtro automatico è spento: «Controlla adesso» funziona lo stesso; per il controllo ogni 5 minuti accendilo nella scheda «Filtro».", "avv")
      : st.esito && st.esito !== "ok" ? avviso("Ultimo giro del filtro: " + st.esito + (st.errore ? " — " + st.errore : "") + ". Le email nuove aspettano: il testo non va mai a un modello online.", "no")
      : h("p", { class: "sotto" }, "Filtrate dal modello locale (" + d.modello + ")" + (st.quando ? " · ultimo giro " + _dataPosta(st.quando) : "") + ".");
    const lavora = h("button", { class: "s", type: "button", disabled: !!d.in_corso }, d.in_corso ? "Il modello locale sta leggendo…" : "Controlla adesso");
    lavora.onclick = async () => { lavora.disabled = true; lavora.textContent = "Il modello locale sta leggendo…"; messaggio = null;
      try { await api("POST", "/gestione/posta-in/vaglia"); seguiva = true; } catch (e) { messaggio = avviso("Non sono riuscito a far partire il controllo: " + e.message, "no"); }
      carica(); };
    const alertBox = (t) => { messaggio = avviso(t, "no"); box.prepend(messaggio); };
    const voce = (x) => {
      const riga = h("div", { class: "posta-voce" + (x.urgenza >= 2 ? " urgente" : ""), role: "button", tabindex: "0" },
        h("div", { class: "posta-testa" }, h("strong", {}, _mittente(x.mittente)), h("span", { class: "sotto" }, _dataPosta(x.data) + " · " + x.casella)),
        h("div", { class: "posta-oggetto" }, x.oggetto || "(senza oggetto)"),
        x.riassunto ? h("div", {}, x.riassunto) : null,
        h("div", { class: "posta-etichette" },
          x.urgenza ? h("span", { class: "etichetta urg" + x.urgenza }, _URGENZA[x.urgenza]) : null,
          x.motivo ? h("span", { class: "sotto" }, x.motivo) : null,
          x.situazione ? h("button", { class: "collegamento", type: "button", onclick: (ev) => { ev.stopPropagation(); _apriConversazione(x.situazione_id); } }, "↳ " + x.situazione) : null));
      const letta = h("button", { class: "s piccolo", type: "button", title: "Segna come letta", onclick: async (ev) => { ev.stopPropagation(); try { await api("POST", "/gestione/posta-in/" + x.id + "/letta"); riga.parentNode.remove(); } catch (e) { alertBox(e.message); } } }, "✓ Letta");
      const apri = () => _apriEmail(x.origine + "-" + x.casella_id, x.msg_id, contenitore);
      riga.onclick = apri; riga.onkeydown = (ev) => { if (ev.key === "Enter") apri(); };
      const contenitore = h("div", { class: "posta-riga" }, riga, letta);
      return h("div", {}, contenitore);
    };
    const c = d.conteggi || {};
    const filtro = h("label", { class: "sotto", style: "display:flex;gap:6px;align-items:center" }, h("input", { type: "checkbox", checked: tutte, onchange: (ev) => { tutte = ev.target.checked; carica(); } }), "Mostra anche quelle normali");
    const tutteLette = d.email.length ? h("button", { class: "s", type: "button", onclick: async () => { await api("POST", "/gestione/posta-in/tutte-lette"); carica(); } }, "Segna tutte come lette") : null;
    riempi(box, [messaggio, statoRiga,
      h("p", { class: "sotto" }, "Ultimi 14 giorni: " + (c.importante || 0) + " importanti, " + (c.normale || 0) + " normali, " + (c.scartabile || 0) + " scartate dal filtro."),
      h("div", { class: "azioni" }, lavora, tutteLette, filtro),
      d.email.length ? d.email.map(voce) : h("p", { class: "sotto" }, tutte ? "Nessuna email da leggere." : "Nessuna email importante da leggere.")]);
  };
  carica();
  return box;
}

function _pannelloSituazioni() {
  const box = h("div"), dett = h("div");
  const apri = async (id) => {
    let s; try { s = await api("GET", "/gestione/posta-in/situazioni/" + id); } catch (e) { riempi(dett, avviso(e.message, "no")); return; }
    const titolo = h("input", { value: s.titolo, style: "width:100%" });
    riempi(dett, h("div", { class: "carta" },
      h("label", {}, "Titolo", titolo),
      h("div", { class: "sotto" }, (s.interlocutori || "") + " · " + s.email_n + " email · ultimo messaggio di " + (s.ultimo_da || "?") + " " + _dataPosta(s.ultimo_il || s.aggiornata_il)),
      h("div", { class: "posta-etichette" }, _chi(s), _scadenza(s.scadenza)),
      s.prossimo_passo ? h("div", { class: "posta-passo" }, "→ " + s.prossimo_passo) : null,
      h("pre", { class: "posta-testo" }, s.riassunto || (s.da_riassumere ? "Il modello locale la riassume al prossimo giro." : "Nessun riassunto ancora.")),
      h("div", { class: "azioni" },
        s.tocca_a_te ? h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { tocca_a_te: false }); apri(id); carica(); } }, "✓ Fatto, non tocca più a me")
          : h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { tocca_a_te: true }); apri(id); carica(); } }, "Tocca a me"),
        h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { titolo: titolo.value }); carica(); } }, "Salva titolo"),
        h("button", { class: "s", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/situazioni/" + id, { aperta: !s.aperta }); riempi(dett, null); carica(); } }, s.aperta ? "Chiudi la situazione" : "Riapri")),
      h("h3", {}, "Email"),
      s.email.map(e => { const r = h("div", { class: "posta-voce", role: "button", tabindex: "0" },
        h("div", { class: "posta-testa" }, h("strong", {}, e.da_me ? "Tu" : _mittente(e.mittente)), h("span", { class: "sotto" }, _dataPosta(e.data))),
        h("div", { class: "posta-oggetto" }, e.oggetto), e.riassunto ? h("div", { class: "sotto" }, e.riassunto) : null);
        if (e.da_me) r.classList.add("mia");
        r.onclick = () => _apriEmail(e.origine + "-" + e.casella_id, e.msg_id, r); return r; })));
    dett.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  let chiuse = false;
  const carica = async () => {
    let l; try { l = await api("GET", "/gestione/posta-in/situazioni?chiuse=" + (chiuse ? "1" : "0")); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    riempi(box, [h("label", { class: "sotto", style: "display:flex;gap:6px;align-items:center" }, h("input", { type: "checkbox", checked: chiuse, onchange: (ev) => { chiuse = ev.target.checked; carica(); } }), "Mostra anche le chiuse"),
      l.length ? h("div", { class: "posta-situazioni" }, l.map(s => h("button", { type: "button", class: "carta posta-sit" + (s.aperta ? "" : " chiusa") + (s.tocca_a_te ? " tocca" : ""), onclick: () => apri(s.id) },
        h("strong", {}, s.titolo), h("div", { class: "posta-etichette" }, _chi(s), _scadenza(s.scadenza)), h("div", { class: "sotto" }, (s.interlocutori || "").slice(0, 80)),
        s.prossimo_passo ? h("div", { class: "posta-passo" }, "→ " + s.prossimo_passo) : null,
        h("div", { class: "posta-riassunto" }, (s.riassunto || (s.da_riassumere ? "Da riassumere…" : "")).slice(0, 200) + ((s.riassunto || "").length > 200 ? "…" : "")),
        h("div", { class: "sotto" }, _dataPosta(s.ultimo_il || s.aggiornata_il) + " · " + s.email_n + " email" + (s.da_leggere ? " · " + s.da_leggere + " da leggere" : "")))))
        : h("p", { class: "sotto" }, "Ancora nessuna conversazione: nella scheda «Il punto» premi «Analizza» per ricostruire quelle delle ultime settimane.")]);
  };
  carica();
  if (stato.postaSituazione) { apri(stato.postaSituazione); stato.postaSituazione = null; }
  return [h("p", { class: "sotto" }, "Ogni conversazione da seguire (una trattativa, una pratica, un progetto), comprese le tue risposte: il modello locale ne tiene il riassunto e dice a chi tocca."),
    dett, box];
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
  const elenco = [["Il punto", _pannelloCosaFare()], ["Da leggere", _pannelloDaLeggere()], ["Conversazioni", _pannelloSituazioni()], ["Le caselle", _pannelloCaselle()],
    ["Da approvare", [h("p", { class: "sotto" }, "Le email che gli agenti hanno preparato e aspettano il tuo via libera."), codaEmailUscita()]], ["Filtro", _pannelloFiltro()]];
  const s = schede(elenco, stato.postaScheda || 0);
  s.querySelectorAll(".scheda-tab").forEach((b, i) => b.addEventListener("click", () => { stato.postaScheda = i; }));
  return [h("h2", {}, "Posta"), s];
}
