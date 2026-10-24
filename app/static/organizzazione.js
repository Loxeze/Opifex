"use strict";
// Organigramma 3D (canvas, nessuna libreria esterna) e gestione di aziende e dipartimenti.
// I dati arrivano dall'API: nessun testo viene inserito come HTML.

const COL_STATO = { sereno: "#34d399", pressione: "#fbbf24", difficolta: "#f87171" };
const TXT_STATO = { sereno: "Sereno", pressione: "Sotto pressione", difficolta: "In difficoltà" };

function apriPannello(titolo, figli) {
  const chiudi = () => sfondo.remove();
  const sfondo = h("div", { class: "pannello-sfondo", onclick: (e) => { if (e.target === sfondo) chiudi(); } },
    h("div", { class: "pannello", role: "dialog", "aria-label": titolo }, h("h2", {}, titolo), figli));
  document.body.append(sfondo);
  return chiudi;
}

// ---------- Organigramma ----------
function calcolaLayout(dati) {
  const nodi = [{ id: 0, nome: "Lorenzo", ruolo: "Titolare", centro: true, depth: 0, aziende: [], attivo: true, stato: "sereno", figli: [] }];
  const per = new Map([[0, nodi[0]]]);
  for (const a of dati.agenti) { const n = { ...a, figli: [], centro: false }; nodi.push(n); per.set(a.id, n); }
  for (const n of nodi.slice(1)) (per.get(n.superiore_id ?? 0) || nodi[0]).figli.push(n);
  const esterno = (n) => n.tipo === "sistema" && n.livello !== "referente" && n.superiore_id == null;
  const profondita = (n, d) => { n.depth = d; n.figli.forEach(f => profondita(f, d + 1)); };
  profondita(nodi[0], 0);
  const foglie = (n) => (n.peso = n.figli.length ? n.figli.reduce((s, f) => s + foglie(f), 0) : 1);
  const interni = nodi[0].figli.filter(f => !esterno(f));
  const supervisori = nodi[0].figli.filter(esterno);
  const pesoTot = interni.reduce((s, f) => s + foglie(f), 0) || 1;
  const angolo = (n, a0, a1) => {
    n.ang = (a0 + a1) / 2;
    let x = a0; const tot = n.figli.reduce((s, f) => s + f.peso, 0) || 1;
    for (const f of n.figli) { const w = (a1 - a0) * f.peso / tot; angolo(f, x, x + w); x += w; }
  };
  let x = 0;
  for (const f of interni) { const w = Math.PI * 2 * f.peso / pesoTot; angolo(f, x, x + w); x += w; }
  const maxD = Math.max(1, ...nodi.filter(n => !esterno(n) && !n.centro).map(n => n.depth));
  const raggio = (d) => d <= 0 ? 0 : 1.5 + (d - 1) * 1.1;
  supervisori.forEach((s, i) => { s.depth = maxD + 1; s.ang = Math.PI * 2 * (i + 0.5) / supervisori.length; s.esterno = true; foglie(s); });
  nodi.forEach((n, i) => {
    n.r = n.esterno ? raggio(maxD) + 1.2 : raggio(n.depth);
    if (n.esterno) n.depth = maxD + 1;
    n.sub = !n.esterno && n.depth > 0 ? n : n;
    n.x = n.r * Math.cos(n.ang || 0); n.z = n.r * Math.sin(n.ang || 0);
    n.y = n.centro ? 0 : 0.8 * Math.sin(i * 2.399 + n.depth);
  });
  // figli di un supervisore esterno: restano vicini al loro capo
  const sposta = (n) => n.figli.forEach((f, k) => { f.esterno = n.esterno; f.r = n.r + 0.9 * (k + 1) / (n.figli.length + 1) + 0.4;
    f.ang = n.ang + (k - (n.figli.length - 1) / 2) * 0.25; f.x = f.r * Math.cos(f.ang); f.z = f.r * Math.sin(f.ang); sposta(f); });
  supervisori.forEach(sposta);
  return { nodi, per, raggi: [...new Set(nodi.filter(n => !n.centro).map(n => Math.round(n.r * 100) / 100))] };
}

function vistaOrganigramma() {
  const cv = h("canvas", {});
  const scena = h("div", { class: "scena" }, cv);
  const scheda = h("div", { class: "scheda", style: "display:none" });
  const sel = h("select", {}, h("option", { value: "" }, "Tutte le aziende"));
  const bRot = h("button", { class: "s" }, "Rotazione: sì");
  const legenda = h("div", { class: "legenda" });
  let dati = null, layout = null, azienda = "", scelto = null;
  let impulsi = [], dopo = null, giro = 0;
  let rotY = 0.4, rotX = 0.35, zoom = 1, auto = true, trascina = false, ultimo = null, mossa = 0, pinch = 0;
  let W = 360, H = 640, DPR = 1;
  const cx = cv.getContext("2d");
  const stelle = Array.from({ length: 120 }, () => ({ x: (Math.random() * 2 - 1) * 9, y: (Math.random() * 2 - 1) * 9, z: (Math.random() * 2 - 1) * 9 }));

  const colore = (n) => n.centro ? "#22d3ee" : !n.attivo ? "#4b5563" : n.esterno ? "#a78bfa" : COL_STATO[n.stato] || "#34d399";
  const aziendaNome = (id) => dati.aziende.find(z => z.id === id);
  const visibile = (n) => !azienda || n.centro || !n.aziende.length || n.aziende.includes(Number(azienda));

  const proietta = (x, y, z) => {
    const cy = Math.cos(rotY), sy = Math.sin(rotY), cxr = Math.cos(rotX), sxr = Math.sin(rotX);
    const x1 = x * cy - z * sy, z1 = x * sy + z * cy;
    const y2 = y * cxr - z1 * sxr, z2 = y * sxr + z1 * cxr;
    const f = 5.5 / (5.5 + z2 + 3.2);
    const s = Math.min(W, H) * 0.145 * zoom;
    return { px: W / 2 + x1 * s * f, py: H / 2 + y2 * s * f, f, z: z2 };
  };

  const misura = () => {
    const r = scena.getBoundingClientRect();
    const w = Math.round(r.width) || 360, hh = Math.round(r.height) || 640, d = Math.min(window.devicePixelRatio || 1, 2);
    if (w !== W || hh !== H || d !== DPR || cv.width !== Math.round(w * d)) {
      W = w; H = hh; DPR = d; cv.width = Math.round(W * d); cv.height = Math.round(H * d);
      cv.style.width = W + "px"; cv.style.height = H + "px";
    }
    cx.setTransform(DPR, 0, 0, DPR, 0, 0);
  };

  const disegnaScena = () => {
    cx.fillStyle = "#05070a"; cx.fillRect(0, 0, W, H);
    cx.fillStyle = "rgba(125,138,153,0.35)";
    for (const s of stelle) { const p = proietta(s.x, s.y, s.z); cx.fillRect(p.px, p.py, 1.2, 1.2); }
    if (!layout) {
      cx.fillStyle = "#7d8a99"; cx.font = "13px monospace"; cx.textAlign = "center"; cx.fillText("Caricamento…", W / 2, H / 2); return;
    }
    cx.strokeStyle = "rgba(40,54,70,0.9)"; cx.lineWidth = 1;
    for (const r of layout.raggi) {
      cx.beginPath();
      for (let t = 0; t <= 64; t++) { const an = t / 64 * Math.PI * 2; const p = proietta(r * Math.cos(an), 0, r * Math.sin(an)); t ? cx.lineTo(p.px, p.py) : cx.moveTo(p.px, p.py); }
      cx.stroke();
    }
    for (const n of layout.nodi) n.p = proietta(n.x, n.y, n.z);
    for (const n of layout.nodi) {
      if (n.centro) continue;
      const s = layout.per.get(n.superiore_id ?? 0) || layout.nodi[0];
      cx.globalAlpha = visibile(n) ? 1 : 0.15;
      cx.strokeStyle = n.esterno && !n.superiore_id ? "rgba(167,139,250,0.35)" : n.attivo ? "rgba(34,211,238,0.35)" : "rgba(75,85,99,0.35)";
      cx.beginPath(); cx.moveTo(s.p.px, s.p.py); cx.lineTo(n.p.px, n.p.py); cx.stroke();
    }
    cx.globalAlpha = 1;
    disegnaImpulsi();
    const ord = layout.nodi.slice().sort((a, b) => b.p.z - a.p.z);
    for (const n of ord) {
      const r = Math.max((n.centro ? 13 : 5 + (n.livello === "manager" ? 2.5 : 0) + (n.carico || 0) / 100 * 4) * n.p.f * 1.5 * zoom, 3);
      const c = colore(n);
      cx.globalAlpha = visibile(n) ? 1 : 0.15;
      cx.shadowColor = c; cx.shadowBlur = n.attivo ? 14 : 0; cx.fillStyle = c;
      cx.beginPath(); cx.arc(n.p.px, n.p.py, r, 0, Math.PI * 2); cx.fill(); cx.shadowBlur = 0;
      const az = n.aziende && n.aziende.length ? aziendaNome(n.aziende[0]) : null;
      if (az) { cx.strokeStyle = az.colore; cx.lineWidth = 2; cx.beginPath(); cx.arc(n.p.px, n.p.py, r + 3, 0, Math.PI * 2); cx.stroke(); }
      if (scelto === n.id) { cx.strokeStyle = "#fff"; cx.lineWidth = 2; cx.beginPath(); cx.arc(n.p.px, n.p.py, r + 7, 0, Math.PI * 2); cx.stroke(); }
      cx.fillStyle = "rgba(230,237,243," + Math.min(1, 0.5 + n.p.f * 0.5) + ")";
      cx.font = Math.round(10 + n.p.f * 3) + "px monospace"; cx.textAlign = "center";
      cx.fillText(n.nome, n.p.px, n.p.py - r - 8);
      if (n.richieste) { cx.fillStyle = n.bloccanti ? "#f87171" : "#fbbf24"; cx.beginPath(); cx.arc(n.p.px + r, n.p.py - r, 5, 0, Math.PI * 2); cx.fill(); }
    }
    cx.globalAlpha = 1;
  };

  const ciclo = () => {
    if (!cv.isConnected) return;
    try { misura(); if (auto && !trascina) { rotY += 0.003; if (rotY > 6.2832) rotY -= 6.2832; } disegnaScena(); } catch (e) { /* un fotogramma sbagliato non ferma il resto */ }
    requestAnimationFrame(ciclo);
  };

  const mostraScheda = (n) => {
    scelto = n.id;
    if (n.centro) { scheda.style.display = "block"; riempi(scheda, [h("div", { class: "testa" }, h("div", { class: "avatar" }, "L"), h("div", {}, h("div", { class: "nome" }, "Lorenzo"), h("div", { class: "sotto" }, "Titolare — al centro di tutte le piramidi")), h("button", { class: "chiudi", onclick: chiudiScheda }, "×"))]); return; }
    const c = colore(n);
    const nomiAz = n.aziende.map(i => aziendaNome(i)?.nome).filter(Boolean);
    const sup = n.superiore_id ? layout.per.get(n.superiore_id)?.nome : "Lorenzo";
    const dip = dati.divisioni.find(d => d.id === n.divisione_id)?.nome;
    scheda.style.display = "block";
    riempi(scheda, [
      h("div", { class: "testa" },
        h("div", { class: "avatar", style: "border-color:" + c + ";color:" + c }, n.nome.charAt(0)),
        h("div", {}, h("div", { class: "nome" }, n.nome), h("div", { class: "sotto" }, n.ruolo)),
        h("button", { class: "chiudi", onclick: chiudiScheda }, "×")),
      h("div", { class: "metriche" },
        h("div", {}, h("small", {}, "Umore"), h("span", { style: "color:" + c }, n.attivo ? (n.sospeso ? "Sospeso" : TXT_STATO[n.stato]) : "Spento")),
        h("div", {}, h("small", {}, "Richieste aperte"), h("span", {}, String(n.richieste))),
        h("div", {}, h("small", {}, "Carico mensile"), h("span", {}, n.carico === null ? "senza tetto" : n.carico + "%"),
          n.carico === null ? null : h("div", { class: "barra-c" }, h("i", { style: "width:" + n.carico + "%;background:" + c }))),
        h("div", {}, h("small", {}, "Modello"), h("span", {}, n.modello))),
      h("div", { class: "sotto" }, "Risponde a: " + sup + (dip ? " · " + dip : "")),
      h("div", { class: "sotto" }, "Aziende: " + (nomiAz.join(", ") || "tutte (trasversale)")),
      h("div", { class: "azioni" },
        h("button", { class: "p", onclick: () => { const a = stato.agenti.find(x => x.id === n.id); if (a) modulo(a); } }, "Apri scheda"),
        h("button", { class: "s", onclick: () => { stato.vista = "chat"; disegna(); } }, "Parla"))]);
  };
  const chiudiScheda = () => { scelto = null; scheda.style.display = "none"; };

  const disegnaLegenda = () => riempi(legenda, [
    h("div", {}, h("i", { style: "background:#22d3ee" }), "Lorenzo (centro)"),
    h("div", {}, h("i", { style: "background:#a78bfa" }), "Supervisori esterni"),
    h("div", {}, h("i", { style: "background:#34d399" }), "Sereno"),
    h("div", {}, h("i", { style: "background:#fbbf24" }), "Sotto pressione"),
    h("div", {}, h("i", { style: "background:#f87171" }), "In difficoltà"),
    h("div", {}, h("i", { style: "background:#4b5563" }), "Spento"),
    dati ? dati.aziende.filter(z => z.attiva).map(z => h("div", {}, h("i", { style: "background:transparent;border:2px solid " + z.colore }), z.nome)) : null,
    h("div", { style: "color:#7d8a99" }, "I raggi di luce mostrano i messaggi in tempo reale"),
    h("div", { style: "color:#7d8a99" }, "Trascina: ruota · rotella: zoom · tocca un punto")]);


  // Raggi di luce: ogni interazione tra due soggetti illumina il collegamento e lo percorre con un lampo.
  const DURATA = 1300, CODA = 2600;
  const disegnaImpulsi = () => {
    const ora = performance.now();
    impulsi = impulsi.filter(i => ora - i.t0 < CODA + (i.tipo === "chat" ? DURATA : 0));
    for (const i of impulsi) {
      const A = layout.per.get(i.da), B = layout.per.get(i.a);
      if (!A || !B || !A.p || !B.p) continue;
      const colore_ = i.tipo === "richiesta" ? "251,191,36" : i.tipo === "chat" ? "34,211,238" : "167,139,250";
      const t = ora - i.t0;
      if (t < 0) continue;
      const fade = Math.max(0, 1 - t / CODA);
      // il collegamento resta acceso e sfuma
      cx.save(); cx.lineCap = "round";
      cx.strokeStyle = "rgba(" + colore_ + "," + (0.15 + 0.7 * fade) + ")"; cx.lineWidth = 1.5 + 2.5 * fade;
      cx.shadowColor = "rgb(" + colore_ + ")"; cx.shadowBlur = 16 * fade;
      cx.beginPath(); cx.moveTo(A.p.px, A.p.py); cx.lineTo(B.p.px, B.p.py); cx.stroke();
      // fotone che percorre il collegamento (e' tornare indietro per la chat: andata e ritorno)
      const fasi = i.tipo === "chat" ? 2 : 1;
      const fase = Math.min(fasi - 1, Math.floor(t / DURATA));
      const u0 = Math.min(1, (t - fase * DURATA) / DURATA);
      if (t < DURATA * fasi) {
        for (let k = 0; k < 6; k++) {
          let u = Math.max(0, u0 - k * 0.035); if (fase === 1) u = 1 - u;
          const x = A.p.px + (B.p.px - A.p.px) * u, y = A.p.py + (B.p.py - A.p.py) * u;
          cx.fillStyle = "rgba(255,255,255," + (1 - k / 6) + ")"; cx.shadowBlur = 20 * (1 - k / 6);
          cx.beginPath(); cx.arc(x, y, Math.max(1.5, 4.5 - k * 0.6), 0, Math.PI * 2); cx.fill();
        }
      }
      // all'arrivo il nodo di destinazione si accende
      const arrivo = DURATA * fasi;
      if (t >= arrivo - 150 && t < arrivo + 900) {
        const dest = fasi === 2 ? A : B, q = (t - (arrivo - 150)) / 1050;
        cx.strokeStyle = "rgba(" + colore_ + "," + (1 - q) + ")"; cx.lineWidth = 2; cx.shadowBlur = 12;
        cx.beginPath(); cx.arc(dest.p.px, dest.p.py, 8 + 22 * q, 0, Math.PI * 2); cx.stroke();
      }
      cx.restore();
    }
  };

  const interroga = async () => {
    try {
      const r = await api("GET", "/gestione/organigramma/impulsi" + (dopo ? "?dopo=" + encodeURIComponent(dopo) : ""));
      dopo = r.adesso;
      const ora = performance.now();
      r.impulsi.forEach((x, k) => impulsi.push({ ...x, t0: ora + k * 450 }));
    } catch (e) { /* riprova al prossimo giro */ }
  };

  const carica = async () => {
    try {
      dati = await api("GET", "/gestione/organigramma");
      layout = calcolaLayout(dati);
      const corrente = sel.value;
      riempi(sel, [h("option", { value: "" }, "Tutte le aziende"), dati.aziende.filter(z => z.attiva).map(z => h("option", { value: z.id }, z.nome))]);
      sel.value = corrente; azienda = sel.value;
      disegnaLegenda();
      if (scelto !== null) { const n = layout.per.get(scelto); if (n) mostraScheda(n); }
    } catch (e) { /* ritenta al prossimo giro */ }
  };

  sel.addEventListener("change", () => { azienda = sel.value; });
  bRot.addEventListener("click", () => { auto = !auto; bRot.textContent = "Rotazione: " + (auto ? "sì" : "no"); });
  const punto = (e) => { const r = cv.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  cv.addEventListener("pointerdown", (e) => { trascina = true; ultimo = { x: e.clientX, y: e.clientY }; mossa = 0; try { cv.setPointerCapture(e.pointerId); } catch (x) { /* ok */ } });
  cv.addEventListener("pointermove", (e) => {
    if (!trascina || !ultimo) return;
    const dx = e.clientX - ultimo.x, dy = e.clientY - ultimo.y; mossa += Math.abs(dx) + Math.abs(dy);
    rotY += dx * 0.006; rotX = Math.max(-1.4, Math.min(1.4, rotX + dy * 0.006)); ultimo = { x: e.clientX, y: e.clientY };
  });
  cv.addEventListener("pointerup", (e) => {
    trascina = false;
    if (mossa < 8 && layout) {
      const p = punto(e); let best = null, bd = 30;
      for (const n of layout.nodi) { if (!n.p) continue; const d = Math.hypot(n.p.px - p.x, n.p.py - p.y); if (d < bd) { bd = d; best = n; } }
      if (best) mostraScheda(best); else chiudiScheda();
    }
  });
  cv.addEventListener("pointercancel", () => { trascina = false; });
  cv.addEventListener("wheel", (e) => { e.preventDefault(); zoom = Math.max(0.5, Math.min(2.5, zoom * (e.deltaY > 0 ? 0.92 : 1.08))); }, { passive: false });
  cv.addEventListener("touchmove", (e) => {
    if (e.touches.length === 2) {
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      if (pinch) zoom = Math.max(0.5, Math.min(2.5, zoom * d / pinch)); pinch = d;
    }
  }, { passive: true });
  cv.addEventListener("touchend", () => { pinch = 0; });

  scena.append(h("div", { class: "comandi" }, sel, bRot,
    h("button", { class: "s", onclick: () => { rotY = 0.4; rotX = 0.35; zoom = 1; } }, "Centra vista"),
    h("button", { class: "s", onclick: () => { stato.vista = "struttura"; disegna(); } }, "+ Azienda / reparto"),
    h("button", { class: "s", onclick: () => modulo(null) }, "+ Nuovo agente")), legenda, scheda);
  carica(); interroga();
  stato.timer = setInterval(() => { interroga(); if (++giro % 8 === 0) carica(); }, 2000);
  requestAnimationFrame(ciclo);
  return scena;
}

// ---------- Struttura: aziende e dipartimenti ----------
function vistaStruttura() {
  const lista = h("div");
  const carica = async () => {
    try {
      const [aziende, divisioni] = await Promise.all([api("GET", "/gestione/aziende"), api("GET", "/gestione/divisioni")]);
      riempi(lista, [
        h("div", { class: "riga", style: "align-items:center" }, h("h3", {}, "Aziende"),
          h("div", { style: "text-align:right;flex:0 0 auto" }, h("button", { class: "p", onclick: () => formAzienda(null, aziende, carica) }, "+ Nuova azienda"))),
        h("p", { class: "aiuto" }, "Ogni agente può lavorare per una o più aziende (si sceglie nella sua scheda). Senza azienda lavora per tutte."),
        h("div", { class: "griglia" }, aziende.length ? aziende.map(z => h("div", { class: "carta agente", tabindex: 0, role: "button", onclick: () => formAzienda(z, aziende, carica) },
          h("div", { class: "nome" }, h("span", { class: "puntino", style: "background:" + z.colore }), z.nome, z.attiva ? "" : " (disattivata)"),
          h("div", { class: "sotto" }, z.territorio || "—"),
          h("div", { class: "sotto" }, z.agenti.length + " agenti · " + z.divisioni.length + " dipartimenti"))) : h("p", { class: "sotto" }, "Nessuna azienda ancora.")),
        h("div", { class: "riga", style: "align-items:center" }, h("h3", {}, "Dipartimenti (le piramidi)"),
          h("div", { style: "text-align:right;flex:0 0 auto" }, h("button", { class: "p", onclick: () => formDivisione(null, aziende, carica) }, "+ Nuovo dipartimento"))),
        h("p", { class: "aiuto" }, "Una piramide nasce da un agente senza «Risponde a»: nella scheda dell'agente scegli dipartimento e superiore per costruire strutture anche complesse."),
        h("div", { class: "griglia" }, divisioni.map(d => h("div", { class: "carta agente", tabindex: 0, role: "button", onclick: () => formDivisione(d, aziende, carica) },
          h("div", { class: "nome" }, h("span", { class: "puntino", style: "background:" + d.colore }), d.nome, d.attiva ? "" : " (disattivato)"),
          h("div", { class: "sotto" }, d.descrizione || "—"),
          h("div", { class: "sotto" }, (aziende.find(z => z.id === d.azienda_id)?.nome || "Nessuna azienda") + " · " + d.agenti + " agenti"))))]);
    } catch (e) { lista.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Struttura"), lista];
}

function formAzienda(z, tutte, dopo) {
  const d = z || { nome: "", territorio: "", profilo: "", criteri_interesse: "", colore: "#22d3ee", attiva: true };
  const nome = h("input", { type: "text", value: d.nome, maxlength: 80 });
  const terr = h("input", { type: "text", value: d.territorio || "", maxlength: 200 });
  const prof = h("textarea", {}); prof.value = d.profilo || "";
  const crit = h("textarea", {}); crit.value = d.criteri_interesse || "";
  const col = h("input", { type: "color", value: d.colore });
  const att = h("input", { type: "checkbox" }); att.checked = d.attiva;
  const msg = h("div");
  const corpo = () => ({ nome: nome.value.trim(), territorio: terr.value.trim() || null, profilo: prof.value.trim() || null,
    criteri_interesse: crit.value.trim() || null, colore: col.value, attiva: att.checked });
  const chiudi = apriPannello(z ? z.nome : "Nuova azienda", [
    h("div", { class: "interruttore" }, att, h("span", {}, "Azienda attiva")),
    h("label", {}, "Nome", nome), h("label", {}, "Territorio", terr),
    h("label", {}, "Profilo", h("p", { class: "aiuto" }, "Cosa fa l'azienda: gli agenti dei bandi lo usano per valutare la coerenza."), prof),
    h("label", {}, "Criteri di interesse", crit),
    h("label", {}, "Colore nel grafico", col), msg,
    h("div", { class: "azioni" },
      h("button", { class: "p", onclick: async () => { try { await api(z ? "PUT" : "POST", z ? "/gestione/aziende/" + z.id : "/gestione/aziende", corpo()); chiudi(); await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
      z ? h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare l'azienda?")) return; try { await api("DELETE", "/gestione/aziende/" + z.id); chiudi(); await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina") : null,
      h("button", { class: "s", onclick: () => chiudi() }, "Annulla"))]);
}

function formDivisione(d0, aziende, dopo) {
  const d = d0 || { nome: "", descrizione: "", azienda_id: null, colore: "#a78bfa", attiva: true };
  const nome = h("input", { type: "text", value: d.nome, maxlength: 80 });
  const desc = h("input", { type: "text", value: d.descrizione || "", maxlength: 500 });
  const az = h("select", {}, h("option", { value: "" }, "Nessuna (trasversale)"), aziende.map(z => h("option", { value: z.id }, z.nome)));
  az.value = d.azienda_id ?? "";
  const col = h("input", { type: "color", value: d.colore });
  const att = h("input", { type: "checkbox" }); att.checked = d.attiva;
  const msg = h("div");
  const corpo = () => ({ nome: nome.value.trim(), descrizione: desc.value.trim() || null, azienda_id: az.value ? Number(az.value) : null, colore: col.value, attiva: att.checked });
  const chiudi = apriPannello(d0 ? d0.nome : "Nuovo dipartimento", [
    h("div", { class: "interruttore" }, att, h("span", {}, "Dipartimento attivo")),
    h("label", {}, "Nome", nome), h("label", {}, "Cosa fa", desc), h("label", {}, "Azienda", az), h("label", {}, "Colore", col), msg,
    h("div", { class: "azioni" },
      h("button", { class: "p", onclick: async () => { try { await api(d0 ? "PUT" : "POST", d0 ? "/gestione/divisioni/" + d0.id : "/gestione/divisioni", corpo()); chiudi(); await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Salva"),
      d0 ? h("button", { class: "r", onclick: async () => { if (!confirm("Eliminare il dipartimento?")) return; try { await api("DELETE", "/gestione/divisioni/" + d0.id); chiudi(); await ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Elimina") : null,
      h("button", { class: "s", onclick: () => chiudi() }, "Annulla"))]);
}

// ---------- Aggiornamenti ----------
function vistaAggiornamenti() {
  const corpo = h("div");
  const msg = h("div");
  const quando = (t) => t ? new Date(t).toLocaleString("it-IT") : "mai";
  const carica = async () => {
    try {
      const s = await api("GET", "/gestione/aggiornamenti");
      const repo = h("input", { type: "text", value: s.repo || "", placeholder: "Loxeze/Opifex", maxlength: 160 });
      const token = h("input", { type: "password", autocomplete: "off", placeholder: s.token_presente ? "Token già salvato (scrivi solo per sostituirlo)" : "github_pat_…" });
      const aut = h("select", {}, h("option", { value: "no" }, "No: installo io quando decido"), h("option", { value: "patch" }, "Solo le correzioni (es. 0.9.0 → 0.9.1)"));
      aut.value = s.automatico;
      const inCorso = s.esito && s.esito.stato === "in_corso";
      const classe = !s.esito ? "" : s.esito.stato === "riuscito" ? "ok" : s.esito.stato === "in_corso" ? "avv" : "no";
      riempi(corpo, [
        h("div", { class: "carta" },
          h("div", { class: "nome" }, "Versione installata: " + s.versione),
          h("div", { class: "sotto" }, "Ultimo controllo: " + quando(s.ultima_verifica)),
          s.disponibile ? avviso("Disponibile la versione " + s.disponibile + (s.note ? ". " + s.note : ""), "ok") : (s.ultima_verifica ? avviso("Sei aggiornato.", "ok") : null),
          s.esito ? avviso(({ riuscito: "Ultimo aggiornamento riuscito: ", in_corso: "In corso: ", errore: "Rifiutato: ", annullato: "Annullato, versione precedente ripristinata: " })[s.esito.stato] + s.esito.messaggio + " (" + quando(s.esito.quando) + ")", classe) : null,
          h("div", { class: "azioni" },
            h("button", { class: "s", onclick: async (e) => { e.currentTarget.disabled = true; msg.replaceChildren(); try { await api("POST", "/gestione/aggiornamenti/controlla"); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } carica(); } }, "Controlla ora"),
            s.disponibile && !inCorso ? h("button", { class: "p", onclick: async (e) => {
              if (!confirm("Installo la versione " + s.disponibile + "? Faccio prima il backup del database. L'interfaccia si interrompe per qualche secondo.")) return;
              e.currentTarget.disabled = true; msg.replaceChildren();
              try { await api("POST", "/gestione/aggiornamenti/installa"); msg.replaceChildren(avviso("Aggiornamento avviato: attendi, la pagina si aggiorna da sola.", "avv")); attendi(); }
              catch (x) { msg.replaceChildren(avviso(x.message, "no")); e.currentTarget.disabled = false; } } }, "Installa " + s.disponibile) : null)),
        msg,
        h("h3", {}, "Collegamento a GitHub"),
        h("div", { class: "carta" },
          h("label", {}, "Repository", h("p", { class: "aiuto" }, "Nel formato proprietario/nome, ad esempio Loxeze/Opifex."), repo),
          h("label", {}, "Token di sola lettura", h("p", { class: "aiuto" }, "Su GitHub: Settings → Developer settings → Fine-grained tokens → Generate. Repository: solo Opifex. Permessi: Contents = Read-only (nient'altro). Il token viene cifrato sul server e nessuno, agenti compresi, lo vede mai."), token),
          h("label", {}, "Aggiornamento automatico", aut),
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            msg.replaceChildren();
            try { await api("PUT", "/gestione/aggiornamenti/configurazione", { repo: repo.value.trim(), token: token.value.trim() || null, automatico: aut.value });
              msg.replaceChildren(avviso("Salvato.", "ok")); carica(); } catch (x) { msg.replaceChildren(avviso(x.message, "no")); } } }, "Salva"))),
        s.storico.length ? [h("h3", {}, "Storico"), h("div", { class: "carta" }, s.storico.map(r => h("div", { class: "sotto" }, quando(r.creato_il) + " · " + r.versione + " · " + r.esito + (r.dettagli ? " · " + r.dettagli : ""))))] : null]);
      if (inCorso) attendi();
    } catch (e) { corpo.replaceChildren(avviso(e.message + " — riprovo tra poco (il servizio potrebbe essersi riavviato)", "avv")); attendi(); }
  };
  // durante l'installazione il servizio si riavvia: riprovo finché risponde
  const attendi = () => { clearTimeout(stato.attesa); stato.attesa = setTimeout(carica, 4000); };
  carica();
  return [h("h2", {}, "Aggiornamenti"), corpo];
}

function vistaCanali() {
  const corpo = h("div");
  const msg = h("div");
  const via = async (metodo, p, dati, ok) => {
    msg.replaceChildren();
    try { const r = await api(metodo, "/gestione/canali/telegram" + p, dati); if (ok) msg.replaceChildren(avviso(ok, "ok")); return r; }
    catch (x) { msg.replaceChildren(avviso(x.message, "no")); return null; }
  };
  const carica = async () => {
    try {
      const s = await api("GET", "/gestione/canali/telegram");
      const token = h("input", { type: "password", autocomplete: "off", placeholder: "Token del bot (da @BotFather)", maxlength: 200 });
      const fascia = h("select", {}, h("option", { value: "pubblico" }, "Pubblico: solo informazioni non riservate"), h("option", { value: "interno" }, "Interno: anche dati interni (non riservati)"));
      fascia.value = s.fascia_dati;
      let blocco;
      if (!s.configurato) {
        blocco = h("div", { class: "carta" },
          h("div", { class: "nome" }, "1. Crea il bot"),
          h("p", { class: "aiuto" }, "Su Telegram apri @BotFather, scrivi /newbot e scegli nome e username. Ti darà un token: incollalo qui sotto (solo qui, mai in chat). Se lo hai già mostrato a qualcuno, rigeneralo con /revoke."),
          token,
          h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
            if (await via("PUT", "/token", { token: token.value.trim() }, "Bot riconosciuto.")) carica(); } }, "Salva token")));
      } else if (!s.collegato) {
        blocco = h("div", { class: "carta" },
          h("div", { class: "nome" }, "2. Collega la tua chat al bot @" + (s.bot || "")),
          h("p", { class: "aiuto" }, "Genera un codice (vale 10 minuti, si usa una volta sola) e inviane uno al bot su Telegram, in chat privata, scrivendo: /collega CODICE"),
          h("div", { id: "codice-tg", class: "nome" }),
          h("div", { class: "azioni" },
            h("button", { class: "p", onclick: async () => {
              const r = await via("POST", "/codice"); if (r) document.getElementById("codice-tg").textContent = "Codice: " + r.codice; } }, "Genera codice"),
            h("button", { class: "s", onclick: carica }, "Ho inviato il codice"),
            h("button", { class: "s", onclick: async () => { if (confirm("Rimuovere il bot?") && await via("DELETE", "")) carica(); } }, "Rimuovi bot")));
      } else {
        blocco = h("div", { class: "carta" },
          avviso("Collegato al bot @" + s.bot + ". Solo la tua chat riceve risposte; gli altri vengono ignorati.", "ok"),
          h("label", {}, "Che dati può usare Aurora su Telegram", fascia),
          h("p", { class: "aiuto" }, "Comandi nel bot: /richieste, /rispondi N testo, /briefing, /stato, /fascia, /aiuto. Un testo libero va ad Aurora. Le notifiche urgenti (agenti bloccati) e i briefing arrivano da soli."),
          h("div", { class: "azioni" },
            h("button", { class: "p", onclick: () => via("PUT", "/fascia", { fascia: fascia.value }, "Livello aggiornato.") }, "Salva livello"),
            h("button", { class: "s", onclick: () => via("POST", "/prova", undefined, "Messaggio di prova inviato.") }, "Invia messaggio di prova"),
            h("button", { class: "s", onclick: async () => { if (confirm("Scollegare la chat?") && await via("POST", "/scollega")) carica(); } }, "Scollega"),
            h("button", { class: "s", onclick: async () => { if (confirm("Rimuovere il bot e il token?") && await via("DELETE", "")) carica(); } }, "Rimuovi bot")));
      }
      riempi(corpo, [s.ultimo_errore ? avviso("Ultimo errore: " + s.ultimo_errore, "avv") : null, blocco, msg,
        h("h3", {}, "Altri canali"), h("div", { class: "carta" }, h("div", { class: "sotto" }, "In arrivo: WhatsApp, email e messaggi vocali.")) ]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "Canali"), corpo];
}
