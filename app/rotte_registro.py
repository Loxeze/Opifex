"""Consultazione ed esportazione del registro delle decisioni (solo titolare)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from . import registro
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/registro")


def _righe(conn, tipo, utente_id, dal, al, q, limite):
    cond, par = [], []
    if tipo: cond.append("tipo = %s"); par.append(tipo)
    if utente_id: cond.append("utente_id = %s"); par.append(utente_id)
    if dal: cond.append("quando >= %s"); par.append(dal)
    if al: cond.append("quando < (%s::date + 1)"); par.append(al)
    if q:
        cond.append("(oggetto ILIKE %s OR nota ILIKE %s OR utente_nome ILIKE %s)")
        par += [f"%{q}%"] * 3
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return conn.execute(
        f"""SELECT id, quando, utente_id, utente_nome, utente_email, tipo, esito, oggetto_tipo, oggetto_id, oggetto, nota, dettagli
            FROM registro_decisioni {where} ORDER BY id DESC LIMIT %s""", (*par, limite)).fetchall()


@router.get("")
def elenco(tipo: str | None = Query(default=None, max_length=40), utente_id: int | None = None,
           dal: date | None = None, al: date | None = None, q: str | None = Query(default=None, max_length=100),
           limite: int = Query(default=200, ge=1, le=2000), formato: str = Query(default="json", pattern="^(json|csv)$"),
           _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        righe = _righe(conn, tipo, utente_id, dal, al, q, limite)
        persone = conn.execute("SELECT DISTINCT utente_id, utente_nome FROM registro_decisioni ORDER BY utente_nome").fetchall()
    if formato == "csv":
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["quando", "chi", "email", "tipo", "esito", "oggetto", "nota"])
        for r in righe:
            # le celle che iniziano con = + - @ sarebbero interpretate come formule dal foglio di calcolo
            sicuro = lambda s: ("'" + s) if s[:1] in ("=", "+", "-", "@") else s
            w.writerow([r["quando"].isoformat(), sicuro(r["utente_nome"]), r["utente_email"] or "", registro.TIPI.get(r["tipo"], r["tipo"]),
                        r["esito"], sicuro(r["oggetto"]), sicuro(r["nota"])])
        return Response(out.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="registro-decisioni.csv"'})
    return {"righe": righe, "tipi": registro.TIPI, "persone": persone}
