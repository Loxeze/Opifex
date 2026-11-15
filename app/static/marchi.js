// Social per marchio (2.61): la classifica in Plancia, la scheda di ogni marchio con il suo agente, i commenti da approvare.
const RETI_M = [["instagram", "Instagram"], ["facebook", "Facebook"], ["linkedin", "LinkedIn"], ["tiktok", "TikTok"], ["youtube", "YouTube"], ["pinterest", "Pinterest"], ["threads", "Threads"], ["x", "X"]];
const ET_RETE = Object.fromEntries(RETI_M);
const _nM = (n) => n == null ? "—" : Number(n).toLocaleString("it-IT");
const _varM = (v) => v == null ? null : h("span", { class: "mq-var " + (v > 0 ? "su" : v < 0 ? "giu" : "") }, (v > 0 ? "▲ " : v < 0 ? "▼ " : "") + Math.abs(v) + "%");

// ---------- Plancia: i social a colpo d'occhio ----------
function riquadroSocialPlancia() {
  const el = h("article", { class: "bt-card mq-plancia" }, h("div", { class: "bt-cap" }, "Social a colpo d'occhio"), h("p", { class: "bt-sotto" }, "Carico…"));
  const ricarica = async () => {
    if (inPausa(el)) return;
    let d; try { d = await api("GET", "/gestione/marchi/plancia"); } catch (e) { el.hidden = true; return; }
    if (!d.marchi.length) { el.hidden = true; return; }
    el.hidden = false;
    const max = Math.max(1, ...d.marchi.map(m => m.interazioni));
    const t = d.totali;
    const riga = (m) => h("button", { class: "mq-riga", type: "button", onclick: () => { schedaSocial = "marchi"; stato.marchioAperto = m.id; vai("social"); }, title: "Apri " + m.nome },
      h("span", { class: "mq-pos" }, String(m.posizione)),
      h("span", { class: "mq-nome" }, h("i", { style: "background:" + m.colore }), h("b", {}, m.nome),
        m.agente_al_lavoro ? h("span", { class: "mq-lavora", title: "Il suo agente sta lavorando" }, h("span", { class: "bt-pulsa", "aria-hidden": "true" }), "al lavoro") : null),
      h("span", { class: "mq-barra", "aria-hidden": "true" }, h("span", { style: "width:" + Math.round(100 * m.interazioni / max) + "%;background:" + m.colore })),
      h("span", { class: "mq-num" }, h("b", {}, _nM(m.interazioni)), " interazioni ", _varM(m.variazione)),
      h("span", { class: "mq-dett" }, m.post + " post in 30 gg" + (m.seguaci != null ? " · " + _nM(m.seguaci) + " seguaci" + (m.seguaci_variazione ? " (" + (m.seguaci_variazione > 0 ? "+" : "") + _nM(m.seguaci_variazione) + ")" : "") : "")
        + (m.in_uscita ? " · " + m.in_uscita + " in uscita" : "") + (m.da_approvare ? " · " + m.da_approvare + " da approvare" : "")
        + (m.commenti_da_rispondere + m.risposte_da_approvare ? " · " + (m.commenti_da_rispondere + m.risposte_da_approvare) + (m.commenti_da_rispondere + m.risposte_da_approvare === 1 ? " commento" : " commenti") : "")
        + (!m.collegati ? " · nessun canale collegato" : "")));
    riempi(el, [
      h("div", { class: "bt-testa" }, h("div", { class: "bt-cap" }, "Social a colpo d'occhio · ultimi 30 giorni"),
        h("button", { class: "s piccolo", type: "button", onclick: () => { schedaSocial = "marchi"; vai("social"); } }, "Apri")),
      h("div", { class: "mq-totali" }, [["post", t.post], ["interazioni", t.interazioni], ["in uscita", t.in_uscita], ["post da approvare", t.da_approvare], ["risposte da approvare", t.risposte_da_approvare]]
        .map(([et, n]) => h("span", {}, h("b", {}, _nM(n)), " " + et))),
      h("div", { class: "mq-classifica" }, d.marchi.map(riga)),
      d.marchi.some(m => !m.collegati) ? h("p", { class: "bt-nota" }, "I numeri arrivano dai canali collegati direttamente (Meta, LinkedIn, TikTok…): Buffer pubblica ma non dà i risultati.") : null]);
  };
  return { el, ricarica };
}

// ---------- Social → Marchi ----------
async function schedaMarchi(corpo, apri) {
  const d = await api("GET", "/gestione/marchi");
  const ricarica = () => schedaMarchi(corpo, apri);
  const scheda = (m) => {
    const s = m.scheda || {};
    const box = h("div", { class: "carta mq-marchio" + (stato.marchioAperto === m.id ? " aperto" : ""), id: "marchio-" + m.id });
    const esito = h("div");
    // agente
    const bAg = h("button", { class: m.agente ? "s" : "p", type: "button" }, m.agente ? "Parla con " + m.agente : "Crea il suo agente");
    bAg.onclick = async () => {
      if (m.agente) { stato.chatAgente = m.agente_id; vai("chat"); return; }
      bAg.disabled = true; try { await api("POST", "/gestione/marchi/" + m.id + "/agente"); ricarica(); } catch (e) { riempi(esito, avviso(e.message, "no")); bAg.disabled = false; } };
    // analisi
    const file = h("input", { type: "file", accept: "image/*", multiple: true, "aria-label": "Screenshot dei profili" });
    const bAn = h("button", { class: "p", type: "button" }, m.analizzata_il ? "Rifai l'analisi" : "Analizza il marchio");
    bAn.onclick = async () => {
      const fs = [...file.files].slice(0, 4);
      bAn.disabled = true; bAn.textContent = "L'agente sta analizzando…";
      try {
        const imm = await Promise.all(fs.map(f => new Promise((ok, ko) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = ko; r.readAsDataURL(f); })));
        await api("POST", "/gestione/marchi/" + m.id + "/analizza", { immagini: imm }); stato.marchioAperto = m.id; ricarica();
      } catch (e) { riempi(esito, avviso(e.message, "no")); bAn.disabled = false; bAn.textContent = "Analizza il marchio"; }
    };
    // profili e canali
    const righe = RETI_M.map(([r, et]) => {
      const c = (m.canali || []).find(x => x.rete === r) || {};
      const att = h("input", { type: "checkbox", checked: (m.reti || []).includes(r), "aria-label": et });
      const ind = h("input", { type: "text", value: c.indirizzo || "", placeholder: "link del profilo o @nome", "aria-label": "Profilo " + et });
      const sel = h("select", { "aria-label": "Canale collegato " + et }, h("option", { value: "" }, "non collegato"),
        d.canali_disponibili.filter(x => x.rete === r || (r === "x" && x.rete === "twitter")).map(x => h("option", { value: x.id, selected: c.canale_id === x.id }, x.nome + (x.nativo ? " · diretto" : " · Buffer"))));
      return { r, att, ind, sel, el: h("div", { class: "mq-rete" }, h("label", {}, att, " " + et), ind, sel) };
    });
    const note = h("textarea", { rows: 2, placeholder: "Cosa vuoi per questo marchio (obiettivi, cose da dire o da evitare)…", "aria-label": "Note per l'agente" }, m.note_lorenzo || "");
    const colore = h("input", { type: "color", value: m.colore, "aria-label": "Colore del marchio" });
    const bSalva = h("button", { class: "s", type: "button" }, "Salva profili e note");
    bSalva.onclick = async () => {
      bSalva.disabled = true;
      try {
        await api("PUT", "/gestione/marchi/" + m.id, { nome: m.nome, tipo: m.tipo, colore: colore.value, note_lorenzo: note.value,
          canali: righe.filter(x => x.att.checked).map(x => ({ rete: x.r, indirizzo: x.ind.value.trim(), canale_id: x.sel.value || null })) });
        stato.marchioAperto = m.id; ricarica();
      } catch (e) { riempi(esito, avviso(e.message, "no")); bSalva.disabled = false; }
    };
    const colori = (s.colori || []).length ? h("div", { class: "mq-colori" }, s.colori.map(c => h("span", { class: "mq-colore", title: (c.nome || "") + " " + c.hex + (c.quota ? " · " + c.quota + "% dei pixel" : "") },
      h("i", { style: "background:" + c.hex }), h("span", {}, (c.nome || c.hex) + (c.quota ? " · " + c.quota + "%" : ""))))) : null;
    const voce = (et, v) => v ? h("div", { class: "mq-voce" }, h("span", { class: "sotto" }, et), h("div", {}, v)) : null;
    const dettaglio = h("details", { open: stato.marchioAperto === m.id }, h("summary", {}, "Profili, canali e note"),
      h("div", { class: "mq-reti" }, righe.map(x => x.el)), note, h("div", { class: "riga-azioni" }, h("label", { class: "sotto" }, "Colore ", colore), bSalva));
    riempi(box, [
      h("div", { class: "posta-testa" }, h("div", { class: "mq-titolo" }, h("i", { style: "background:" + m.colore }), h("h3", {}, m.nome),
        h("span", { class: "sotto" }, (m.reti || []).map(r => ET_RETE[r] || r).join(" · "))),
        h("span", { class: "etichetta" }, "n. " + m.posizione + " in classifica")),
      h("div", { class: "mq-numeri" }, [["post in 30 gg", m.post], ["interazioni", m.interazioni], ["seguaci", m.seguaci], ["in uscita", m.in_uscita], ["da approvare", m.da_approvare], ["commenti aperti", m.commenti_da_rispondere + m.risposte_da_approvare]]
        .map(([et, n]) => h("div", { class: "casati-numero" }, h("b", {}, _nM(n)), h("span", { class: "sotto" }, et)))),
      m.migliore ? h("p", { class: "sotto" }, "Il post migliore: «" + m.migliore.testo + "» · " + _nM(m.migliore.interazioni) + " interazioni", m.migliore.link ? [" · ", h("a", { href: m.migliore.link, target: "_blank", rel: "noopener noreferrer" }, "apri")] : null) : null,
      h("h4", {}, "Scheda del marchio"),
      m.analizzata_il ? h("div", { class: "mq-scheda" }, voce("Tono di voce", s.tono), voce("Stile", s.stile), voce("Pubblico", s.pubblico),
        voce("Temi", (s.temi || []).join(" · ")), voce("Cosa funziona", s.cosa_funziona), voce("Da evitare", s.da_evitare), colori, voce("Su cosa si basa", s.fonti))
        : h("p", { class: "sotto" }, "Non ancora analizzato. Carica 1-4 screenshot dei profili (la griglia dei post): i colori si misurano sui pixel, tono e stile li scrive l'agente leggendo post e note."),
      h("div", { class: "riga-azioni" }, file, bAn, bAg), esito, dettaglio]);
    return box;
  };
  const nuovo = h("form", { class: "casati-modulo" }, h("input", { type: "text", name: "nome", placeholder: "Nuovo marchio (impresa, progetto…)", "aria-label": "Nuovo marchio", required: true }),
    h("button", { class: "s", type: "submit" }, "Aggiungi marchio"));
  nuovo.onsubmit = async (ev) => { ev.preventDefault(); try { await api("POST", "/gestione/marchi", { nome: nuovo.nome.value.trim(), tipo: "impresa", colore: "#8A6A2F", note_lorenzo: "", canali: [] }); ricarica(); } catch (e) { alert(e.message); } };
  const imp = h("button", { class: "s piccolo", type: "button" }, "Importa Buffer e collegamenti dalla 2");
  imp.onclick = async () => { imp.disabled = true; try { const r = await api("POST", "/gestione/marchi/importa"); imp.replaceWith(avviso("Importati " + r.collegamenti + " account.", "ok")); ricarica(); } catch (e) { imp.replaceWith(avviso(e.message, "no")); } };
  riempi(corpo, [
    h("p", { class: "sotto" }, "Un agente per ogni marchio: conosce tono, stile e colori e adatta lo stesso messaggio a ogni rete. Le regole delle singole reti sono competenze di Padre Casati, condivise da tutti."),
    !d.canali_disponibili.length ? h("div", { class: "carta" }, h("p", { class: "aiuto" }, "Nessun canale collegato. Per pubblicare collega uno o più account Buffer; per i numeri e i commenti collega Instagram e Facebook direttamente (Meta)."),
      h("div", { class: "riga-azioni" }, h("button", { class: "p", type: "button", onclick: () => { stato.sezione = "social"; vai("impostazioni", "social"); } }, "Collega i canali"), imp)) : null,
    ...d.marchi.map(scheda), nuovo]);
  if (stato.marchioAperto) { const x = document.getElementById("marchio-" + stato.marchioAperto); if (x) x.scrollIntoView({ block: "start" }); }
}

// ---------- Social → Commenti ----------
const STATI_COMM = { da_rispondere: "da rispondere", proposta: "risposta da approvare", pubblicata: "pubblicata", copiata: "incollata da te", scartata: "scartata", errore: "errore" };
async function schedaCommenti(corpo, apri) {
  const [lista, d] = await Promise.all([api("GET", "/gestione/marchi/commenti"), api("GET", "/gestione/marchi")]);
  const ricarica = () => schedaCommenti(corpo, apri);
  const carta = (c) => {
    const esito = h("div");
    const ta = h("textarea", { rows: 2, placeholder: "La risposta…", "aria-label": "Risposta a " + (c.autore || "commento") }, c.risposta || "");
    const azione = (et, cls, f) => { const b = h("button", { class: cls, type: "button" }, et); b.onclick = async () => { b.disabled = true; try { await f(); } catch (e) { riempi(esito, avviso(e.message, "no")); b.disabled = false; } }; return b; };
    const salva = () => api("PUT", "/gestione/marchi/commenti/" + c.id, { risposta: ta.value });
    const approva = async () => {
      await salva();
      const r = await api("POST", "/gestione/marchi/commenti/" + c.id + "/approva");
      if (r.pubblicata) { ricarica(); return; }
      try { await navigator.clipboard.writeText(r.testo); } catch (x) { ta.select(); }
      riempi(esito, [avviso((r.errore ? "La rete ha risposto: " + r.errore + ". " : "") + "Risposta copiata: incollala sotto il commento.", r.errore ? "avv" : "ok"),
        h("div", { class: "riga-azioni" }, r.link ? h("a", { class: "pulsante s", href: r.link, target: "_blank", rel: "noopener noreferrer" }, "Apri il post") : null,
          azione("✓ Fatto, l'ho incollata", "p", async () => { await api("POST", "/gestione/marchi/commenti/" + c.id + "/copiata"); ricarica(); }))]);
    };
    return h("div", { class: "carta mq-commento" },
      h("div", { class: "posta-testa" }, h("span", {}, h("i", { class: "mq-pallino", style: "background:" + (c.colore || "#999") }), h("b", {}, c.marchio || "—"), " · " + (ET_RETE[c.rete] || c.rete) + " · " + (c.autore || "anonimo")),
        h("span", { class: "etichetta" }, STATI_COMM[c.stato] || c.stato)),
      c.post_testo ? h("div", { class: "sotto mq-post" }, "Sul post: «" + c.post_testo.slice(0, 120) + (c.post_testo.length > 120 ? "…" : "") + "»") : null,
      h("blockquote", { class: "mq-testo" }, c.testo),
      c.errore ? avviso(c.errore, "no") : null,
      ta, h("div", { class: "riga-azioni" },
        azione(c.risposta ? "Riscrivila con l'agente" : "Fai preparare la risposta", "s", async () => { await api("POST", "/gestione/marchi/commenti/" + c.id + "/prepara"); ricarica(); }),
        azione(c.ext_id && (c.rete === "instagram" || c.rete === "facebook") ? "✓ Approva e pubblica" : "✓ Approva e copia", "p", approva),
        azione("Scarta", "s", async () => { await api("POST", "/gestione/marchi/commenti/" + c.id + "/scarta"); ricarica(); }),
        c.post_url ? h("a", { href: c.post_url, target: "_blank", rel: "noopener noreferrer", class: "sotto" }, "Apri il post") : null), esito);
  };
  const selM = h("select", { name: "marchio", "aria-label": "Marchio" }, d.marchi.map(m => h("option", { value: m.id }, m.nome)));
  const selR = h("select", { name: "rete", "aria-label": "Rete" }, RETI_M.map(([r, et]) => h("option", { value: r }, et)));
  const man = h("form", { class: "mq-manuale" }, selM, selR, h("input", { name: "autore", placeholder: "Chi l'ha scritto", "aria-label": "Autore" }),
    h("input", { name: "url", placeholder: "Link del post (facoltativo)", "aria-label": "Link del post" }),
    h("textarea", { name: "testo", rows: 2, placeholder: "Incolla qui il commento", required: true, "aria-label": "Commento" }), h("button", { class: "s", type: "submit" }, "Aggiungi"));
  man.onsubmit = async (ev) => { ev.preventDefault();
    try { const r = await api("POST", "/gestione/marchi/commenti", { marchio_id: +selM.value, rete: selR.value, autore: man.autore.value, post_url: man.url.value.trim(), testo: man.testo.value });
      await api("POST", "/gestione/marchi/commenti/" + r.id + "/prepara").catch(() => null); ricarica(); } catch (e) { alert(e.message); } };
  const agg = h("button", { class: "s", type: "button" }, "Controlla adesso");
  agg.onclick = async () => { agg.disabled = true; try { await api("POST", "/gestione/marchi/commenti/aggiorna"); ricarica(); } catch (e) { alert(e.message); agg.disabled = false; } };
  riempi(corpo, [
    h("p", { class: "sotto" }, "I commenti di Instagram e Facebook arrivano da soli ogni 30 minuti se i profili sono collegati direttamente (Meta) e assegnati a un marchio; quelli delle altre reti li incolli qui. L'agente del marchio prepara la risposta, tu la approvi: Instagram e Facebook la pubblicano, per le altre reti viene copiata e si apre il post."),
    h("div", { class: "riga-azioni" }, agg, d.meta_collegato ? null : h("span", { class: "sotto" }, "Meta non collegato: i commenti si incollano a mano.")),
    lista.length ? lista.map(carta) : h("p", { class: "sotto" }, "Nessun commento in attesa."),
    h("details", {}, h("summary", {}, "Incolla un commento"), man)]);
}
