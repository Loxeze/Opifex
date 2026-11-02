"""Ponte con il computer di Lorenzo: l'app Archivio chiede a Opifex i lavori da fare sul PC (per ora il browser delle Finestre)
e consegna i risultati. Il PC si collega verso Opifex (nessuna porta da aprire); vale solo con l'accesso del titolare.
Il PC e' considerato collegato se ha chiesto lavori negli ultimi 40 secondi."""
import base64
import json
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/ponte", dependencies=[Depends(solo_titolare)])
VISTO_ENTRO = 40
ATTESA_RISPOSTA = 45


def stato_pc() -> dict:
    with connessione() as c:
        r = c.execute("SELECT EXTRACT(EPOCH FROM (NOW() - visto)) AS eta, capacita, destinazione FROM ponte_pc WHERE id = 1").fetchone()
    eta = r["eta"] if r else None
    return {"collegato": eta is not None and float(eta) < VISTO_ENTRO, "capacita": (r or {}).get("capacita") or {}, "destinazione": (r or {}).get("destinazione") or "server"}


def destinazione() -> str:
    return stato_pc()["destinazione"]


def esegui_pc(tipo: str, parametri: dict, attesa: int = ATTESA_RISPOSTA):
    """Mette un lavoro in coda per il PC e aspetta il risultato. Solleva ErroreFinestre se il PC non risponde."""
    from .finestre import ErroreFinestre
    if not stato_pc()["collegato"]:
        raise ErroreFinestre("Il computer non e' collegato: apri l'app Archivio sul PC e accedi a Opifex")
    with connessione() as c:
        c.execute("DELETE FROM ponte_lavori WHERE creato < NOW() - INTERVAL '5 minutes'")
        jid = c.execute("INSERT INTO ponte_lavori (tipo, parametri) VALUES (%s, %s::jsonb) RETURNING id", (tipo, json.dumps(parametri))).fetchone()["id"]
        c.commit()
    fine = time.time() + attesa
    while time.time() < fine:
        with connessione() as c:
            r = c.execute("SELECT stato, risultato, errore FROM ponte_lavori WHERE id = %s", (jid,)).fetchone()
        if r and r["stato"] == "finito":
            return _da_json(r["risultato"])
        if r and r["stato"] == "errore":
            raise ErroreFinestre(r["errore"] or "Operazione sul computer non riuscita")
        time.sleep(0.25)
    with connessione() as c:
        c.execute("UPDATE ponte_lavori SET stato='errore', errore='scaduto' WHERE id = %s AND stato IN ('coda','preso')", (jid,))
        c.commit()
    raise ErroreFinestre("Il computer non risponde: controlla che l'app Archivio sia aperta")


def _da_json(v):
    if isinstance(v, dict) and set(v) == {"_bytes"}:
        return base64.b64decode(v["_bytes"])
    if isinstance(v, dict) and set(v) == {"_valore"}:
        return v["_valore"]
    return v


class Risultato(BaseModel):
    ok: bool = True
    dati: object | None = None
    errore: str = Field(default="", max_length=500)


@router.get("/stato")
def stato():
    return stato_pc()


@router.get("/prossimo")
def prossimo(attesa: int = 20, finestre: bool = False):
    """Long polling: l'app sul PC aspetta qui un lavoro."""
    attesa = max(1, min(attesa, 25))
    with connessione() as c:
        c.execute("UPDATE ponte_pc SET visto = NOW(), capacita = %s::jsonb WHERE id = 1", (json.dumps({"finestre": bool(finestre)}),))
        c.commit()
    fine = time.time() + attesa
    while True:
        with connessione() as c:
            r = c.execute("""UPDATE ponte_lavori SET stato = 'preso' WHERE id = (
                               SELECT id FROM ponte_lavori WHERE stato = 'coda' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
                             RETURNING id, tipo, parametri""").fetchone()
            c.commit()
        if r:
            return {"id": r["id"], "tipo": r["tipo"], "parametri": r["parametri"]}
        if time.time() >= fine:
            return {"nessuno": True}
        time.sleep(0.3)


@router.post("/{jid}/risultato")
def risultato(jid: int, d: Risultato):
    with connessione() as c:
        n = c.execute("UPDATE ponte_lavori SET stato = %s, risultato = %s::jsonb, errore = %s, finito = NOW() WHERE id = %s AND stato = 'preso'",
                      ("finito" if d.ok else "errore", json.dumps(d.dati), d.errore or None, jid)).rowcount
        c.commit()
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavoro non trovato o gia' chiuso")
    return {"ok": True}
