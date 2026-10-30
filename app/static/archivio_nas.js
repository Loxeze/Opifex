"use strict";
// Archivio NAS: connettore sul NAS, cartelle da catalogare, ricerca di foto e video con miniature, richieste di foto pronte e trascrizioni.
async function _blobArchivio(url, opzioni) {
  const r = await fetch(url, { ...(opzioni || {}), headers: { ...(token ? { Authorization: "Bearer " + token } : {}), ...((opzioni && opzioni.headers) || {}) } });
  if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) { /* ignora */ } throw new Error(typeof messaggioErrore === "function" ? messaggioErrore(d) : "Operazione non riuscita"); }
  return r;
}
function _salvaBlob(blob, nome) { const l = h("a", { href: URL.createObjectURL(blob), download: nome }); document.body.append(l); l.click(); l.remove(); }
function _miniaturaArchivio(fid, n) {
  const img = h("img", { alt: "", loading: "lazy", style: "width:112px;height:84px;object-fit:cover;border-radius:6px;background:rgba(128,128,128,.15)" });
  _blobArchivio("/gestione/archivio/file/" + fid + "/miniatura/" + n).then(r => r.blob()).then(b => { img.src = URL.createObjectURL(b); }).catch(() => {});
  return img;
}
const _durataArch = (s) => s ? Math.floor(s / 60) + "′" + String(Math.floor(s % 60)).padStart(2, "0") + "″" : "";

function vistaArchivio() {
  const msg = h("div"), stato = h("div"), cerca = h("div"), esiti = h("div"), dett = h("div");
  const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
  let dati = null;

  const nuovoNome = h("input", { maxlength: 60, placeholder: "Nome del NAS (es. UGREEN)", value: "NAS" });
  const creaConn = h("button", { class: "p", type: "button" }, "Crea il connettore e scarica il pacchetto");
  creaConn.addEventListener("click", async () => {
    try { const r = await _blobArchivio("/gestione/archivio/connettori", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome: nuovoNome.value }) });
      _salvaBlob(await r.blob(), "opifex-nas.zip"); msg.replaceChildren(avviso("Pacchetto scaricato: segui il file LEGGIMI.txt per installarlo sul NAS. La chiave è dentro il file docker-compose.yml: non condividerlo.", "ok")); carica();
    } catch (e) { err(e); }
  });

  const pacchetto = (c) => h("button", { class: "s", type: "button", title: "Genera una chiave nuova (la vecchia smette di funzionare) e scarica il pacchetto", onclick: async () => {
    try { const r = await _blobArchivio("/gestione/archivio/connettori/" + c.id + "/pacchetto", { method: "POST" }); _salvaBlob(await r.blob(), "opifex-nas.zip"); msg.replaceChildren(avviso("Pacchetto con chiave nuova scaricato: reinstallalo sul NAS.", "ok")); } catch (e) { err(e); } } }, "Nuovo pacchetto");

  const formCartella = () => {
    const conn = h("select", {}, dati.connettori.map(c => h("option", { value: c.id }, c.nome)));
    const nome = h("input", { maxlength: 80, placeholder: "Nome (es. Montarrenti video)" });
    const perc = h("input", { maxlength: 300, placeholder: "Percorso sotto /dati (es. Video/Montarrenti), vuoto = tutto" });
    const tipo = h("select", {}, [["misto", "Foto, video e documenti"], ["foto", "Solo foto"], ["video", "Solo video"]].map(([v, t]) => h("option", { value: v }, t)));
    const pref = h("input", { maxlength: 300, placeholder: "Percorso sul PC (es. \\\\UGREEN\\Video oppure Z:\\Video)" });
    const prog = h("select", {}, h("option", { value: "" }, "Progetto: riconosci dal nome delle cartelle"), dati.progetti.map(p => h("option", { value: p.id }, p.nome)));
    const descr = h("input", { type: "checkbox" }); descr.checked = true;
    const trasc = h("input", { type: "checkbox" });
    const ok = h("button", { class: "p", type: "button" }, "Aggiungi la cartella");
    ok.addEventListener("click", async () => {
      try { await api("POST", "/gestione/archivio/cartelle", { connettore_id: Number(conn.value), nome: nome.value, percorso: perc.value, tipo: tipo.value, prefisso_pc: pref.value, descrivi: descr.checked, trascrivi: trasc.checked, progetto_id: prog.value ? Number(prog.value) : null });
        nome.value = ""; perc.value = ""; msg.replaceChildren(avviso("Cartella aggiunta: il NAS la scansiona entro pochi minuti.", "ok")); carica(); } catch (e) { err(e); } });
    return h("details", { class: "carta" }, h("summary", {}, "+ Aggiungi una cartella da catalogare"),
      h("div", { style: "display:grid;gap:6px;margin-top:8px" }, conn, nome, perc, tipo, pref, prog,
        h("label", { class: "interruttore" }, descr, h("span", {}, "Descrivi le foto con l'intelligenza artificiale (costo basso, modello Haiku)")),
        h("label", { class: "interruttore" }, trasc, h("span", {}, "Trascrivi automaticamente il parlato dei video (costo Whisper, più lento)")), ok));
  };

  const rigaCartella = (k) => h("div", { class: "carta", style: "margin-top:8px" },
    h("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, h("b", {}, k.nome), h("span", { class: "etichetta" }, "/dati/" + (k.percorso || "")), h("span", { class: "etichetta " + (k.attiva ? "ok" : "no") }, k.attiva ? "attiva" : "sospesa"),
      k.errore ? h("span", { class: "etichetta no", title: k.errore }, "errore") : null),
    h("div", { class: "sotto" }, `${k.totale} file (${k.foto} foto, ${k.video} video, ${k.documenti || 0} documenti) · ${k.descritti} descritti · ${k.in_attesa} in attesa` + (k.senza_miniatura ? ` · ${k.senza_miniatura} senza miniatura` : "") + (k.errori ? ` · ${k.errori} con errore` : "") + (k.ultima_scansione ? " · ultima scansione " + new Date(k.ultima_scansione).toLocaleString("it-IT") : " · non ancora scansionata")),
    k.errore ? h("div", { class: "sotto" }, k.errore) : null,
    h("div", { class: "azioni" },
      h("button", { class: "s", type: "button", onclick: async () => { try { await api("PUT", "/gestione/archivio/cartelle/" + k.id, { attiva: !k.attiva }); carica(); } catch (e) { err(e); } } }, k.attiva ? "Sospendi" : "Riattiva"),
      h("button", { class: "s", type: "button", onclick: async () => { try { await api("PUT", "/gestione/archivio/cartelle/" + k.id, { trascrivi: !k.trascrivi }); carica(); } catch (e) { err(e); } } }, k.trascrivi ? "Non trascrivere più" : "Trascrivi i video"),
      h("button", { class: "s", type: "button", onclick: async () => { if (!confirm("Togliere la cartella dal catalogo? I file sul NAS non vengono toccati.")) return; try { await api("DELETE", "/gestione/archivio/cartelle/" + k.id); carica(); } catch (e) { err(e); } } }, "Rimuovi dal catalogo")));

  const impost = () => {
    const tetto = h("input", { type: "number", min: 0, style: "width:90px", value: dati.tetto_giorno });
    const ok = h("button", { class: "s", type: "button" }, "Salva");
    ok.addEventListener("click", async () => { try { await api("PUT", "/gestione/archivio/impostazioni", { tetto_giorno: Number(tetto.value) }); msg.replaceChildren(avviso("Salvato.", "ok")); } catch (e) { err(e); } });
    const adesso = h("button", { class: "s", type: "button", onclick: async () => { try { const r = await api("POST", "/gestione/archivio/analizza"); msg.replaceChildren(avviso(r.avviata ? "Descrizione avviata in sottofondo." : r.motivo, r.avviata ? "ok" : "avv")); setTimeout(carica, 4000); } catch (e) { err(e); } } }, "Descrivi adesso le foto in attesa");
    const riass = h("button", { class: "s", type: "button", onclick: async () => { try { const r = await api("POST", "/gestione/archivio/riassegna-progetti"); msg.replaceChildren(avviso(r.assegnati + " file collegati a un progetto.", "ok")); } catch (e) { err(e); } } }, "Riconosci di nuovo i progetti");
    return h("div", { class: "carta", style: "margin-top:8px" }, h("div", { class: "sotto" }, `Oggi descritti ${dati.descritti_oggi} file. Tetto giornaliero di descrizioni (tiene bassa la spesa):`), h("div", { class: "azioni" }, tetto, ok, adesso, riass),
      dati.ultimo_esito ? avviso("Ultimo problema nella descrizione: " + dati.ultimo_esito, "avv") : null,
      ...(dati.diagnosi || []).map(t => avviso(t, "avv")));
  };

  const q = h("input", { placeholder: "Cerca: soggetto, luogo, progetto, nome del file…", style: "flex:1;min-width:180px" });
  const tipoQ = h("select", {}, [["", "Tutto"], ["foto", "Foto"], ["video", "Video"], ["audio", "Audio"], ["documento", "Documenti"]].map(([v, t]) => h("option", { value: v }, t)));
  const oriQ = h("select", {}, [["", "Ogni formato"], ["verticale", "Verticale"], ["orizzontale", "Orizzontale"], ["quadrata", "Quadrata"]].map(([v, t]) => h("option", { value: v }, t)));
  const cercaBtn = h("button", { class: "p", type: "button" }, "Cerca");
  const lancia = async () => {
    try { const p = new URLSearchParams({ q: q.value, tipo: tipoQ.value, orientamento: oriQ.value });
      const r = await api("GET", "/gestione/archivio/cerca?" + p);
      riempi(esiti, r.length ? h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:8px" }, r.map(f =>
        h("div", { class: "carta", style: "cursor:pointer;padding:6px", tabindex: 0, role: "button", onclick: () => apriFile(f.id), onkeydown: (e) => { if (e.key === "Enter") apriFile(f.id); } },
          f.miniature ? _miniaturaArchivio(f.id, Math.min(1, f.miniature - 1)) : h("div", { class: "sotto", style: "height:84px" }, "nessuna anteprima"),
          h("div", { class: "sotto", style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap", title: f.rel }, f.nome),
          h("div", { class: "sotto" }, [f.tipo, _durataArch(f.durata_s), f.progetto].filter(Boolean).join(" · "))))) : h("div", { class: "sotto" }, "Nessun risultato."));
    } catch (e) { err(e); }
  };
  cercaBtn.addEventListener("click", lancia); q.addEventListener("keydown", (e) => { if (e.key === "Enter") lancia(); });

  async function apriFile(id) {
    try { const f = await api("GET", "/gestione/archivio/file/" + id);
      const richiedi = (tipo) => h("button", { class: "s", type: "button", onclick: async () => { try { const r = await api("POST", "/gestione/archivio/file/" + id + "/richiedi", { tipo, lato_max: 2400 }); msg.replaceChildren(avviso(r.gia_in_coda ? "Richiesta già in coda." : "Richiesta inviata al NAS: sarà pronta in pochi minuti.", "ok")); carica(); } catch (e) { err(e); } } },
        tipo === "foto" ? "Chiedi la foto per i post (2400 px)" : "Trascrivi il parlato");
      riempi(dett, h("div", { class: "carta", style: "margin-top:8px" },
        h("div", { style: "display:flex;gap:6px;flex-wrap:wrap" }, Array.from({ length: f.miniature }, (_, i) => _miniaturaArchivio(id, i))),
        h("h3", {}, f.nome), h("div", { class: "sotto" }, [f.tipo, f.larghezza ? f.larghezza + "×" + f.altezza : "", _durataArch(f.durata_s), f.codec, f.fotocamera, f.scattato_il ? new Date(f.scattato_il).toLocaleDateString("it-IT") : "", f.progetto ? "progetto " + f.progetto : ""].filter(Boolean).join(" · ")),
        h("p", {}, f.descrizione || "(non ancora descritto)"), f.etichette && f.etichette.length ? h("div", {}, f.etichette.map(t => h("span", { class: "etichetta" }, t))) : null,
        h("div", { class: "sotto" }, "Sul PC: ", h("code", {}, f.percorso_pc), " ", h("button", { class: "s", type: "button", onclick: () => { try { navigator.clipboard.writeText(f.percorso_pc); } catch (e) { /* ignora */ } } }, "Copia")),
        f.trascrizione ? h("details", {}, h("summary", {}, "Trascrizione"), h("div", { style: "white-space:pre-wrap;max-height:260px;overflow:auto" }, f.trascrizione)) : null,
        h("div", { class: "azioni" }, f.tipo === "foto" ? richiedi("foto") : richiedi("trascrizione"))));
      dett.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) { err(e); }
  }

  async function carica() {
    try { dati = await api("GET", "/gestione/archivio");
      riempi(stato, [
        h("p", { class: "aiuto" }, "Foto, video e documenti restano sul tuo NAS: a Opifex arrivano solo schede, miniature e il testo dei documenti (PDF, Word, Excel, PowerPoint, testo) per poterli cercare. Gli agenti dei reparti Contenuti e Social possono cercare nell'archivio e chiedere al NAS una foto pronta per un post."),
        dati.connettori.length ? dati.connettori.map(c => h("div", { class: "carta", style: "margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap" },
          h("b", {}, c.nome), h("span", { class: "etichetta " + (c.online ? "ok" : "no") }, c.online ? "online" : "non collegato"),
          h("span", { class: "sotto" }, c.ultimo_contatto ? "ultimo contatto " + new Date(c.ultimo_contatto).toLocaleString("it-IT") + (c.versione ? " · v" + c.versione : "") : "mai collegato"), pacchetto(c),
          h("button", { class: "s", type: "button", onclick: async () => { if (!confirm("Eliminare il connettore e il suo catalogo?")) return; try { await api("DELETE", "/gestione/archivio/connettori/" + c.id); carica(); } catch (e) { err(e); } } }, "Elimina"))) : h("div", { class: "sotto" }, "Nessun NAS collegato."),
        h("div", { class: "azioni" }, nuovoNome, creaConn),
        dati.connettori.length ? [formCartella(), dati.cartelle.map(rigaCartella), impost()] : null,
        dati.richieste.length ? h("details", { class: "carta", style: "margin-top:8px" }, h("summary", {}, "Ultime richieste al NAS (" + dati.richieste.length + ")"),
          dati.richieste.map(r => h("div", { class: "sotto" }, `${r.tipo} · ${r.nome} · ${r.stato}${r.agente ? " · chiesta da " + r.agente : ""}${r.errore ? " · " + r.errore : ""} `,
            r.scaricabile ? h("button", { class: "s", type: "button", onclick: async () => { try { const x = await _blobArchivio("/gestione/archivio/richieste/" + r.id + "/scarica"); _salvaBlob(await x.blob(), r.nome.replace(/\.[^.]+$/, "") + "_web.jpg"); } catch (e) { err(e); } } }, "Scarica") : null))) : null]);
      if (!cerca.childNodes.length) riempi(cerca, h("div", { class: "carta", style: "margin-top:12px" }, h("h3", {}, "Cerca nell'archivio"), h("div", { class: "azioni" }, q, tipoQ, oriQ, cercaBtn), esiti, dett));
    } catch (e) { err(e); }
  }
  carica();
  return [h("h2", {}, "Archivio NAS"), msg, stato, cerca];
}
