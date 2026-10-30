"use strict";
// Stile di vetro: sfondo fotografico (tre scene disegnate al volo), densita' del vetro, interruttore per tornare allo stile classico.
// Le preferenze stanno sul server, una per utente.
const Vetro = (() => {
  const SCENE = { alba: "Alba sui monti", notte: "Città di notte", oceano: "Oceano", arte: "Opere d'arte" };
  const pref = { stile: "vetro", sfondo: "alba", vetro: 0.46 };
  let attuale = null, timer = {};

  function rng(seed) { let a = seed >>> 0; return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function cresta(base, amp, seed, f1, f2, f3) {
    let d = "M0 900 L0 " + base.toFixed(1);
    for (let x = 0; x <= 1440; x += 20) d += " L" + x + " " + (base + amp * (0.5 * Math.sin(x * f1 + seed) + 0.3 * Math.sin(x * f2 + seed * 2.1) + 0.2 * Math.sin(x * f3 + seed * 3.3))).toFixed(1);
    return d + " L1440 900 Z";
  }
  function stelle(seed, n, maxY) { const r = rng(seed); let d = ""; for (let i = 0; i < n; i++) d += "M" + (r() * 1440).toFixed(0) + " " + (r() * maxY).toFixed(0) + "h.1"; return d; }
  function citta(seed) {
    const r = rng(seed); let far = "M0 900 L0 640", near = "M0 900 L0 700", caldo = "", freddo = "", x = 0;
    while (x < 1440) { const w = 30 + r() * 50, top = 560 + r() * 130; far += " L" + x.toFixed(0) + " " + top.toFixed(0) + " L" + (x + w).toFixed(0) + " " + top.toFixed(0); x += w; }
    far += " L1440 900 Z"; x = 0;
    while (x < 1440) {
      const w = 44 + r() * 70, top = 600 + r() * 230;
      near += " L" + x.toFixed(0) + " " + top.toFixed(0) + " L" + (x + w).toFixed(0) + " " + top.toFixed(0);
      for (let cx = x + 8; cx < x + w - 8; cx += 14) for (let cy = top + 12; cy < 880; cy += 20) {
        const q = r(); if (q < 0.22) caldo += "M" + cx.toFixed(0) + " " + cy.toFixed(0) + "h6v8h-6z"; else if (q < 0.30) freddo += "M" + cx.toFixed(0) + " " + cy.toFixed(0) + "h6v8h-6z";
      }
      x += w + (r() < 0.3 ? 0 : 4);
    }
    return { far, near: near + " L1440 900 Z", caldo, freddo };
  }
  function riflessi(seed, op) {
    const r = rng(seed); let d = "";
    for (let y = 534; y < 890; y += 5 + r() * 6) { const spread = 16 + (y - 520) * 0.85, w = (4 + r() * 30) * (0.5 + (y - 520) / 300), cx = 720 + (r() - 0.5) * spread; if (r() < op) d += "M" + (cx - w / 2).toFixed(0) + " " + y.toFixed(0) + "H" + (cx + w / 2).toFixed(0); }
    return d;
  }
  const stop = (o, c) => `<stop offset="${o}" stop-color="${c}"/>`;
  const SVG = (corpo) => `<svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${corpo}</svg>`;
  const costruisci = {
    alba() {
      const cr = [[540, 46, 1.1, 0.006, 0.013, 0.031, "aR0"], [610, 66, 2.4, 0.005, 0.011, 0.027, "aR1"], [690, 84, 3.7, 0.004, 0.009, 0.021, "aR2"], [780, 96, 5.2, 0.0035, 0.008, 0.017, "aR3"]];
      return SVG(`<defs><linearGradient id="aSky" x1="0" y1="0" x2="0" y2="1">${stop(0, "#0C1330")}${stop(.38, "#2B2A58")}${stop(.62, "#85506F")}${stop(.8, "#C8806A")}${stop(1, "#E3A877")}</linearGradient>
        <radialGradient id="aSun" cx=".64" cy=".62" r=".42"><stop offset="0" stop-color="#FFE2A8" stop-opacity=".9"/><stop offset=".25" stop-color="#FFB07A" stop-opacity=".45"/><stop offset="1" stop-color="#FF8A6A" stop-opacity="0"/></radialGradient>
        <linearGradient id="aR0" x1="0" y1="0" x2="0" y2="1">${stop(0, "#8A5C7E")}${stop(1, "#C58290")}</linearGradient><linearGradient id="aR1" x1="0" y1="0" x2="0" y2="1">${stop(0, "#5A3F6E")}${stop(1, "#8A5679")}</linearGradient>
        <linearGradient id="aR2" x1="0" y1="0" x2="0" y2="1">${stop(0, "#34304F")}${stop(1, "#554066")}</linearGradient><linearGradient id="aR3" x1="0" y1="0" x2="0" y2="1">${stop(0, "#151829")}${stop(1, "#242238")}</linearGradient></defs>
        <rect width="1440" height="900" fill="url(#aSky)"/><path d="${stelle(3, 70, 300)}" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round" opacity=".7"/>
        <rect width="1440" height="900" fill="url(#aSun)"/><circle cx="920" cy="545" r="30" fill="#FFF1CF" opacity=".92"/>
        ${cr.map((c) => `<path d="${cresta(c[0], c[1], c[2], c[3], c[4], c[5])}" fill="url(#${c[6]})"/>`).join("")}
        <g style="filter:blur(38px)"><ellipse class="vt-d1" cx="420" cy="640" rx="360" ry="34" fill="#F8D2B8" opacity=".30"/><ellipse class="vt-d2" cx="1020" cy="700" rx="420" ry="40" fill="#F8D2B8" opacity=".26"/></g>`);
    },
    notte() {
      const c = citta(11), rb = rng(5), col = ["#FF8AC2", "#8AB4FF", "#FFD58A", "#7BE0D0"]; let bokeh = "";
      for (let i = 0; i < 14; i++) bokeh += `<circle cx="${(rb() * 1440).toFixed(0)}" cy="${(560 + rb() * 220).toFixed(0)}" r="${(12 + rb() * 34).toFixed(0)}" fill="${col[i % 4]}" opacity="${(0.14 + rb() * 0.22).toFixed(2)}"/>`;
      return SVG(`<defs><linearGradient id="nSky" x1="0" y1="0" x2="0" y2="1">${stop(0, "#050816")}${stop(.5, "#101C42")}${stop(.74, "#2E3F7C")}${stop(1, "#6A4A8C")}</linearGradient>
        <radialGradient id="nGlow" cx=".5" cy=".74" r=".5"><stop offset="0" stop-color="#FF7BB8" stop-opacity=".5"/><stop offset=".4" stop-color="#6A8CFF" stop-opacity=".22"/><stop offset="1" stop-color="#6A8CFF" stop-opacity="0"/></radialGradient></defs>
        <rect width="1440" height="900" fill="url(#nSky)"/><path d="${stelle(8, 90, 380)}" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" opacity=".6"/>
        <rect width="1440" height="900" fill="url(#nGlow)"/><path d="${c.far}" fill="#16224A"/><path d="${c.near}" fill="#090E1E"/>
        <path d="${c.caldo}" fill="#FFD58A" opacity=".85"/><path d="${c.freddo}" fill="#9FD8FF" opacity=".7"/><g style="filter:blur(7px)">${bokeh}</g>`);
    },
    oceano() {
      return SVG(`<defs><linearGradient id="oSky" x1="0" y1="0" x2="0" y2="1">${stop(0, "#091630")}${stop(.3, "#1F466E")}${stop(.5, "#9A7C8A")}${stop(.578, "#EBAA78")}${stop(1, "#EBAA78")}</linearGradient>
        <linearGradient id="oSea" x1="0" y1="0" x2="0" y2="1">${stop(0, "#2A4E68")}${stop(.35, "#12304B")}${stop(1, "#040C18")}</linearGradient>
        <radialGradient id="oSun" cx=".5" cy=".578" r=".36"><stop offset="0" stop-color="#FFE7B8" stop-opacity=".95"/><stop offset=".3" stop-color="#FFB27A" stop-opacity=".4"/><stop offset="1" stop-color="#FF9A6A" stop-opacity="0"/></radialGradient></defs>
        <rect width="1440" height="900" fill="url(#oSky)"/><g style="filter:blur(30px)"><ellipse class="vt-d1" cx="360" cy="260" rx="300" ry="30" fill="#F2B3B8" opacity=".38"/><ellipse class="vt-d2" cx="1080" cy="330" rx="340" ry="26" fill="#F2B3B8" opacity=".32"/></g>
        <rect width="1440" height="900" fill="url(#oSun)"/><circle cx="720" cy="520" r="44" fill="#FFF3D6"/><rect y="520" width="1440" height="380" fill="url(#oSea)"/><rect y="518" width="1440" height="6" fill="#FFE2B0" opacity=".5"/>
        <path d="${riflessi(21, .9)}" fill="none" stroke="#FFE3B8" stroke-width="2.2" stroke-linecap="round" opacity=".85"/><path d="${riflessi(22, .8)}" fill="none" stroke="#FFE3B8" stroke-width="2" stroke-linecap="round" opacity=".5"/>
        <path d="${riflessi(23, .7)}" fill="none" stroke="#BFE3FF" stroke-width="1.6" stroke-linecap="round" opacity=".3"/>`);
    },
  };
  // Opere d'arte da Wikimedia Commons: una nuova ogni 10 minuti, scelta dal server; sotto restano le scene disegnate come ripiego
  costruisci.arte = () => costruisci.alba() + '<div class="arte-l arte-a"></div><div class="arte-l arte-b"></div>';
  const arte = { slot: null, timer: null, fronte: "a", url: null };
  function fermaArte() { clearTimeout(arte.timer); arte.timer = null; const d = document.getElementById("vetro-didascalia"); if (d) d.hidden = true; }
  async function aggiornaArte() {
    clearTimeout(arte.timer);
    if (arte.volo) return;
    arte.volo = true;
    let attesa = 60;
    try {
      const r = await api("GET", "/sfondo-arte/corrente");
      if (r.disponibile) {
        if (r.slot !== arte.slot) {
          const resp = await fetch("/sfondo-arte/immagine/" + r.slot, { headers: typeof token !== "undefined" && token ? { Authorization: "Bearer " + token } : {} });
          if (resp.ok) {
            const url = URL.createObjectURL(await resp.blob());
            const dietro = arte.fronte === "a" ? "b" : "a", el = document.querySelector("#vetro-sfondo .arte-" + dietro), davanti = document.querySelector("#vetro-sfondo .arte-" + arte.fronte);
            if (el) {
              el.style.backgroundImage = "url(" + url + ")"; el.classList.add("on"); if (davanti) davanti.classList.remove("on");
              arte.fronte = dietro; const vecchio = arte.url; arte.url = url; arte.slot = r.slot;
              if (vecchio) setTimeout(() => URL.revokeObjectURL(vecchio), 4000);
            }
          }
        }
        let d = document.getElementById("vetro-didascalia");
        if (!d) { d = document.createElement("div"); d.id = "vetro-didascalia"; document.body.append(d); }
        d.hidden = false;
        riempi(d, [r.titolo, r.autore ? " — " + r.autore : "", r.licenza ? " · " + r.licenza : "", " · ", r.pagina ? h("a", { href: r.pagina, target: "_blank", rel: "noopener noreferrer" }, "Wikimedia Commons") : "Wikimedia Commons"]);
        attesa = Math.max(15, Math.min(600, (r.cambia_tra || 60) + 2));
      } else attesa = r.riprova_tra || 30;
    } catch (e) { attesa = 60; }
    arte.volo = false;
    arte.timer = setTimeout(aggiornaArte, attesa * 1000);
  }
  const GRANA = `<svg aria-hidden="true" style="mix-blend-mode:overlay;opacity:.5"><filter id="grana" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="2" seed="7"/><feColorMatrix type="matrix" values="0 0 0 0 .5  0 0 0 0 .5  0 0 0 0 .5  0 0 0 .9 -.25"/></filter><rect width="100%" height="100%" filter="url(#grana)"/></svg>`;

  function applica() {
    let box = document.getElementById("vetro-sfondo");
    if (!box) { box = document.createElement("div"); box.id = "vetro-sfondo"; box.setAttribute("aria-hidden", "true"); document.body.prepend(box); }
    const attivo = pref.stile === "vetro";
    document.body.classList.toggle("vetro", attivo);
    document.documentElement.style.setProperty("--g", String(pref.vetro));
    if (attivo && attuale !== pref.sfondo) { box.innerHTML = costruisci[pref.sfondo]() + GRANA + '<div class="vignetta"></div>'; attuale = pref.sfondo; arte.slot = null; arte.url = null; arte.fronte = "a"; fermaArte(); }
    if (attivo && pref.sfondo === "arte") { if (!arte.timer) aggiornaArte(); } else fermaArte();
  }
  async function carica() {
    try {
      const p = await api("GET", "/account/preferenze");
      if (p.stile === "vetro" || p.stile === "classico") pref.stile = p.stile;
      if (SCENE[p.sfondo]) pref.sfondo = p.sfondo;
      if (typeof p.vetro === "number") pref.vetro = Math.min(0.75, Math.max(0.3, p.vetro));
      return p;
    } catch (e) { return {}; } finally { applica(); }
  }
  function imposta(chiave, valore) {
    pref[chiave] = valore; applica();
    clearTimeout(timer[chiave]);
    timer[chiave] = setTimeout(() => { api("PUT", "/account/preferenze/" + chiave, { valore }).catch(() => { /* resta valido finche' la pagina e' aperta */ }); }, 400);
  }
  const chip = (testo, premuto, onclick) => h("button", { class: "pl-chip", type: "button", "aria-pressed": premuto ? "true" : "false", onclick }, testo);

  // controlli riutilizzabili (Plancia e Il mio account)
  function controlli(dopo) {
    const corpo = h("div", { class: "pl-gruppo" });
    const slider = h("input", { id: "vt-vetro", type: "range", min: "0.3", max: "0.75", step: "0.01", value: String(pref.vetro), "aria-label": "Densità del vetro" });
    slider.addEventListener("input", () => { imposta("vetro", parseFloat(slider.value)); });
    const disegna = () => {
      riempi(corpo, [h("span", {}, "Stile"), chip("Vetro", pref.stile === "vetro", () => { imposta("stile", "vetro"); disegna(); if (dopo) dopo(); }), chip("Classico", pref.stile === "classico", () => { imposta("stile", "classico"); disegna(); if (dopo) dopo(); }),
        h("span", {}, "Sfondo"), Object.keys(SCENE).map((k) => chip(SCENE[k], pref.sfondo === k, () => { imposta("stile", "vetro"); imposta("sfondo", k); disegna(); })),
        h("label", { for: "vt-vetro" }, "Densità del vetro"), slider]);
    };
    disegna();
    return corpo;
  }
  function sezioneAccount() {
    return [h("h3", {}, "Aspetto"), h("div", { class: "carta" }, controlli(), h("p", { class: "aiuto" }, "Vale per tutta l'app e si ricorda su ogni dispositivo. Con «Classico» torni ai colori di prima."))];
  }
  return { carica, applica, imposta, controlli, sezioneAccount, pref, SCENE };
})();
