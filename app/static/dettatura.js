"use strict";
// Dettatura su ogni campo di testo: quando tocchi un campo compare un microfono accanto; parli e il testo entra nel campo.
// Usa lo stesso motore della chat (Voce): sul telefono la trascrizione passa dal server (piu' precisa), sul computer dal browser.
(() => {
  if (typeof Voce === "undefined" || !Voce.supportoDettatura) return;
  const NO_TIPI = new Set(["password", "email", "number", "url", "tel", "date", "datetime-local", "time", "month", "week", "file", "checkbox", "radio", "range", "color", "hidden", "button", "submit", "reset", "image"]);
  let campo = null, stato = "riposo", timerNota = null, ritardo = null;
  const b = document.createElement("button");
  b.type = "button"; b.className = "mic-campo"; b.hidden = true; b.textContent = "🎤"; b.setAttribute("aria-label", "Detta con la voce"); b.title = "Detta con la voce";
  const nota = document.createElement("div");
  nota.className = "mic-nota"; nota.hidden = true; nota.setAttribute("role", "status");
  document.body.append(b, nota);

  const idoneo = (el) => {
    if (!el || !el.tagName) return false;
    const t = el.tagName;
    if (t !== "TEXTAREA" && !(t === "INPUT" && !NO_TIPI.has((el.getAttribute("type") || "text").toLowerCase()))) return false;
    if (el.disabled || el.readOnly || el.hasAttribute("data-senza-voce") || el.getAttribute("autocomplete") === "one-time-code" || el.inputMode === "numeric") return false;
    const riga = el.closest(".chat-riga-invio");
    if (riga && riga.querySelector('button[title^="Detta"]')) return false;   // la chat ha gia' il suo microfono
    return el.getBoundingClientRect().width >= 120;
  };
  const posiziona = () => {
    if (!campo || b.hidden) return;
    const r = campo.getBoundingClientRect(), d = b.offsetWidth || 36;
    if (r.bottom < 0 || r.top > innerHeight || !r.width) { b.style.visibility = "hidden"; nota.hidden = true; return; }
    b.style.visibility = "visible";
    const alto = campo.tagName === "TEXTAREA" ? 6 : Math.max(0, (r.height - d) / 2);
    const y = Math.min(Math.max(r.top + alto, 4), innerHeight - d - 4), x = Math.min(r.right - d - 6, innerWidth - d - 4);
    b.style.top = y + "px"; b.style.left = x + "px";
    const larg = nota.offsetWidth || 240;
    nota.style.top = Math.max(4, y - nota.offsetHeight - 8) + "px"; nota.style.left = Math.max(4, Math.min(x + d - larg, innerWidth - larg - 4)) + "px";
  };
  const imposta = (s) => {
    stato = s;
    b.classList.toggle("ascolto", s === "ascolto"); b.classList.toggle("lavoro", s === "trascrivo");
    b.textContent = s === "ascolto" ? "⏹" : s === "trascrivo" ? "…" : "🎤";
    b.disabled = s === "trascrivo";
    b.title = s === "ascolto" ? "Tocca per fermare" : "Detta con la voce";
    if (s === "ascolto") mostraNota("Ti ascolto… tocca ⏹ quando hai finito", 0);
    else if (s === "trascrivo") mostraNota("Trascrivo…", 0);
    else if (!timerNota) nota.hidden = true;
  };
  const mostraNota = (t, ms = 7000) => {
    nota.textContent = t; nota.hidden = false; clearTimeout(timerNota); timerNota = null;
    if (ms) timerNota = setTimeout(() => { timerNota = null; if (stato === "riposo") nota.hidden = true; }, ms);
    posiziona();
  };
  const mostra = (el) => {
    clearTimeout(ritardo);
    if (campo && campo !== el) restituisci(campo);
    campo = el; b.hidden = false;
    if (!el.dataset.micPad) { el.dataset.micPad = el.style.paddingRight || "-"; el.style.paddingRight = "48px"; }
    posiziona();
  };
  const restituisci = (el) => { if (el && el.dataset.micPad) { el.style.paddingRight = el.dataset.micPad === "-" ? "" : el.dataset.micPad; delete el.dataset.micPad; } };
  const nascondi = () => { if (stato !== "riposo") return; restituisci(campo); b.hidden = true; nota.hidden = true; campo = null; };

  document.addEventListener("focusin", (e) => { if (idoneo(e.target)) mostra(e.target); else if (e.target !== b && stato === "riposo") nascondi(); });
  document.addEventListener("focusout", (e) => { if (e.target === campo) ritardo = setTimeout(() => { if (document.activeElement !== b && document.activeElement !== campo) nascondi(); }, 250); });
  ["scroll", "resize"].forEach(ev => addEventListener(ev, posiziona, true));
  document.addEventListener("input", posiziona, true);
  setInterval(posiziona, 500);
  // il tocco sul pulsante non deve togliere il fuoco dal campo
  b.addEventListener("mousedown", (e) => e.preventDefault());
  b.addEventListener("touchstart", (e) => e.preventDefault(), { passive: false });
  b.addEventListener("click", (e) => {
    e.preventDefault();
    if (!campo) return;
    if (Voce.inAscolto()) { Voce.viva = false; Voce.termina(); return; }
    Voce.viva = false;
    const bersaglio = campo;
    const fine = () => { bersaglio.dispatchEvent(new Event("input", { bubbles: true })); };
    const st = (s) => { if (s === null) imposta("riposo"); else if (s === "ascolto") imposta("ascolto"); else if (s === "trascrivo") imposta("trascrivo"); else if (s) { imposta("riposo"); mostraNota(s, 9000); } };
    if (Voce.modo === "server") { if (!Voce.registra(bersaglio, fine, st, "pubblico")) mostraNota("Questo browser non può registrare dal microfono."); }
    else if (!Voce.ascolta(bersaglio, fine, st)) mostraNota("Il tuo browser non supporta la dettatura vocale: usa Chrome, Edge o Safari.");
    bersaglio.focus({ preventScroll: true });
  });
})();
