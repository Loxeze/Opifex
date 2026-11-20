"use strict";
// Il legale (2.68): consiglia e non blocca, non inventa (cita solo fonti verificate), vigila sul lavoro della squadra, studia i fascicoli.

const RISCHIO_LG = { basso: ["basso", "ok"], medio: ["medio", "avv"], alto: ["alto", "no"] };
const CATEGORIE_LG = { rapporto: "Rapporti in essere", polizza: "Polizze", ente_pubblico: "Contratti con enti pubblici", privato: "Contratti con privati",
  fornitore: "Fornitori", collaboratore: "Collaboratori", causa: "Cause", altro: "Altri documenti" };
const TIPI_FASC_LG = { causa: "Causa", contratto: "Contratto", pratica: "Pratica", verifica: "Verifica" };
const STATI_DOC_LG = { da_leggere: "da leggere", in_lettura: "in lettura", letto: "letto", errore: "non leggibile" };
const STATI_INC_LG = { in_coda: "in coda", studio: "studio", ricerca: "ricerca", relazione: "relazione", consegnato: "consegnato", errore: "errore" };
const ORDINI_LG = ["Studia questi documenti e imposta la difesa", "Trovami una via d'uscita da questa situazione", "Prepara le domande da fare al mio avvocato",
  "Trova sentenze su casi simili e dimmi come sono finite"];
const _btnLg = (testo, fn, cls) => h("button", { class: cls || "s", type: "button", onclick: async (ev) => { const b = ev.currentTarget; b.disabled = true; try { await fn(); } finally { b.disabled = false; } } }, testo);
const _quandoLg = (x) => x ? new Date(x).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const _etLg = (r) => { const [t, c] = RISCHIO_LG[r] || ["—", ""]; return h("span", { class: "etichetta " + c }, "rischio " + t); };

function vistaLegale() {
  const corpo = h("div", { class: "lg" }, h("p", { class: "sotto" }, "Carico…"));
  const ricarica = async () => {
    let d;
    try { d = await api("GET", "/gestione/legale"); } catch (e) { riempi(corpo, avviso(e.message, "no")); return; }
    if (!d.attivo) { riempi(corpo, avviso("Il legale c'è solo in Opifex 3.", "avv")); return; }
    if (stato.legaleFascicolo) { riempi(corpo, await _fascicoloLg(d, stato.legaleFascicolo, ricarica)); return; }
    const scheda = stato.legaleScheda || "quadro";
    const tab = (id, et, n) => h("button", { type: "button", class: scheda === id ? "attivo" : "", "aria-current": scheda === id ? "page" : null,
      onclick: () => { stato.legaleScheda = id; ricarica(); } }, et, n ? h("span", { class: "lg-n" }, String(n)) : null);
    const c = d.conteggi;
    const tessera = (titolo, valore, sotto, dove) => h("button", { type: "button", class: "tessera cliccabile lg-tessera", onclick: () => { stato.legaleScheda = dove; ricarica(); } },
      h("div", { class: "sotto" }, titolo), h("div", { class: "valore" }, String(valore)), sotto ? h("div", { class: "sotto" }, sotto) : null);
    const pagine = { quadro: _quadroLg, consigli: _consigliLg, fascicoli: _fascicoliLg, contratti: _contrattiLg, domande: _domandeLg, biblioteca: _bibliotecaLg, formazione: _formazioneLg };
    riempi(corpo, [
      h("p", { class: "aiuto" }, "Il " + d.agenti.master.nome + " consiglia e non blocca: chi gli chiede un parere va avanti comunque. Cita solo norme e sentenze verificate su siti ufficiali; " +
        "le ricerche sul web le fa il " + (d.agenti.ricercatore ? d.agenti.ricercatore.nome : "Ricercatore legale") + " con domande anonime. I fascicoli riservati li legge solo il modello locale."),
      h("div", { class: "lg-stato" },
        h("span", { class: "lg-pallino" + (d.fase ? " attivo" : "") }), h("span", {}, d.fase ? "Adesso: " + d.fase : "In attesa di lavoro"),
        h("span", { class: "etichetta " + (d.locale ? "ok" : "avv") }, d.locale ? "computer locale collegato" : "nessun computer locale: i fascicoli riservati aspettano"),
        d.drive ? h("a", { class: "lg-link", href: d.drive, target: "_blank", rel: "noopener" }, "Apri Drive › Legale ↗")
          : _btnLg("Prepara la cartella Drive «Legale»", async () => { try { const r = await api("POST", "/gestione/legale/drive"); window.open(r.drive, "_blank", "noopener"); ricarica(); } catch (e) { alert(e.message); } })),
      h("div", { class: "tessere" },
        tessera("Rischio alto da vedere", c.alto, "consigli", "consigli"),
        tessera("Domande per te", c.domande, "da chiarire", "domande"),
        tessera("Scadenze entro 30 giorni", c.scadenze_30, "contratti e pratiche", "contratti"),
        tessera("Fascicoli aperti", d.fascicoli.filter(f => f.stato === "aperto").length, null, "fascicoli"),
        tessera("Fonti verificate", d.fonti.filter(f => f.verificata).length, "in biblioteca", "biblioteca")),
      h("nav", { class: "schede-gruppo lg-schede", "aria-label": "Sezioni del legale" },
        tab("quadro", "Cosa sta facendo"), tab("consigli", "Consigli", c.alto), tab("fascicoli", "Fascicoli"), tab("contratti", "Contratti e scadenze"),
        tab("domande", "Da chiarire", c.domande), tab("biblioteca", "Biblioteca"), tab("formazione", "Formazione")),
      (pagine[scheda] || _quadroLg)(d, ricarica)]);
  };
  ricarica();
  const timer = setInterval(() => { if (!corpo.isConnected) { clearInterval(timer); return; } if (!corpo.querySelector("textarea:focus, input:focus") && !stato.legaleFascicolo) ricarica(); }, 30000);
  return [h("h2", {}, "Legale"), corpo];
}

function _chiediLg(ricarica) {
  const dom = h("textarea", { rows: 3, placeholder: "Es. Posso usare le foto di un evento pubblico per la pagina di Renovatio senza chiedere il consenso a chi compare?" });
  const amb = h("input", { type: "text", placeholder: "Impresa o attività (facoltativo)", maxlength: 200 });
  const esito = h("div");
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Chiedi un consiglio"),
    h("label", {}, "La domanda", dom), h("label", {}, "Ambito", amb),
    h("div", { class: "azioni" }, _btnLg("Chiedi al legale", async () => {
      if (dom.value.trim().length < 5) { esito.replaceChildren(avviso("Scrivi la domanda", "avv")); return; }
      esito.replaceChildren(h("p", { class: "sotto" }, "Il legale ci pensa…"));
      try { const p = await api("POST", "/gestione/legale/pareri", { domanda: dom.value, ambito: amb.value }, { scadenzaMs: 120000 }); esito.replaceChildren(_parereLg(p, ricarica, true)); dom.value = ""; }
      catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
    }, "p")), esito);
}

function _quadroLg(d, ricarica) {
  return h("div", { class: "lg-griglia" },
    h("div", {}, _chiediLg(ricarica)),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Cosa ha fatto"),
      d.registro.length ? h("ul", { class: "lg-registro" }, d.registro.slice(0, 14).map(r => h("li", {}, h("span", { class: "sotto" }, _quandoLg(r.creato_il)), " ", r.testo)))
        : h("p", { class: "sotto" }, "Ancora niente: appena carichi un documento, apri un fascicolo o un agente gli chiede un parere, lo vedi qui.")));
}

function _parereLg(p, ricarica, nuovo) {
  if (p.stato === "in_coda") return avviso("Il legale non può rispondere adesso: la domanda è in coda e il consiglio arriva qui appena possibile.", "avv");
  const fonti = p.fonti || [];
  return h("div", { class: "lg-parere" + (p.visto || nuovo ? "" : " nuovo") },
    h("div", { class: "lg-parere-testa" }, _etLg(p.rischio),
      h("span", { class: "sotto" }, [p.origine === "vigilanza" ? "dalla vigilanza" : p.agente ? "chiesto da " + p.agente : p.origine === "lorenzo" || nuovo ? "chiesto da te" : "", p.ambito, _quandoLg(p.creato_il)].filter(Boolean).join(" · "))),
    p.domanda ? h("div", { class: "lg-domanda" }, p.domanda) : null,
    h("div", { class: "lg-consiglio" }, p.consiglio),
    p.perche ? h("div", { class: "sotto" }, h("b", {}, "Perché: "), p.perche) : null,
    p.prossimo_passo ? h("div", { class: "sotto" }, h("b", {}, "Prossimo passo: "), p.prossimo_passo) : null,
    fonti.length ? h("div", { class: "lg-fonti" }, fonti.map(f => _fonteRigaLg(f))) : p.ricerche ? h("div", { class: "sotto" }, "Il Ricercatore legale sta verificando norme e precedenti.") : null,
    !nuovo && !p.visto ? h("div", { class: "azioni" }, _btnLg("Visto", async () => { await api("POST", "/gestione/legale/pareri/" + p.id + "/visto"); ricarica(); })) : null);
}

function _fonteRigaLg(f) {
  return h("div", { class: "lg-fonte" + (f.verificata ? " ok" : "") },
    h("span", { class: "lg-spunta", title: f.verifica || "" }, f.verificata ? "✓" : "?"),
    h("a", { href: f.url, target: "_blank", rel: "noopener" }, f.estremi),
    f.verificata ? null : h("span", { class: "sotto" }, " — " + (f.verifica || "da controllare: non citarla")));
}

function _consigliLg(d, ricarica) {
  const filtro = stato.legaleRischio || "";
  const el = d.pareri.filter(p => !filtro || p.rischio === filtro);
  const chip = (v, et) => h("button", { type: "button", class: "chip" + (filtro === v ? " ok" : ""), onclick: () => { stato.legaleRischio = v; ricarica(); } }, et);
  return h("div", {},
    h("div", { class: "azioni", style: "align-items:center" }, h("span", { class: "sotto" }, "Mostra:"), chip("", "tutti"), chip("alto", "rischio alto"), chip("medio", "medio"), chip("basso", "basso")),
    el.length ? h("div", { class: "lg-pareri" }, el.map(p => _parereLg(p, ricarica))) : h("p", { class: "sotto" }, "Nessun consiglio ancora. Gli agenti lo chiedono quando il lavoro tocca un tema legale; la vigilanza guarda il lavoro della squadra due volte al giorno."));
}

function _nuovoFascicoloLg(ricarica) {
  const titolo = h("input", { type: "text", maxlength: 160, placeholder: "Es. Causa con ex collaboratrice" });
  const tipo = h("select", {}, Object.entries(TIPI_FASC_LG).map(([k, v]) => h("option", { value: k }, v)));
  const fatti = h("textarea", { rows: 5, placeholder: "Racconta i fatti con parole tue: chi, cosa, quando, a che punto siete." });
  const parti = h("textarea", { rows: 2, placeholder: "I nomi delle parti, uno per riga: servono a toglierli dalle ricerche online" });
  const ris = h("input", { type: "checkbox", checked: true }), cl = h("input", { type: "checkbox" });
  const msg = h("div");
  return h("div", { class: "carta" }, h("div", { class: "nome" }, "Nuovo fascicolo"),
    h("div", { class: "griglia" }, h("label", {}, "Titolo", titolo), h("label", {}, "Tipo", tipo)),
    h("label", {}, "I fatti", fatti), h("label", {}, "Le parti (restano cifrate)", parti),
    h("label", { class: "interruttore" }, ris, h("span", {}, "Riservato: i documenti li legge solo il modello locale, niente esce da Opifex")),
    h("label", { class: "interruttore" }, cl, h("span", {}, "Permetti Claude per questo fascicolo (qualità migliore; i testi passano dal servizio di Anthropic)")),
    msg, h("div", { class: "azioni" }, _btnLg("Crea il fascicolo", async () => {
      try { const r = await api("POST", "/gestione/legale/fascicoli", { titolo: titolo.value, tipo: tipo.value, descrizione: fatti.value, parti: parti.value, riservato: ris.checked, claude_ammesso: cl.checked && ris.checked });
        stato.legaleFascicolo = r.id; ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    }, "p")));
}

function _fascicoliLg(d, ricarica) {
  const form = h("div");
  return h("div", {},
    h("p", { class: "aiuto" }, "Un fascicolo è una pratica: una causa, un rapporto, una verifica. Ci carichi i documenti (o li metti in Drive › Legale › Cause, una cartella per causa) e dai un incarico al legale: studia, cerca precedenti verificati e ti consegna la relazione."),
    h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: () => form.firstChild ? form.replaceChildren() : form.replaceChildren(_nuovoFascicoloLg(ricarica)) }, "+ Nuovo fascicolo")), form,
    d.fascicoli.length ? h("div", { class: "lg-elenco" }, d.fascicoli.map(f => h("button", { type: "button", class: "lg-riga", onclick: () => { stato.legaleFascicolo = f.id; ricarica(); } },
      h("span", { class: "lg-riga-titolo" }, h("b", {}, f.titolo), f.riservato ? h("span", { class: "etichetta" }, "riservato") : null, f.stato === "chiuso" ? h("span", { class: "etichetta" }, "chiuso") : null),
      h("span", { class: "sotto" }, [TIPI_FASC_LG[f.tipo], f.documenti + (f.documenti === 1 ? " documento" : " documenti") + (f.da_leggere ? " (" + f.da_leggere + " da leggere)" : ""),
        f.incarico ? "incarico: " + (f.incarico.fase || STATI_INC_LG[f.incarico.stato]) : "nessun incarico", f.domande ? f.domande + " domande per te" : null].filter(Boolean).join(" · ")))))
      : h("p", { class: "sotto" }, "Nessun fascicolo ancora."));
}

async function _fascicoloLg(d, fid, ricarica) {
  let f;
  try { f = await api("GET", "/gestione/legale/fascicoli/" + fid); } catch (e) { stato.legaleFascicolo = null; return avviso(e.message, "no"); }
  const indietro = h("button", { class: "s", type: "button", onclick: () => { stato.legaleFascicolo = null; ricarica(); } }, "← Tutti i fascicoli");
  const file = h("input", { type: "file", multiple: true });
  const esitoFile = h("div");
  const ordine = h("textarea", { rows: 3, placeholder: "Cosa deve fare il legale con questo fascicolo?" });
  const msg = h("div");
  const interr = (et, val, campo, aiuto) => { const c = h("input", { type: "checkbox", checked: !!val, onchange: async () => { try { await api("PUT", "/gestione/legale/fascicoli/" + fid, { [campo]: c.checked }); ricarica(); } catch (e) { alert(e.message); } } });
    return h("label", { class: "interruttore" }, c, h("span", {}, et, aiuto ? h("span", { class: "sotto" }, " — " + aiuto) : null)); };
  const fatti = h("textarea", { rows: 4 }, f.descrizione), parti = h("textarea", { rows: 2 }, f.parti);
  return h("div", {},
    h("div", { class: "azioni" }, indietro),
    h("div", { class: "lg-fasc-testa" }, h("div", { class: "lg-titolo" }, f.titolo), h("span", { class: "etichetta" }, TIPI_FASC_LG[f.tipo]), f.riservato ? h("span", { class: "etichetta avv" }, f.claude_ammesso ? "riservato · Claude ammesso" : "riservato · solo modello locale") : null,
      f.drive ? h("a", { class: "lg-link", href: f.drive, target: "_blank", rel: "noopener" }, "Cartella in Drive ↗") : null),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Dai un incarico"),
      h("div", { class: "lg-suggeriti" }, ORDINI_LG.map(o => h("button", { type: "button", class: "chip", onclick: () => { ordine.value = o; ordine.focus(); } }, o))),
      ordine, msg, h("div", { class: "azioni" }, _btnLg("Affida al legale", async () => {
        try { await api("POST", "/gestione/legale/fascicoli/" + fid + "/incarichi", { ordine: ordine.value }); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
      }, "p")),
      h("p", { class: "sotto" }, "Il legale finisce di leggere i documenti, studia il fascicolo, fa cercare al Ricercatore norme e sentenze (con domande anonime), le verifica e ti consegna la relazione qui. Le domande che restano aperte le trovi sotto, senza che il lavoro si fermi.")),
    f.incarichi.length ? h("div", {}, f.incarichi.map(i => h("details", { class: "carta lg-incarico", open: i === f.incarichi[0] && i.stato === "consegnato" },
      h("summary", {}, h("b", {}, i.ordine), " ", h("span", { class: "etichetta " + (i.stato === "consegnato" ? "ok" : i.stato === "errore" ? "no" : "avv") }, STATI_INC_LG[i.stato]),
        h("span", { class: "sotto" }, " " + (i.stato === "consegnato" ? "consegnato " + _quandoLg(i.consegnato_il) : (i.fase || "")))),
      i.risultato ? h("div", { class: "lg-relazione" }, i.risultato) : i.errore ? avviso(i.errore, "no") : h("p", { class: "sotto" }, "Al lavoro: " + (i.fase || "in coda"))))) : null,
    f.domande.length ? h("div", { class: "carta" }, h("div", { class: "nome" }, "Da chiarire con te"), f.domande.map(q => _domandaLg(q, ricarica))) : null,
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Documenti"),
      f.documenti.length ? f.documenti.map(x => _documentoLg(x, ricarica)) : h("p", { class: "sotto" }, "Nessun documento: caricali qui o mettili nella cartella del fascicolo in Drive."),
      h("div", { class: "azioni", style: "align-items:center" }, file, _btnLg("Carica", async () => {
        if (!file.files.length) return;
        const fd = new FormData(); for (const x of file.files) fd.append("file", x);
        try { const r = await api("POST", "/gestione/legale/fascicoli/" + fid + "/documenti", fd, { scadenzaMs: 180000 }); esitoFile.replaceChildren(avviso(r.caricati + " caricati" + (r.errori.length ? ". " + r.errori.join("; ") : ""), r.errori.length ? "avv" : "ok")); ricarica(); }
        catch (e) { esitoFile.replaceChildren(avviso(e.message, "no")); }
      }, "p")), esitoFile),
    f.fonti.length ? h("div", { class: "carta" }, h("div", { class: "nome" }, "Precedenti e norme trovati"), f.fonti.map(x => h("div", { class: "lg-fonte-blocco" }, _fonteRigaLg(x),
      x.fatti ? h("div", { class: "sotto" }, h("b", {}, "Fatti: "), x.fatti) : null, x.decisione ? h("div", { class: "sotto" }, h("b", {}, "Decisione: "), x.decisione) : null,
      x.perche_serve ? h("div", { class: "sotto" }, h("b", {}, "Perché serve: "), x.perche_serve) : null))) : null,
    h("details", { class: "carta" }, h("summary", {}, "Fatti, parti e impostazioni del fascicolo"),
      h("label", {}, "I fatti", fatti), h("label", {}, "Le parti", parti),
      h("div", { class: "azioni" }, _btnLg("Salva", async () => { await api("PUT", "/gestione/legale/fascicoli/" + fid, { descrizione: fatti.value, parti: parti.value }); ricarica(); })),
      interr("Riservato", f.riservato, "riservato", "i documenti li legge solo il modello locale"),
      f.riservato ? interr("Permetti Claude", f.claude_ammesso, "claude_ammesso", "qualità migliore, i testi passano dal servizio di Anthropic") : null,
      h("div", { class: "azioni" }, _btnLg(f.stato === "aperto" ? "Chiudi il fascicolo" : "Riapri il fascicolo", async () => { await api("PUT", "/gestione/legale/fascicoli/" + fid, { stato: f.stato === "aperto" ? "chiuso" : "aperto" }); ricarica(); }))));
}

function _schedaLg(s) {
  if (!s) return null;
  const lista = (et, v) => { const a = (v || []).map(x => typeof x === "object" ? (x.data ? x.data + ": " : "") + (x.cosa || JSON.stringify(x)) : x).filter(Boolean); return a.length ? h("div", {}, h("b", {}, et), h("ul", {}, a.slice(0, 12).map(x => h("li", {}, x)))) : null; };
  return h("div", { class: "lg-scheda" }, s.sintesi ? h("p", {}, s.sintesi) : null, lista("Parti", s.parti), lista("Obblighi", s.obblighi), lista("Scadenze", s.scadenze), lista("Penali", s.penali),
    lista("Riservatezza", s.riservatezza), lista("Importi", s.importi), lista("Punti critici", s.punti_critici));
}

function _documentoLg(x, ricarica) {
  return h("details", { class: "lg-doc" },
    h("summary", {}, h("span", {}, x.nome), " ", h("span", { class: "etichetta " + (x.stato === "letto" ? "ok" : x.stato === "errore" ? "no" : "avv") },
      STATI_DOC_LG[x.stato] + (x.stato === "in_lettura" ? " " + x.pezzi_letti + "/" + x.pezzi : "")),
      h("span", { class: "sotto" }, " " + [x.fascicolo_id ? null : CATEGORIE_LG[x.categoria], x.controparte, x.in_drive ? "in Drive" : "da archiviare in Drive"].filter(Boolean).join(" · "))),
    x.errore ? avviso(x.errore, "no") : null, _schedaLg(x.scheda),
    h("div", { class: "azioni" }, x.stato === "letto" || x.stato === "errore" ? _btnLg("Rileggi", async () => { try { await api("POST", "/gestione/legale/documenti/" + x.id + "/rileggi"); ricarica(); } catch (e) { alert(e.message); } }) : null,
      _btnLg("Togli da Opifex", async () => { await api("DELETE", "/gestione/legale/documenti/" + x.id); ricarica(); })));
}

function _contrattiLg(d, ricarica) {
  const file = h("input", { type: "file", multiple: true });
  const cat = h("select", {}, Object.entries(CATEGORIE_LG).filter(([k]) => k !== "causa").map(([k, v]) => h("option", { value: k, selected: k === "rapporto" }, v)));
  const esito = h("div");
  return h("div", {},
    h("p", { class: "aiuto" }, "Polizze e contratti con enti pubblici, privati, fornitori e collaboratori. Caricali qui (il legale li archivia nella sottocartella giusta del Drive) o mettili in blocco in Drive › Legale. Di ognuno nasce una scheda con obblighi, scadenze, penali e riservatezza: gli agenti che lavorano con quella controparte la vedono, e le scadenze ti arrivano come promemoria a 30, 7 e 1 giorno."),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Carica documenti"), h("div", { class: "azioni lg-carica", style: "align-items:center" }, file, cat, _btnLg("Carica", async () => {
      if (!file.files.length) return;
      const fd = new FormData(); for (const x of file.files) fd.append("file", x); fd.append("categoria", cat.value);
      try { const r = await api("POST", "/gestione/legale/documenti", fd, { scadenzaMs: 180000 }); esito.replaceChildren(avviso(r.caricati + " caricati" + (r.errori.length ? ". " + r.errori.join("; ") : ""), r.errori.length ? "avv" : "ok")); ricarica(); }
      catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
    }, "p")), esito),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Scadenze"),
      d.scadenze.length ? h("ul", { class: "lg-scadenze" }, d.scadenze.map(s => { const g = Math.round((new Date(s.data) - new Date(new Date().toDateString())) / 86400000);
        return h("li", { class: g <= 7 ? "vicina" : "" }, h("b", {}, dataIt(s.data)), h("span", { class: "sotto" }, g <= 0 ? " oggi" : g === 1 ? " domani" : " tra " + g + " giorni"), " ", s.titolo,
          s.fascicolo ? h("span", { class: "sotto" }, " · " + s.fascicolo) : null, " ", _btnLg("Fatta", async () => { await api("POST", "/gestione/legale/scadenze/" + s.id + "/fatta"); ricarica(); }, "s piccolo")); }))
        : h("p", { class: "sotto" }, "Nessuna scadenza: arrivano dalle schede dei documenti letti.")),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Registro dei documenti"),
      d.registro_contratti.length ? Object.entries(CATEGORIE_LG).map(([k, v]) => { const el = d.registro_contratti.filter(x => x.categoria === k); return el.length ? h("div", { class: "lg-gruppo" }, h("div", { class: "bt-cap" }, v + " (" + el.length + ")"), el.map(x => _documentoLg(x, ricarica))) : null; })
        : h("p", { class: "sotto" }, "Nessun documento ancora.")));
}

function _domandaLg(q, ricarica) {
  if (q.stato !== "aperta") return h("div", { class: "lg-domanda-fatta" }, h("div", { class: "sotto" }, q.domanda), h("div", {}, "→ " + (q.risposta || "non serve più")));
  const t = h("textarea", { rows: 2, placeholder: "La tua risposta" });
  return h("div", { class: "lg-domanda-aperta" }, h("div", {}, q.domanda), q.fascicolo ? h("div", { class: "sotto" }, q.fascicolo) : null, t,
    h("div", { class: "azioni" }, _btnLg("Rispondi", async () => { if (!t.value.trim()) return; await api("POST", "/gestione/legale/domande/" + q.id, { risposta: t.value }); ricarica(); }, "p"),
      _btnLg("Non serve più", async () => { await api("POST", "/gestione/legale/domande/" + q.id + "/superata"); ricarica(); })));
}

function _domandeLg(d, ricarica) {
  const aperte = d.domande.filter(q => q.stato === "aperta"), fatte = d.domande.filter(q => q.stato !== "aperta");
  return h("div", {}, h("p", { class: "aiuto" }, "Le domande che il legale ti fa per lavorare meglio. Non aspetta le risposte: quando rispondi, il prossimo incarico su quel fascicolo ne tiene conto."),
    aperte.length ? h("div", { class: "carta" }, aperte.map(q => _domandaLg(q, ricarica))) : h("p", { class: "sotto" }, "Nessuna domanda aperta."),
    fatte.length ? h("details", { class: "carta" }, h("summary", {}, "Risposte recenti (" + fatte.length + ")"), fatte.map(q => _domandaLg(q, ricarica))) : null);
}

function _bibliotecaLg(d, ricarica) {
  const luoghi = h("textarea", { rows: 4 }, d.luoghi);
  const ver = d.fonti.filter(f => f.verificata), altre = d.fonti.filter(f => !f.verificata);
  const blocco = (f) => h("div", { class: "lg-fonte-blocco" }, _fonteRigaLg(f), h("div", { class: "sotto" }, [f.tipo, f.ente, f.data_atto, f.luogo].filter(Boolean).join(" · ")),
    f.decisione ? h("div", { class: "sotto" }, f.decisione) : null);
  return h("div", {},
    h("p", { class: "aiuto" }, "Le norme, le sentenze e i regolamenti trovati dal Ricercatore legale. Una fonte è verificata quando il link è uscito dalla ricerca, la pagina è di un sito ufficiale, si apre e contiene il numero dell'atto: solo queste il legale le cita."),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Luoghi da sorvegliare"), h("p", { class: "sotto" }, "Uno per riga. Ogni mese il Ricercatore cerca i regolamenti vigenti di questi luoghi (eventi, suolo pubblico, turismo, paesaggio, commercio)."),
      luoghi, h("div", { class: "azioni" }, _btnLg("Salva i luoghi", async () => { await api("PUT", "/gestione/legale/luoghi", { testo: luoghi.value }); ricarica(); }, "p"))),
    h("div", { class: "carta" }, h("div", { class: "nome" }, "Verificate (" + ver.length + ")"), ver.length ? ver.map(blocco) : h("p", { class: "sotto" }, "Nessuna ancora.")),
    altre.length ? h("details", { class: "carta" }, h("summary", {}, "Trovate ma non verificate (" + altre.length + "): spunti da controllare, non da citare"), altre.map(blocco)) : null);
}

function _formazioneLg(d) {
  return h("div", {},
    h("p", { class: "aiuto" }, "Padre Casati studia per il legale i rami del diritto e la strategia legale: cerca i canali migliori, te li propone e li studia video per video. Il livello sale con lo studio, gli esami notturni e la pratica."),
    h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: () => vai("scuola") }, "Approva i canali in Padre Casati →")),
    h("div", { class: "lg-formazione" }, d.formazione.map(c => h("div", { class: "carta" },
      h("div", { class: "lg-comp-testa" }, h("b", {}, c.nome), h("span", { class: "etichetta" + (c.livello ? " ok" : "") }, "livello " + c.livello)),
      c.carta ? h("div", { class: "sotto" }, c.carta) : null,
      h("div", { class: "sotto" }, [c.sezioni + (c.sezioni === 1 ? " sezione del manuale" : " sezioni del manuale"), c.fonti_studiate + " fonti studiate",
        c.fonti_da_studiare ? c.fonti_da_studiare + " da studiare" : null, c.canali_proposti ? c.canali_proposti + " canali da approvare" : null,
        c.in_cerca ? "Padre Casati cerca i canali" : null].filter(Boolean).join(" · "))))));
}
