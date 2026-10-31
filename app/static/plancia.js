"use strict";
// Plancia 2.0: i numeri che contano a colpo d'occhio (CRM, consumi, uso, social) e le cose che aspettano te.
// Tutti i testi arrivano dall'API e sono inseriti come testo; i grafici sono SVG disegnati qui, senza librerie.

const PB = { verde: "#1E8466", ottone: "#B07A10", blu: "#3B7DC4", terra: "#C4502A", inchiostro: "#1B2421", tenue: "#5E6863", griglia: "#E3DED1",
  rampa: ["#EEF4F1", "#CFE3DA", "#9CCBBB", "#5FAA93", "#2E8A6F", "#0E5A45"], imbuto: ["#BFDACF", "#8CC0AC", "#5FAA93", "#2E8A6F", "#0E5A45"] };

function svgEl(tag, attrs, ...figli) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, String(v));
  for (const f of figli.flat(Infinity)) if (f !== null && f !== undefined && f !== false) e.append(typeof f === "string" ? document.createTextNode(f) : f);
  return e;
}
const nIt = (n, dec) => Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: dec || 0, maximumFractionDigits: dec == null ? 0 : dec });
const compatto = (n) => n >= 1e6 ? nIt(n / 1e6, 2) + " M" : n >= 1e3 ? nIt(n / 1e3, 1) + " k" : nIt(n);
const eur = (usd) => euro(usd);
const eurInt = (v) => "€ " + nIt(v);
const GIORNI_BREVI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const pbData = (iso) => { const d = new Date(iso + "T12:00:00"); return d.getDate() + " " + ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"][d.getMonth()]; };
function variazione(ora, prima) {
  if (!prima) return null;
  const p = Math.round(100 * (ora - prima) / prima);
  return { testo: (p > 0 ? "+" : "") + p + "%", su: p > 0 };
}

function graficoArea(valori, etichette, colore, formato, alt) {
  const W = 480, H = 190, l = 46, r = 8, t = 10, b = 24, iw = W - l - r, ih = H - t - b;
  const mx = Math.max(1e-9, ...valori) * 1.1;
  const X = (i) => l + iw * i / Math.max(1, valori.length - 1), Y = (v) => t + ih * (1 - v / mx);
  const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": alt, class: "bt-grafico" });
  for (let k = 0; k <= 3; k++) {
    const v = mx * k / 3;
    s.append(svgEl("line", { x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: PB.griglia }), svgEl("text", { x: l - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 12, fill: PB.tenue }, formato(v)));
  }
  [0, 10, 20, valori.length - 1].forEach(i => s.append(svgEl("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === valori.length - 1 ? "end" : "middle", "font-size": 12, fill: PB.tenue }, pbData(etichette[i]))));
  const linea = valori.map((v, i) => X(i).toFixed(1) + "," + Y(v).toFixed(1)).join(" L");
  s.append(svgEl("path", { d: `M${linea} L${X(valori.length - 1)},${Y(0)} L${X(0)},${Y(0)} Z`, fill: colore, "fill-opacity": ".14" }),
    svgEl("path", { d: "M" + linea, fill: "none", stroke: colore, "stroke-width": 2, "stroke-linejoin": "round" }),
    svgEl("circle", { cx: X(valori.length - 1), cy: Y(valori[valori.length - 1]), r: 4, fill: colore, stroke: "#FBF9F4", "stroke-width": 2 }));
  valori.forEach((v, i) => s.append(svgEl("circle", { cx: X(i), cy: Y(v), r: 9, fill: "transparent" }, svgEl("title", {}, pbData(etichette[i]) + ": " + formato(v)))));
  return s;
}

function graficoBarre(valori, etichette, colore, formato, alt) {
  const W = 480, H = 190, l = 46, r = 8, t = 16, b = 24, iw = W - l - r, ih = H - t - b;
  const mx = Math.max(1e-9, ...valori) * 1.12, n = valori.length, passo = iw / n, larg = Math.max(4, passo * 0.68);
  const Y = (v) => t + ih * (1 - v / mx);
  const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": alt, class: "bt-grafico" });
  for (let k = 0; k <= 3; k++) {
    const v = mx * k / 3;
    s.append(svgEl("line", { x1: l, x2: W - r, y1: Y(v), y2: Y(v), stroke: PB.griglia }), svgEl("text", { x: l - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 12, fill: PB.tenue }, formato(v)));
  }
  const imax = valori.indexOf(Math.max(...valori));
  valori.forEach((v, i) => {
    const x = l + passo * i + (passo - larg) / 2, oggi = i === n - 1, alt_ = Math.max(v ? 2 : 0, ih * v / mx);
    s.append(svgEl("rect", { x, y: t + ih - alt_, width: larg, height: alt_, rx: 2, fill: colore, "fill-opacity": oggi ? 1 : 0.55 }, svgEl("title", {}, pbData(etichette[i]) + ": " + formato(v))));
    if (oggi || i === imax) s.append(svgEl("text", { x: x + larg / 2, y: Math.max(11, t + ih - alt_ - 4), "text-anchor": oggi && n - 1 - imax < 3 && i !== imax ? "end" : "middle", "font-size": 12, "font-weight": 600, fill: PB.inchiostro }, formato(v)));
  });
  [0, 10, 20, n - 1].forEach(i => s.append(svgEl("text", { x: l + passo * i + passo / 2, y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle", "font-size": 12, fill: PB.tenue }, pbData(etichette[i]))));
  return s;
}

function sparkline(valori, colore) {
  const w = 120, hh = 34, mx = Math.max(...valori), mn = Math.min(...valori);
  const p = valori.map((v, i) => `${(i * w / Math.max(1, valori.length - 1)).toFixed(1)},${(hh - 3 - (hh - 6) * (v - mn) / ((mx - mn) || 1)).toFixed(1)}`).join(" ");
  return svgEl("svg", { viewBox: `0 0 ${w} ${hh}`, width: 120, height: 34, "aria-hidden": "true" }, svgEl("polyline", { points: p, fill: "none", stroke: colore, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
}

function graficoImbuto(imbuto) {
  const W = 440, riga = 78, H = imbuto.length * riga, maxW = W - 70;
  const mx = Math.max(1, imbuto[0].n);
  const s = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": "Imbuto di vendita dai contatti del CRM", class: "bt-grafico" });
  imbuto.forEach((f, i) => {
    const y = i * riga, w = Math.max(8, maxW * f.n / mx);
    s.append(svgEl("g", {}, svgEl("title", {}, f.fase + ": " + nIt(f.n)),
      svgEl("text", { x: 0, y: y + 16, "font-size": 15, "font-weight": 600, fill: PB.inchiostro }, f.fase, svgEl("tspan", { "font-weight": 400, fill: PB.tenue, "font-size": 13 }, "  " + (f.dal_precedente == null ? "tutti i contatti" : f.dal_precedente + "% di prima"))),
      svgEl("rect", { x: 0, y: y + 26, width: w, height: 36, rx: 6, fill: PB.imbuto[i] }),
      svgEl("text", { x: w + 12, y: y + 55, "font-size": 28, "font-weight": 500, fill: PB.inchiostro, "font-family": "Newsreader, Georgia, serif" }, nIt(f.n))));
  });
  return s;
}

function mappaUso(uso) {
  const flat = uso.flat().filter(n => n > 0).sort((a, b) => a - b);
  const soglia = (q) => flat.length ? flat[Math.min(flat.length - 1, Math.floor(q * flat.length))] : 0;
  const liv = (n) => n <= 0 ? 0 : n <= soglia(.2) ? 1 : n <= soglia(.45) ? 2 : n <= soglia(.7) ? 3 : n <= soglia(.9) ? 4 : 5;
  const s = svgEl("svg", { viewBox: "0 0 600 236", width: "100%", role: "img", "aria-label": "Quando si usa il sistema, per giorno e ora", class: "bt-grafico" });
  uso.forEach((riga, d) => {
    s.append(svgEl("text", { x: 32, y: d * 29 + 22, "text-anchor": "end", "font-size": 12, fill: PB.tenue }, GIORNI_BREVI[d]));
    riga.forEach((n, ora) => s.append(svgEl("rect", { x: 38 + ora * 23, y: d * 29 + 5, width: 21, height: 26, rx: 4, fill: PB.rampa[liv(n)] }, svgEl("title", {}, GIORNI_BREVI[d] + " " + ora + ":00 · " + n + " richieste"))));
  });
  [0, 6, 12, 18, 23].forEach(o => s.append(svgEl("text", { x: 38 + o * 23 + 10, y: 7 * 29 + 18, "text-anchor": "middle", "font-size": 12, fill: PB.tenue }, o + ":00")));
  return s;
}

const pbTessera = (titolo, valore, sotto, extra) => h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, titolo), h("div", { class: "bt-num" }, valore), h("div", { class: "bt-sotto" }, sotto), extra ? h("div", { class: "bt-sp" }, extra) : null);
const pbScheda = (titolo, corpo, azione, classe) => h("article", { class: "bt-card " + (classe || "") }, h("div", { class: "bt-testa" }, h("h2", {}, titolo), azione || null), corpo);

function apriOrganigramma() {
  const f = window.open(location.pathname + "#organigramma", "opifex-organigramma", "popup=yes,width=1360,height=880");
  if (!f) vai("organigramma");   // finestre bloccate dal browser: si apre in questa pagina
  else try { f.focus(); } catch (e) { /* ok */ }
}

function vistaOrganigrammaPagina() {
  const scena = vistaOrganigramma();
  scena.classList.add("scena-pagina", "scena-intera");
  return [window.name === "opifex-organigramma" ? null : h("div", { class: "bt-testa-pagina" }, h("h2", {}, "Organigramma"), h("button", { class: "s", onclick: () => vai("dashboard") }, "Torna alla plancia")), scena];
}

function vistaDashboard() {
  const ora = new Date().getHours(), saluto = ora < 6 ? "Buonanotte" : ora < 13 ? "Buongiorno" : ora < 19 ? "Buon pomeriggio" : "Buonasera";
  const titolo = h("h1", { class: "bt-titolo" }, saluto + (stato.nome ? " " + stato.nome.split(" ")[0] : "") + ". ");
  const sottotitolo = h("span", { class: "bt-corsivo" }, "Carico la plancia…"); titolo.append(sottotitolo);
  const kpi = h("section", { class: "bt-griglia bt-kpis" }, [1, 2, 3, 4, 5, 6].map(() => h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-sotto" }, "…"))));
  const riga1 = h("section", { class: "bt-griglia" });
  const riga2 = h("section", { class: "bt-griglia" });
  const colDec = h("div", { class: "bt-col" });
  let attesa = 0, iniziativeDaApprovare = 0;
  const boxRic = h("div", { class: "bt-lista" }), boxIni = h("div", { class: "bt-lista" }), boxPro = h("div", { class: "bt-lista" });

  const aggiornaTitolo = () => {
    const n = (stato.richieste || 0) + iniziativeDaApprovare;
    sottotitolo.textContent = n ? (n === 1 ? "Una cosa aspetta te." : n === 2 ? "Due cose aspettano te." : n + " cose aspettano te.") : "Niente aspetta te, gli agenti vanno avanti da soli.";
  };
  const caricaRichieste = async () => {
    try {
      const el = await api("GET", "/gestione/richieste?stato=aperta");
      stato.richieste = el.length; aggiornaTitolo();
      if (boxRic.contains(document.activeElement) || [...boxRic.querySelectorAll("input")].some(i => i.value.trim())) return;
      riempi(boxRic, el.length ? [el.slice(0, 3).map(r => {
        const ris = h("input", { type: "text", placeholder: "Rispondi a " + r.agente + "…", maxlength: 2000, "aria-label": "Rispondi a " + r.agente });
        const invia = async (btn) => {
          if (!ris.value.trim()) return; if (btn) btn.disabled = true; ris.disabled = true;
          try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); ris.value = ""; caricaRichieste(); }
          catch (x) { alert(x.message); ris.disabled = false; if (btn) btn.disabled = false; }
        };
        ris.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); invia(null); } });
        return h("div", { class: "bt-decisione" + (r.bloccante ? " bloccante" : "") },
          h("div", { class: "bt-riga-tag" }, h("span", { class: "bt-tag" + (r.bloccante ? " rosso" : "") }, r.bloccante ? "Bloccante" : "Domanda"), h("span", { class: "bt-sotto" }, r.agente)),
          h("p", { class: "bt-domanda" }, r.domanda),
          h("div", { class: "bt-invia" }, ris, h("button", { class: "p", onclick: (e) => invia(e.currentTarget) }, "Invia")));
      }), el.length > 3 ? h("button", { class: "s", onclick: () => vai("richieste") }, "Vedi tutte (" + el.length + ")") : null]
        : h("p", { class: "bt-sotto" }, "Nessuna domanda aperta. Gli agenti hanno tutto ciò che serve."));
    } catch (e) { boxRic.replaceChildren(avviso(e.message, "no")); }
  };
  const caricaIniziative = async () => {
    try {
      const d = await api("GET", "/gestione/iniziative");
      const aperte = d.iniziative.filter(i => i.stato === "da_approvare" || i.stato === "in_corso");
      iniziativeDaApprovare = aperte.filter(i => i.stato === "da_approvare").length; aggiornaTitolo();
      if (boxIni.contains(document.activeElement)) return;
      riempi(boxIni, aperte.slice(0, 3).map(i => {
        const decidi = async (azione, btn) => { btn.disabled = true; try { await api("POST", "/gestione/iniziative/" + i.id + "/decisione", { azione }); caricaIniziative(); } catch (x) { alert(x.message); btn.disabled = false; } };
        return h("div", { class: "bt-decisione" },
          h("div", { class: "bt-riga-tag" }, h("span", { class: "bt-tag" + (i.stato === "da_approvare" ? " rosso" : " verde") }, i.stato === "da_approvare" ? "Da approvare" : "In corso"), h("span", { class: "bt-sotto" }, (i.aperta_da || "?") + " · " + i.rami_fatti + "/" + i.rami + " task")),
          h("p", { class: "bt-domanda" }, i.titolo),
          i.stato === "da_approvare" ? h("div", { class: "bt-invia" }, h("button", { class: "p", onclick: (e) => decidi("approva", e.currentTarget) }, "Approva"), h("button", { class: "s", onclick: (e) => decidi("rifiuta", e.currentTarget) }, "Rifiuta")) : null);
      }));
    } catch (e) { boxIni.replaceChildren(avviso(e.message, "no")); }
  };
  const caricaProgetti = async () => {
    try {
      const d = await api("GET", "/gestione/progetti");
      const att = d.progetti.filter(p => !p.archiviato && !p.eliminato_il);
      riempi(boxPro, att.length ? att.slice(0, 5).map(p => h("button", { class: "bt-riga-prog", onclick: () => vai("progetti") },
        h("span", { class: "punto-col", style: "background:" + (p.colore || PB.ottone) }), h("b", {}, p.nome), h("span", { class: "bt-sotto" }, p.agenti.length + " agenti" + (p.drive_stato !== "ok" ? " · Drive: " + ({ da_sincronizzare: "da creare", errore: "errore" })[p.drive_stato] : "")))) : h("p", { class: "bt-sotto" }, "Nessun progetto."));
    } catch (e) { boxPro.replaceChildren(avviso(e.message, "no")); }
  };
  const daFare = pannelloDaFare();
  const garanzie = ((stato.opzioni && stato.opzioni.fornitori) || []).filter(f => !(f.non_conservazione_attiva && f.dpa_firmato));

  const disegnaDati = (d) => {
    const c = d.crm, k = d.consumi, so = d.social, op = c.operazioni;
    const g14 = k.giorni.slice(-14), prec7 = k.giorni.slice(-8, -1), media7 = prec7.reduce((a, x) => a + x.costo, 0) / Math.max(1, prec7.length), vc = variazione(k.mese.costo, k.mese.costo_periodo_prima);
    riempi(kpi, [
      pbTessera("Contatti CRM", nIt(c.contatti.totale), c.contatti.nuovi_7g ? "+" + nIt(c.contatti.nuovi_7g) + " in 7 giorni" : "nessun nuovo in 7 giorni"),
      pbTessera("Operazioni aperte", nIt(op.aperte), op.in_pausa ? nIt(op.in_pausa) + " in pausa" : "nessuna in pausa"),
      pbTessera("Valore in trattativa", eurInt(op.valore_aperto), "pesato " + eurInt(op.valore_pesato)),
      pbTessera("Costo di oggi", eur(k.oggi.costo), compatto(k.oggi.token) + " token · media 7 giorni " + eur(media7), sparkline(g14.map(x => x.costo), PB.terra)),
      pbTessera("Costo del mese", eur(k.mese.costo), (vc ? h("span", {}, h("b", { class: vc.su ? "bt-giu" : "bt-su" }, vc.testo), " sul mese scorso · ") : "") + compatto(k.mese.token) + " token"),
      pbTessera("Progetti vinti", eurInt(op.valore_vinto_anno), nIt(op.vinte_anno) + " da inizio anno · totale " + eurInt(op.valore_vinto_totale) + " (" + nIt(op.vinte_totali) + ")")]);

    const imbuto = pbScheda("Imbuto di vendita", [graficoImbuto(c.imbuto), h("p", { class: "bt-nota" }, c.conversione != null ? "Da contatto a cliente vinto: " + nIt(c.conversione, 1) + "% · perse negli ultimi 90 giorni: " + op.perse_90g : "Importa i contatti nel CRM per vedere l'imbuto.")],
      h("button", { class: "s", onclick: () => vai("crm") }, "Apri il CRM"), "bt-s4");
    const NOMI = { nuova: ["Nuova", PB.imbuto[0]], contattato: ["Contattato", PB.imbuto[1]], in_trattativa: ["In trattativa", PB.imbuto[3]], in_pausa: ["In pausa", "#9AA39E"] };
    const tab = h("table", { class: "bt-tab" }, h("thead", {}, h("tr", {}, h("th", {}, "Fase"), h("th", {}, "Operazioni"), h("th", {}, "Valore"))),
      h("tbody", {}, op.per_fase.map(f => h("tr", {}, h("td", {}, h("i", { class: "bt-chip", style: "background:" + NOMI[f.stato][1] }), NOMI[f.stato][0]), h("td", {}, nIt(f.n)), h("td", {}, eurInt(f.valore))))));
    const mov = c.da_muovere.length ? [h("div", { class: "bt-cap", style: "margin-top:18px" }, "Da muovere questa settimana"), c.da_muovere.map(m => h("div", { class: "bt-riga-mov" }, h("span", {}, m.titolo),
      h("span", { class: "bt-tag" + (m.giorni > 0 ? " rosso" : "") }, m.giorni > 0 ? "scaduta da " + m.giorni + (m.giorni === 1 ? " giorno" : " giorni") : m.giorni === 0 ? "scade oggi" : "scade tra " + (-m.giorni) + " giorni")))] : null;
    const operazioni = pbScheda("Operazioni commerciali aperte", [tab, mov], h("button", { class: "s", onclick: () => vai("crm") }, "Apri"), "bt-s4");

    const giorni = k.giorni.map(x => x.giorno);
    const consumi = pbScheda("Token e costi, ultimi 30 giorni", h("div", { class: "bt-due" }, h("div", {}, h("div", { class: "bt-cap" }, "Token al giorno"), graficoArea(k.giorni.map(x => x.token), giorni, PB.verde, compatto, "Token al giorno negli ultimi 30 giorni")),
      h("div", {}, h("div", { class: "bt-cap" }, "Costo al giorno, euro (oggi in evidenza)"), graficoBarre(k.giorni.map(x => x.costo * ((stato.opzioni && stato.opzioni.cambio_eur) || 0.92)), giorni, PB.terra, (v) => "€ " + nIt(v, v < 10 ? 2 : 0), "Costo al giorno negli ultimi 30 giorni"))),
      h("button", { class: "s", onclick: () => vai("impostazioni", "misure") }, "Dove vanno"), "bt-s4");
    riempi(riga1, [imbuto, operazioni, consumi]);

    const mx = Math.max(0.0001, ...k.per_agente.map(a => a.costo));
    const barre = k.per_agente.length ? k.per_agente.map(a => h("div", { class: "bt-barra", title: a.nome + ": " + eur(a.costo) }, h("span", { class: "bt-bl" }, a.nome), h("span", { class: "bt-bt" }, h("i", { style: "width:" + Math.max(2, 100 * a.costo / mx) + "%" })), h("span", { class: "bt-bv" }, eur(a.costo)))) : h("p", { class: "bt-sotto" }, "Nessun consumo nel mese.");
    const COL = { Sonnet: PB.verde, Opus: PB.blu, Haiku: PB.ottone, Altri: PB.terra };
    const fam = {}; k.modelli.forEach(m => { const n = COL[m.nome] ? m.nome : "Altri"; fam[n] = (fam[n] || 0) + m.token; });
    const totM = Object.values(fam).reduce((a, b) => a + b, 0) || 1;
    const voci = Object.entries(fam).map(([n, t]) => [n, Math.round(100 * t / totM)]);
    const modelli = voci.length ? [h("div", { class: "bt-cap", style: "margin-top:22px" }, "Modelli usati nel mese"), h("div", { class: "bt-seg", role: "img", "aria-label": "Quota di token per modello" }, voci.map(([n, p]) => h("i", { style: "flex:" + p + ";background:" + COL[n], title: n + " " + p + "%" }))),
      h("div", {}, voci.map(([n, p]) => h("span", { class: "bt-leg" }, h("b", { style: "background:" + COL[n] }), n + " " + p + "%")))] : null;
    const uso = pbScheda("Quando si usa il sistema", [mappaUso(k.uso), h("div", { class: "bt-leg2" }, h("span", {}, "meno"), PB.rampa.map(c2 => h("i", { style: "background:" + c2 })), h("span", {}, "più")), h("p", { class: "bt-nota" }, "Richieste agli agenti per ora, ultime 4 settimane.")], null, "bt-s4");
    const costi = pbScheda("Costo per agente, mese", [barre, modelli], null, "bt-s4");

    const sc = so.totali, vs = variazione(sc.creati, sc.creati_prima);
    const social = h("article", { class: "bt-card" }, h("div", { class: "bt-testa" }, h("div", { class: "bt-cap" }, "Social · mese su mese"), h("button", { class: "s", onclick: () => vai("social") }, "Apri")),
      h("div", { class: "bt-trio" }, h("div", {}, h("div", { class: "bt-num piccolo" }, nIt(sc.creati)), h("div", { class: "bt-sotto" }, "post preparati")), h("div", {}, h("div", { class: "bt-num piccolo" }, nIt(sc.inviati)), h("div", { class: "bt-sotto" }, "inviati")),
        h("div", {}, h("div", { class: "bt-num piccolo" }, so.da_approvare), h("div", { class: "bt-sotto" }, "da approvare"))),
      h("p", { class: "bt-nota" }, vs ? "Rispetto allo stesso periodo del mese scorso: " + vs.testo + " post." : "Il mese scorso non c'erano post per il confronto."));
    const casati = bannerCasati(); casati.className = "bt-card bt-casati";
    const dec = h("article", { class: "bt-card bt-decidere" }, h("div", { class: "bt-testa" }, h("h2", {}, "Da decidere")), boxRic, boxIni);
    const prog = h("article", { class: "bt-card" }, h("div", { class: "bt-testa" }, h("div", { class: "bt-cap" }, "Progetti in corso"), h("button", { class: "s", onclick: () => vai("progetti") }, "Apri")), boxPro);
    const fare = daFare.el; fare.className = "bt-card bt-fare";
    riempi(colDec, [dec, fare, casati, social, prog]);
    riempi(riga2, [uso, costi, colDec]);
  };

  const carica = async () => {
    try { disegnaDati(await api("GET", "/gestione/plancia")); }
    catch (e) { riempi(riga1, avviso(e.message, "no")); }
  };
  carica(); caricaRichieste(); caricaIniziative(); caricaProgetti();
  stato.timer2 = setInterval(() => { attesa++; caricaRichieste(); caricaIniziative(); if (attesa % 4 === 0) { caricaProgetti(); daFare.ricarica(); } if (attesa % 20 === 0) carica(); }, 3000);

  return h("div", { class: "bt-plancia" },
    h("div", { class: "bt-intesta" }, h("div", {}, h("div", { class: "bt-cap" }, new Date().toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" })), titolo),
      h("div", { class: "bt-azioni" }, h("button", { class: "s", onclick: apriOrganigramma }, "Organigramma 3D ↗"), bottoneAllinea(), h("button", { class: "s", onclick: () => vai("task") }, "Task"), h("button", { class: "p", onclick: () => vai("riunioni") }, "Avvia una riunione"))),
    kpi, riga1, riga2,
    garanzie.length ? h("p", { class: "bt-nota" }, "Dati interni e riservati bloccati verso: " + garanzie.map(f => f.nome).join(", ") + ". ", h("a", { href: "#", onclick: (e) => { e.preventDefault(); vai("impostazioni", "sicurezza"); } }, "Dichiara le garanzie")) : null);
}
