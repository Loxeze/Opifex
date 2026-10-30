"""Preferenze personali di ogni utente (aspetto e disposizione dei pannelli). Valori controllati: nulla di libero finisce nel database."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .db import connessione
from .permessi import utente_corrente

router = APIRouter(prefix="/account/preferenze", tags=["preferenze"])

PANNELLI = {"aurora", "decisioni", "costi", "task", "squadra", "briefing"}
STILI, SFONDI, PERIODI, DISPOSIZIONI = {"vetro", "classico"}, {"alba", "notte", "oceano", "arte"}, {"7", "14", "30"}, {"operativo", "focus", "panorama", "personale"}


def _numero(v, minimo, massimo):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not minimo <= v <= massimo:
        raise ValueError
    return round(float(v), 3)


def _scelta(insieme):
    def f(v):
        if v not in insieme:
            raise ValueError
        return v
    return f


def _layout(v):
    """{pannello: [x, y, larghezza, altezza, aperto, ancorato]} per al massimo sei pannelli noti."""
    if not isinstance(v, dict) or not v or len(v) > len(PANNELLI):
        raise ValueError
    out = {}
    for k, a in v.items():
        if k not in PANNELLI or not isinstance(a, list) or len(a) != 6:
            raise ValueError
        out[k] = [_numero(a[0], 0, 6000), _numero(a[1], 0, 6000), _numero(a[2], 200, 3000), _numero(a[3], 100, 3000), int(bool(a[4])), int(bool(a[5]))]
    return out


CHIAVI = {"stile": _scelta(STILI), "sfondo": _scelta(SFONDI), "vetro": lambda v: _numero(v, 0.3, 0.75),
          "plancia_periodo": _scelta(PERIODI), "plancia_disposizione": _scelta(DISPOSIZIONI), "plancia_layout": _layout}


class Valore(BaseModel):
    valore: object


@router.get("")
def leggi(u: dict = Depends(utente_corrente)):
    with connessione() as conn:
        return {r["chiave"]: r["valore"] for r in conn.execute("SELECT chiave, valore FROM preferenze_utente WHERE utente_id=%s", (u["id"],)).fetchall()}


@router.put("/{chiave}")
def scrivi(chiave: str, d: Valore, u: dict = Depends(utente_corrente)):
    if chiave not in CHIAVI:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preferenza sconosciuta")
    try:
        v = CHIAVI[chiave](d.valore)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Valore non valido") from None
    import json
    with connessione() as conn:
        conn.execute("""INSERT INTO preferenze_utente (utente_id, chiave, valore) VALUES (%s,%s,%s::jsonb)
                        ON CONFLICT (utente_id, chiave) DO UPDATE SET valore = EXCLUDED.valore, aggiornata_il = NOW()""", (u["id"], chiave, json.dumps(v)))
    return {"chiave": chiave, "valore": v}


@router.delete("/{chiave}")
def azzera(chiave: str, u: dict = Depends(utente_corrente)):
    if chiave not in CHIAVI:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preferenza sconosciuta")
    with connessione() as conn:
        conn.execute("DELETE FROM preferenze_utente WHERE utente_id=%s AND chiave=%s", (u["id"], chiave))
    return {"azzerata": True}
