"""Rotte per parlare con gli agenti e per le proposte di sviluppo dell'Architetto tecnico."""
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from . import chat_coda, registro
from .db import connessione
from .documenti import ELENCO_FORMATI, ESTENSIONI, FileNonLeggibile, estrai_testo, lettore_visivo
from .esecuzione import EsecuzioneBloccata, esegui_agente
from .cassaforte import CassaforteNonConfigurata
from .fornitori import ErroreFornitore
from .navigatore import ErroreNavigazione
from .permessi import divisioni_visibili, solo_titolare, utente_corrente

router = APIRouter()


class Domanda(BaseModel):
    messaggio: str
    fascia_dati: str = "interno"
    asincrono: bool = False   # True: il messaggio viene preso in carico subito e la risposta arriva in sottofondo


def _accesso(agente_id: int, utente: dict, fascia_dati: str):
    if fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    visibili = divisioni_visibili(utente)
    if visibili is not None:
        with connessione() as conn:
            a = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
        if a is None or a["divisione_id"] not in visibili:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Agente fuori dalle tue divisioni")


MAX_ALLEGATI, MAX_BYTE_ALLEGATO, MAX_CARATTERI_ALLEGATO, MAX_CARATTERI_TOTALI = 5, 10 * 1024 * 1024, 40_000, 80_000


@router.post("/agenti/{agente_id}/chat-allegati")
def chat_con_allegati(agente_id: int, messaggio: str = Form(""), fascia_dati: str = Form("interno"), asincrono: bool = Form(False),
                      file: list[UploadFile] = File(...), utente: dict = Depends(utente_corrente)):
    """Messaggio con file allegati (PDF, Word, Excel, PowerPoint, immagini, testo e altri). Il testo dei file serve solo per questa risposta: non entra nel repository."""
    _accesso(agente_id, utente, fascia_dati)
    if not file or len(file) > MAX_ALLEGATI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Allega da 1 a {MAX_ALLEGATI} file")
    allegati, totale, tagliati = [], 0, []
    for f in file:
        nome = (f.filename or "allegato").strip()[:120]
        if not nome.lower().endswith(ESTENSIONI):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"«{nome}»: formato non supportato (usa {ELENCO_FORMATI})")
        dati = f.file.read(MAX_BYTE_ALLEGATO + 1)
        if len(dati) > MAX_BYTE_ALLEGATO:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"«{nome}» supera i 10 MB")
        try:
            testo = estrai_testo(nome, dati, lettore_visivo(fascia_dati))
        except FileNonLeggibile as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"«{nome}»: {e}")
        limite = min(MAX_CARATTERI_ALLEGATO, MAX_CARATTERI_TOTALI - totale)
        if limite <= 0:
            tagliati.append(nome); continue
        if len(testo) > limite:
            testo = testo[:limite] + "\n[...file troncato: e' stata letta solo la prima parte]"; tagliati.append(nome)
        totale += len(testo)
        allegati.append((nome, testo))
    domanda = messaggio.strip() or "Leggi gli allegati e dimmi di cosa si tratta e cosa mi serve sapere."
    if asincrono:
        return JSONResponse({"coda_id": chat_coda.accoda(agente_id, utente["id"], domanda, fascia_dati, allegati, {"allegati_letti": [n for n, _ in allegati], "allegati_troncati": tagliati})}, status_code=202)
    try:
        r = esegui_agente(agente_id, domanda, fascia_dati, utente["id"], memorizza=True, allegati=allegati)
    except EsecuzioneBloccata as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except (ErroreFornitore, CassaforteNonConfigurata, ErroreNavigazione) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    r["allegati_letti"] = [n for n, _ in allegati]
    r["allegati_troncati"] = tagliati
    return r


@router.post("/agenti/{agente_id}/chat")
def chat_con_agente(agente_id: int, d: Domanda, utente: dict = Depends(utente_corrente)):
    if d.fascia_dati not in ("pubblico", "interno", "riservato"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fascia dati non valida")
    visibili = divisioni_visibili(utente)
    if visibili is not None:
        with connessione() as conn:
            a = conn.execute("SELECT divisione_id FROM agenti WHERE id = %s", (agente_id,)).fetchone()
        if a is None or a["divisione_id"] not in visibili:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Agente fuori dalle tue divisioni")
    if d.asincrono:
        return JSONResponse({"coda_id": chat_coda.accoda(agente_id, utente["id"], d.messaggio, d.fascia_dati)}, status_code=202)
    try:
        return esegui_agente(agente_id, d.messaggio, d.fascia_dati, utente["id"], memorizza=True)
    except EsecuzioneBloccata as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except (ErroreFornitore, CassaforteNonConfigurata, ErroreNavigazione) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


@router.get("/chat-coda/{coda_id}")
def stato_coda(coda_id: int, utente: dict = Depends(utente_corrente)):
    """Stato di un messaggio inviato senza attesa; quando e' finito contiene la risposta."""
    with connessione() as conn:
        r = conn.execute("SELECT id, agente_id, utente_id, stato, risultato, errore, secondi, creato_il FROM chat_coda WHERE id = %s", (coda_id,)).fetchone()
    if r is None or (r["utente_id"] != utente["id"] and utente.get("ruolo_globale") != "titolare"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Messaggio inesistente")
    return {"id": r["id"], "stato": r["stato"], "risultato": r["risultato"], "errore": r["errore"], "secondi": float(r["secondi"]) if r["secondi"] is not None else None}


@router.get("/chat-coda")
def in_corso(utente: dict = Depends(utente_corrente)):
    """I messaggi dell'utente ancora in attesa di risposta (per riprendere dopo un ricaricamento della pagina)."""
    with connessione() as conn:
        return conn.execute("""SELECT c.id, c.agente_id, a.nome AS agente, c.messaggio, c.stato FROM chat_coda c JOIN agenti a ON a.id = c.agente_id
                               WHERE c.utente_id = %s AND c.stato IN ('in_coda','in_lavoro') AND c.creato_il > NOW() - INTERVAL '2 hours' ORDER BY c.id""", (utente["id"],)).fetchall()


class NuovaProposta(BaseModel):
    titolo: str
    motivazione: str
    tipo: str = "miglioramento"
    gravita: str = "media"
    codice_proposto: str | None = None
    piano_collaudo: str | None = None


@router.post("/proposte", status_code=201)
def crea_proposta(p: NuovaProposta, utente: dict = Depends(solo_titolare)):
    """Lorenzo propone all'Architetto uno sviluppo (l'Architetto propone a lui con la stessa struttura)."""
    if p.tipo not in ("falla_sicurezza", "miglioramento", "nuova_funzione", "prestazioni"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo non valido")
    if p.gravita not in ("info", "media", "alta", "critica"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Gravita' non valida")
    with connessione() as conn:
        riga = conn.execute(
            """INSERT INTO proposte_sviluppo
               (proposta_da_utente, titolo, motivazione, tipo, gravita, codice_proposto, piano_collaudo)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (utente["id"], p.titolo, p.motivazione, p.tipo, p.gravita, p.codice_proposto, p.piano_collaudo),
        ).fetchone()
    return {"id": riga["id"]}


@router.get("/proposte")
def elenco_proposte(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute(
            "SELECT id, titolo, tipo, gravita, stato, creata_il FROM proposte_sviluppo ORDER BY creata_il DESC"
        ).fetchall()


class Decisione(BaseModel):
    decisione: str  # 'approvata' | 'respinta'
    note: str | None = None


@router.post("/proposte/{proposta_id}/decisione")
def decidi_proposta(proposta_id: int, d: Decisione, utente: dict = Depends(solo_titolare)):
    """Solo il titolare approva o respinge. Un'approvazione porta la proposta in collaudo, mai direttamente in produzione."""
    if d.decisione not in ("approvata", "respinta"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Decisione non valida")
    with connessione() as conn:
        riga = conn.execute("SELECT stato, titolo FROM proposte_sviluppo WHERE id = %s", (proposta_id,)).fetchone()
        if riga is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta inesistente")
        if riga["stato"] not in ("proposta", "in_discussione", "da_approvare"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposta gia' decisa")
        conn.execute(
            "UPDATE proposte_sviluppo SET stato = %s, note_lorenzo = %s, decisa_da = %s, decisa_il = NOW() WHERE id = %s",
            (d.decisione, d.note, utente["id"], proposta_id),
        )
        registro.registra(conn, utente, "proposta_sviluppo", d.decisione, riga.get("titolo") or f"Proposta {proposta_id}", "proposta", proposta_id, d.note or "")
    return {"stato": d.decisione}
