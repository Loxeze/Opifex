"use strict";
// Service worker dell'app vocale: la rende installabile. Nessun dato dell'applicazione viene conservato in cache.
const VERSIONE = "opifex-voce-1";
self.addEventListener("install", (e) => { e.waitUntil(caches.open(VERSIONE).then((c) => c.addAll(["./", "voce-app.css", "voce-app.js"])).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((k) => Promise.all(k.filter((x) => x !== VERSIONE).map((x) => caches.delete(x)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/v1/")) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
