"""Cambio di massa: ogni agente passa al modello piu' economico che puo' davvero usare. Reversibile."""
from . import catalogo_modelli, registro

MARCA = "modello_economico_1_32"


def _imp(conn, k):
    r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (k,)).fetchone()
    return r["valore"] if r else None


def _serve_anthropic(conn, a) -> bool:
    """La ricerca web e la navigazione dei siti funzionano solo con i modelli Claude."""
    if a["accesso_web"]:
        return True
    return conn.execute("SELECT 1 FROM agenti_connessioni ac JOIN connessioni c ON c.id=ac.connessione_id AND c.stato='attiva' "
                        "JOIN accessi_siti s ON s.connessione_id=c.id WHERE ac.agente_id=%s LIMIT 1", (a["id"],)).fetchone() is not None


def piano(conn) -> list[dict]:
    """Per ogni agente: modello attuale e modello proposto (None se non c'e' nulla di adatto o e' gia' quello)."""
    out = []
    for a in conn.execute("SELECT id, nome, modello, fascia_dati_max, accesso_web FROM agenti ORDER BY nome").fetchall():
        sc = catalogo_modelli.scegli_per_dialogo(conn, {"fascia_dati_max": a["fascia_dati_max"], "accesso_web": _serve_anthropic(conn, a)})
        out.append({"id": a["id"], "nome": a["nome"], "attuale": a["modello"], "proposto": sc,
                    "cambia": bool(sc and sc != a["modello"])})
    return out


def applica(conn, utente=None) -> dict:
    p = piano(conn)
    n = 0
    for r in p:
        if r["cambia"]:
            conn.execute("UPDATE agenti SET modello_precedente = COALESCE(modello_precedente, modello), modello = %s WHERE id = %s", (r["proposto"], r["id"]))
            n += 1
    conn.execute("UPDATE agenti SET modello_dialogo = NULL WHERE modello_dialogo IS NOT NULL")
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_modello_automatico', 'true') ON CONFLICT (chiave) DO UPDATE SET valore = 'true'")
    if utente is not None:
        registro.registra(conn, utente, "modelli", "tutti gli agenti al modello economico", "Tutti gli agenti", dettagli={"agenti": n})
    return {"agenti_cambiati": n, "senza_scelta": [r["nome"] for r in p if not r["proposto"]], "piano": piano(conn)}


def ripristina(conn, utente=None) -> dict:
    n = conn.execute("UPDATE agenti SET modello = modello_precedente, modello_precedente = NULL WHERE modello_precedente IS NOT NULL").rowcount
    if utente is not None:
        registro.registra(conn, utente, "modelli", "modelli degli agenti ripristinati", "Tutti gli agenti", dettagli={"agenti": n})
    return {"agenti_ripristinati": n}


def una_volta(conn) -> int:
    """Alla prima partenza dopo l'aggiornamento 1.32.0: tutti gli agenti al modello economico. Non si ripete (le scelte successive restano)."""
    if _imp(conn, MARCA):
        return 0
    if not any(r["proposto"] for r in piano(conn)):
        return 0   # nessun fornitore pronto (chiavi non ancora inserite): riprovo alla prossima partenza
    n = applica(conn)["agenti_cambiati"]
    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s, 'fatto') ON CONFLICT (chiave) DO NOTHING", (MARCA,))
    if n:
        conn.execute("INSERT INTO notifiche (testo, urgente, critica) VALUES (%s, FALSE, FALSE)",
                     (f"Aggiornamento: {n} agenti ora usano il modello piu' economico adatto ai loro dati. In Impostazioni → Backup e costi puoi tornare ai modelli di prima.",))
    return n
