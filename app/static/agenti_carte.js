"use strict";
// Carte degli agenti: formazione, competenze e spesa di token del mese (grafico animato). I dati arrivano da /gestione/agenti-riepilogo.
const SVG_NS = "http://www.w3.org/2000/svg";
function _svg(tag, attrs) { const e = document.createElementNS(SVG_NS, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; }
const _fmtTok = (n) => n >= 1e6 ? (n / 1e6).toFixed(1).replace(".", ",") + " M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(".", ",") + " k" : String(n);

// Andamento cumulato dei token dal 1° del mese a oggi; la linea si disegna da sinistra e l'area sfuma (niente animazione con «movimento ridotto»)
function graficoSpesa(giorni, giorniMese, budget) {
  const W = 220, H = 52, P = 3;
  const cum = []; giorni.reduce((s, v, i) => (cum[i] = s + v, s + v), 0);
  const tot = cum.length ? cum[cum.length - 1] : 0;
  const max = Math.max(budget || 0, tot, 1);
  const x = (i) => P + (giorniMese > 1 ? i / (giorniMese - 1) : 0) * (W - 2 * P);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const svg = _svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "spesa-svg", role: "img", preserveAspectRatio: "none",
    "aria-label": tot ? `Token spesi nel mese: ${_fmtTok(tot)}, andamento giorno per giorno` : "Nessun token speso nel mese" });
  svg.append(_svg("line", { x1: P, x2: W - P, y1: H - P, y2: H - P, class: "spesa-base" }));
  if (budget) svg.append(_svg("line", { x1: P, x2: W - P, y1: y(budget), y2: y(budget), class: "spesa-budget" }));
  if (cum.length && tot > 0) {
    const pts = cum.map((v, i) => [x(i), y(v)]);
    const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
    svg.append(_svg("path", { d: d + ` L${pts[pts.length - 1][0].toFixed(1)} ${H - P} L${pts[0][0].toFixed(1)} ${H - P} Z`, class: "spesa-area" }));
    const linea = _svg("path", { d, class: "spesa-linea", pathLength: "1" });
    svg.append(linea);
    const ultimo = pts[pts.length - 1];
    svg.append(_svg("circle", { cx: ultimo[0].toFixed(1), cy: ultimo[1].toFixed(1), r: 2.6, class: "spesa-punto" }));
  }
  return svg;
}

function pallini(livello) {
  const el = h("span", { class: "pallini", role: "img", "aria-label": "livello " + livello + " su 5" });
  for (let i = 1; i <= 5; i++) el.append(h("i", { class: i <= livello ? "on" : "" }));
  return el;
}

function extraAgente(r) {
  if (!r) return null;
  const f = r.formazioni || {};
  const comp = r.competenze || [];
  const mostrate = comp.slice(0, 3);
  const formaz = [f.concluse ? f.concluse + (f.concluse === 1 ? " formazione conclusa" : " formazioni concluse") : "Nessuna formazione conclusa", f.in_corso ? f.in_corso + " in corso" : null, f.in_coda ? f.in_coda + " in coda" : null,
    f.ultima ? "ultima il " + new Date(f.ultima).toLocaleDateString("it-IT", { day: "numeric", month: "short" }) : null].filter(Boolean).join(" · ");
  const perc = r.budget ? Math.round(100 * r.token_mese / r.budget) : null;
  return h("div", { class: "agente-extra" },
    h("div", { class: "extra-titolo" }, "Competenze", comp.length ? h("span", { class: "extra-dx" }, "livello medio " + String(r.livello_medio).replace(".", ",") + " · " + comp.length) : null),
    comp.length ? h("div", { class: "skills" }, mostrate.map(c => h("div", { class: "skill" }, h("span", { class: "skill-nome", title: c.nome }, c.nome), pallini(c.livello))),
      comp.length > 3 ? h("div", { class: "sotto" }, "e altre " + (comp.length - 3)) : null) : h("div", { class: "sotto" }, "Nessuna competenza assegnata."),
    h("div", { class: "sotto" }, formaz),
    h("div", { class: "extra-titolo" }, "Token nel mese", h("span", { class: "extra-dx" }, _fmtTok(r.token_mese) + (perc !== null ? " · " + perc + "% del budget" : ""))),
    r.token_mese > 0 ? graficoSpesa(r.token_giorni || [], r.__giorniMese || 30, r.budget) : h("div", { class: "sotto" }, "Nessun token speso finora."));
}

async function riempiExtraAgenti(radice) {
  try {
    const d = await api("GET", "/gestione/agenti-riepilogo");
    radice.querySelectorAll(".agente-extra-posto").forEach(el => {
      const r = d.agenti[el.dataset.id];
      if (r) { r.__giorniMese = d.giorni_mese; const x = extraAgente(r); if (x) el.replaceWith(x); } else el.remove();
    });
  } catch (e) { radice.querySelectorAll(".agente-extra-posto").forEach(el => el.remove()); }
}
