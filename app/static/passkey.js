// Accesso con impronta, volto o PIN del telefono (passkey). Le chiavi restano sul dispositivo: il server conserva solo la parte pubblica.
const Passkey = (() => {
  const supportato = !!(window.PublicKeyCredential && navigator.credentials && window.isSecureContext);
  const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const da64 = (s) => { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), (c) => c.charCodeAt(0)).buffer; };
  const spiega = (e) => (e && e.name === "NotAllowedError") ? new Error("Operazione annullata o scaduta") : e;

  async function registra(nome) {
    const o = await api("POST", "/v1/passkey/registra/opzioni");
    const pk = o.publicKey;
    pk.challenge = da64(pk.challenge); pk.user.id = da64(pk.user.id);
    pk.excludeCredentials = (pk.excludeCredentials || []).map((e) => ({ ...e, id: da64(e.id) }));
    let cred;
    try { cred = await navigator.credentials.create({ publicKey: pk }); } catch (e) { throw spiega(e); }
    return api("POST", "/v1/passkey/registra", { sfida: o.sfida, nome, client_data_json: b64u(cred.response.clientDataJSON), attestation_object: b64u(cred.response.attestationObject) });
  }

  async function accedi() {
    const o = await api("POST", "/v1/accesso/opzioni");
    const pk = o.publicKey; pk.challenge = da64(pk.challenge);
    let cred;
    try { cred = await navigator.credentials.get({ publicKey: pk }); } catch (e) { throw spiega(e); }
    const r = cred.response;
    return api("POST", "/v1/accesso", { sfida: o.sfida, credenziale_id: b64u(cred.rawId), client_data_json: b64u(r.clientDataJSON), authenticator_data: b64u(r.authenticatorData), firma: b64u(r.signature) });
  }

  // pulsante della schermata di accesso
  function pulsanteAccesso(msg) {
    if (!supportato) return null;
    return h("button", { class: "s", type: "button", onclick: async () => {
      msg.replaceChildren();
      try { await proseguiAccesso(await accedi()); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); }
    } }, "Entra con impronta o volto");
  }

  // sezione della pagina «Il mio account»
  function sezioneAccount() {
    const corpo = h("div");
    const msg = h("div");
    const nome = h("input", { type: "text", maxlength: 60, placeholder: "Es. Telefono di Lorenzo" });
    const carica = async () => {
      try {
        const el = await api("GET", "/v1/passkey");
        riempi(corpo, [
          el.length ? el.map((p) => h("div", { class: "carta" }, h("div", { class: "nome" }, p.nome),
            h("div", { class: "sotto" }, "Aggiunto il " + new Date(p.creata_il).toLocaleDateString("it-IT") + " · ultimo uso: " + (p.ultimo_uso ? new Date(p.ultimo_uso).toLocaleString("it-IT") : "mai")),
            h("div", { class: "azioni" }, h("button", { class: "s", onclick: async () => {
              if (!confirm("Togliere questo dispositivo?")) return;
              try { await api("DELETE", "/v1/passkey/" + p.id); carica(); } catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Togli")))) : h("p", { class: "aiuto" }, "Nessun dispositivo registrato."),
          supportato ? h("div", { class: "carta" }, h("label", {}, "Nome del dispositivo", nome),
            h("div", { class: "azioni" }, h("button", { class: "p", onclick: async () => {
              try { await registra(nome.value.trim() || "Telefono"); nome.value = ""; msg.replaceChildren(avviso("Dispositivo aggiunto: da ora puoi entrare con impronta o volto.", "ok")); carica(); }
              catch (e) { msg.replaceChildren(avviso(e.message, "no")); } } }, "Aggiungi questo dispositivo")))
            : avviso("Questo browser, o questo indirizzo non protetto, non permette l'accesso con impronta o volto.", "avv"),
          msg]);
      } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
    };
    carica();
    return [h("h3", {}, "Accesso con impronta o volto"), h("p", { class: "aiuto" }, "Serve all'assistente vocale: entri con l'impronta o il volto, senza password. Il collegamento resta valido alcune ore."), corpo];
  }
  return { supportato, registra, accedi, pulsanteAccesso, sezioneAccount };
})();
