"""Quando lavora un agente: trigger a orario, a evento e manuali.

Ogni trigger e' acceso solo da Lorenzo, ha un tetto di token per esecuzione e un massimo di esecuzioni al giorno. Le esecuzioni
innescate da altri agenti (consegne) hanno una profondita' massima, per evitare catene infinite. Tutto resta nel registro delle esecuzioni."""
import threading
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import connessione

SINCRONO = False   # nei collaudi si esegue nello stesso thread
FUSO = ZoneInfo("Europe/Rome")
EVENTI = ("documento_caricato", "task_assegnato", "consegna_ricevuta", "studio_concluso")
FREQUENZE = ("giornaliero", "settimanale", "ogni_ore")
MAX_PROFONDITA = 3
RITARDO_MAX_ORE = 6          # un'esecuzione a orario non parte oltre 6 ore dopo l'ora fissata
_ctx = threading.local()


class ErroreTrigger(Exception):
    pass


def profondita() -> int:
    return getattr(_ctx, "prof", 0)


def valida(d: dict) -> dict:
    """Controlla e normalizza i campi di un trigger (usato da creazione e modifica)."""
    nome = " ".join(str(d.get("nome") or "").split())
    compito = str(d.get("compito") or "").strip()
    if not 3 <= len(nome) <= 80:
        raise ErroreTrigger("Il nome deve essere tra 3 e 80 caratteri")
    if not 10 <= len(compito) <= 3000:
        raise ErroreTrigger("Il compito deve essere tra 10 e 3000 caratteri")
    tipo = d.get("tipo")
    if tipo not in ("orario", "evento", "manuale"):
        raise ErroreTrigger("Tipo di trigger non valido")
    r = {"nome": nome, "compito": compito, "tipo": tipo, "frequenza": None, "ora": None, "giorni": [], "ogni_ore": None, "evento": None, "parole": None,
         "max_token": int(d.get("max_token") or 2500), "max_al_giorno": int(d.get("max_al_giorno") or 3), "notifica": bool(d.get("notifica", True))}
    if not 500 <= r["max_token"] <= 8000:
        raise ErroreTrigger("Il tetto di token deve essere tra 500 e 8000")
    if not 1 <= r["max_al_giorno"] <= 24:
        raise ErroreTrigger("Le esecuzioni al giorno devono essere da 1 a 24")
    if tipo == "orario":
        if d.get("frequenza") not in FREQUENZE:
            raise ErroreTrigger("Scegli la frequenza: giornaliero, settimanale o ogni N ore")
        r["frequenza"] = d["frequenza"]
        if r["frequenza"] == "ogni_ore":
            try:
                r["ogni_ore"] = int(d.get("ogni_ore"))
            except (TypeError, ValueError):
                raise ErroreTrigger("Indica ogni quante ore (da 1 a 24)")
            if not 1 <= r["ogni_ore"] <= 24:
                raise ErroreTrigger("Ogni quante ore: da 1 a 24")
        else:
            try:
                hh, mm = str(d.get("ora") or "").split(":")[:2]
                r["ora"] = time(int(hh), int(mm))
            except (ValueError, TypeError):
                raise ErroreTrigger("Indica l'ora nel formato 07:30")
            if r["frequenza"] == "settimanale":
                g = sorted({int(x) for x in (d.get("giorni") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
                if not g:
                    raise ErroreTrigger("Scegli almeno un giorno della settimana")
                r["giorni"] = g
    elif tipo == "evento":
        if d.get("evento") not in EVENTI:
            raise ErroreTrigger("Evento non valido")
        r["evento"] = d["evento"]
        r["parole"] = " ".join(str(d.get("parole") or "").split())[:200] or None
    return r


def _dovuto(t: dict, adesso: datetime) -> bool:
    """True se un trigger a orario deve partire adesso."""
    ultimo = t["ultimo_run_il"]
    if t["frequenza"] == "ogni_ore":
        return ultimo is None or adesso - ultimo >= timedelta(hours=t["ogni_ore"])
    loc = adesso.astimezone(FUSO)
    if t["frequenza"] == "settimanale" and loc.weekday() not in (t["giorni"] or []):
        return False
    programmata = datetime.combine(loc.date(), t["ora"], FUSO)
    if loc < programmata or loc - programmata > timedelta(hours=RITARDO_MAX_ORE):
        return False
    return ultimo is None or ultimo.astimezone(FUSO) < programmata


def tick(conn, adesso: datetime | None = None) -> list[int]:
    """Chiamata ogni minuto: avvia i trigger a orario che sono dovuti. Restituisce gli id avviati."""
    adesso = adesso or datetime.now(timezone.utc)
    avviati = []
    for t in conn.execute("""SELECT t.* FROM trigger_agente t JOIN agenti a ON a.id = t.agente_id
                             WHERE t.attivo AND t.tipo = 'orario' AND a.attivo""").fetchall():
        if _dovuto(t, adesso):
            # segna subito: due tick consecutivi non devono lanciarlo due volte
            conn.execute("UPDATE trigger_agente SET ultimo_run_il = %s, ultimo_esito = 'in corso' WHERE id = %s", (adesso, t["id"]))
            conn.commit()
            avvia(t["id"], "orario programmato")
            avviati.append(t["id"])
    return avviati


def emetti(evento: str, testo: str = "", agente_id: int | None = None, contesto: str = "") -> list[int]:
    """Un avvenimento: avvia i trigger accesi su quell'evento (e, se indicato, solo quelli dell'agente) il cui filtro di parole coincide."""
    if evento not in EVENTI or profondita() >= MAX_PROFONDITA:
        return []
    avviati = []
    with connessione() as conn:
        for t in conn.execute("""SELECT t.id, t.parole, t.agente_id FROM trigger_agente t JOIN agenti a ON a.id = t.agente_id
                                 WHERE t.attivo AND t.tipo = 'evento' AND t.evento = %s AND a.attivo""", (evento,)).fetchall():
            if agente_id is not None and t["agente_id"] != agente_id:
                continue
            parole = [p.lower() for p in (t["parole"] or "").split()]
            if parole and not any(p in (testo or "").lower() for p in parole):
                continue
            avviati.append(t["id"])
    for tid in avviati:
        avvia(tid, f"evento: {evento}", (f"Cosa e' successo: {testo[:600]}\n{contesto}" if testo or contesto else ""))
    return avviati


def avvia(trigger_id: int, causa: str, contesto: str = ""):
    prof = profondita() + 1
    if SINCRONO:
        _lavora(trigger_id, causa, contesto, prof)
    else:
        threading.Thread(target=_lavora, args=(trigger_id, causa, contesto, prof), daemon=True).start()


def _registra(conn, t, causa, esito, token=0, risultato=None):
    conn.execute("INSERT INTO trigger_esecuzioni (trigger_id, agente_id, causa, esito, token, risultato) VALUES (%s,%s,%s,%s,%s,%s)",
                 (t["id"], t["agente_id"], causa[:200], esito, token, (risultato or "")[:6000] or None))
    conn.execute("UPDATE trigger_agente SET ultimo_run_il = GREATEST(COALESCE(ultimo_run_il, NOW()), NOW()), ultimo_esito = %s WHERE id = %s", (esito, t["id"]))


def _lavora(trigger_id: int, causa: str, contesto: str, prof: int):
    from .esecuzione import EsecuzioneBloccata, esegui_agente
    anteriore = profondita()
    _ctx.prof = prof
    try:
        with connessione() as conn:
            t = conn.execute("""SELECT t.*, a.nome AS agente FROM trigger_agente t JOIN agenti a ON a.id = t.agente_id WHERE t.id = %s""", (trigger_id,)).fetchone()
            if t is None:
                return
            if prof > MAX_PROFONDITA:
                _registra(conn, t, causa, "saltato", risultato="Catena di esecuzioni troppo lunga: fermata per sicurezza")
                return
            oggi = conn.execute("""SELECT count(*) AS n FROM trigger_esecuzioni WHERE trigger_id = %s AND esito <> 'saltato'
                                   AND creato_il > date_trunc('day', NOW() AT TIME ZONE 'Europe/Rome') AT TIME ZONE 'Europe/Rome'""", (trigger_id,)).fetchone()["n"]
            if oggi >= t["max_al_giorno"]:
                _registra(conn, t, causa, "saltato", risultato=f"Raggiunto il massimo di {t['max_al_giorno']} esecuzioni al giorno")
                return
            prompt = (f"ESECUZIONE AUTOMATICA «{t['nome']}» ({causa}).\nCompito: {t['compito']}\n{contesto}\n\n"
                      "Quando hai finito riassumi in massimo 10 righe cosa hai fatto e cosa hai trovato. Se trovi qualcosa che spetta a un altro manager, "
                      "passalo con passa_a. Non inventare dati: se non trovi nulla, dillo.")
            conn.commit()
        try:
            r = esegui_agente(t["agente_id"], prompt, "interno", None, max_token=t["max_token"])
            esito, testo, token = "ok", r["risposta"], r["token_input"] + r["token_output"]
        except EsecuzioneBloccata as e:
            esito, testo, token = "saltato", str(e), 0
        except Exception as e:  # noqa: BLE001 - l'errore va nel registro, non ferma il pianificatore
            esito, testo, token = "errore", str(e)[:300], 0
        with connessione() as conn:
            _registra(conn, t, causa, esito, token, testo)
            if t["notifica"] and esito != "saltato":
                conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, %s)",
                             (f"{t['agente']} ha eseguito «{t['nome']}»" + (": " + testo[:180] if esito == "ok" else " ma c'e' stato un errore."), esito == "errore"))
    finally:
        _ctx.prof = anteriore
