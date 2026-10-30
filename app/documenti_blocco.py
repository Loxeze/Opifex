"""Caricamento in blocco: tanti file insieme, oppure uno zip con una cartella intera. Lavora in sottofondo, un file alla volta: un file
illeggibile non ferma gli altri e finisce nell'elenco dei problemi. Stesso nome e stessa lunghezza di un documento gia' presente: saltato."""
import json
import threading
import zipfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from .db import connessione
from .documenti import ELENCO_FORMATI, ESTENSIONI, MAX_BYTE, FileNonLeggibile, dividi_in_pezzi, estrai_testo, lettore_visivo
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/documenti-blocco", tags=["documenti"])
SINCRONO = False
MAX_TOTALE = 400 * 1024 * 1024
MAX_VOCI_ZIP = 3000
MAX_ESPANSO = 2 * 1024 * 1024 * 1024
FASCE = ("pubblico", "interno", "riservato")


def avvia(conn, utente_id: int, files: list[tuple[str, bytes]], fascia: str, per_tutti: bool, agenti: list[int]) -> int:
    lavori = []   # (nome_visibile, byte)
    for nome, dati in files:
        if nome.lower().endswith(".zip"):
            try:
                z = zipfile.ZipFile(BytesIO(dati))
            except zipfile.BadZipFile:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{nome}: lo zip non e' valido") from None
            voci = [i for i in z.infolist() if not i.is_dir() and not any(p.startswith(".") or p == "__MACOSX" for p in i.filename.split("/"))]
            if len(voci) > MAX_VOCI_ZIP or sum(i.file_size for i in voci) > MAX_ESPANSO:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"{nome}: troppi file o troppo grande una volta aperto (massimo {MAX_VOCI_ZIP} file)")
            for i in voci:
                lavori.append((i.filename, (z, i.filename, i.file_size)))
        else:
            lavori.append((nome, dati))
    if not lavori:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nessun file da caricare")
    bid = conn.execute("INSERT INTO caricamenti_blocco (totale, creato_da_utente_id) VALUES (%s,%s) RETURNING id", (len(lavori), utente_id)).fetchone()["id"]
    conn.commit()
    if SINCRONO:
        _lavora(bid, lavori, fascia, per_tutti, agenti, utente_id)
    else:
        threading.Thread(target=_lavora, args=(bid, lavori, fascia, per_tutti, agenti, utente_id), daemon=True).start()
    return bid


def _lavora(bid: int, lavori: list, fascia: str, per_tutti: bool, agenti: list[int], utente_id: int):
    from .rotte_documenti import _assegna
    try:
        for nome, contenuto in lavori:
            base = nome.rsplit("/", 1)[-1][:200]
            problema = None
            try:
                if isinstance(contenuto, tuple):
                    z, interno, dim = contenuto
                    if dim > MAX_BYTE:
                        raise FileNonLeggibile("file troppo grande (massimo 15 MB)")
                    contenuto = z.read(interno)
                if not base.lower().endswith(ESTENSIONI):
                    problema = "formato non supportato"
                elif len(contenuto) > MAX_BYTE:
                    problema = "file troppo grande (massimo 15 MB)"
                else:
                    testo = estrai_testo(base, contenuto, lettore_visivo(fascia))
                    with connessione() as conn:
                        if conn.execute("SELECT 1 FROM documenti WHERE nome_file = %s AND caratteri = %s", (base, len(testo))).fetchone():
                            conn.execute("UPDATE caricamenti_blocco SET saltati = saltati + 1 WHERE id = %s", (bid,))
                            continue
                        did = conn.execute("INSERT INTO documenti (nome, nome_file, fascia_dati, per_tutti, caratteri, caricato_da) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                                           (base, base, fascia, per_tutti, len(testo), utente_id)).fetchone()["id"]
                        for i, p in enumerate(dividi_in_pezzi(testo)):
                            conn.execute("INSERT INTO pezzi_documenti (documento_id, ordine, testo) VALUES (%s,%s,%s)", (did, i, p))
                        if agenti:
                            _assegna(conn, did, agenti)
                        conn.execute("UPDATE caricamenti_blocco SET caricati = caricati + 1 WHERE id = %s", (bid,))
            except FileNonLeggibile as e:
                problema = str(e)
            except Exception as e:  # noqa: BLE001 - un file rotto non ferma gli altri
                problema = "errore imprevisto: " + str(e)[:120]
            if problema:
                with connessione() as conn:
                    conn.execute("UPDATE caricamenti_blocco SET saltati = saltati + 1, problemi = problemi || %s::jsonb WHERE id = %s",
                                 (json.dumps([{"file": base, "motivo": problema}]), bid))
        with connessione() as conn:
            conn.execute("UPDATE caricamenti_blocco SET stato = 'concluso' WHERE id = %s", (bid,))
            conn.execute("INSERT INTO registro_azioni (azione, dettagli, utente_id) VALUES ('documenti_blocco', %s::jsonb, %s)", (json.dumps({"caricamento": bid, "file": len(lavori)}), utente_id))
    except Exception as e:  # noqa: BLE001
        with connessione() as conn:
            conn.execute("UPDATE caricamenti_blocco SET stato = 'errore', problemi = problemi || %s::jsonb WHERE id = %s", (json.dumps([{"file": "-", "motivo": str(e)[:200]}]), bid))


@router.post("", status_code=202)
async def carica(file: list[UploadFile] = File(...), fascia_dati: str = Form("interno"), per_tutti: bool = Form(False), agenti: str = Form(""), u: dict = Depends(solo_titolare)):
    if fascia_dati not in FASCE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Livello di riservatezza non valido")
    try:
        ids = [int(x) for x in agenti.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elenco agenti non valido") from None
    files, tot = [], 0
    for f in file:
        dati = await f.read(MAX_TOTALE + 1)
        tot += len(dati)
        if tot > MAX_TOTALE:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Troppi dati in una volta (massimo 400 MB): dividi in piu' caricamenti")
        files.append(((f.filename or "documento").strip(), dati))
    def lavoro():
        with connessione() as conn:
            return avvia(conn, u["id"], files, fascia_dati, per_tutti, ids)
    return {"id": await run_in_threadpool(lavoro), "formati": ELENCO_FORMATI}


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute("SELECT id, stato, totale, caricati, saltati, problemi, creato_il FROM caricamenti_blocco ORDER BY id DESC LIMIT 8").fetchall()
