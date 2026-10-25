"use strict";
// Service worker di Opifex: rende l'app installabile, mostra una pagina se manca la rete e riceve le notifiche push.
// Non conserva in cache dati dell'applicazione: ogni risposta dell'API arriva sempre dal server.
const VERSIONE = "opifex-sw-1";
self.addEventListener("install", (e) => { e.waitUntil(caches.open(VERSIONE).then((c) => c.add("offline.html")).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((k) => Promise.all(k.filter((x) => x !== VERSIONE).map((x) => caches.delete(x)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  if (e.request.mode === "navigate") e.respondWith(fetch(e.request).catch(() => caches.match("offline.html")));
});
self.addEventListener("push", (e) => {
  let d = { titolo: "Opifex", testo: "", url: "/app/" };
  try { d = { ...d, ...e.data.json() }; } catch (x) { /* messaggio senza dati */ }
  e.waitUntil(self.registration.showNotification(d.titolo, { body: d.testo, icon: "icona-192.png", badge: "icona-192.png", data: { url: d.url } }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/app/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((w) => { for (const c of w) { if ("focus" in c) return c.focus(); } return self.clients.openWindow(url); }));
});
