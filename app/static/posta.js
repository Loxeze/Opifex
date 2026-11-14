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
// «Mi interessa / Non mi interessa»: il filtro impara da qui. vid = la riga del filtro; se manca (scheda Le caselle) si passa la casella.
function _pulsantiInteresse(x, dopo) {
  let stato_ = x.interessa;
  const si = h("button", { class: "s piccolo voto", type: "button", title: "Mi interessa: il filtro te le porterà in evidenza" }, "👍 Mi interessa");
  const no = h("button", { class: "s piccolo voto", type: "button", title: "Non mi interessa: il filtro le scarterà" }, "👎 Non mi interessa");
  const mostra = () => { si.classList.toggle("scelto", stato_ === true); no.classList.toggle("scelto", stato_ === false); };
  const vota = async (ev, v) => { ev.stopPropagation(); const nuovo = stato_ === v ? null : v;
    try {
      if (x.vaglio_id || x.id_vaglio) await api("POST", "/gestione/posta-in/" + (x.vaglio_id || x.id_vaglio) + "/interesse", { interessa: nuovo });
      else { const r = await api("POST", "/gestione/posta-in/interesse", { chiave: x.chiave, msg_id: x.msg_id, da: x.da || "", oggetto: x.oggetto || "", interessa: nuovo === null ? v : nuovo }); x.vaglio_id = r.id; }
      stato_ = nuovo; mostra(); if (dopo) dopo(nuovo);
    } catch (e) { si.parentNode && si.parentNode.append(avviso(e.message, "no")); } };
  si.onclick = (ev) => vota(ev, true); no.onclick = (ev) => vota(ev, false); mostra();
  return h("span", { class: "posta-voti" }, si, no);
}

// Modulo «nuovo compito» (per te o per un collaboratore). proposta: già pronta (da una conversazione) oppure la chiede al modello locale (da un'email).
function _moduloCompito(dove, { vid, sid, proposta }) {
  if (dove._compito) { dove._compito.remove(); dove._compito = null; return; }
  const box = h("div", { class: "carta posta-compito" }, h("p", { class: "sotto" }, vid && !proposta ? "Il modello locale legge l'email e prepara una proposta di compito…" : "…"));
  dove._compito = box; dove.after(box);
  const disegnaModulo = (p, persone) => {
    const titolo = h("input", { value: p.titolo || "", maxlength: 200 });
    const descr = h("textarea", { style: "min-height:90px" }, p.descrizione || "");
    const scad = h("input", { type: "date", value: p.scadenza || "" });
    const prio = h("select", {}, ["bassa", "normale", "alta", "urgente"].map(v => h("option", { value: v, selected: v === (p.priorita || "normale") }, v)));
    const chi = h("select", {}, [h("option", { value: "" }, "A me"),
      h("optgroup", { label: "Persone" }, persone.utenti.map(u => h("option", { value: "u" + u.id, selected: p.assegnato_utente_id === u.id }, u.nome))),
      persone.agenti.length ? h("optgroup", { label: "Agenti" }, persone.agenti.map(a => h("option", { value: "a" + a.id }, a.nome))) : null]);
    const msg = h("div");
    const salva = h("button", { class: "p", type: "button" }, "Crea il compito");
    salva.onclick = async () => { salva.disabled = true; msg.replaceChildren();
      const v = chi.value, corpo = { titolo: titolo.value.trim(), descrizione: descr.value.trim() || null, scadenza: scad.value || null, priorita: prio.value,
        assegnato_utente_id: v.startsWith("u") ? Number(v.slice(1)) : null, assegnato_agente_id: v.startsWith("a") ? Number(v.slice(1)) : null };
      try { const r = await api("POST", vid ? "/gestione/posta-in/" + vid + "/compito" : "/gestione/posta-in/situazioni/" + sid + "/compito", corpo);
        riempi(box, [avviso("Compito creato.", "ok"), h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => vai("task") }, "Vai ai compiti"),
          h("button", { class: "s", type: "button", onclick: () => { box.remove(); dove._compito = null; } }, "Chiudi"))]);
        void r; }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); salva.disabled = false; } };
    riempi(box, [h("h3", {}, "Nuovo compito"), h("label", {}, "Cosa fare", titolo), h("label", {}, "Dettagli", descr),
      h("div", { class: "posta-campi" }, h("label", {}, "Per chi", chi), h("label", {}, "Entro il", scad), h("label", {}, "Priorità", prio)),
      msg, h("div", { class: "azioni" }, salva, h("button", { class: "s", type: "button", onclick: () => { box.remove(); dove._compito = null; } }, "Annulla"))]);
    box.scrollIntoView({ behavior: "smooth", block: "start" });
    box.querySelectorAll("input, textarea, select").forEach(el => el.addEventListener("focus", () => setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "center" }), 300)));
  };
  (async () => {
    let persone = { utenti: [], agenti: [] };
    try { persone = await api("GET", "/gestione/posta-in/persone"); } catch (e) { /* si crea comunque per te */ }
    if (proposta || !vid) { disegnaModulo(proposta || {}, persone); return; }
    try { disegnaModulo(await api("POST", "/gestione/posta-in/" + vid + "/proponi-compito", undefined, { scadenzaMs: 300000 }), persone); }
    catch (e) { disegnaModulo({}, persone); box.prepend(avviso("Proposta non disponibile (" + e.message + "): scrivilo tu.", "avv")); }
  })();
}

function _apriEmail(chiave, msgId, dove, info) {
  if (dove._aperto) { dove._aperto.remove(); dove._aperto = null; return; }
  const box = h("div", { class: "posta-lettore" }, h("p", { class: "sotto" }, "Apro l'email…"));
  dove._aperto = box; dove.after(box);
  api("GET", "/gestione/posta-in/caselle/" + chiave + "/" + encodeURIComponent(msgId))
    .then(r => {
      const x = { ...(info || {}), vaglio_id: r.vaglio_id, interessa: r.interessa, chiave, msg_id: msgId };
      const azioni = h("div", { class: "azioni" });
      azioni.append(_pulsantiInteresse(x),
        r.task_id ? h("span", { class: "etichetta" }, "compito già creato") : h("button", { class: "s", type: "button", onclick: () => _moduloCompito(azioni, { vid: r.vaglio_id }), disabled: !r.vaglio_id }, "+ Compito"),
        h("button", { class: "s", type: "button", onclick: () => { box.remove(); dove._aperto = null; } }, "Chiudi"));
      const nota = r.casella === "permesso" ? avviso("Letta qui, ma non segnata come letta in Gmail: serve un permesso in più. In Caselle e Google ricollega l'account spuntando anche «Gmail: segna come lette».", "avv")
        : r.casella === "errore" ? h("p", { class: "sotto" }, "Non sono riuscito a segnarla come letta nella casella.") : null;
      riempi(box, [h("pre", { class: "posta-testo" }, r.testo), nota, azioni]);
    })
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
// Mentre stai leggendo un'email o scrivendo un compito, l'aggiornamento automatico della pagina aspetta: non deve chiuderti il modulo sotto le dita.
function _occupato(box) {
  if (box.querySelector(".posta-compito, .posta-lettore")) return true;
  const a = document.activeElement;
  return !!(a && box.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
}
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
  const carica = async (auto) => {
    clearTimeout(attesa);
    if (auto && _occupato(box)) { attesa = setTimeout(() => { if (box.isConnected) carica(true); }, 5000); return; }
    let d; try { d = await api("GET", "/gestione/posta-in"); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const st = d.stato || {};
    if (seguiva && !d.in_corso) messaggio = st.esito === "ok"
      ? avviso("Fatto: " + (st.nuove || 0) + " email nuove, " + (st.vagliate || 0) + " lette, " + (st.situazioni || 0) + " conversazioni riassunte.", "ok")
      : avviso("Non è riuscito: " + (st.esito || "") + (st.errore ? " — " + st.errore : "") + ". Quello che manca si fa al prossimo giro, sempre in locale.", "no");
    seguiva = !!d.in_corso;
    if (d.in_corso) attesa = setTimeout(() => { if (box.isConnected) carica(true); }, 5000);
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
      const compito = h("button", { class: "s piccolo", type: "button", onclick: (ev) => { ev.stopPropagation();
        _moduloCompito(riga, { sid: f.id, proposta: { titolo: f.prossimo_passo || f.titolo, descrizione: (f.riassunto || "") + "\n\nConversazione: " + f.titolo + " (" + (f.interlocutori || "") + ")", scadenza: f.scadenza } }); } }, "+ Compito");
      riga = h("div", { class: "posta-riga" }, scheda, h("div", { class: "posta-colonna" }, fatto(f, () => riga), compito)); return riga; };
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
  const carica = async (auto) => {
    clearTimeout(attesa);
    if (auto && _occupato(box)) { attesa = setTimeout(() => { if (box.isConnected) carica(true); }, 5000); return; }
    let d;
    try { d = await api("GET", "/gestione/posta-in?tutte=" + (tutte ? "1" : "0")); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const st = d.stato || {};
    if (seguiva && !d.in_corso) {   // il controllo chiesto e' finito: il risultato resta sullo schermo finche' non ne chiedi un altro
      messaggio = st.esito === "ok" ? avviso("Controllo finito: " + (st.nuove || 0) + " email nuove, " + (st.vagliate || 0) + " lette dal modello locale.", "ok")
        : avviso("Il controllo non è riuscito: " + (st.esito || "") + (st.errore ? " — " + st.errore : "") + ". Le email restano in attesa e verranno lette al prossimo giro.", "no");
    }
    seguiva = !!d.in_corso;
    if (d.in_corso && box.isConnected !== false) attesa = setTimeout(() => { if (box.isConnected) carica(true); }, 5000);
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
          x.imparata ? h("span", { class: "etichetta imparata" }, "✦ " + x.imparata) : null,
          x.documento ? h("span", { class: "etichetta doc" }, "💶 " + (_TIPI_DOC[x.documento] || "documento") + (x.documento_importo !== null && x.documento_importo !== undefined ? " " + _euro(x.documento_importo) : "") + (x.documento_sito ? " · 🔗 dal sito" : "")) : null,
          x.situazione ? h("button", { class: "collegamento", type: "button", onclick: (ev) => { ev.stopPropagation(); _apriConversazione(x.situazione_id); } }, "↳ " + x.situazione) : null),
        h("div", { class: "posta-etichette", onclick: (ev) => ev.stopPropagation() },
          _pulsantiInteresse({ ...x, vaglio_id: x.id }, (v) => { if (v === false) setTimeout(() => contenitore.parentNode && contenitore.parentNode.remove(), 400); }),
          x.task_id ? h("span", { class: "etichetta" }, "compito creato") : h("button", { class: "s piccolo", type: "button", onclick: (ev) => { ev.stopPropagation(); _moduloCompito(contenitore, { vid: x.id }); } }, "+ Compito")));
      const letta = h("button", { class: "s piccolo", type: "button", title: "Segna come letta", onclick: async (ev) => { ev.stopPropagation(); try { const r = await api("POST", "/gestione/posta-in/" + x.id + "/letta"); riga.parentNode.parentNode.remove(); if (r.casella === "permesso") alertBox("Segnata come letta qui; per segnarla anche in Gmail ricollega l'account spuntando «Gmail: segna come lette»."); } catch (e) { alertBox(e.message); } } }, "✓ Letta");
      const apri = () => _apriEmail(x.origine + "-" + x.casella_id, x.msg_id, contenitore, x);
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
      h("div", { class: "posta-oggetto" }, e.oggetto || "(senza oggetto)"), h("div", { class: "sotto" }, e.riassunto || e.anteprima),
      h("div", { class: "posta-etichette", onclick: (ev) => ev.stopPropagation() }, _pulsantiInteresse({ vaglio_id: e.vaglio_id, interessa: e.interessa, chiave: scelta, msg_id: e.id, da: e.da, oggetto: e.oggetto })));
      r.onclick = () => { r.classList.remove("nonletta"); _apriEmail(scelta, e.id, r, e); }; r.onkeydown = (ev) => { if (ev.key === "Enter") r.click(); }; return r; }) : h("p", { class: "sotto" }, "Nessuna email."));
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
    const attivo = h("input", { type: "checkbox", checked: d.attivo }), solo = h("input", { type: "checkbox", checked: d.solo_locale }), segna = h("input", { type: "checkbox", checked: d.segna_casella });
    const imparatoBox = h("div");
    const caricaImparato = () => api("GET", "/gestione/posta-in/imparato").then(l => riempi(imparatoBox, l.length
      ? h("div", { class: "posta-imparato" }, l.map(r => h("div", { class: "posta-imparato-riga" },
          h("span", { class: "etichetta " + (r.voto > 0 ? "si" : "no") }, r.voto > 0 ? "👍 ti interessa" : "👎 non ti interessa"),
          h("span", { class: "posta-imparato-chi" }, r.mittente), h("span", { class: "sotto" }, r.segnali + " segnali"),
          h("button", { class: "collegamento", type: "button", onclick: async () => { await api("DELETE", "/gestione/posta-in/imparato?mittente=" + encodeURIComponent(r.mittente)); caricaImparato(); } }, "dimentica"))))
      : h("p", { class: "sotto" }, "Ancora niente: usa «Mi interessa» / «Non mi interessa» sulle email, e apri quelle che ti servono. Il filtro impara da questo.")))
      .catch(e => riempi(imparatoBox, avviso(e.message, "no")));
    caricaImparato();
    const reg = h("textarea", { style: "min-height:140px;width:100%", placeholder: "Es.: sempre importanti le email di Comuni, Regione, università e partner dei progetti; scadenze dei bandi; Arianna, Matteo, Giuseppe, Fabio. Scarta le newsletter di software e le notifiche dei social." }, d.regole || "");
    const msg = h("div");
    riempi(box, [
      h("label", { style: "display:flex;gap:8px;align-items:center" }, attivo, "Filtro acceso: ogni 5 minuti il modello locale legge le email nuove e le smista"),
      h("label", { style: "display:flex;gap:8px;align-items:center" }, solo, "La posta passa solo dai modelli locali: gli agenti con un modello online non leggono le caselle"),
      h("label", { style: "display:flex;gap:8px;align-items:center" }, segna, "Quando apro un'email qui, segnala come letta anche nella mia casella"),
      h("label", {}, "Cosa conta per te (il filtro lo segue)", reg),
      h("p", { class: "sotto" }, "Modello usato: " + d.modello + " (quello dell'agente Posta se è locale). Se nessun computer locale risponde, il filtro aspetta: non ripiega mai su un modello online."),
      h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: async () => { msg.replaceChildren();
        try { await api("PUT", "/gestione/posta-in/impostazioni", { attivo: attivo.checked, solo_locale: solo.checked, segna_casella: segna.checked, regole: reg.value }); msg.replaceChildren(avviso("Salvato.", "ok")); }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
        h("button", { class: "s", type: "button", onclick: () => vai("sez", "collegamenti") }, "Collega o controlla le caselle")), msg,
      h("h3", { style: "margin-top:24px" }, "Cosa ha imparato da te"),
      h("p", { class: "sotto" }, "Dai pulsanti «Mi interessa / Non mi interessa», dalle email che apri (qui o nella tua casella) e da quelle da cui crei un compito. Chi ti interessa finisce sempre in evidenza; chi non ti interessa viene scartato senza disturbare il modello."),
      imparatoBox]);
  }).catch(e => riempi(box, avviso(e.message, "no")));
  return box;
}


// Fatture e pagamenti: i documenti amministrativi trovati nella posta (base per il controllo di gestione)
const _TIPI_DOC = { fattura: "Fattura", ricevuta: "Ricevuta", avviso_pagamento: "Avviso di pagamento", sollecito: "Sollecito", nota_credito: "Nota di credito", altro: "Altro" };
const _STATI_DOC = { da_verificare: "da verificare", da_pagare: "da pagare", pagato: "pagato", da_incassare: "da incassare", incassato: "incassato" };
function _euro(v, valuta) { return v === null || v === undefined ? "—" : Number(v).toLocaleString("it-IT", { style: "currency", currency: valuta || "EUR" }); }
function _giorno(iso) { return iso ? new Date(iso + (iso.length === 10 ? "T12:00:00" : "")).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" }) : "—"; }

function _pannelloPagamenti() {
  const box = h("div"); const oggi = new Date();
  let anno = oggi.getFullYear(), mese = 0, tipo = "", statoF = "";
  const carica = async () => {
    let d; try { d = await api("GET", "/gestione/posta-in/amministrazione?anno=" + anno + (mese ? "&mese=" + mese : "") + (tipo ? "&tipo=" + tipo : "") + (statoF ? "&stato=" + statoF : "")); }
    catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const sel = (opz, val, cambia, stile) => h("select", { style: stile || "width:auto", onchange: (ev) => { cambia(ev.target.value); carica(); } }, opz.map(([v, t]) => h("option", { value: v, selected: String(v) === String(val) }, t)));
    const anni = [...new Set([oggi.getFullYear(), ...d.anni])].sort((a, b) => b - a);
    const filtri = h("div", { class: "azioni", style: "align-items:center" },
      sel(anni.map(a => [a, String(a)]), anno, v => { anno = Number(v); }),
      sel([[0, "tutto l'anno"], ...MESI_IT.map((m, i) => [i + 1, m])], mese, v => { mese = Number(v); }),
      sel([["", "tutti i tipi"], ...Object.entries(_TIPI_DOC)], tipo, v => { tipo = v; }),
      sel([["", "tutti gli stati"], ...Object.entries(_STATI_DOC)], statoF, v => { statoF = v; }),
      h("button", { class: "s", type: "button", onclick: async () => {
        try { const r = await fetch("/gestione/posta-in/amministrazione.csv?anno=" + anno, { headers: { Authorization: "Bearer " + token } });
          if (!r.ok) throw new Error("Esportazione non riuscita (" + r.status + ")");
          const l = h("a", { href: URL.createObjectURL(await r.blob()), download: "opifex-fatture-" + anno + ".csv" }); document.body.append(l); l.click(); l.remove(); }
        catch (e) { box.prepend(avviso(e.message, "no")); } } }, "Scarica l'elenco (Excel)"));
    const t = d.totali;
    const somma = (...k) => k.reduce((a, x) => a + (t[x] || 0), 0);
    const cifre = h("div", { class: "posta-cifre" },
      h("div", { class: "carta" }, h("div", { class: "sotto" }, "Uscite pagate"), h("strong", {}, _euro(somma("uscita_pagato")))),
      h("div", { class: "carta" }, h("div", { class: "sotto" }, "Da pagare"), h("strong", {}, _euro(somma("uscita_da_pagare")))),
      h("div", { class: "carta" }, h("div", { class: "sotto" }, "Entrate incassate"), h("strong", {}, _euro(somma("entrata_incassato")))),
      h("div", { class: "carta" }, h("div", { class: "sotto" }, "Da incassare"), h("strong", {}, _euro(somma("entrata_da_incassare")))));
    const riga = (x) => {
      const statoSel = h("select", { style: "width:auto", onchange: async (ev) => { await api("PUT", "/gestione/posta-in/amministrazione/" + x.id, { stato: ev.target.value }); carica(); } },
        Object.entries(_STATI_DOC).map(([v, t_]) => h("option", { value: v, selected: v === x.stato }, t_)));
      const file = (x.file_drive || []).map(f => h("a", { href: f.link, target: "_blank", rel: "noopener", class: "etichetta si", title: f.nome }, "📎 su Drive"));
      const segni = [
        ...file,
        x.da_sito ? h("a", { href: x.link_sito, target: "_blank", rel: "noopener noreferrer", class: "etichetta urg2", title: "La ricevuta non è allegata: va scaricata dal sito (" + (x.link_sito.split("/")[2] || "") + ")" }, "🔗 da scaricare dal sito") : null,
        x.drive_stato === "nessun_allegato" ? h("span", { class: "etichetta", title: "Nessun allegato e nessun link: guarda l'email" }, "nessun allegato") : null,
        x.drive_stato === "drive_non_collegato" ? h("span", { class: "etichetta urg2" }, "Drive non collegato") : null,
        x.drive_stato.startsWith("errore") ? h("button", { class: "etichetta urg3", type: "button", title: x.drive_stato, onclick: async () => { await api("POST", "/gestione/posta-in/amministrazione/" + x.id + "/archivia"); carica(); } }, "⚠ Drive: riprova") : null,
        x.verificato ? h("span", { class: "etichetta si" }, "✓ verificato") : null];
      const scheda = h("div", { class: "posta-voce doc" + (x.direzione === "entrata" ? " entrata" : "") },
        h("div", { class: "posta-testa" }, h("strong", {}, x.controparte || "?"), h("strong", { class: "doc-importo" }, (x.direzione === "entrata" ? "+ " : "") + _euro(x.importo, x.valuta))),
        h("div", { class: "posta-etichette" }, h("span", { class: "etichetta" }, _TIPI_DOC[x.tipo] || x.tipo), h("span", { class: "sotto" }, _giorno(x.data_documento) + (x.numero ? " · n. " + x.numero : "")),
          x.scadenza ? h("span", { class: "sotto" }, "scadenza " + _giorno(x.scadenza)) : null),
        x.descrizione ? h("div", {}, x.descrizione) : null,
        h("div", { class: "posta-etichette" }, ...segni),
        h("div", { class: "azioni", style: "align-items:center" }, statoSel,
          h("button", { class: "s piccolo", type: "button", onclick: () => _apriEmail(x.origine + "-" + x.casella_id, x.msg_id, scheda, x) }, "Apri l'email"),
          h("button", { class: "s piccolo", type: "button", onclick: () => modifica(x, scheda) }, "Correggi"),
          x.verificato ? null : h("button", { class: "s piccolo", type: "button", onclick: async () => { await api("PUT", "/gestione/posta-in/amministrazione/" + x.id, { verificato: true }); carica(); } }, "✓ Dati giusti"),
          h("button", { class: "collegamento", type: "button", onclick: async () => { await api("DELETE", "/gestione/posta-in/amministrazione/" + x.id); carica(); } }, "non è un documento")));
      return scheda;
    };
    const modifica = (x, dove) => {
      if (dove._modifica) { dove._modifica.remove(); dove._modifica = null; return; }
      const c = {};
      const campo = (k, etichetta, attr) => { c[k] = h("input", { value: x[k] ?? "", ...attr }); return h("label", {}, etichetta, c[k]); };
      c.tipo = h("select", {}, Object.entries(_TIPI_DOC).map(([v, t_]) => h("option", { value: v, selected: v === x.tipo }, t_)));
      c.direzione = h("select", {}, [["uscita", "Pago io (passiva)"], ["entrata", "Incasso io (attiva)"]].map(([v, t_]) => h("option", { value: v, selected: v === x.direzione }, t_)));
      const f = h("div", { class: "carta posta-compito" }, h("h3", {}, "Correggi i dati"),
        h("div", { class: "posta-campi" }, h("label", {}, "Tipo", c.tipo), h("label", {}, "Direzione", c.direzione), campo("controparte", "Controparte"), campo("importo", "Importo", { type: "number", step: "0.01" }),
          campo("data_documento", "Data", { type: "date" }), campo("scadenza", "Scadenza", { type: "date" }), campo("numero", "Numero"), campo("attivita", "Attività (Logos, Renovatio…)")),
        campo("descrizione", "Descrizione"),
        h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: async () => {
          const v = (k) => c[k].value.trim();
          try { await api("PUT", "/gestione/posta-in/amministrazione/" + x.id, { tipo: v("tipo"), direzione: v("direzione"), controparte: v("controparte"), descrizione: v("descrizione"),
              importo: v("importo") === "" ? null : Number(v("importo")), data_documento: v("data_documento") || null, scadenza: v("scadenza") || null, numero: v("numero"), attivita: v("attivita"), verificato: true });
            carica(); } catch (e) { f.append(avviso(e.message, "no")); } } }, "Salva"),
          h("button", { class: "s", type: "button", onclick: () => { f.remove(); dove._modifica = null; } }, "Annulla")));
      dove._modifica = f; dove.after(f);
    };
    riempi(box, [
      h("p", { class: "sotto" }, "Fatture, ricevute e avvisi di pagamento trovati nella posta dal modello locale. Gli allegati finiscono su Drive in Controllo di gestione → Passive (o Attive) → anno → mese; "
        + "quando la ricevuta va presa da un sito compare 🔗." + (d.drive ? "" : " Drive non è collegato: i file restano nelle email finché non lo colleghi.")),
      filtri,
      d.scadono.length ? h("div", { class: "carta" }, h("h3", {}, "In scadenza nei prossimi 14 giorni"),
        d.scadono.map(x => h("div", { class: "posta-imparato-riga" }, h("strong", {}, _giorno(x.scadenza)), h("span", {}, x.controparte), h("span", {}, _euro(x.importo, x.valuta)), h("span", { class: "sotto" }, _STATI_DOC[x.stato])))) : null,
      cifre,
      d.documenti.length ? d.documenti.map(riga) : h("p", { class: "sotto" }, "Nessun documento in questo periodo. Il filtro li cerca nella posta nuova; per quella passata usa «Analizza» nella scheda Il punto.")]);
  };
  carica();
  return box;
}
const MESI_IT = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

function vistaPosta() {
  const elenco = [["Il punto", _pannelloCosaFare()], ["Da leggere", _pannelloDaLeggere()], ["Conversazioni", _pannelloSituazioni()], ["Fatture e pagamenti", _pannelloPagamenti()], ["Le caselle", _pannelloCaselle()],
    ["Da approvare", [h("p", { class: "sotto" }, "Le email che gli agenti hanno preparato e aspettano il tuo via libera."), codaEmailUscita()]], ["Filtro", _pannelloFiltro()]];
  const s = schede(elenco, stato.postaScheda || 0);
  s.querySelectorAll(".scheda-tab").forEach((b, i) => b.addEventListener("click", () => { stato.postaScheda = i; }));
  return [h("h2", {}, "Posta"), s];
}
