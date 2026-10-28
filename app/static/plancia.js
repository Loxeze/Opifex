"use strict";
// Plancia: pannelli di vetro mobili. Si trascinano dall'intestazione (o con le frecce), si agganciano ai bordi e agli altri pannelli (passo di 12 px),
// si ridimensionano dall'angolo, si comprimono e si ancorano. Disposizioni predefinite e disposizione personale salvate sul server, per utente.

const PL_TESTA = 52, PL_GRIGLIA = 12, PL_SOGLIA = 14, PL_LARGHEZZA_BASE = 1440, PL_STRETTO = 820;
const PL_META = {
  aurora: "Aurora", decisioni: "Decisioni in attesa", costi: "Costi", task: "Task e scadenze", squadra: "Squadra e Ginnasio", briefing: "Briefing",
};
const PL_ORDINE = ["aurora", "decisioni", "costi", "task", "squadra", "briefing"];
// [x, y, larghezza, altezza, aperto, ancorato] su una larghezza di 1440 px: si adatta alla larghezza reale
const PL_PRESET = {
  operativo: { aurora: [0, 0, 380, 300, 1, 0], decisioni: [0, 312, 380, 348, 1, 0], costi: [392, 0, 600, 264, 1, 0], task: [392, 276, 600, 300, 1, 0], squadra: [1004, 0, 364, 324, 1, 0], briefing: [1004, 336, 364, 324, 1, 0] },
  focus: { aurora: [0, 0, 520, 580, 1, 1], decisioni: [532, 0, 440, 580, 1, 0], costi: [984, 0, 384, 252, 1, 0], task: [984, 264, 384, 300, 0, 0], squadra: [984, 328, 384, 324, 0, 0], briefing: [984, 392, 384, 324, 0, 0] },
  panorama: { aurora: [0, 0, 220, 300, 0, 0], decisioni: [232, 0, 220, 348, 0, 0], costi: [464, 0, 220, 264, 0, 0], task: [696, 0, 220, 300, 0, 0], squadra: [928, 0, 220, 324, 0, 0], briefing: [1160, 0, 220, 324, 0, 0] },
};
const PL_ETICHETTE = { operativo: "Operativa", focus: "Concentrata", panorama: "Panorama", personale: "Personale" };
const PL_PERIODI = { "7": "7 giorni", "14": "14 giorni", "30": "30 giorni" };
const plIcona = (m) => { const t = document.createElement("template"); t.innerHTML = m.trim(); return t.content.firstElementChild; };
const plMenoMovimento = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const plUsd = (v) => "$ " + Number(v || 0).toFixed(2).replace(".", ",");
const plLerp = (a, b, t) => Array.isArray(a) ? a.map((x, i) => x + (b[i] - x) * t) : a + (b - a) * t;

function vistaPlancia() {
  const scena = h("div", { class: "pl-scena" });
  const barra = h("div", { class: "pl-barra pill", role: "toolbar", "aria-label": "Strumenti della Plancia" });
  const contenitore = h("div", { class: "plancia" }, barra, scena);
  const S = { layout: {}, disposizione: "operativo", personale: null, periodo: "7", z: 10, ghost: null, mov: null, dati: {}, costi: { tot: 0, serie: new Array(11).fill(0), pct: null }, rimandate: new Set(), aurora: { id: null, testo: "", attesa: false }, el: {}, salva: null };
  let raf = null;

  // ---------- disposizione ----------
  const larghezza = () => Math.max(320, scena.clientWidth || contenitore.clientWidth || 1000);
  const impilata = () => larghezza() < PL_STRETTO;
  const eh = (p) => p.aperto ? p.h : PL_TESTA;
  const snap12 = (v) => Math.round(v / PL_GRIGLIA) * PL_GRIGLIA;
  function daPreset(nome) {
    const W = larghezza(), k = W / PL_LARGHEZZA_BASE, out = {};
    PL_ORDINE.forEach((id, i) => {
      const a = PL_PRESET[nome][id], w = Math.min(W, Math.max(nome === "panorama" ? 180 : 240, snap12(a[2] * k)));
      out[id] = { id, x: Math.max(0, Math.min(W - w, snap12(a[0] * k))), y: a[1], w, h: a[3], aperto: !!a[4], ancorato: !!a[5], z: 10 + i };
    });
    return out;
  }
  function daSalvato(l) {
    const base = daPreset("operativo"), W = larghezza();
    PL_ORDINE.forEach((id, i) => {
      const a = l && l[id]; if (!Array.isArray(a) || a.length !== 6) return;
      const w = Math.max(200, Math.min(W, a[2]));
      base[id] = { id, x: Math.max(0, Math.min(W - w, a[0])), y: Math.max(0, a[1]), w, h: Math.max(100, a[3]), aperto: !!a[4], ancorato: !!a[5], z: 10 + i };
    });
    return base;
  }
  const comePreset = (id) => { const p = S.layout[id]; return [Math.round(p.x), Math.round(p.y), Math.round(p.w), Math.round(p.h), p.aperto ? 1 : 0, p.ancorato ? 1 : 0]; };
  const comeSalvato = () => Object.fromEntries(PL_ORDINE.map((id) => [id, comePreset(id)]));

  function posiziona(id) {
    const p = S.layout[id], el = S.el[id]; if (!p || !el) return;
    el.root.style.left = p.x + "px"; el.root.style.top = p.y + "px"; el.root.style.width = p.w + "px"; el.root.style.height = eh(p) + "px"; el.root.style.zIndex = p.z;
    el.root.classList.toggle("ancorato", p.ancorato && S.mov !== id); el.root.classList.toggle("sollevato", S.mov === id);
    el.corpo.hidden = !p.aperto; el.maniglia.hidden = !p.aperto || p.ancorato;
    el.pin.setAttribute("aria-pressed", p.ancorato ? "true" : "false"); { const t = p.ancorato ? "Disancora il pannello" : "Ancora il pannello"; el.pin.title = t; el.pin.setAttribute("aria-label", t); }
    el.pin.firstElementChild.setAttribute("fill", p.ancorato ? "#ffc46b" : "none"); el.pin.firstElementChild.setAttribute("stroke", p.ancorato ? "#ffc46b" : "#f2f5fb");
    el.chev.setAttribute("aria-expanded", p.aperto ? "true" : "false"); { const t = p.aperto ? "Comprimi il pannello" : "Espandi il pannello"; el.chev.title = t; el.chev.setAttribute("aria-label", t); }
    el.chev.firstElementChild.style.transform = "rotate(" + (p.aperto ? 0 : -90) + "deg)";
    el.root.style.cursor = "";
    el.testa.style.cursor = p.ancorato ? "default" : (S.mov === id ? "grabbing" : "grab");
  }
  function tuttiPosiziona() {
    contenitore.classList.toggle("impilata", impilata());
    PL_ORDINE.forEach(posiziona);
    if (impilata()) { scena.style.height = ""; return; }
    scena.style.height = Math.max(520, ...PL_ORDINE.map((id) => S.layout[id].y + eh(S.layout[id]))) + 28 + "px";
  }
  const davanti = (id) => { S.layout[id].z = ++S.z; posiziona(id); };

  // ---------- aggancio ----------
  function agganciato(id, x, y, w, h_) {
    const W = larghezza(), altri = PL_ORDINE.filter((q) => q !== id).map((q) => ({ x: S.layout[q].x, y: S.layout[q].y, w: S.layout[q].w, h: eh(S.layout[q]) }));
    const sx = [0, W - w], sy = [0, 1e5];
    altri.forEach((o) => { sx.push(o.x, o.x + o.w - w, o.x + o.w + PL_GRIGLIA, o.x - w - PL_GRIGLIA); sy.push(o.y, o.y + o.h - h_, o.y + o.h + PL_GRIGLIA, o.y - h_ - PL_GRIGLIA); });
    const scegli = (v, c) => { let best = null, bd = PL_SOGLIA + 1; c.forEach((k) => { const d = Math.abs(k - v); if (d < bd) { bd = d; best = k; } }); return best === null ? snap12(v) : best; };
    return { x: Math.max(0, Math.min(W - w, scegli(x, sx))), y: Math.max(0, scegli(y, sy.filter((v) => v < 1e5))) };
  }
  function mostraGhost(g) {
    if (!g) { if (S.ghost) { S.ghost.remove(); S.ghost = null; } return; }
    if (!S.ghost) { S.ghost = h("div", { class: "pl-ghost", "aria-hidden": "true" }); scena.append(S.ghost); }
    Object.assign(S.ghost.style, { left: g.x + "px", top: g.y + "px", width: g.w + "px", height: g.h + "px" });
  }
  function salvaLayout() {
    S.disposizione = "personale"; S.personale = comeSalvato(); disegnaBarra();
    clearTimeout(S.salva);
    S.salva = setTimeout(async () => {
      try { await api("PUT", "/account/preferenze/plancia_layout", { valore: S.personale }); await api("PUT", "/account/preferenze/plancia_disposizione", { valore: "personale" }); } catch (e) { /* resta valido finche' la pagina e' aperta */ }
    }, 600);
  }

  // ---------- trascinamento e ridimensionamento ----------
  function iniziaTrascinamento(id, e) {
    if (impilata() || (e.target.closest && e.target.closest("button"))) return;
    if (e.button !== undefined && e.button !== 0) return;
    const p = S.layout[id]; davanti(id);
    if (p.ancorato) return;
    const sx = e.clientX, sy = e.clientY, ox = p.x, oy = p.y, W = larghezza(); let cur = { x: ox, y: oy }, mosso = false;
    S.mov = id; posiziona(id);
    const muovi = (ev) => {
      mosso = true;
      cur = { x: Math.max(0, Math.min(W - p.w, ox + ev.clientX - sx)), y: Math.max(0, oy + ev.clientY - sy) };
      p.x = cur.x; p.y = cur.y; const g = agganciato(id, cur.x, cur.y, p.w, eh(p));
      mostraGhost({ x: g.x, y: g.y, w: p.w, h: eh(p) }); posiziona(id);
    };
    const fine = () => {
      window.removeEventListener("pointermove", muovi); window.removeEventListener("pointerup", fine); window.removeEventListener("pointercancel", fine);
      const g = agganciato(id, cur.x, cur.y, p.w, eh(p)); p.x = g.x; p.y = g.y; S.mov = null; mostraGhost(null); tuttiPosiziona(); if (mosso) salvaLayout();
    };
    window.addEventListener("pointermove", muovi); window.addEventListener("pointerup", fine); window.addEventListener("pointercancel", fine);
  }
  function iniziaRidimensione(id, e) {
    e.stopPropagation(); e.preventDefault();
    const p = S.layout[id], sx = e.clientX, sy = e.clientY, ow = p.w, oh = p.h, W = larghezza(); davanti(id); S.mov = id;
    const calcola = (ev) => ({ w: Math.max(240, Math.min(W - p.x, ow + ev.clientX - sx)), h: Math.max(150, oh + ev.clientY - sy) });
    const muovi = (ev) => { const c = calcola(ev); p.w = c.w; p.h = c.h; mostraGhost({ x: p.x, y: p.y, w: snap12(c.w), h: snap12(c.h) }); posiziona(id); };
    const fine = (ev) => {
      window.removeEventListener("pointermove", muovi); window.removeEventListener("pointerup", fine); window.removeEventListener("pointercancel", fine);
      const c = calcola(ev); p.w = snap12(c.w); p.h = snap12(c.h); S.mov = null; mostraGhost(null); tuttiPosiziona(); salvaLayout();
    };
    window.addEventListener("pointermove", muovi); window.addEventListener("pointerup", fine); window.addEventListener("pointercancel", fine);
  }
  function tastiera(id, e) {   // frecce: sposta di 12 px; con Maiusc ridimensiona
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!d || impilata() || e.target !== e.currentTarget) return;
    const p = S.layout[id]; if (p.ancorato) return; e.preventDefault(); const W = larghezza();
    if (e.shiftKey) { p.w = Math.max(240, Math.min(W - p.x, p.w + d[0] * PL_GRIGLIA)); p.h = Math.max(150, p.h + d[1] * PL_GRIGLIA); }
    else { const g = agganciato(id, p.x + d[0] * PL_GRIGLIA, p.y + d[1] * PL_GRIGLIA, p.w, eh(p)); p.x = g.x; p.y = g.y; }
    tuttiPosiziona(); salvaLayout();
  }

  // ---------- costruzione dei pannelli ----------
  function costruisciPannello(id) {
    const titolo = h("span", { class: "pl-titolo" }, PL_META[id]), badge = h("span", { class: "pl-badge" });
    const pin = h("button", { type: "button", class: "pl-ib pl-ancora", onclick: () => { const p = S.layout[id]; p.ancorato = !p.ancorato; if (p.ancorato) { const g = agganciato(id, p.x, p.y, p.w, eh(p)); p.x = g.x; p.y = g.y; } tuttiPosiziona(); salvaLayout(); } },
      plIcona('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f2f5fb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/><path d="M12 14v7"/></svg>'));
    const chev = h("button", { type: "button", class: "pl-ib", onclick: () => { const p = S.layout[id]; p.aperto = !p.aperto; tuttiPosiziona(); salvaLayout(); } },
      plIcona('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f2f5fb" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="transition:transform .25s"><path d="M6 9l6 6 6-6"/></svg>'));
    const testa = h("header", { class: "pl-testa", tabindex: "0", "aria-label": PL_META[id] + ": trascina, oppure usa le frecce per spostare e Maiusc più frecce per ridimensionare" },
      plIcona('<svg width="12" height="16" viewBox="0 0 12 16" aria-hidden="true" fill="rgba(255,255,255,.6)"><circle cx="3" cy="3" r="1.4"/><circle cx="9" cy="3" r="1.4"/><circle cx="3" cy="8" r="1.4"/><circle cx="9" cy="8" r="1.4"/><circle cx="3" cy="13" r="1.4"/><circle cx="9" cy="13" r="1.4"/></svg>'), titolo, badge, pin, chev);
    testa.addEventListener("pointerdown", (e) => iniziaTrascinamento(id, e));
    testa.addEventListener("keydown", (e) => tastiera(id, e));
    const corpo = h("div", { class: "pl-corpo" });
    const maniglia = h("div", { class: "pl-maniglia", "aria-hidden": "true" }, plIcona('<svg width="26" height="26" viewBox="0 0 26 26" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="1.5" stroke-linecap="round"><path d="M21 11L11 21M21 17l-4 4"/></svg>'));
    maniglia.addEventListener("pointerdown", (e) => iniziaRidimensione(id, e));
    const root = h("section", { class: "pl-pannello", "aria-label": PL_META[id] }, testa, corpo, maniglia);
    S.el[id] = { root, testa, titolo, badge, corpo, pin, chev, maniglia };
    scena.append(root);
  }

  // ---------- contenuti ----------
  const vuoto = (t) => h("p", { class: "pl-tenue" }, t);
  const apri = (testo, vista) => h("button", { type: "button", class: "pl-btn sec", onclick: () => vai(vista) }, testo);
  function conGuardia(id, riempiFn) {   // non ridisegna mentre stai scrivendo
    const c = S.el[id].corpo;
    if (c.contains(document.activeElement) && document.activeElement.tagName === "INPUT" && document.activeElement.value) return;
    if ([...c.querySelectorAll("input")].some((i) => i.value.trim())) return;
    riempiFn(c);
  }

  function pannelloAurora() {
    const c = S.el.aurora.corpo, a = S.aurora;
    const risposta = h("div", { class: "pl-risposta", "aria-live": "polite" }, a.testo || "Scrivimi qui o usa il microfono: ti rispondo con quello che sta succedendo.");
    const campo = h("input", { type: "text", maxlength: 4000, placeholder: "Scrivi ad Aurora", "aria-label": "Scrivi ad Aurora" });
    const msg = h("div");
    const manda = async () => {
      const t = campo.value.trim(); if (!t || a.attesa || !a.id) return;
      a.attesa = true; campo.value = ""; risposta.textContent = "Aurora sta pensando…";
      try {
        const r = await api("POST", "/agenti/" + a.id + "/chat", { messaggio: t, fascia_dati: "interno", asincrono: true });
        for (let i = 0; i < 120; i++) {
          await new Promise((ok) => setTimeout(ok, 1500));
          if (!document.body.contains(contenitore)) return;
          const q = await api("GET", "/chat-coda/" + r.coda_id);
          if (q.stato === "finito") { a.testo = (q.risultato && q.risultato.risposta) || "(nessuna risposta)"; break; }
          if (q.stato === "errore") { a.testo = "Non sono riuscita a rispondere: " + (q.errore || "errore"); break; }
        }
      } catch (e) { a.testo = e.message; }
      a.attesa = false; risposta.textContent = a.testo || "Nessuna risposta arrivata: riprova tra poco.";
    };
    campo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); manda(); } });
    const mic = (typeof bottoneMic === "function") ? bottoneMic(campo, msg) : null;
    if (mic) mic.classList.add("pl-ib");
    riempi(c, [h("div", { style: "display:flex;align-items:center;gap:12px" },
      h("span", { style: "width:34px;height:34px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#ffe2a8,#ffb06b 55%,#c9694a);box-shadow:0 0 22px rgba(255,176,107,.6);flex:0 0 34px" }),
      h("div", {}, h("div", { style: "font-weight:700;font-size:15px" }, "Aurora"), h("div", { class: "pl-tenue" }, a.id ? "referente · in linea" : "non trovata"))),
      risposta, h("div", { style: "margin-top:auto" }, msg, h("div", { class: "pl-campo" }, campo, mic, h("button", { type: "button", class: "pl-btn", onclick: manda }, "Invia")))]);
  }

  function pannelloDecisioni() {
    const el = (S.dati.richieste || []).filter((r) => !S.rimandate.has(r.id));
    S.el.decisioni.badge.textContent = String((S.dati.richieste || []).length || "");
    conGuardia("decisioni", (c) => riempi(c, [
      el.length ? el.slice(0, 4).map((r) => {
        const ris = h("input", { type: "text", maxlength: 2000, placeholder: "Rispondi…", "aria-label": "Risposta a " + r.agente });
        const invia = async (b) => { if (!ris.value.trim()) return; ris.disabled = true; if (b) b.disabled = true;
          try { await api("POST", "/gestione/richieste/" + r.id + "/risposta", { risposta: ris.value }); ris.value = ""; await caricaRichieste(); } catch (x) { ris.disabled = false; if (b) b.disabled = false; ris.placeholder = x.message; } };
        ris.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); invia(null); } });
        let btn; btn = h("button", { type: "button", class: "pl-btn", onclick: () => invia(btn) }, "Rispondi");
        return h("div", { class: "pl-voce" + (r.bloccante ? " urgente" : "") }, h("div", { style: "font-size:14px;font-weight:600;line-height:1.35" }, r.domanda),
          h("div", { class: "pl-tenue" }, (r.bloccante ? "Blocca il lavoro · " : "") + r.agente), ris,
          h("div", { style: "display:flex;gap:8px" }, btn, h("button", { type: "button", class: "pl-btn sec", onclick: () => { S.rimandate.add(r.id); pannelloDecisioni(); } }, "Rimanda")));
      }) : vuoto("Nessuna decisione in attesa."),
      (S.dati.richieste || []).length > 4 ? vuoto("e altre " + ((S.dati.richieste || []).length - 4) + "…") : null, apri("Apri tutte le richieste", "richieste")]));
  }

  function pannelloCosti() {
    const c = S.el.costi.corpo, R = {};
    R.tot = h("span", { class: "pl-num", style: "font-size:32px;letter-spacing:-.02em;min-width:150px" });
    R.sub = h("span", { class: "pl-tenue" });
    const ns = "http://www.w3.org/2000/svg", s = (t, at) => { const e = document.createElementNS(ns, t); for (const k in at) e.setAttribute(k, at[k]); return e; };
    const svg = s("svg", { viewBox: "0 0 500 130", preserveAspectRatio: "none", role: "img", "aria-label": "Andamento della spesa cumulata nel periodo scelto" });
    const defs = s("defs", {}); const gr = s("linearGradient", { id: "pl-area", x1: "0", y1: "0", x2: "0", y2: "1" });
    gr.append(s("stop", { offset: "0", "stop-color": "#ffc46b", "stop-opacity": ".45" }), s("stop", { offset: "1", "stop-color": "#ffc46b", "stop-opacity": "0" })); defs.append(gr);
    R.area = s("path", { fill: "url(#pl-area)" }); R.line = s("path", { fill: "none", stroke: "#ffc46b", "stroke-width": "2.4", "stroke-linejoin": "round", "stroke-linecap": "round", "vector-effect": "non-scaling-stroke", pathLength: "1", class: "pl-linea" });
    svg.append(defs, R.area, R.line);
    R.punto = h("span", { "aria-hidden": "true", style: "position:absolute;right:-5px;width:10px;height:10px;margin-top:-5px;border-radius:50%;background:#ffe2a8;box-shadow:0 0 14px #ffc46b" });
    R.legenda = h("div", { class: "pl-tenue", style: "display:flex;gap:14px;flex-wrap:wrap" });
    const griglia = [25, 50, 75].map((t) => h("div", { "aria-hidden": "true", style: "position:absolute;left:0;right:0;top:" + t + "%;border-top:1px solid rgba(255,255,255,.1)" }));
    riempi(c, [h("div", { style: "display:flex;align-items:baseline;gap:10px;flex-wrap:wrap" }, R.tot, R.sub), h("div", { class: "pl-grafico" }, griglia, svg, R.punto), R.legenda,
      h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, h("button", { type: "button", class: "pl-btn sec", onclick: () => vai("impostazioni", "sistema") }, "Dettaglio costi"))]);
    S.refCosti = R; disegnaCosti(S.costi); legendaCosti();
  }
  function disegnaCosti(v) {
    const R = S.refCosti; if (!R) return;
    R.tot.textContent = plUsd(v.tot);
    let d = ""; v.serie.forEach((a, i) => { d += (i ? " L" : "M") + i * 50 + " " + Math.max(8, 124 - a * 110).toFixed(1); });
    R.line.setAttribute("d", d); R.area.setAttribute("d", d + " L500 130 L0 130 Z");
    R.punto.style.top = (Math.max(8, 124 - v.serie[10] * 110) / 130 * 100).toFixed(1) + "%";
    const cap = S.costi.cap;
    R.sub.textContent = cap ? "su " + plUsd(cap) + " di tetto · " + Math.round(cap > 0 ? v.tot / cap * 100 : 0) + "%" : "nessun tetto impostato";
    S.el.costi.badge.textContent = cap ? Math.round(v.tot / cap * 100) + "%" : "";
  }
  function legendaCosti() {
    const R = S.refCosti; if (!R) return; const q = S.dati.costi; if (!q) return;
    const gruppi = { Claude: 0, GPT: 0, Grok: 0, Altro: 0 };
    (q.stima.per_modello || []).forEach((m) => { const n = (m.modello || "").toLowerCase(); gruppi[n.includes("claude") ? "Claude" : n.includes("gpt") || n.includes("openai") ? "GPT" : n.includes("grok") ? "Grok" : "Altro"] += m.costo; });
    const tot = Object.values(gruppi).reduce((a, b) => a + b, 0), col = { Claude: "#ffc46b", GPT: "#bfe3ff", Grok: "#d9b6ff", Altro: "#c9d1e2" };
    riempi(R.legenda, tot > 0 ? Object.entries(gruppi).filter(([, v]) => v > 0).map(([k, v]) => h("span", {}, h("i", { style: "display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:" + col[k] }), k + " " + Math.round(v / tot * 100) + "%")) : h("span", {}, "Nessuna spesa nel periodo."));
  }
  function animaCosti(da, a) {
    if (raf) cancelAnimationFrame(raf);
    if (plMenoMovimento()) { S.costi.mostrato = a; disegnaCosti(a); return; }
    const t0 = performance.now();
    const passo = (ora) => {
      const t = Math.min(1, (ora - t0) / 1100), e = 1 - Math.pow(1 - t, 3);
      const v = { tot: plLerp(da.tot, a.tot, e), serie: plLerp(da.serie, a.serie, e) }; S.costi.mostrato = v; disegnaCosti(v);
      if (t < 1) raf = requestAnimationFrame(passo);
    };
    raf = requestAnimationFrame(passo);
  }

  function pannelloTask() {
    const t = (S.dati.task && S.dati.task.task) || [];
    S.el.task.badge.textContent = String(t.length || "");
    riempi(S.el.task.corpo, [t.length ? t.slice(0, 7).map((x) => h("div", { class: "pl-voce" + (x.scaduta ? " urgente" : "") }, h("div", { style: "font-size:14px;font-weight:600;line-height:1.35" }, x.titolo),
      h("div", { class: "pl-tenue" }, (x.scaduta ? "Scaduta · " : "") + (x.scadenza ? "scadenza " + new Date(x.scadenza).toLocaleDateString("it-IT") : "senza scadenza") + (x.progetto ? " · " + x.progetto : "")))) : vuoto("Non hai task aperte."),
      t.length > 7 ? vuoto("e altre " + (t.length - 7) + "…") : null, apri("Apri le task", "task")]);
  }

  function pannelloSquadra() {
    const ag = stato.agenti || [], lavoro = S.dati.lavoro || [], g = S.dati.ginnasio;
    S.el.squadra.badge.textContent = String(ag.filter((a) => a.attivo).length || "");
    riempi(S.el.squadra.corpo, [h("div", { class: "pl-contatori" },
      h("div", {}, h("span", { class: "pl-tenue" }, "Attivi"), h("b", {}, String(ag.filter((a) => a.attivo).length))),
      h("div", {}, h("span", { class: "pl-tenue" }, "Spenti"), h("b", {}, String(ag.filter((a) => !a.attivo).length))),
      h("div", { style: lavoro.length ? "border-color:rgba(255,196,107,.5)" : "" }, h("span", { class: "pl-tenue" }, "Al lavoro"), h("b", { style: lavoro.length ? "color:#ffc46b" : "" }, String(lavoro.length)))),
      lavoro.length ? lavoro.slice(0, 5).map((l) => h("div", { class: "pl-barra-riga" }, h("span", { class: "pl-punto", style: "background:#ffc46b;box-shadow:0 0 10px #ffc46b" }), h("span", { style: "flex:1;font-size:13.5px;font-weight:600" }, l.agente), h("span", { class: "pl-tenue" }, Math.max(1, Math.round(l.da_secondi / 60)) + " min"))) : vuoto("Nessun agente sta riprendendo un lavoro in questo momento."),
      g ? h("div", { class: "pl-voce" }, h("div", { style: "font-weight:700;font-size:14px" }, "Ginnasio"), h("div", { class: "pl-tenue" }, g.sintesi)) : null, apri("Apri il Ginnasio", "ginnasio")]);
  }

  function pannelloBriefing() {
    const b = S.dati.briefing;
    S.el.briefing.badge.textContent = b && b.briefing ? (b.briefing.tipo === "sera" ? "sera" : "mattina") : "";
    riempi(S.el.briefing.corpo, [b && b.briefing ? [h("div", { class: "pl-risposta" }, b.sintesi),
      (b.briefing.manager || []).slice(0, 4).map((m) => h("div", { class: "pl-voce" }, h("div", { style: "font-weight:700;font-size:13.5px" }, m.nome + (m.divisione ? " · " + m.divisione : "")), h("div", { class: "pl-tenue" }, m.sintesi)))] : vuoto("Non c'è ancora nessun briefing."),
      apri("Apri i briefing", "briefing")]);
  }
  const DISEGNA = { aurora: pannelloAurora, decisioni: pannelloDecisioni, costi: pannelloCosti, task: pannelloTask, squadra: pannelloSquadra, briefing: pannelloBriefing };

  // ---------- dati ----------
  async function caricaRichieste() { try { S.dati.richieste = await api("GET", "/gestione/richieste?stato=aperta"); stato.richieste = S.dati.richieste.length; } catch (e) { S.dati.richieste = []; } pannelloDecisioni(); }
  async function caricaCosti(anima) {
    try {
      const n = parseInt(S.periodo, 10), q = await api("GET", "/gestione/costi?giorni=" + n + "&fornitori=false"); S.dati.costi = q;
      const giorni = []; for (let i = n - 1; i >= 0; i--) { const d = new Date(Date.now() - i * 86400000); giorni.push(d.toLocaleDateString("sv-SE")); }
      let somma = 0; const cum = giorni.map((g) => (somma += (q.stima.per_giorno[g] || {}).costo || 0));
      const serie = Array.from({ length: 11 }, (_, k) => { const v = cum[Math.round(k * (n - 1) / 10)] || 0; return somma > 0 ? v / somma : 0; });
      const lim = q.limiti || {}; S.costi.cap = n === 30 ? (lim.tetto_mese || null) : (lim.tetto_giorno ? lim.tetto_giorno * n : null);
      const da = S.costi.mostrato || { tot: 0, serie: new Array(11).fill(0) }, a = { tot: somma, serie };
      S.costi.tot = somma; S.costi.serie = serie;
      if (S.refCosti) { legendaCosti(); anima ? animaCosti(da, a) : (S.costi.mostrato = a, disegnaCosti(a)); }
    } catch (e) { if (S.refCosti) S.refCosti.sub.textContent = "Costi non disponibili: " + e.message; }
  }
  async function caricaAltri() {
    const [t, l, g, b] = await Promise.allSettled([api("GET", "/v1/task"), api("GET", "/gestione/richieste/lavoro"), api("GET", "/v1/ginnasio"), api("GET", "/v1/briefing")]);
    S.dati.task = t.value || { task: [] }; S.dati.lavoro = l.value || []; S.dati.ginnasio = g.value || null; S.dati.briefing = b.value || null;
    pannelloTask(); pannelloSquadra(); pannelloBriefing();
  }
  async function aggiorna() { await Promise.all([caricaRichieste(), caricaCosti(false), caricaAltri()]); }

  // ---------- barra ----------
  const chip = (t, on, f, disabilitato) => h("button", { class: "pl-chip", type: "button", "aria-pressed": on ? "true" : "false", disabled: !!disabilitato, onclick: f }, t);
  function disegnaBarra() {
    riempi(barra, [
      h("div", { class: "pl-gruppo", role: "group", "aria-label": "Disposizione" }, h("span", {}, "Disposizione"),
        ["operativo", "focus", "panorama"].map((k) => chip(PL_ETICHETTE[k], S.disposizione === k, () => applicaPreset(k))),
        chip(PL_ETICHETTE.personale, S.disposizione === "personale", () => { if (S.personale) { S.layout = daSalvato(S.personale); S.disposizione = "personale"; tuttiPosiziona(); disegnaBarra(); api("PUT", "/account/preferenze/plancia_disposizione", { valore: "personale" }).catch(() => {}); } }, !S.personale)),
      h("div", { class: "pl-gruppo", role: "group", "aria-label": "Periodo dei costi" }, h("span", {}, "Periodo"),
        Object.keys(PL_PERIODI).map((k) => chip(PL_PERIODI[k], S.periodo === k, async () => { S.periodo = k; disegnaBarra(); api("PUT", "/account/preferenze/plancia_periodo", { valore: k }).catch(() => {}); await caricaCosti(true); }))),
      Vetro.controlli(),
      h("div", { class: "pl-aiuto" }, "Trascina dall'intestazione · puntina per ancorare")]);
  }
  function applicaPreset(nome) {
    S.layout = daPreset(nome); S.disposizione = nome; tuttiPosiziona(); disegnaBarra();
    api("PUT", "/account/preferenze/plancia_disposizione", { valore: nome }).catch(() => {});
  }

  // ---------- avvio ----------
  PL_ORDINE.forEach(costruisciPannello);
  S.layout = daPreset("operativo"); disegnaBarra();
  (async () => {
    let p = {}; try { p = await api("GET", "/account/preferenze"); } catch (e) { /* si parte dai valori di base */ }
    if (p.plancia_periodo && PL_PERIODI[p.plancia_periodo]) S.periodo = p.plancia_periodo;
    if (p.plancia_layout) S.personale = p.plancia_layout;
    const d = p.plancia_disposizione;
    if (d === "personale" && S.personale) { S.layout = daSalvato(S.personale); S.disposizione = "personale"; } else if (PL_PRESET[d]) { S.layout = daPreset(d); S.disposizione = d; }
    S.z = 10 + PL_ORDINE.length; tuttiPosiziona(); disegnaBarra();
    const aur = (stato.agenti || []).find((a) => a.nome === "Aurora"); S.aurora.id = aur ? aur.id : null;
    if (S.aurora.id) { try { const c = await api("GET", "/chat/conversazioni/" + S.aurora.id + "?limite=1"); const m = c.messaggi[c.messaggi.length - 1]; if (m && m.risposta) S.aurora.testo = m.risposta; } catch (e) { /* nessuna cronologia */ } }
    pannelloAurora(); pannelloCosti(); pannelloDecisioni(); pannelloTask(); pannelloSquadra(); pannelloBriefing();
    aggiorna();
    stato.timer = setInterval(aggiorna, 60000);
  })();
  const adatta = () => { if (!document.body.contains(contenitore)) { window.removeEventListener("resize", adatta); return; } const W = larghezza(); PL_ORDINE.forEach((id) => { const p = S.layout[id]; p.w = Math.min(p.w, W); p.x = Math.max(0, Math.min(W - p.w, p.x)); }); tuttiPosiziona(); };
  window.addEventListener("resize", adatta);
  return [h("h2", {}, "Plancia"), contenitore];
}
