"""Controllo finale prima di consegnare: l'agente verifica i punti della checklist con una prova e li registra; un punto «no» blocca la consegna."""
import json

MAX_VOCI = 40


def registra(conn, agente_id: int, progetto_id, dati: dict) -> str:
    voci = []
    for v in (dati.get("voci") or [])[:MAX_VOCI]:
        if not isinstance(v, dict):
            continue
        esito = str(v.get("esito") or "").strip().lower()
        punto = " ".join(str(v.get("punto") or "").split())[:200]
        if esito not in ("ok", "no", "non_verificabile") or not punto:
            continue
        voci.append({"punto": punto, "esito": esito, "prova": " ".join(str(v.get("prova") or "").split())[:300]})
    if not voci:
        return "ERRORE: servono i punti del controllo, ognuno con punto, esito (ok, no, non_verificabile) e prova"
    senza_prova = [v["punto"] for v in voci if v["esito"] == "ok" and len(v["prova"]) < 5]
    no = [v for v in voci if v["esito"] == "no"]
    nv = [v for v in voci if v["esito"] == "non_verificabile"]
    esito = "bloccata" if (no or senza_prova) else "ok"
    conn.execute("INSERT INTO verifiche_consegna (agente_id, progetto_id, lavoro, esito, voci) VALUES (%s,%s,%s,%s,%s::jsonb)",
                 (agente_id, progetto_id, " ".join(str(dati.get("lavoro") or "").split())[:200], esito, json.dumps(voci)))
    if no:
        return "BLOCCATO: non consegnare. Da correggere: " + "; ".join(v["punto"] + (" (" + v["prova"] + ")" if v["prova"] else "") for v in no) + ". Correggi, rifai il lavoro e ripeti il controllo."
    if senza_prova:
        return "BLOCCATO: i punti «ok» vogliono una prova (file, tempo, numero): " + "; ".join(senza_prova) + ". Controllali davvero e ripeti."
    return "OK: controllo registrato." + (" Dichiara nella consegna cio' che non hai potuto verificare: " + "; ".join(v["punto"] for v in nv) + "." if nv else "")


def blocco_chiusura(conn, agente_id: int, progetto_id: int) -> str | None:
    """Se il progetto ha una buona pratica con checklist, chiudere una task richiede un controllo di consegna riuscito nelle ultime 24 ore (stesso progetto)."""
    p = conn.execute("SELECT nome, descrizione, obiettivo FROM progetti WHERE id = %s", (progetto_id,)).fetchone()
    if not p:
        return None
    from . import best_practice
    if not best_practice.cerca(conn, f"{p['nome']} {p['descrizione'] or ''} {p['obiettivo'] or ''}", 1, escludi_progetto=progetto_id):
        return None
    r = conn.execute("SELECT esito FROM verifiche_consegna WHERE progetto_id = %s AND creata_il > NOW() - interval '1 day' ORDER BY id DESC LIMIT 1", (progetto_id,)).fetchone()
    if r and r["esito"] == "ok":
        return None
    return ("BLOCCATO: per chiudere la task serve prima il controllo di consegna sulla checklist della buona pratica di questo progetto "
            "(best_practice_cerca, poi consegna_verifica con una prova per ogni punto)." + (" L'ultimo controllo e' stato bloccato: correggi e ripeti." if r else ""))
