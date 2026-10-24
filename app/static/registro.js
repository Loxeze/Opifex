"use strict";
// Registro delle decisioni: chi ha approvato, respinto o autorizzato cosa e quando.

function vistaRegistro() {
  const corpo = h("div");
  const fTipo = h("select", {}, h("option", { value: "" }, "Tutti i tipi"));
  const fChi = h("select", {}, h("option", { value: "" }, "Tutte le persone"));
  const dal = h("input", { type: "date" }), al = h("input", { type: "date" });
  const q = h("input", { type: "search", maxlength: 100, placeholder: "Cerca nel testo…" });
  let primo = true;
  const parametri = (extra) => {
    const p = new URLSearchParams();
    if (fTipo.value) p.set("tipo", fTipo.value);
    if (fChi.value) p.set("utente_id", fChi.value);
    if (dal.value) p.set("dal", dal.value);
    if (al.value) p.set("al", al.value);
    if (q.value.trim()) p.set("q", q.value.trim());
    if (extra) for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p.toString();
  };
  const carica = async () => {
    try {
      const d = await api("GET", "/gestione/registro?" + parametri());
      if (primo) {
        for (const [k, t] of Object.entries(d.tipi)) fTipo.append(h("option", { value: k }, t));
        for (const x of d.persone) if (x.utente_id) fChi.append(h("option", { value: x.utente_id }, x.utente_nome));
        primo = false;
      }
      riempi(corpo, d.righe.length ? d.righe.map(r => h("div", { class: "carta", style: "margin-bottom:8px" },
        h("div", { class: "nome" }, r.utente_nome + " — " + r.esito),
        h("div", { class: "sotto" }, new Date(r.quando).toLocaleString("it-IT") + " · " + (d.tipi[r.tipo] || r.tipo) + (r.utente_email ? " · " + r.utente_email : "")),
        r.oggetto ? h("div", { class: "risposta" }, r.oggetto) : null,
        r.nota ? h("div", { class: "sotto" }, "Nota: " + r.nota) : null))
        : h("p", { class: "sotto" }, "Nessuna decisione registrata con questi filtri."));
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  const esporta = async () => {
    try {
      const r = await fetch("/gestione/registro?" + parametri({ formato: "csv", limite: 2000 }), { headers: { Authorization: "Bearer " + token } });
      if (!r.ok) throw new Error("Esportazione non riuscita");
      const url = URL.createObjectURL(await r.blob());
      const a = h("a", { href: url, download: "registro-decisioni.csv" }); document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { corpo.prepend(avviso(e.message, "no")); }
  };
  [fTipo, fChi, dal, al].forEach(x => x.addEventListener("change", carica));
  q.addEventListener("input", () => { clearTimeout(stato.attesa); stato.attesa = setTimeout(carica, 300); });
  carica();
  return [h("h2", {}, "Registro decisioni"),
    h("p", { class: "aiuto" }, "Chi ha approvato, respinto o autorizzato cosa, e quando: proposte, fasi dei percorsi, post social, risposte agli agenti, task, garanzie e chiavi dei fornitori, collegamenti. Il registro si può solo leggere: nessuno può modificarlo o cancellarlo."),
    h("div", { class: "riga" }, h("label", {}, "Tipo", fTipo), h("label", {}, "Persona", fChi), h("label", {}, "Dal", dal), h("label", {}, "Al", al)),
    h("label", {}, "Cerca", q),
    h("div", { class: "azioni" }, h("button", { class: "s", onclick: esporta }, "Esporta CSV")),
    corpo];
}
