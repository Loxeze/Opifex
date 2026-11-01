"use strict";
// Social: collegamento diretto alle reti e coda dei post preparati dagli agenti, da approvare prima della pubblicazione.
// Tutti i testi arrivano dall'API e vengono inseriti come testo, mai come HTML.

const STATI_POST = { da_approvare: ["Da approvare", "avv"], inviato: ["Inviato", "ok"], programmato: ["Programmato", "avv"], in_pubblicazione: ["In pubblicazione…", "avv"], pubblicato: ["Pubblicato", "ok"], rifiutato: ["Rifiutato", "no"], errore: ["Errore", "no"] };
const quandoS = (t) => t ? new Date(t).toLocaleString("it-IT", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "appena approvato";
const perInput = (t) => { const d = new Date(t); const p = (n) => String(n).padStart(2, "0"); return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes()); };

let schedaSocial = null;
function vistaSocial() {
  const corpo = h("div"); const barra = h("div", { class: "azioni", style: "margin:6px 0 14px" });
  const SCHEDE = [["risultati", "Risultati"], ["pubblica", "Scrivi e pubblica"], ["post", "Post e approvazioni"], ["canali", "Canali e collegamenti"]];
  const apri = async (k) => {
    schedaSocial = k;
    barra.replaceChildren(...SCHEDE.map(([id, et]) => h("button", { class: id === k ? "p" : "s", type: "button", onclick: () => apri(id) }, et)));
    corpo.replaceChildren(h("p", { class: "sotto" }, "Carico…"));
    try { await ({ risultati: schedaRisultati, pubblica: schedaPubblica, post: schedaPost, canali: schedaCanali })[k](corpo, apri); }
    catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  (async () => {
    if (schedaSocial) return apri(schedaSocial);
    try { const st = await api("GET", "/gestione/social-nativo/stato"); apri(st.provider.some(p => p.account.length) ? "risultati" : "canali"); } catch (e) { apri("post"); }
  })();
  return [h("h2", {}, "Social"), barra, corpo];
}

async function schedaPost(corpo) {
  const lista = await api("GET", "/gestione/social/post");
  const riepilogo = h("div", { class: "bt-plancia", style: "margin-bottom:18px" });
  riassuntoSocial(riepilogo);
  const ricarica = () => schedaPost(corpo);
  riempi(corpo, [riepilogo, h("h3", {}, "Post preparati dagli agenti e da te"), listaPost(lista, ricarica)]);
}

// ---------- canali e collegamenti ----------
const GUIDA_APP = {
  meta: ["Instagram e Facebook", "developers.facebook.com → «Crea app» (tipo Business) → aggiungi «Facebook Login» e «Instagram» → in Impostazioni app copia ID app e Chiave segreta → in Facebook Login → Impostazioni incolla l'indirizzo di ritorno qui sotto. Finché l'app resta in modalità sviluppo funziona per le Pagine e gli account di cui sei amministratore: non serve la revisione di Meta. L'account Instagram deve essere professionale e collegato a una Pagina Facebook."],
  linkedin: ["LinkedIn", "linkedin.com/developers → «Create app» (chiede una Pagina LinkedIn da associare) → scheda Products: aggiungi «Share on LinkedIn» e «Sign In with LinkedIn using OpenID Connect» → scheda Auth: copia Client ID e Primary Client Secret e incolla l'indirizzo di ritorno tra i Redirect URLs. Il tuo profilo personale funziona subito. Le pagine aziendali e le statistiche richiedono un'approvazione di LinkedIn (programma Community Management): puoi chiederla più avanti."],
  tiktok: ["TikTok", "developers.tiktok.com → «Manage apps» → «Connect an app» → aggiungi i prodotti «Login Kit» e «Content Posting API» → copia Client key e Client secret e incolla l'indirizzo di ritorno in Login Kit. Se TikTok chiede degli utenti di prova, aggiungi il tuo account. Finché l'app non e' verificata da TikTok i video escono solo in privato: e' proprio quello che facciamo, poi li rendi pubblici dall'app di TikTok."],
  youtube: ["YouTube", "console.cloud.google.com → crea un progetto → «API e servizi» → abilita «YouTube Data API v3» → Schermata consenso OAuth (tipo Esterno, aggiungi il tuo account tra gli utenti di prova) → Credenziali → «ID client OAuth» di tipo Applicazione web → incolla l'indirizzo di ritorno qui sotto tra gli URI di reindirizzamento e copia ID e segreto. Finché il progetto non e' verificato da Google i video caricati dall'API possono restare privati (e' un limite di YouTube): chiedi la verifica dal modulo «API Services Audit» quando vuoi pubblicare in pubblico. Quota iniziale: circa 100 caricamenti al giorno. Il testo del post: la prima riga e' il titolo del video, il resto la descrizione."],
  threads: ["Threads", "developers.facebook.com → la stessa app usata per Instagram (o una nuova) → aggiungi il caso d'uso «Accedi a Threads API» → in Impostazioni di Threads copia ID app Threads e Chiave segreta (sono diversi da quelli di Facebook) → incolla l'indirizzo di ritorno tra gli URL di reindirizzamento e aggiungi il tuo account Threads come tester. Il testo puo' avere fino a 500 caratteri."],
  x: ["X (Twitter)", "developer.x.com → crea un progetto e un'app → «User authentication settings»: Read and write, tipo «Web App», incolla l'indirizzo di ritorno come Callback URI → copia Client ID e Client Secret (OAuth 2.0, non le chiavi API). ATTENZIONE: l'API di X e' a consumo, senza piano gratuito per i nuovi sviluppatori (circa 0,015 $ per post, 0,20 $ se il post contiene un link): carica credito dal portale e imposta un limite di spesa. Per ora Opifex pubblica solo testo (max 280 caratteri)."],
  pinterest: ["Pinterest", "developers.pinterest.com → «My apps» → «Connect app» → copia App id e App secret e incolla l'indirizzo di ritorno in Redirect URIs. Con l'accesso iniziale («Trial») Pinterest puo' limitare la visibilita' dei pin creati dall'API: se vedi che non sono pubblici, richiedi l'accesso «Standard» dal portale."],
};
function copiabile(testo) {
  const m = h("span", { class: "sotto" });
  return h("div", { class: "azioni", style: "align-items:center;gap:8px" }, h("code", { style: "word-break:break-all" }, testo),
    h("button", { class: "s", type: "button", onclick: async () => { try { await navigator.clipboard.writeText(testo); m.textContent = "Copiato"; } catch (e) { m.textContent = "Selezionalo e copialo a mano"; } } }, "Copia"), m);
}
function schedaApp(p, ricarica) {
  const msg = h("div"); const cid = h("input", { style: "width:100%", autocomplete: "off", placeholder: p.provider === "tiktok" ? "Client key" : "ID app / Client ID" }); cid.value = p.client_id || "";
  const sec = h("input", { type: "password", autocomplete: "off", placeholder: p.segreto_salvato ? "(segreto già salvato: lascia vuoto per non cambiarlo)" : "Segreto / Client secret" });
  const pag = h("input", { type: "checkbox" });
  const ritorno = p.redirect || (location.origin + "/gestione/social-nativo/callback/" + p.provider);
  const [titolo, guida] = GUIDA_APP[p.provider];
  const salva = async () => {
    msg.replaceChildren();
    try { await api("PUT", "/gestione/social-nativo/app/" + p.provider, { client_id: cid.value.trim(), segreto: sec.value.trim() || null, origine: location.origin }); return true; }
    catch (e) { msg.replaceChildren(avviso(e.message, "no")); return false; }
  };
  const pronta = p.client_id && p.segreto_salvato;
  return h("div", { class: "carta", style: "margin-bottom:14px" }, h("div", { class: "nome" }, titolo),
    h("details", {}, h("summary", {}, "Come ottengo ID e segreto"), h("p", { class: "aiuto" }, guida), h("div", { class: "sotto" }, "Indirizzo di ritorno da incollare nel portale:"), copiabile(ritorno)),
    pronta ? null : h("p", { class: "aiuto" }, "Prima crea l'app sul portale (guida qui sopra), poi incolla qui ID e segreto."),
    h("label", {}, "ID", cid), h("label", {}, "Segreto", sec),
    p.provider === "linkedin" ? h("label", { class: "spunta" }, pag, "Collega anche le pagine aziendali (serve l'approvazione LinkedIn)") : null, msg,
    h("div", { class: "azioni" },
      h("button", { class: "s", type: "button", onclick: async () => { if (await salva()) { msg.replaceChildren(avviso("Salvato", "ok")); ricarica(); } } }, "Salva credenziali"),
      h("button", { class: "p", type: "button", onclick: async () => {
        if (!(await salva())) return;
        try { const r = await api("POST", "/gestione/social-nativo/collega/" + p.provider, { pagine: pag.checked }); location.href = r.url; }
        catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, p.account.length ? "Collega un altro profilo" : "Collega")),
    p.account.map(a => {
      const m2 = h("div"); const org = h("input", { placeholder: "ID numerico della pagina" }); const nome = h("input", { placeholder: "Nome della pagina" });
      return h("div", { style: "border-top:1px solid var(--bordo,#ddd);margin-top:10px;padding-top:8px" },
        h("div", { class: "nome" }, a.nome), a.ultimo_errore ? avviso(a.ultimo_errore, "no") : null,
        a.scade_il ? h("div", { class: "sotto" }, "Accesso valido fino al " + new Date(a.scade_il).toLocaleDateString("it-IT") + (new Date(a.scade_il) < new Date() ? " (scaduto: ricollega)" : "")) : null,
        h("div", { class: "spunte" }, a.canali.map(c => h("label", { class: "spunta" }, (() => { const x = h("input", { type: "checkbox" }); x.checked = c.attivo;
          x.onchange = async () => { try { await api("PUT", "/gestione/social-nativo/canale/" + c.id, { attivo: x.checked }); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } }; return x; })(), c.nome + " (" + c.rete + ")"))),
        p.provider === "linkedin" && a.extra && a.extra.pagine ? h("div", {}, h("div", { class: "sotto" }, "Aggiungi una pagina aziendale (l'ID e' il numero nell'indirizzo dell'area amministratore)"), org, nome,
          h("button", { class: "s", type: "button", onclick: async () => { try { await api("POST", `/gestione/social-nativo/account/${a.id}/pagina-linkedin`, { org_id: org.value, nome: nome.value }); ricarica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi pagina")) : null,
        m2, h("div", { class: "azioni" }, h("button", { class: "s", type: "button", onclick: async () => { if (!confirm("Scollegare " + a.nome + "? I post gia' pubblicati restano nello storico.")) return; try { await api("DELETE", "/gestione/social-nativo/account/" + a.id); ricarica(); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Scollega")));
    }));
}
async function schedaCanali(corpo, apri) {
  const st = await api("GET", "/gestione/social-nativo/stato");
  const ricarica = () => schedaCanali(corpo, apri);
  const esito = st.esito ? (st.esito.startsWith("ok:") ? avviso(st.esito.slice(3), "ok") : avviso(st.esito, "no")) : null;
  riempi(corpo, [esito, h("p", { class: "aiuto" }, "Ogni rete richiede una piccola app registrata sul suo portale per sviluppatori (una volta sola, gratuita). Opifex pubblica e raccoglie i risultati direttamente, senza limiti di canali. Gli agenti preparano i post, ma pubblichi solo tu con l'approvazione."),
    st.provider.map(p => schedaApp(p, ricarica)),
    h("h3", {}, "A chi serve ogni canale"), boxCanali(ricarica)]);
}

// ---------- scrivi e pubblica ----------
async function schedaPubblica(corpo, apri) {
  const st = await api("GET", "/gestione/social-nativo/stato");
  const canali = st.provider.flatMap(p => p.account.flatMap(a => a.canali.filter(c => c.attivo)));
  if (!canali.length) return riempi(corpo, [h("p", { class: "sotto" }, "Nessun canale collegato: collega prima almeno una rete."), h("button", { class: "p", type: "button", onclick: () => apri("canali") }, "Vai ai collegamenti")]);
  const msg = h("div"); const testo = h("textarea", { style: "min-height:130px" }); const conta = h("span", { class: "sotto" });
  const sel = canali.map(c => { const x = h("input", { type: "checkbox" }); return [c, x]; });
  const media = []; const lista = h("div"); const quando = h("input", { type: "datetime-local" }); const url = h("input", { placeholder: "oppure incolla l'indirizzo https di una foto o di un video" });
  const disegna = () => lista.replaceChildren(...media.map((m, i) => h("div", { class: "sotto" }, (m.tipo === "video" ? "Video: " : "Foto: ") + m.url.split("/").pop() + " ", h("a", { href: "#", onclick: (e) => { e.preventDefault(); media.splice(i, 1); disegna(); } }, "togli"))));
  const avvisoTT = h("div");
  const agg = () => { conta.textContent = testo.value.length + " caratteri"; avvisoTT.replaceChildren(...(sel.some(([c, x]) => x.checked && c.rete === "tiktok") ? [avviso("TikTok: il video esce in privato. Lo rendi pubblico tu dall'app di TikTok.", "avv")] : [])); };
  testo.oninput = agg; sel.forEach(([, x]) => x.onchange = agg); agg();
  const file = h("input", { type: "file", accept: "image/*,video/mp4,video/quicktime", multiple: true });
  file.onchange = async () => {
    for (const f of file.files) {
      msg.replaceChildren(avviso("Carico " + f.name + "…", "avv"));
      try { const fd = new FormData(); fd.append("file", f); const r = await api("POST", "/gestione/social-nativo/media", fd); media.push({ tipo: r.tipo, url: r.url }); msg.replaceChildren(); disegna(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    }
    file.value = "";
  };
  const invia = async (ev) => {
    const b = ev.currentTarget; msg.replaceChildren();
    const scelti = sel.filter(([, x]) => x.checked).map(([c]) => "n:" + c.id);
    if (!scelti.length) return msg.replaceChildren(avviso("Scegli almeno un canale", "no"));
    if (url.value.trim()) { media.push({ tipo: /\.(mp4|mov|m4v)(\?|$)/i.test(url.value) ? "video" : "image", url: url.value.trim() }); url.value = ""; disegna(); }
    b.disabled = true;
    try {
      await api("POST", "/gestione/social-nativo/post", { canali: scelti, testo: testo.value, media, programmato_il: quando.value ? new Date(quando.value).toISOString() : null });
      testo.value = ""; media.length = 0; disegna(); quando.value = ""; sel.forEach(([, x]) => x.checked = false); agg();
      msg.replaceChildren(avviso(quando.value || scelti.length ? "Fatto. Lo trovi in «Post e approvazioni»: lo stato passa da «In pubblicazione» a «Pubblicato» entro qualche minuto." : "Fatto", "ok"));
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    b.disabled = false;
  };
  riempi(corpo, [h("div", { class: "carta" }, h("div", { class: "nome" }, "Nuovo post"),
    h("div", { class: "sotto" }, "Dove pubblicare"), h("div", { class: "spunte" }, sel.map(([c, x]) => h("label", { class: "spunta" }, x, c.nome + " (" + c.rete + ")"))),
    h("label", {}, "Testo", testo), conta,
    h("label", {}, "Foto o video dal tuo computer", file), lista, h("label", {}, "", url),
    h("label", {}, "Data e ora (vuoto = pubblica subito)", quando), avvisoTT, msg,
    h("div", { class: "azioni" }, h("button", { class: "p", type: "button", onclick: invia }, "Pubblica")))]);
}

// ---------- risultati ----------
let periodoSocial = 30;
async function schedaRisultati(corpo, apri) {
  const a = await api("GET", "/gestione/social-nativo/analisi?giorni=" + periodoSocial);
  const ricarica = () => schedaRisultati(corpo, apri);
  if (!a.canali.length) return riempi(corpo, [h("p", { class: "sotto" }, "Nessun canale collegato: collega le reti e qui compariranno seguaci, visualizzazioni e interazioni."), h("button", { class: "p", type: "button", onclick: () => apri("canali") }, "Vai ai collegamenti")]);
  const msg = h("div");
  const scarica = async () => {
    try {
      const r = await fetch("/gestione/social-nativo/analisi.csv?giorni=" + Math.max(90, periodoSocial), { headers: { Authorization: "Bearer " + token } });
      if (!r.ok) throw new Error("Esportazione non riuscita");
      const u = URL.createObjectURL(await r.blob()); const l = h("a", { href: u, download: "risultati_social.csv" }); document.body.append(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(u), 5000);
    } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
  };
  const barra = h("div", { class: "azioni", style: "align-items:center;margin-bottom:10px" },
    [7, 30, 90].map(g => h("button", { class: g === periodoSocial ? "p" : "s", type: "button", onclick: () => { periodoSocial = g; ricarica(); } }, g + " giorni")),
    h("button", { class: "s", type: "button", onclick: async (ev) => { ev.currentTarget.disabled = true; msg.replaceChildren(avviso("Leggo i dati dalle reti…", "avv")); try { await api("POST", "/gestione/social-nativo/raccogli"); ricarica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); ev.currentTarget.disabled = false; } } }, "Aggiorna i dati ora"),
    h("button", { class: "s", type: "button", onclick: scarica }, "Esporta in CSV"),
    h("span", { class: "sotto" }, a.ultima_raccolta ? "Ultimo aggiornamento: " + new Date(a.ultima_raccolta).toLocaleString("it-IT") : "Dati non ancora raccolti: premi «Aggiorna i dati ora»"));
  const T = a.totali, seg = a.canali.reduce((s, c) => s + (c.seguaci || 0), 0);
  const kpi = (t, n, s) => h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, t), h("div", { class: "bt-num" }, n), h("div", { class: "bt-sotto" }, s));
  const righe = a.canali.map(c => h("tr", {}, h("td", {}, c.nome, h("span", { class: "bt-sotto" }, " · " + c.rete), c.errore ? h("div", { class: "bt-sotto", style: "color:var(--no,#b4402a)" }, c.errore) : null),
    h("td", {}, c.seguaci == null ? "—" : nIt(c.seguaci)), h("td", {}, c.seguaci_variazione == null ? "—" : (c.seguaci_variazione >= 0 ? "+" : "") + nIt(c.seguaci_variazione)),
    h("td", {}, nIt(c.post)), h("td", {}, c.dati_post ? compatto(c.visualizzazioni) : "n.d."), h("td", {}, c.dati_post ? nIt(c.interazioni) : "n.d."),
    h("td", {}, c.coinvolgimento == null ? "—" : nIt(c.coinvolgimento, 1) + "%"),
    h("td", {}, c.serie.length > 1 ? sparkline(c.serie.map(x => x.seguaci), PB.terra) : "")));
  riempi(corpo, [barra, msg,
    h("section", { class: "bt-plancia bt-fitta" },
      h("section", { class: "bt-griglia bt-kpis" }, kpi("Post pubblicati", nIt(T.post), "negli ultimi " + a.giorni + " giorni"), kpi("Visualizzazioni", compatto(T.visualizzazioni), "somma dei post"), kpi("Interazioni", nIt(T.interazioni), "mi piace, commenti, condivisioni, salvataggi"), kpi("Seguaci", compatto(seg), "su tutti i canali")),
      h("article", { class: "bt-card", style: "margin-top:12px;overflow-x:auto" }, h("div", { class: "bt-testa" }, h("h2", {}, "Per canale")),
        h("table", { class: "bt-tab" }, h("thead", {}, h("tr", {}, ["Canale", "Seguaci", "Variazione", "Post", "Visual.", "Interazioni", "Coinvolgimento", "Seguaci nel tempo"].map(t => h("th", {}, t)))), h("tbody", {}, righe)),
        h("p", { class: "bt-nota" }, "Coinvolgimento = interazioni diviso visualizzazioni (o persone raggiunte). LinkedIn non fornisce questi dati senza l'approvazione del suo programma partner. I dati dei post si aggiornano ogni 6 ore.")),
      h("section", { class: "bt-griglia", style: "margin-top:12px" },
        h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "Post migliori")),
          a.migliori.length ? a.migliori.map(p => h("div", { class: "bt-riga-mov" }, h("div", {}, h("b", {}, p.canale_nome), " · " + nIt(p.interazioni) + " interazioni" + (p.visualizzazioni ? ", " + compatto(p.visualizzazioni) + " visualizzazioni" : "")),
            h("div", { class: "bt-sotto" }, (p.testo || "").slice(0, 120), p.permalink ? [" ", h("a", { href: p.permalink, target: "_blank", rel: "noopener noreferrer" }, "apri")] : null)))
            : h("p", { class: "bt-sotto" }, "Appena i post pubblicati ricevono interazioni, compaiono qui.")),
        h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "Quando funziona meglio")),
          a.momenti.length ? a.momenti.map(m => h("div", { class: "bt-riga-mov" }, h("b", {}, m.rete), " · " + m.giorno + ", " + m.fascia, h("div", { class: "bt-sotto" }, nIt(m.interazioni_medie, 1) + " interazioni per post (su " + m.post + " post)")))
            : h("p", { class: "bt-sotto" }, "Servono almeno 2 post nella stessa fascia di giorno e ora per dare un'indicazione."))))]);
}

function boxCanali(ricarica) {
  const box = h("div"); const msg = h("div");
  (async () => {
    try {
      const d = await api("GET", "/gestione/social/canali");
      riempi(box, [h("h4", {}, "A chi serve ogni canale"),
        h("p", { class: "aiuto" }, "Assegna ogni canale alle aziende e ai progetti che lo usano: gli agenti vedono e usano solo i canali del loro ambito. Un canale senza assegnazioni resta libero per tutti gli agenti social."),
        d.canali.map(c => {
          const az = d.aziende.map(a => { const x = h("input", { type: "checkbox" }); x.checked = c.aziende.includes(a.id); return [a, x]; });
          const pr = d.progetti.map(a => { const x = h("input", { type: "checkbox" }); x.checked = c.progetti.includes(a.id); return [a, x]; });
          const m2 = h("div");
          return h("div", { class: "carta", style: "margin-bottom:8px" }, h("div", { class: "nome" }, c.name + " · " + c.service),
            h("div", { class: "sotto" }, "Aziende"), h("div", { class: "spunte" }, az.map(([a, x]) => h("label", { class: "spunta" }, x, a.nome))),
            h("div", { class: "sotto" }, "Progetti"), h("div", { class: "spunte" }, pr.map(([a, x]) => h("label", { class: "spunta" }, x, a.nome))), m2,
            h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
              try { await api("PUT", "/gestione/social/canali/" + encodeURIComponent(c.id), { aziende: az.filter(([, x]) => x.checked).map(([a]) => a.id), progetti: pr.filter(([, x]) => x.checked).map(([a]) => a.id) });
                m2.replaceChildren(avviso("Salvato", "ok")); } catch (e) { m2.replaceChildren(avviso(e.message, "no")); } } }, "Salva")));
        }), msg]);
    } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
  })();
  return box;
}

function listaPost(lista, ricarica) {
  if (!lista.length) return h("p", { class: "sotto" }, "Nessun post ancora.");
  return lista.map(p => {
    const [t, cl] = STATI_POST[p.stato] || [p.stato, ""];
    const msg = h("div");
    const testo = h("textarea", { style: "min-height:110px" }); testo.value = p.testo;
    const quando = h("input", { type: "datetime-local" }); if (p.programmato_il) quando.value = perInput(p.programmato_il);
    const modificabile = p.stato === "da_approvare" || p.stato === "errore";
    const azione = async (az) => {
      msg.replaceChildren();
      try {
        if (az === "approva") {
          await api("PUT", "/gestione/social/post/" + p.id, quando.value ? { testo: testo.value, programmato_il: new Date(quando.value).toISOString() } : { testo: testo.value, senza_orario: true });
        }
        await api("POST", "/gestione/social/post/" + p.id + "/decisione", { azione: az });
        ricarica();
      } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    };
    return h("div", { class: "carta", style: "margin-top:12px" },
      h("div", { class: "nome" }, p.canale_nome + " · " + p.servizio),
      h("div", { class: "sotto" }, (p.agente ? "Preparato da " + p.agente + " · " : "") + "pubblicazione: " + quandoS(p.programmato_il)),
      h("div", {}, h("span", { class: "etichetta " + cl }, t)),
      modificabile ? [h("label", {}, "Testo", testo), h("label", {}, "Data e ora (vuoto = subito dopo l'approvazione)", quando)]
        : h("div", { class: "risposta", style: "margin-top:8px" }, p.testo),
      (p.media || []).length ? h("div", { class: "sotto" }, "File: " + p.media.map(m => m.tipo + " " + m.url).join(", ")) : null,
      p.permalink ? h("div", { class: "sotto" }, h("a", { href: p.permalink, target: "_blank", rel: "noopener noreferrer" }, "Apri il post")) : null,
      p.errore ? avviso(p.errore, "no") : null, msg,
      modificabile ? h("div", { class: "azioni" }, h("button", { class: "s", onclick: () => azione("rifiuta") }, "Rifiuta"),
        h("button", { class: "p", onclick: () => azione("approva") }, "Approva e programma")) : null);
  });
}

// Riepilogo mese su mese: mese in corso fino a oggi contro lo stesso numero di giorni del mese scorso.
async function riassuntoSocial(box) {
  try {
    const d = await api("GET", "/gestione/plancia/social");
    const v = (a, b) => { const x = variazione(a, b); return x ? h("span", { class: "bt-var" }, " " + x.testo) : null; };
    const T = d.totali;
    const kpi = (tit, n, prima, nota) => h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, tit), h("div", { class: "bt-num" }, String(n)), h("div", { class: "bt-sotto" }, "scorso mese: " + prima, v(n, prima)), nota ? h("div", { class: "bt-sotto" }, nota) : null);
    const mx = Math.max(1, ...d.canali.map(c => Math.max(c.creati, c.creati_prima)));
    const righe = d.canali.length ? d.canali.map(c => h("div", { class: "bt-confronto" }, h("div", { class: "bt-bl" }, c.canale),
      h("div", {}, h("div", { class: "bt-bt" }, h("i", { style: "width:" + (100 * c.creati / mx) + "%" })), h("div", { class: "bt-bt prima" }, h("i", { style: "width:" + (100 * c.creati_prima / mx) + "%" }))),
      h("div", { class: "bt-bv" }, c.creati + " / " + c.creati_prima))) : h("p", { class: "bt-sotto" }, "Ancora nessun post: appena gli agenti ne preparano, il confronto compare qui.");
    const prof = d.profili.length ? d.profili.map(p => h("tr", {}, h("td", {}, p.nome, h("span", { class: "bt-sotto" }, " · " + p.piattaforma)), h("td", {}, p.seguaci == null ? "—" : nIt(p.seguaci)),
      h("td", {}, p.seguaci != null && p.seguaci_prima != null ? (p.seguaci - p.seguaci_prima >= 0 ? "+" : "") + nIt(p.seguaci - p.seguaci_prima) : "—"), h("td", {}, p.visualizzazioni == null ? "—" : compatto(p.visualizzazioni)))) : null;
    riempi(box, [h("section", { class: "bt-griglia bt-kpis tre" }, kpi("Post preparati", T.creati, T.creati_prima), kpi("Post inviati", T.inviati, T.inviati_prima), h("article", { class: "bt-card bt-kpi" }, h("div", { class: "bt-cap" }, "Da approvare"), h("div", { class: "bt-num" }, String(d.da_approvare)), h("div", { class: "bt-sotto" }, "in attesa del tuo OK"))),
      h("section", { class: "bt-griglia" }, h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "Post per canale")), righe,
        h("div", { class: "bt-leg2" }, h("i", { style: "background:#1E8466" }), h("span", {}, "mese in corso"), h("i", { style: "background:#CFE3DA" }), h("span", {}, "stesso periodo del mese scorso"))),
        h("article", { class: "bt-card bt-s6" }, h("div", { class: "bt-testa" }, h("h2", {}, "I tuoi profili")), prof ? h("table", { class: "bt-tab" }, h("thead", {}, h("tr", {}, h("th", {}, "Profilo"), h("th", {}, "Seguaci"), h("th", {}, "4 sett."), h("th", {}, "Visualizzazioni"))), h("tbody", {}, prof))
          : h("p", { class: "bt-sotto" }, "Nessun profilo tuo monitorato. Aggiungilo in Impostazioni, Profili social monitorati, e qui vedrai seguaci e visualizzazioni a confronto.")),
      ),
      h("p", { class: "bt-nota" }, "Mi piace e commenti per singolo post dipendono da cosa la rete restituisce. Qui contano i post preparati dagli agenti e i dati dei profili monitorati.")]);
  } catch (e) { box.replaceChildren(avviso(e.message, "no")); }
}
