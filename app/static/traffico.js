"use strict";
// Siti: traffico da Google Analytics (sola lettura). Riquadro in Plancia e pagina Comunicazione › Traffico dei siti (abbinamento alle imprese).

const _nS = (n) => n == null ? "—" : Number(n).toLocaleString("it-IT");
const _durataSito = (s) => !s ? "—" : s < 60 ? s + " s" : Math.floor(s / 60) + " min " + (s % 60 ? (s % 60) + " s" : "");

function riquadroSitiPlancia() {
  const el = h("article", { class: "bt-card mq-plancia si-plancia" }, h("div", { class: "bt-cap" }, "Siti a colpo d'occhio"), h("p", { class: "bt-sotto" }, "Carico…"));
  el.hidden = true;
  const ricarica = async () => {
    if (inPausa(el)) return;
    let d; try { d = await api("GET", "/gestione/analytics?giorni=30"); } catch (e) { el.hidden = true; return; }
    const attivi = d.siti.filter(s => s.attivo);
    if (!attivi.length) { el.hidden = true; return; }
    el.hidden = false;
    const max = Math.max(1, ...attivi.map(s => s.utenti));
    const riga = (s, i) => h("button", { class: "mq-riga", type: "button", onclick: () => { stato.sitoAperto = s.id; vai("traffico"); }, title: "Apri " + s.nome },
      h("span", { class: "mq-pos" }, String(i + 1)),
      h("span", { class: "mq-nome" }, h("i", { style: "background:" + (s.colore || "#8A6A2F") }), h("b", {}, s.nome)),
      h("span", { class: "mq-barra", "aria-hidden": "true" }, h("span", { style: "width:" + Math.round(100 * s.utenti / max) + "%;background:" + (s.colore || "#8A6A2F") })),
      h("span", { class: "mq-num" }, h("b", {}, _nS(s.utenti)), " visitatori ", _varM(s.var_utenti)),
      h("span", { class: "mq-dett" }, (s.impresa || "senza impresa") + " · " + _nS(s.visualizzazioni) + " pagine viste" + (s.fonti && s.fonti.length ? " · da " + s.fonti[0].fonte.toLowerCase() + " " + Math.round(100 * s.fonti[0].sessioni / Math.max(1, s.sessioni)) + "%" : "") + (s.errore ? " · ⚠ " + s.errore : "")));
    const t = d.totali;
    riempi(el, [
      h("div", { class: "bt-testa" }, h("div", { class: "bt-cap" }, "Siti a colpo d'occhio · ultimi 30 giorni (fino a ieri)"),
        h("button", { class: "s piccolo", type: "button", onclick: () => vai("traffico") }, "Apri")),
      h("div", { class: "mq-totali" }, [["visitatori", t.utenti], ["sessioni", t.sessioni], ["pagine viste", t.visualizzazioni]].map(([et, n]) => h("span", {}, h("b", {}, _nS(n)), " " + et))),
      d.imprese.length > 1 ? h("div", { class: "mq-totali" }, d.imprese.map(i => h("span", {}, h("i", { class: "si-pallino", style: "background:" + (i.colore || "#8A6A2F") }), i.impresa + " ", h("b", {}, _nS(i.utenti))))) : null,
      h("div", { class: "mq-classifica" }, attivi.slice(0, 8).map(riga))]);
  };
  return { el, ricarica };
}

function vistaTraffico() {
  const corpo = h("div", {}, h("p", { class: "sotto" }, "Carico…"));
  let giorni = 30;
  const carica = async () => {
    let d; try { d = await api("GET", "/gestione/analytics?giorni=" + giorni); } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); return; }
    const msg = h("div");
    const cerca = _btnCp("Cerca i siti su Analytics", async () => {
      try { const r = await api("POST", "/gestione/analytics/scopri"); msg.replaceChildren(avviso("Trovati " + r.siti + " siti" + (r.nuove ? " (" + r.nuove + " nuovi)" : "") + "." + (r.errori.length ? " Problemi: " + r.errori.join("; ") : ""), r.errori.length ? "avv" : "ok")); carica(); }
      catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    }, "p");
    const periodo = h("select", { class: "si-periodo", onchange: () => { giorni = Number(periodo.value); carica(); }, "aria-label": "Periodo" }, [[7, "7 giorni"], [30, "30 giorni"], [90, "90 giorni"], [365, "un anno"]].map(([v, t]) => { const o = h("option", { value: v }, t); if (v === giorni) o.selected = true; return o; }));
    const testa = [h("p", { class: "aiuto" }, "Il traffico dei siti delle tue imprese, da Google Analytics (sola lettura, numeri aggregati senza dati personali). Si aggiorna da solo ogni 6 ore; i dati arrivano fino a ieri. Abbina ogni sito alla sua impresa: così compare nel cruscotto e gli agenti possono usarlo."),
      h("div", { class: "azioni" }, cerca, periodo), msg];
    if (!d.collegato) {
      riempi(corpo, [...testa, avviso("Nessun account Google è collegato con Analytics. Vai in Impostazioni › Google, premi «Collega con Google» e spunta «Google Analytics: traffico dei siti». Nel progetto Google Cloud devono essere abilitate «Google Analytics Data API» e «Google Analytics Admin API».", "avv")]);
      return;
    }
    if (!d.siti.length) { riempi(corpo, [...testa, h("p", { class: "sotto" }, "Nessun sito ancora: premi «Cerca i siti su Analytics».")]); return; }
    const scheda = (s) => {
      const imp = h("select", { "aria-label": "Impresa di " + s.nome }, [h("option", { value: "" }, "— nessuna impresa —")].concat(d.aziende.map(z => { const o = h("option", { value: z.id }, z.nome); if (z.id === s.azienda_id) o.selected = true; return o; })));
      imp.onchange = async () => { try { await api("PUT", "/gestione/analytics/siti/" + s.id, { azienda_id: imp.value ? Number(imp.value) : null }); carica(); } catch (e) { alert(e.message); } };
      const att = h("input", { type: "checkbox" }); att.checked = s.attivo;
      att.onchange = async () => { try { await api("PUT", "/gestione/analytics/siti/" + s.id, { attivo: att.checked }); carica(); } catch (e) { alert(e.message); } };
      const esito = h("div");
      const agg = h("button", { class: "s piccolo", type: "button" }, "Aggiorna ora");
      agg.onclick = async () => { agg.disabled = true; try { await api("POST", "/gestione/analytics/siti/" + s.id + "/aggiorna"); carica(); } catch (e) { esito.replaceChildren(avviso(e.message, "no")); agg.disabled = false; } };
      return h("div", { class: "carta mq-marchio" + (stato.sitoAperto === s.id ? " aperto" : ""), id: "sito-" + s.id },
        h("div", { class: "mq-titolo" }, h("i", { style: "background:" + (s.colore || "#8A6A2F") }), h("h3", {}, s.nome), s.indirizzo ? h("a", { href: s.indirizzo, target: "_blank", rel: "noopener", class: "sotto" }, s.indirizzo.replace(/^https?:\/\//, "")) : null),
        s.attivo ? h("div", { class: "mq-numeri" }, [["visitatori", _nS(s.utenti), s.var_utenti], ["nuovi", _nS(s.nuovi_utenti)], ["sessioni", _nS(s.sessioni), s.var_sessioni], ["pagine viste", _nS(s.visualizzazioni), s.var_visualizzazioni], ["durata media", _durataSito(s.durata_media)]]
          .map(([et, v, vr]) => h("div", { class: "pb-tessera" }, h("div", { class: "sotto" }, et), h("b", {}, v, " ", vr !== undefined ? _varM(vr) : null)))) : h("p", { class: "sotto" }, "Non seguito: i numeri non si scaricano."),
        s.attivo && s.andamento && s.andamento.some(x => x) ? h("div", { class: "si-andamento" }, h("span", { class: "sotto" }, "Sessioni al giorno"), sparkline(s.andamento, s.colore || "#8A6A2F")) : null,
        s.attivo && s.fonti && s.fonti.length ? h("div", { class: "sotto" }, h("b", {}, "Da dove arrivano: "), s.fonti.map(f => f.fonte + " " + Math.round(100 * f.sessioni / Math.max(1, s.sessioni)) + "%").join(" · ")) : null,
        s.attivo && s.pagine && s.pagine.length ? h("div", { class: "sotto" }, h("b", {}, "Pagine più lette (30 gg): "), s.pagine.map(p => (p.titolo || p.pagina) + " (" + _nS(p.visualizzazioni) + ")").join(" · ")) : null,
        h("div", { class: "azioni", style: "align-items:center" }, h("label", { class: "sotto" }, "Impresa ", imp), h("label", { class: "spunta" }, att, h("span", {}, "Seguilo")), agg,
          h("span", { class: "sotto" }, s.scaricato_il ? "Aggiornato " + new Date(s.scaricato_il).toLocaleString("it-IT") : "Mai scaricato")),
        s.errore ? avviso(s.errore, "no") : null, esito);
    };
    riempi(corpo, [...testa,
      h("div", { class: "mq-totali" }, [["visitatori", d.totali.utenti], ["sessioni", d.totali.sessioni], ["pagine viste", d.totali.visualizzazioni]].map(([et, n]) => h("span", {}, h("b", {}, _nS(n)), " " + et)), h("span", {}, "dal " + new Date(d.dal).toLocaleDateString("it-IT") + " al " + new Date(d.al).toLocaleDateString("it-IT"))),
      d.siti.map(scheda)]);
    if (stato.sitoAperto) { const x = document.getElementById("sito-" + stato.sitoAperto); if (x) x.scrollIntoView({ block: "start" }); stato.sitoAperto = null; }
  };
  carica();
  return [h("h2", {}, "Traffico dei siti"), corpo];
}
