// Padre Casati (3.0): studia canali YouTube con il modello locale e costruisce le competenze degli agenti.
// Schede: Al lavoro · Da studiare · Competenze · Esami · Richieste.

function _quandoCasati(iso) {
  if (!iso) return "";
  const d = new Date(iso), oggi = new Date();
  return d.toDateString() === oggi.toDateString() ? d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("it-IT", { day: "numeric", month: "short" }) + " " + d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}
const _STATI_TARGET = { proposto: "da approvare", attivo: "in studio", in_pausa: "in pausa", finito: "finito", rifiutato: "rifiutato" };
const _STATI_FONTE = { da_studiare: "da studiare", studiata: "studiata, da integrare", integrata: "nel manuale", saltata: "saltata", errore: "errore" };

// tre barre: studio (quanto c'e' dietro la competenza), esami, pratica
function _barra(etichetta, valore, massimo, testo) {
  const p = massimo > 0 ? Math.min(100, Math.round(100 * valore / massimo)) : 0;
  return h("div", { class: "casati-barra" }, h("span", { class: "sotto" }, etichetta),
    h("div", { class: "casati-traccia", role: "img", "aria-label": etichetta + ": " + testo }, h("div", { class: "casati-pieno", style: "width:" + p + "%" })),
    h("span", { class: "casati-val" }, testo));
}

function _casatiAlLavoro(d, ricarica) {
  const a = d.adesso || {}, c = d.conti || {};
  const interr = h("button", { class: "s", type: "button" }, d.attivo ? "Ferma lo studio" : "Fai studiare Padre Casati");
  interr.onclick = async () => { interr.disabled = true; try { await api("POST", "/gestione/scuola/attivo", { attivo: !d.attivo }); } catch (e) { alert(e.message); } ricarica(); };
  const ora = !d.attivo ? avviso("Lo studio è fermo.", "avv")
    : a.fase ? h("div", { class: "casati-ora" }, h("span", { class: "casati-punto", "aria-hidden": "true" }), h("div", {}, h("strong", {}, a.fase), h("div", { class: "sotto" }, "dalle " + _quandoCasati(a.da) + (d.notte ? " · è notte: prima gli esami" : ""))))
    : avviso(a.pausa || (d.occupato ? "In pausa: il modello locale serve agli agenti o alla posta." : "In attesa del prossimo giro…"), "avv");
  const numeri = h("div", { class: "casati-numeri" },
    ...[["video da studiare", c.da_studiare], ["da integrare", c.da_integrare], ["nel manuale", c.integrate], ["oggi", c.oggi], ["saltati (senza sottotitoli)", c.saltate]]
      .map(([t, n]) => h("div", { class: "casati-numero" }, h("b", {}, String(n || 0)), h("span", { class: "sotto" }, t))));
  const reg = h("ul", { class: "casati-registro" }, ...(d.registro || []).map(r => h("li", {}, h("span", { class: "sotto" }, _quandoCasati(r.quando)), " ", r.testo)));
  const extra = [];
  if (d.importabile) {
    const imp = h("button", { class: "s piccolo", type: "button" }, "Importa competenze e studi dalla 2");
    imp.onclick = async () => { imp.disabled = true; try { const r = await api("POST", "/gestione/scuola/importa"); imp.replaceWith(avviso("Importate " + r.competenze + " competenze e " + r.video + " video già studiati.", "ok")); } catch (e) { imp.replaceWith(avviso(e.message, "no")); } };
    extra.push(imp);
  }
  return [h("p", { class: "sotto" }, "Studia solo con il modello locale e solo quando il computer non serve agli agenti o alla posta. Di notte (1–6) interroga gli agenti."),
    ora, numeri, h("div", { class: "riga-azioni" }, interr, ...extra), h("h3", {}, "Diario"), (d.registro || []).length ? reg : h("p", { class: "sotto" }, "Ancora niente.")];
}

function _casatiTarget(d, ricarica) {
  const nomiComp = (d.competenze || []).map(c => c.nome);
  const ind = h("input", { type: "text", placeholder: "Link YouTube (canale, playlist o video) oppure il nome del canale", "aria-label": "Canale da studiare" });
  const comp = h("input", { type: "text", list: "casati-comp", placeholder: "Per quale competenza", "aria-label": "Competenza" });
  const dl = h("datalist", { id: "casati-comp" }, ...nomiComp.map(n => h("option", { value: n })));
  const esito = h("div");
  const aggiungi = h("button", { class: "s", type: "submit" }, "Aggiungi");
  const modulo = h("form", { class: "casati-modulo" }, ind, comp, dl, aggiungi);
  modulo.onsubmit = async (ev) => { ev.preventDefault(); aggiungi.disabled = true;
    try { await api("POST", "/gestione/scuola/target", { indirizzo: ind.value.trim(), competenza: comp.value.trim() }); ricarica(); }
    catch (e) { riempi(esito, avviso(e.message, "no")); aggiungi.disabled = false; } };
  const tema = h("input", { type: "text", placeholder: "Un tema nuovo: Padre Casati cerca i canali migliori e te li propone", "aria-label": "Tema da studiare" });
  const cerca = h("button", { class: "s", type: "submit" }, "Cerca canali");
  const modTema = h("form", { class: "casati-modulo" }, tema, cerca);
  modTema.onsubmit = async (ev) => { ev.preventDefault(); cerca.disabled = true;
    try { await api("POST", "/gestione/scuola/competenze", { nome: tema.value.trim() }); ricarica(); } catch (e) { riempi(esito, avviso(e.message, "no")); cerca.disabled = false; } };
  const azione = (t, az, testo) => { const b = h("button", { class: "s piccolo", type: "button" }, testo);
    b.onclick = async () => { b.disabled = true; try { await api("POST", "/gestione/scuola/target/" + t.id, { azione: az }); ricarica(); } catch (e) { riempi(esito, avviso(e.message, "no")); } }; return b; };
  const proposti = (d.target || []).filter(t => t.stato === "proposto"), altri = (d.target || []).filter(t => t.stato !== "proposto" && t.tipo !== "tema");
  const temi = (d.target || []).filter(t => t.tipo === "tema" && t.stato === "attivo");
  const carta = (t) => h("div", { class: "carta casati-target" + (t.stato === "proposto" ? " proposto" : "") },
    h("div", { class: "posta-testa" }, h("strong", {}, t.nome || t.indirizzo), h("span", { class: "etichetta" }, _STATI_TARGET[t.stato] || t.stato)),
    h("div", { class: "sotto" }, "per «" + t.competenza + "» · " + (t.tipo === "video" ? "video" : t.video_totali + " video") + " · " + t.studiati + " studiati" + (t.restanti ? " · " + t.restanti + " in coda" : "") + (t.saltati ? " · " + t.saltati + " senza sottotitoli" : "")),
    t.motivo && t.proposto_da === "casati" ? h("div", {}, "Perché: " + t.motivo) : null,
    t.errore ? avviso("Ultimo tentativo: " + t.errore, "no") : null,
    t.indirizzo.startsWith("http") ? h("a", { href: t.indirizzo, target: "_blank", rel: "noopener" }, "Apri su YouTube") : null,
    h("div", { class: "riga-azioni" }, ...(t.stato === "proposto" ? [azione(t, "approva", "✓ Approva"), azione(t, "rifiuta", "Rifiuta")]
      : t.stato === "attivo" ? [azione(t, "pausa", "Pausa"), azione(t, "elimina", "Togli")] : [azione(t, "riprendi", "Riprendi"), azione(t, "elimina", "Togli")])));
  return [esito,
    proposti.length ? h("div", {}, h("h3", {}, "Proposte di Padre Casati"), h("p", { class: "sotto" }, "Non studia questi canali finché non li approvi."), ...proposti.map(carta)) : null,
    temi.length ? avviso("Sta cercando i canali migliori su: " + temi.map(t => "«" + t.indirizzo + "»").join(", "), "avv") : null,
    h("h3", {}, "Canali da studiare"), modulo, modTema,
    ...(altri.length ? altri.map(carta) : [h("p", { class: "sotto" }, "Nessun canale: aggiungine uno.")])];
}

function _casatiDettaglio(id, box, agenti) {
  riempi(box, h("p", { class: "sotto" }, "Carico…"));
  api("GET", "/gestione/scuola/competenze/" + id).then(c => {
    const scegli = h("select", { "aria-label": "Agente" }, h("option", { value: "" }, "Dai a un agente…"),
      ...agenti.filter(a => !c.agenti.some(x => x.id === a.id)).map(a => h("option", { value: a.id }, a.nome)));
    scegli.onchange = async () => { if (!scegli.value) return; await api("POST", "/gestione/scuola/competenze/" + id + "/agenti", { agente_id: +scegli.value }); _casatiDettaglio(id, box, agenti); };
    const agente = (x) => h("div", { class: "carta casati-agente" },
      h("div", { class: "posta-testa" }, h("strong", {}, x.nome), h("span", { class: "etichetta" }, "livello " + x.livello)),
      _barra("Studio", Math.min(c.tetto, x.livello + 1), Math.max(c.tetto, x.livello + 1), "può arrivare al " + c.tetto),
      _barra("Esami", x.esami_superati, x.esami_superati + x.esami_falliti || 1, x.esami_superati + " superati · " + x.esami_falliti + " no"),
      _barra("Pratica", Math.min(x.usi_dal_livello, 1), 1, x.usi + " usi" + (x.usi_dal_livello ? "" : " · da usare per salire")),
      x.esame_in_sospeso ? h("div", { class: "sotto" }, "Esame superato: sale appena la usa nel lavoro.") : null,
      x.nota ? h("div", { class: "sotto" }, x.nota) : null,
      h("div", { class: "sotto" }, "Assegnata da: " + x.assegnata_da + (x.prossimo_esame ? " · prossimo esame dal " + new Date(x.prossimo_esame).toLocaleDateString("it-IT") : "")),
      h("button", { class: "s piccolo", type: "button", onclick: async () => { await api("POST", "/gestione/scuola/competenze/" + id + "/agenti", { agente_id: x.id, togli: true }); _casatiDettaglio(id, box, agenti); } }, "Togli"));
    const sezioni = c.sezioni.map(s => h("details", { class: "casati-sezione" }, h("summary", {}, s.titolo), h("div", { class: "casati-testo" }, s.testo)));
    const fonti = h("ul", { class: "casati-fonti" }, ...c.fonti.slice(0, 120).map(f => h("li", {},
      f.tipo === "video" ? h("a", { href: "https://www.youtube.com/watch?v=" + f.rif, target: "_blank", rel: "noopener" }, f.titolo || f.rif) : (f.titolo || f.rif),
      h("span", { class: "sotto" }, " — " + (f.autore || "") + " · " + (_STATI_FONTE[f.stato] || f.stato) + (f.errore && f.stato === "saltata" ? " (" + f.errore.slice(0, 60) + ")" : "")))));
    riempi(box, h("div", { class: "casati-dettaglio" },
      h("p", {}, c.carta || h("span", { class: "sotto" }, "La carta d'identità arriva col primo manuale.")),
      h("p", { class: "sotto" }, "Versione " + c.versione + " · livello massimo raggiungibile oggi: " + c.tetto + (c.drive_id ? " · copia su Drive in Agenti/Padre Casati/Competenze" : "")),
      h("h4", {}, "Agenti (" + c.agenti.length + ")"), scegli, ...c.agenti.map(agente),
      h("h4", {}, "Manuale (" + c.sezioni.length + " sezioni)"), ...(sezioni.length ? sezioni : [h("p", { class: "sotto" }, "Ancora vuoto.")]),
      h("h4", {}, "Fonti (" + c.fonti.length + ")"), fonti));
  }).catch(e => riempi(box, avviso(e.message, "no")));
}

function _casatiCompetenze(d) {
  if (!(d.competenze || []).length) return [h("p", { class: "sotto" }, "Nessuna competenza ancora.")];
  return (d.competenze || []).map(c => {
    const box = h("div");
    const testa = h("button", { class: "casati-comp-testa", type: "button", "aria-expanded": "false" },
      h("strong", {}, c.nome), h("span", { class: "sotto" }, c.sezioni + " sezioni · " + c.fonti + " fonti · " + c.agenti + (c.agenti === 1 ? " agente" : " agenti") + " · fino al livello " + c.tetto));
    testa.onclick = () => { const ap = testa.getAttribute("aria-expanded") === "true"; testa.setAttribute("aria-expanded", ap ? "false" : "true"); if (ap) riempi(box, ""); else _casatiDettaglio(c.id, box, d.agenti || []); };
    return h("div", { class: "carta casati-comp" }, testa, c.carta ? h("div", { class: "sotto" }, c.carta) : null, box);
  });
}

function _casatiEsami(d) {
  if (!(d.esami || []).length) return [h("p", { class: "sotto" }, "Nessun esame ancora: si fanno di notte, tra l'1 e le 6, quando un manuale è pronto.")];
  return [h("div", { class: "tabella-scorre" }, h("table", { class: "tabella" },
    h("thead", {}, h("tr", {}, ...["Quando", "Agente", "Competenza", "Livello", "Voto", "Esito", "Commento"].map(t => h("th", {}, t)))),
    h("tbody", {}, ...d.esami.map(e => h("tr", {}, h("td", {}, _quandoCasati(e.fatto_il)), h("td", {}, e.agente), h("td", {}, e.competenza), h("td", {}, String(e.livello_tentato)),
      h("td", {}, e.voto === null ? "" : e.voto + "/100"), h("td", {}, e.superato ? "✓ superato" : "✗ da ripassare"), h("td", {}, e.commento))))))];
}

function _casatiRichieste(d) {
  if (!(d.richieste || []).length) return [h("p", { class: "sotto" }, "Nessuna richiesta: gli agenti chiedono qui le competenze che sentono di non avere.")];
  return (d.richieste || []).map(r => h("div", { class: "carta" },
    h("div", { class: "posta-testa" }, h("strong", {}, r.tema), h("span", { class: "sotto" }, (r.agente || "Lorenzo") + " · " + _quandoCasati(r.creata_il))),
    r.motivo ? h("div", {}, r.motivo) : null,
    h("div", { class: "sotto" }, r.stato === "assegnata" ? "Data subito: «" + (r.competenza || "") + "»" : r.stato === "in_studio" ? "In studio: Padre Casati cerca i canali" : r.stato)));
}

function vistaScuola() {
  const box = h("div", {}, h("p", { class: "sotto" }, "Carico…"));
  let attesa = null;
  const carica = async (auto) => {
    clearTimeout(attesa);
    if (!box.isConnected && auto) return;
    const occupato = box.querySelector(".casati-dettaglio, details[open]") || (document.activeElement && box.contains(document.activeElement) && /^(INPUT|SELECT)$/.test(document.activeElement.tagName));
    if (auto && occupato) { attesa = setTimeout(() => carica(true), 10000); return; }
    let d;
    try { d = await api("GET", "/gestione/scuola"); } catch (e) { riempi(box, avviso(e.message, "no")); return; }
    const da = (d.target || []).filter(t => t.stato === "proposto").length;
    const s = schede([["Al lavoro", _casatiAlLavoro(d, carica)], ["Da studiare" + (da ? " (" + da + ")" : ""), _casatiTarget(d, carica)], ["Competenze", _casatiCompetenze(d)],
      ["Esami", _casatiEsami(d)], ["Richieste", _casatiRichieste(d)]], stato.scuolaScheda || 0);
    s.querySelectorAll(".scheda-tab").forEach((b, i) => b.addEventListener("click", () => { stato.scuolaScheda = i; }));
    riempi(box, s);
    attesa = setTimeout(() => { if (box.isConnected) carica(true); }, 10000);
  };
  carica();
  return [h("h2", {}, "Padre Casati"), box];
}
