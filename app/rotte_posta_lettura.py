"""La posta dentro Opifex (solo titolare): da leggere (filtrata dal modello locale), situazioni, caselle da sfogliare, impostazioni del filtro."""
import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import posta_vaglio, registro, strumenti_posta
from .db import connessione
from .fornitori import ErroreFornitore
from .google import ErroreGoogle
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/posta-in", tags=["posta"])


def _riga(r: dict) -> dict:
    return {**r, "data": r["data"].isoformat() if r.get("data") else None}


@router.get("")
def da_leggere(tutte: bool = False, _: dict = Depends(solo_titolare)):
    in_corso = posta_vaglio.IN_CORSO.locked()   # prima dello stato: se il giro e' finito, il suo esito e' gia' scritto
    with connessione() as conn:
        cat = ("importante", "normale") if tutte else ("importante",)
        righe = conn.execute("""SELECT v.id, v.origine, v.casella_id, v.msg_id, v.casella, v.data, v.mittente, v.oggetto, v.categoria, v.urgenza,
                                       v.riassunto, v.motivo, v.situazione_id, s.titolo AS situazione
                                FROM posta_vaglio v LEFT JOIN posta_situazioni s ON s.id = v.situazione_id
                                WHERE NOT v.letta AND v.categoria = ANY(%s) ORDER BY v.urgenza DESC, v.data DESC NULLS LAST LIMIT 80""", (list(cat),)).fetchall()
        conteggi = {r["categoria"]: r["n"] for r in conn.execute(
            "SELECT categoria, count(*) AS n FROM posta_vaglio WHERE NOT letta AND data > NOW() - INTERVAL '14 days' GROUP BY categoria").fetchall()}
        try:
            q = json.loads(posta_vaglio._imp(conn, "posta_quadro", "") or "{}")
        except ValueError:
            q = {}
        return {"email": [_riga(r) for r in righe], "conteggi": conteggi, "stato": posta_vaglio.stato(conn), "quadro": q,
                "caselle": len(posta_vaglio.caselle(conn)), "modello": posta_vaglio.modello_locale(conn),
                "attivo": posta_vaglio.vaglio_attivo(conn), "in_corso": in_corso, "solo_locale": posta_vaglio.solo_locale(conn), "regole": posta_vaglio.regole(conn)}


@router.post("/{vid}/letta")
def segna_letta(vid: int, letta: bool = True, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("UPDATE posta_vaglio SET letta=%s WHERE id=%s RETURNING id", (letta, vid)).fetchone():
            raise HTTPException(404, "Email non trovata")
    return {"ok": True}


@router.post("/tutte-lette")
def tutte_lette(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        n = conn.execute("UPDATE posta_vaglio SET letta=TRUE WHERE NOT letta AND categoria IN ('importante','normale')").rowcount
    return {"segnate": n}


def _vaglia_dietro():
    try:
        with connessione() as conn:
            posta_vaglio.vaglia(conn, forza=True)
    except Exception as e:  # noqa: BLE001 - l'esito resta nello stato, la schermata lo mostra
        try:
            with connessione() as conn:
                posta_vaglio._segna_stato(conn, esito="non riuscito", errore=str(e)[:300])
        except Exception:  # noqa: BLE001
            pass
    finally:
        posta_vaglio.IN_CORSO.release()


@router.post("/vaglia")
def vaglia_ora(_: dict = Depends(solo_titolare)):
    """Parte subito e risponde subito: il modello locale puo' metterci minuti, la schermata segue lo stato.
    Se un giro e' gia' in corso (anche quello automatico), non ne parte un altro: si aspetta quello."""
    if not posta_vaglio.IN_CORSO.acquire(blocking=False):
        return {"in_corso": True, "gia": True}
    threading.Thread(target=_vaglia_dietro, daemon=True, name="filtro-posta").start()
    return {"in_corso": True}


@router.get("/situazioni")
def situazioni(chiuse: bool = False, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        sit = conn.execute("""SELECT s.id, s.titolo, s.interlocutori, s.riassunto, s.aperta, s.email_n, s.aggiornata_il,
                                     (SELECT count(*) FROM posta_vaglio v WHERE v.situazione_id = s.id AND NOT v.letta) AS da_leggere
                              FROM posta_situazioni s WHERE s.aperta OR %s ORDER BY s.aperta DESC, s.aggiornata_il DESC LIMIT 100""", (chiuse,)).fetchall()
        return [{**s, "aggiornata_il": s["aggiornata_il"].isoformat()} for s in sit]


@router.get("/situazioni/{sid}")
def situazione(sid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        s = conn.execute("SELECT * FROM posta_situazioni WHERE id=%s", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Situazione non trovata")
        em = conn.execute("""SELECT id, origine, casella_id, msg_id, casella, data, mittente, oggetto, riassunto, letta FROM posta_vaglio
                             WHERE situazione_id=%s ORDER BY data DESC NULLS LAST LIMIT 50""", (sid,)).fetchall()
        return {**s, "creata_il": s["creata_il"].isoformat(), "aggiornata_il": s["aggiornata_il"].isoformat(), "email": [_riga(e) for e in em]}


class ModificaSituazione(BaseModel):
    titolo: str | None = Field(default=None, min_length=1, max_length=120)
    aperta: bool | None = None


@router.put("/situazioni/{sid}")
def modifica_situazione(sid: int, d: ModificaSituazione, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if not conn.execute("""UPDATE posta_situazioni SET titolo=COALESCE(%s, titolo), aperta=COALESCE(%s, aperta) WHERE id=%s RETURNING id""",
                            (d.titolo, d.aperta, sid)).fetchone():
            raise HTTPException(404, "Situazione non trovata")
    return {"ok": True}


@router.post("/quadro")
def fai_quadro(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return {"testo": posta_vaglio.quadro(conn)}
        except ErroreFornitore as e:
            raise HTTPException(503, f"Il modello locale non e' disponibile: {e}") from None


@router.get("/caselle")
def caselle(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return posta_vaglio.caselle(conn)


def _origine(chiave: str) -> tuple[str, int]:
    o, _, i = chiave.partition("-")
    if o not in ("gmail", "imap") or not i.isdigit():
        raise HTTPException(400, "Casella non valida")
    return o, int(i)


@router.get("/caselle/{chiave}")
def sfoglia(chiave: str, cerca: str = "", giorni: int = 14, _: dict = Depends(solo_titolare)):
    o, cid = _origine(chiave)
    with connessione() as conn:
        try:
            el = posta_vaglio.recenti(conn, o, cid, 40, max(1, min(giorni, 90)), cerca[:200])
        except (ErroreGoogle, strumenti_posta.ErrorePosta) as e:
            raise HTTPException(502, str(e)) from None
        vaglio = {r["msg_id"]: r for r in conn.execute("SELECT msg_id, categoria, riassunto FROM posta_vaglio WHERE origine=%s AND casella_id=%s AND msg_id = ANY(%s)",
                                                       (o, cid, [e["id"] for e in el])).fetchall()}
    return [{"id": e["id"], "da": e["da"], "oggetto": e["oggetto"], "data": e["data"].isoformat() if e["data"] else None, "non_letta": e["non_letta"],
             "anteprima": e["anteprima"][:200], "categoria": (vaglio.get(e["id"]) or {}).get("categoria"), "riassunto": (vaglio.get(e["id"]) or {}).get("riassunto")} for e in el]


@router.get("/caselle/{chiave}/{msg_id}")
def apri(chiave: str, msg_id: str, u: dict = Depends(solo_titolare)):
    o, cid = _origine(chiave)
    with connessione() as conn:
        try:
            t = posta_vaglio.leggi(conn, o, cid, msg_id[:200])
        except (ErroreGoogle, strumenti_posta.ErrorePosta) as e:
            raise HTTPException(502, str(e)) from None
        if t.startswith("ERRORE"):
            raise HTTPException(404, t)
        conn.execute("UPDATE posta_vaglio SET letta=TRUE WHERE origine=%s AND casella_id=%s AND msg_id=%s", (o, cid, msg_id[:200]))
    return {"testo": t}


class Impostazioni(BaseModel):
    attivo: bool | None = None
    solo_locale: bool | None = None
    regole: str | None = Field(default=None, max_length=4000)


@router.put("/impostazioni")
def imposta(d: Impostazioni, u: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if d.attivo is not None:
            posta_vaglio._scrivi(conn, "posta_vaglio_attivo", "1" if d.attivo else "0")
        if d.solo_locale is not None:
            posta_vaglio._scrivi(conn, "posta_solo_locale", "1" if d.solo_locale else "0")
        if d.regole is not None:
            posta_vaglio._scrivi(conn, "posta_regole", d.regole.strip())
        registro.registra(conn, u, "impostazione", "filtro della posta aggiornato", "", "posta", None, "",
                          {"attivo": d.attivo, "solo_locale": d.solo_locale, "regole_cambiate": d.regole is not None})
    return {"ok": True}
