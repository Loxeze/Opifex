"""Controllo delle dipendenze: una volta a settimana confronta le librerie in uso (requirements.txt) con il database pubblico delle vulnerabilita' OSV.
Se ne trova, avvisa Lorenzo con nome, versione e identificativo; non aggiorna nulla da solo."""
import json
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/dipendenze", tags=["dipendenze"])
OSV = "https://api.osv.dev/v1/querybatch"
GIORNI = 7


def librerie(percorso: Path | None = None) -> list[tuple[str, str]]:
    p = percorso or Path(__file__).resolve().parent.parent / "requirements.txt"
    out = []
    try:
        for riga in p.read_text(encoding="utf-8").splitlines():
            riga = riga.split("#")[0].strip()
            if "==" in riga:
                n, v = riga.split("==", 1)
                out.append((n.split("[")[0].strip(), v.strip()))
    except OSError:
        pass
    return out


def _interroga(lib: list[tuple[str, str]]) -> list[list[str]]:
    """Per ogni libreria, gli identificativi delle vulnerabilita' note. Solleva httpx.HTTPError se la rete non risponde."""
    corpo = {"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in lib]}
    r = httpx.post(OSV, json=corpo, timeout=30)
    r.raise_for_status()
    return [[x["id"] for x in (q.get("vulns") or [])] for q in r.json()["results"]]


def controlla(conn, percorso: Path | None = None) -> dict:
    lib = librerie(percorso)
    if not lib:
        return {"esito": "ok", "dettagli": [], "librerie": 0}
    try:
        ris = _interroga(lib)
    except Exception:  # noqa: BLE001 - nessuna rete o servizio fuori uso: riproveremo
        conn.execute("INSERT INTO controlli_dipendenze (esito, dettagli) VALUES ('non_raggiungibile', '[]')")
        return {"esito": "non_raggiungibile", "dettagli": [], "librerie": len(lib)}
    trovate = [{"libreria": n, "versione": v, "vulnerabilita": ids[:8]} for (n, v), ids in zip(lib, ris) if ids]
    esito = "vulnerabilita" if trovate else "ok"
    conn.execute("INSERT INTO controlli_dipendenze (esito, dettagli) VALUES (%s,%s)", (esito, json.dumps(trovate)))
    if trovate:
        elenco = "; ".join(f"{t['libreria']} {t['versione']} ({', '.join(t['vulnerabilita'][:3])})" for t in trovate[:6])
        conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, TRUE)",
                     (f"Controllo dipendenze: {len(trovate)} librerie con vulnerabilita' note - {elenco}. Aggiorna con la prossima versione di Opifex.",))
    return {"esito": esito, "dettagli": trovate, "librerie": len(lib)}


def da_fare(conn) -> bool:
    r = conn.execute("SELECT max(eseguito_il) AS u FROM controlli_dipendenze WHERE esito <> 'non_raggiungibile'").fetchone()
    if r["u"] is None:
        return True
    return (date.today() - r["u"].date()).days >= GIORNI


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        ult = conn.execute("SELECT eseguito_il, esito, dettagli FROM controlli_dipendenze ORDER BY id DESC LIMIT 1").fetchone()
        return {"ultimo": ult, "librerie": len(librerie())}


@router.post("/controlla")
def controlla_ora(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return controlla(conn)
