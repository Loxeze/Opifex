"""Scatola nera: per ogni lavoro di un agente resta la traccia di che cosa e' successo, in ordine: chiamate al modello (con token e tempi), strumenti usati
(con dati in ingresso e risultato), adattamenti del prompt, passaggi a Claude, schede del lavoro a schede, colleghi interpellati (come tracce figlie), errori.
Serve a capire perche' un agente ha sbagliato, dove si spendono tempo e denaro, e se una modifica ha migliorato le cose. Non chiama mai un modello: costo zero.
Una scrittura fallita non ferma mai il lavoro. Le tracce restano 30 giorni."""
import contextvars
import json
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/scatola-nera", tags=["scatola nera"])
TRACCIA: contextvars.ContextVar = contextvars.ContextVar("traccia_corrente", default=None)
GIORNI = 30
MAX_PASSI = 400
LUNG = 2500


def _t(v, n: int = LUNG) -> str | None:
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + f" […altri {len(s) - n} caratteri]"


def apri(agente_id: int, richiesta: str, utente_id=None, origine: str = "") -> int | None:
    try:
        with connessione() as conn:
            return conn.execute("INSERT INTO tracce (padre_id, agente_id, utente_id, origine, richiesta) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                                (TRACCIA.get(), agente_id, utente_id, (origine or "")[:60], _t(richiesta, 6000))).fetchone()["id"]
    except Exception:  # noqa: BLE001
        return None


def chiudi(tid: int | None, *, risposta: str = "", errore: str = "", token_input: int = 0, token_output: int = 0) -> None:
    if not tid:
        return
    try:
        with connessione() as conn:
            conn.execute("""UPDATE tracce t SET stato = %s, risposta = %s, errore = %s, token_input = %s, token_output = %s, finita_il = clock_timestamp(),
                                   costo = (SELECT sum(c.costo_stimato) FROM costi_api c WHERE c.agente_id = t.agente_id AND c.creato_il BETWEEN t.iniziata_il AND clock_timestamp())
                            WHERE id = %s""", ("errore" if errore else "riuscita", _t(risposta, 6000), _t(errore, 600), int(token_input or 0), int(token_output or 0), tid))
    except Exception:  # noqa: BLE001
        pass


def passo(tipo: str, nome: str = "", ingresso=None, uscita=None, *, token_input=None, token_output=None, ms=None) -> None:
    tid = TRACCIA.get()
    if not tid:
        return
    try:
        with connessione() as conn:
            r = conn.execute("UPDATE tracce SET passi = passi + 1 WHERE id = %s AND passi < %s RETURNING passi", (tid, MAX_PASSI)).fetchone()
            if r is None:
                return
            conn.execute("INSERT INTO tracce_passi (traccia_id, tipo, nome, ingresso, uscita, token_input, token_output, millisecondi) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (tid, tipo, (nome or "")[:120], _t(ingresso), _t(uscita), token_input, token_output, ms))
    except Exception:  # noqa: BLE001
        pass


class Cronometro:
    """with Cronometro() as c: ... poi c.ms"""
    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *a):
        self.ms = int((time.monotonic() - self.t0) * 1000)
        return False


def pulisci(conn) -> None:
    conn.execute("DELETE FROM tracce WHERE iniziata_il < NOW() - make_interval(days => %s)", (GIORNI,))


# ---------- rotte ----------
@router.get("")
def elenco(agente_id: int | None = None, solo_errori: bool = False, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        cond, par = ["t.padre_id IS NULL"], []
        if agente_id:
            cond.append("t.agente_id = %s"); par.append(agente_id)
        if solo_errori:
            cond.append("t.stato = 'errore'")
        righe = conn.execute(f"""SELECT t.id, t.agente_id, a.nome AS agente, t.origine, left(t.richiesta, 200) AS richiesta, t.stato, t.token_input, t.token_output, t.costo::float AS costo,
                                        t.passi, t.voto, t.iniziata_il, EXTRACT(EPOCH FROM (COALESCE(t.finita_il, clock_timestamp()) - t.iniziata_il))::float AS secondi,
                                        (SELECT count(*) FROM tracce f WHERE f.padre_id = t.id) AS figlie
                                 FROM tracce t LEFT JOIN agenti a ON a.id = t.agente_id WHERE {' AND '.join(cond)} ORDER BY t.id DESC LIMIT 60""", par).fetchall()
        oggi = conn.execute("""SELECT count(*) AS n, count(*) FILTER (WHERE stato = 'errore') AS errori, COALESCE(sum(costo),0)::float AS costo,
                                      COALESCE(avg(EXTRACT(EPOCH FROM (finita_il - iniziata_il))) FILTER (WHERE finita_il IS NOT NULL), 0)::float AS secondi_medi
                               FROM tracce WHERE padre_id IS NULL AND iniziata_il >= date_trunc('day', now())""").fetchone()
        return {"tracce": righe, "oggi": oggi}


def _albero(conn, tid: int, prof: int = 0) -> dict | None:
    t = conn.execute("""SELECT t.*, t.costo::float AS costo, a.nome AS agente, EXTRACT(EPOCH FROM (COALESCE(t.finita_il, clock_timestamp()) - t.iniziata_il))::float AS secondi
                        FROM tracce t LEFT JOIN agenti a ON a.id = t.agente_id WHERE t.id = %s""", (tid,)).fetchone()
    if t is None:
        return None
    t = dict(t)
    t["passi_dettaglio"] = conn.execute("SELECT id, tipo, nome, ingresso, uscita, token_input, token_output, millisecondi, creato_il FROM tracce_passi WHERE traccia_id = %s ORDER BY id", (tid,)).fetchall()
    figlie = conn.execute("SELECT id FROM tracce WHERE padre_id = %s ORDER BY id", (tid,)).fetchall()
    t["figlie"] = [x for x in (_albero(conn, f["id"], prof + 1) for f in figlie) if x] if prof < 4 else []
    return t


@router.get("/{tid}")
def dettaglio(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        t = _albero(conn, tid)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Traccia inesistente o gia' cancellata")
        return t


class Voto(BaseModel):
    voto: int = Field(ge=-1, le=1)


@router.put("/{tid}/voto")
def vota(tid: int, d: Voto, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        if conn.execute("UPDATE tracce SET voto = %s WHERE id = %s RETURNING id", (d.voto or None, tid)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Traccia inesistente")
    return {"voto": d.voto}
