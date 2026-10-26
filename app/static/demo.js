"use strict";
// Allineamento documenti (finestra) e modalità demo a schermo intero (organigramma 3D e altre sezioni a rotazione).

const DOC_STATO = { ok: "a posto", assente: "non più su Drive" };

function apriAllineamento() {
  const corpo = h("div", {});
  const esito = h("div", {});
  const chiudi = apriPannello("Allinea documenti", [
    h("p", { class: "sotto" }, "Ogni documento creato da un agente deve stare nella cartella di quell'agente dentro «Opifex» su Drive. Qui vedi i file e puoi riallinearli."),
    esito, corpo, h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => chiudi() }, "Chiudi"))]);
  const disegnaElenco = (file) => {
    if (!file.length) { corpo.replaceChildren(h("p", { class: "sotto" }, "Nessun documento creato dagli agenti finora.")); return; }
    const per = {};
    for (const f of file) (per[f.agente || "Senza agente"] = per[f.agente || "Senza agente"] || []).push(f);
    corpo.replaceChildren(...Object.entries(per).map(([ag, el]) => h("div", { class: "carta" }, h("div", { class: "nome" }, "📁 " + ag + " (" + el.length + ")"),
      ...el.map(f => h("div", { class: "sotto" }, f.link ? h("a", { href: f.link, target: "_blank", rel: "noopener" }, f.nome) : f.nome, " · " + f.tipo + " · " + (DOC_STATO[f.stato] || f.stato))))));
  };
  const carica = async () => {
    try {
      const r = await api("GET", "/documenti/allineamento");
      if (!r.collegato) esito.replaceChildren(avviso("Google Drive non è collegato (Impostazioni → Account Google).", "avv"));
      disegnaElenco(r.file);
    } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
  };
  const b = h("button", { class: "p" }, "Allinea ora");
  b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Allineo…";
    try {
      const r = await api("POST", "/documenti/allineamento");
      esito.replaceChildren(avviso(`Controllati ${r.controllati}: a posto ${r.gia_a_posto}, spostati ${r.spostati}, non più su Drive ${r.assenti}` + (r.errori.length ? ". Errori: " + r.errori.join("; ") : ""), r.errori.length ? "avv" : "ok"));
      disegnaElenco(r.file);
    } catch (e) { esito.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false; b.textContent = "Allinea ora";
  });
  esito.after(b);
  carica();
}

const bottoneAllinea = () => h("button", { class: "s", type: "button", onclick: apriAllineamento }, "📁 Allinea documenti");

// ---------- Modalità demo ----------
const SEZIONI_DEMO = {
  organigramma: { nome: "Organigramma 3D", crea: () => { const s = vistaOrganigramma(); s.classList.add("scena-pagina"); s.style.height = "100%"; return s; } },
  dashboard: { nome: "Dashboard", crea: () => vistaDashboard() },
  chat: { nome: "Chat tra agenti", crea: () => h("div", { class: "demo-largo" }, vistaDialoghi(true)) },
  progetti: { nome: "Progetti", crea: () => h("div", { class: "demo-largo" }, vistaProgetti()) },
  task: { nome: "Task", crea: () => h("div", { class: "demo-largo" }, vistaTask()) },
};

function impostazioniDemo() {
  const base = { sezioni: ["organigramma", "dashboard", "chat"], secondi: 25, ruota: true };
  try { return { ...base, ...(JSON.parse(localStorage.getItem("opifex_demo") || "{}")) }; } catch (e) { return base; }
}

function salvaDemo(c) { try { localStorage.setItem("opifex_demo", JSON.stringify(c)); } catch (e) { /* facoltativo */ } }

function avviaDemo() {
  const cfg = impostazioniDemo();
  const sezioni = cfg.sezioni.filter(s => SEZIONI_DEMO[s]);
  if (!sezioni.length) sezioni.push("organigramma");
  let i = 0, timer = null, pausa = !cfg.ruota;
  const area = h("div", { class: "demo-area" });
  const titolo = h("span", { class: "sotto" });
  const bPausa = h("button", { class: "s" }, pausa ? "▶ Rotazione" : "⏸ Pausa");
  const esci = () => {
    clearTimeout(timer); clearInterval(stato.timer2); stato.timer2 = null;
    document.removeEventListener("keydown", tasti);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    sfondo.remove(); disegna();
  };
  const mostra = (n) => {
    clearTimeout(timer); clearInterval(stato.timer2); stato.timer2 = null;
    i = (n + sezioni.length) % sezioni.length;
    const s = SEZIONI_DEMO[sezioni[i]];
    titolo.textContent = s.nome + " (" + (i + 1) + "/" + sezioni.length + ")";
    area.replaceChildren(s.crea());
    if (!pausa && sezioni.length > 1) timer = setTimeout(() => mostra(i + 1), Math.max(5, cfg.secondi) * 1000);
  };
  const tasti = (e) => { if (e.key === "Escape") esci(); else if (e.key === "ArrowRight") mostra(i + 1); else if (e.key === "ArrowLeft") mostra(i - 1); else if (e.key === " ") { e.preventDefault(); bPausa.click(); } };
  bPausa.addEventListener("click", () => { pausa = !pausa; bPausa.textContent = pausa ? "▶ Rotazione" : "⏸ Pausa"; mostra(i); });
  const sfondo = h("div", { class: "demo-sfondo" },
    h("div", { class: "demo-barra" }, titolo, h("span", { style: "flex:1" }), h("button", { class: "s", onclick: () => mostra(i - 1) }, "◀"), bPausa, h("button", { class: "s", onclick: () => mostra(i + 1) }, "▶"), h("button", { class: "s", onclick: esci }, "Esci (Esc)")),
    area);
  document.body.append(sfondo);
  document.addEventListener("keydown", tasti);
  if (sfondo.requestFullscreen) sfondo.requestFullscreen().catch(() => {});
  mostra(0);
}

function configuraDemo() {
  const cfg = impostazioniDemo();
  const caselle = Object.entries(SEZIONI_DEMO).map(([k, s]) => { const c = h("input", { type: "checkbox" }); c.checked = cfg.sezioni.includes(k); return [k, c, h("label", { style: "display:block" }, c, " " + s.nome)]; });
  const sec = h("input", { type: "number", min: 5, max: 600, value: cfg.secondi, style: "width:80px" });
  const ruota = h("input", { type: "checkbox" }); ruota.checked = cfg.ruota;
  const chiudi = apriPannello("Modalità demo", [
    h("p", { class: "sotto" }, "Schermo intero con le sezioni scelte, a rotazione. Frecce per cambiare, spazio per fermare, Esc per uscire."),
    ...caselle.map(c => c[2]), h("label", { style: "display:block;margin-top:8px" }, "Secondi per sezione ", sec), h("label", { style: "display:block" }, ruota, " Rotazione automatica"),
    h("div", { class: "azioni" }, h("button", { class: "p", onclick: () => {
      salvaDemo({ sezioni: caselle.filter(c => c[1].checked).map(c => c[0]), secondi: Number(sec.value) || 25, ruota: ruota.checked }); chiudi(); avviaDemo(); } }, "▶ Avvia demo"),
      h("button", { class: "s", onclick: () => chiudi() }, "Annulla"))]);
}

const bottoneDemo = () => h("button", { class: "s", type: "button", onclick: configuraDemo }, "🎬 Demo");
