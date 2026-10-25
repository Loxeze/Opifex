"use strict";
// App su smartphone e tablet: installazione con QR code e notifiche push. Il service worker rende l'app installabile.

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("sw.js").catch(() => { /* senza service worker l'app funziona comunque dal browser */ }); });
}

function chiaveBinaria(b64) {
  const p = "=".repeat((4 - b64.length % 4) % 4), s = atob((b64 + p).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...s].map(c => c.charCodeAt(0)));
}
function aB64u(buf) { return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
function nomeDispositivo() {
  const u = navigator.userAgent;
  const so = /iPhone/.test(u) ? "iPhone" : /iPad/.test(u) ? "iPad" : /Android/.test(u) ? "Android" : /Windows/.test(u) ? "Windows" : /Mac/.test(u) ? "Mac" : "Dispositivo";
  const br = /Edg\//.test(u) ? "Edge" : /Firefox\//.test(u) ? "Firefox" : /Chrome\//.test(u) ? "Chrome" : /Safari\//.test(u) ? "Safari" : "";
  return (so + " " + br).trim();
}

async function attivaNotifiche() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) throw new Error("Questo browser non supporta le notifiche. Su iPhone e iPad prima aggiungi l'app alla schermata Home.");
  const permesso = await Notification.requestPermission();
  if (permesso !== "granted") throw new Error("Hai negato il permesso alle notifiche: puoi riattivarlo dalle impostazioni del browser.");
  const reg = await navigator.serviceWorker.ready;
  const { chiave } = await api("GET", "/pwa/chiave");
  const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: chiaveBinaria(chiave) });
  const j = sub.toJSON();
  await api("POST", "/pwa/iscrivi", { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, dispositivo: nomeDispositivo() });
}

function vistaApp() {
  const corpo = h("div"), msg = h("div");
  const carica = async () => {
    try {
      const [inv, dis] = await Promise.all([api("GET", "/gestione/app/invito"), api("GET", "/pwa/dispositivi")]);
      const svg = h("div", { class: "qr", role: "img", "aria-label": "QR code per aprire Opifex" });
      svg.innerHTML = inv.svg;   // SVG generato dal nostro server
      const url = h("input", { type: "text", value: inv.personalizzato ? inv.url.replace(/\/app\/$/, "") : "", placeholder: "https://app.opifex.space", maxlength: 200 });
      const err = (e) => msg.replaceChildren(avviso(e.message, "no"));
      riempi(corpo, [
        h("p", { class: "aiuto" }, "Opifex funziona su smartphone e tablet come una vera app: si installa dal browser, senza store. Inquadra il QR con la fotocamera del telefono, apri il collegamento ed esegui i passi qui sotto."),
        h("div", { class: "riga", style: "align-items:flex-start" },
          h("div", { class: "carta", style: "flex:0 0 auto;text-align:center" }, svg, h("div", { class: "sotto", style: "word-break:break-all;max-width:240px" }, inv.url)),
          h("div", { class: "carta", style: "flex:1 1 300px" },
            h("div", { class: "nome" }, "Come si installa"),
            h("p", { class: "sotto" }, h("b", {}, "iPhone / iPad (Safari): "), "tocca Condividi, poi «Aggiungi alla schermata Home»."),
            h("p", { class: "sotto" }, h("b", {}, "Android (Chrome): "), "tocca i tre puntini, poi «Installa app» (o «Aggiungi a schermata Home»)."),
            h("p", { class: "sotto" }, h("b", {}, "Computer (Chrome / Edge): "), "icona di installazione nella barra dell'indirizzo."),
            h("p", { class: "sotto" }, "Accedi con le tue credenziali di sempre: i collaboratori possono usare lo stesso QR."))),
        h("div", { class: "carta" }, h("div", { class: "nome" }, "Indirizzo pubblico"),
          h("p", { class: "aiuto" }, "Se il QR mostra un indirizzo interno o sbagliato, scrivi qui l'indirizzo con cui apri Opifex da fuori (vuoto = automatico)."),
          h("div", { class: "riga" }, url, h("button", { class: "s", style: "align-self:flex-end;flex:0 0 auto", onclick: async () => { try { await api("PUT", "/gestione/app/url", { url: url.value }); await carica(); } catch (e) { err(e); } } }, "Salva"))),
        h("h3", {}, "Notifiche sul telefono"),
        h("div", { class: "carta" },
          h("p", { class: "aiuto" }, "Ricevi sul dispositivo gli avvisi di Opifex (richieste da approvare, task, promemoria del CRM). Su iPhone e iPad le notifiche funzionano solo dopo aver aggiunto l'app alla schermata Home."),
          h("div", { class: "azioni" },
            h("button", { class: "p", onclick: async () => { try { await attivaNotifiche(); msg.replaceChildren(avviso("Notifiche attivate su questo dispositivo.", "ok")); await carica(); } catch (e) { err(e); } } }, "Attiva su questo dispositivo"),
            h("button", { class: "s", onclick: async () => { try { const r = await api("POST", "/pwa/prova"); msg.replaceChildren(avviso(r.raggiunti ? "Notifica di prova inviata a " + r.raggiunti + " dispositivi." : "Nessun dispositivo raggiunto: attiva prima le notifiche.", r.raggiunti ? "ok" : "avv")); } catch (e) { err(e); } } }, "Invia una notifica di prova")),
          dis.dispositivi.length ? h("div", {}, h("div", { class: "sotto", style: "margin-top:12px" }, "Dispositivi collegati:"), dis.dispositivi.map(x => h("div", { class: "sotto" }, "📱 " + (x.dispositivo || "Dispositivo") + " · dal " + new Date(x.creata_il).toLocaleDateString("it-IT") + " ",
            h("button", { class: "s", style: "padding:2px 10px", onclick: async () => { try { await api("POST", "/pwa/disiscrivi", { endpoint: x.endpoint }); await carica(); } catch (e) { err(e); } } }, "Scollega")))) : h("p", { class: "sotto" }, "Nessun dispositivo collegato."),
          msg)]);
    } catch (e) { corpo.replaceChildren(avviso(e.message, "no")); }
  };
  carica();
  return [h("h2", {}, "App su smartphone"), corpo];
}
