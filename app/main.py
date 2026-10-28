"""Punto di ingresso dell'API della piattaforma agenti AI."""
import os
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import impostazioni
from .db import apri_pool, chiudi_pool, connessione
from .permessi import divisioni_visibili, solo_titolare, utente_corrente
from .rotte_agenti import router as router_agenti
from .rotte_briefing import router as router_briefing
from .rotte_accessi import router as router_accessi
from .rotte_progetti import router as router_progetti
from .rotte_scheda import router as router_scheda
from .rotte_ginnasio import router as router_ginnasio
from .rotte_squadre import router as router_squadre
from .rotte_avatar import router as router_avatar
from .rotte_custode import router as router_custode
from .rotte_chat import router as router_chat
from . import eventi
from .rotte_utenti import router as router_utenti, gestione as gestione_utenti
from .rotte_dialoghi import router as router_dialoghi
from .rotte_richieste import router as router_richieste
from .rotte_organizzazione import router as router_organizzazione
from .rotte_aggiornamenti import router as router_aggiornamenti
from .rotte_canali import router as router_canali
from .rotte_documenti import router as router_documenti
from .rotte_gestione import router as router_gestione
from .rotte_task import router as router_task
from .rotte_percorsi import router as router_percorsi
from .rotte_social import router as router_social
from .rotte_fornitori import router as router_fornitori
from .rotte_posta import router as router_posta
from .rotte_registro import router as router_registro
from .rotte_sistema import router as router_sistema
from .rotte_voce import router as router_voce
from .rotte_memoria import router as router_memoria
from .rotte_brevo import router as router_brevo
from .rotte_canva import router as router_canva
from .allineamento import router as router_allineamento
from .rotte_misure import router as router_misure
from .rotte_sentinelle import router as router_sentinelle
from .rotte_siti import router as router_siti
from .rotte_costi import router as router_costi
from . import etichetta
from .rotte_plaud import router as router_plaud
from .rotte_iniziative import router as router_iniziative
from .rotte_biblioteca import router as router_biblioteca
from .rotte_cerimoniere import router as router_cerimoniere
from .rotte_studi import router as router_studi
from .rotte_trigger import router as router_quando
from .rotte_reparti import router as router_reparti
from .rotte_progetto import router as router_progetto
from .rotte_crm_schede import router as router_crm_schede
from .rotte_crm_modello import router as router_crm_modello
from .rotte_pwa import router as router_pwa
from .rotte_dossier import router as router_dossier
from .rotte_crm import router as router_crm
from .rotte_voce_el import router as router_voce_el
from .sicurezza import HASH_FINTO, cifra_password, crea_token, verifica_password


async def _controllo_aggiornamenti():
    """Ogni 6 ore cerca nuove versioni (in silenzio: gli errori non fermano il servizio)."""
    import asyncio
    from . import aggiornamenti

    def giro():
        with connessione() as conn:
            aggiornamenti.controllo_periodico(conn)
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:
            pass
        await asyncio.sleep(6 * 3600)


async def _canale_telegram():
    """Ascolta Telegram (se configurato). Gli errori non fermano il servizio: si riprova."""
    import asyncio
    from . import telegram
    while True:
        try:
            attivo = await asyncio.to_thread(telegram.giro, 20)
            await asyncio.sleep(1 if attivo else 15)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(15)


def _passo(nome: str, f):
    """Esegue un passo dei lavori di fondo isolandolo: se fallisce lo si registra e si avvisa (una volta al giorno),
    ma gli altri passi proseguono. Prima un guasto nel backup bloccava anche gli allarmi."""
    import logging
    try:
        with connessione() as conn:
            f(conn)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("opifex").exception("passo di fondo '%s' fallito", nome)
        try:
            with connessione() as conn:
                oggi = __import__("datetime").date.today().isoformat()
                chiave = "errore_fondo_" + nome
                r = conn.execute("SELECT valore FROM impostazioni_sistema WHERE chiave=%s", (chiave,)).fetchone()
                if not r or r["valore"] != oggi:
                    conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (chiave, oggi))
                    conn.execute("INSERT INTO notifiche (testo, urgente) VALUES (%s, FALSE)",
                                 (f"Un lavoro automatico non e' riuscito: {nome} ({type(e).__name__}: {str(e)[:120]}). Gli altri proseguono.",))
        except Exception:  # noqa: BLE001 - se non si riesce nemmeno ad avvisare resta il log
            pass


async def _manutenzione():
    """Ogni 10 minuti: allarmi di funzionamento; una volta al giorno: backup cifrato. Ogni passo e' isolato dagli altri."""
    import asyncio
    from . import allarmi, aurora, backup, cerimoniere, competenze_base, custode, crm_schede, ginnasio, plaud, proposte_sentinelle, prova_ripristino, sintesi_memoria, studio

    def giro():
        _passo("backup", lambda c: backup.esegui(c) if backup.da_fare(c) else None)
        _passo("backup dei siti (Maestro di chiavi)", lambda c: custode.esegui_notturno(c) if custode.da_fare(c) else None)
        _passo("competenze di base degli agenti", lambda c: competenze_base.applica(c) if competenze_base.da_fare(c) else None)
        _passo("allarmi", allarmi.controlla)
        _passo("elenco agenti (Cerimoniere)", lambda c: cerimoniere.aggiorna_elenco(c) if cerimoniere.da_fare(c) else None)
        _passo("ronda di Aurora", aurora.ronda)
        _passo("sintesi memoria", lambda c: sintesi_memoria.genera(c) if sintesi_memoria.da_fare(c) else None)
        _passo("posta PLAUD", plaud.controlla)
        _passo("prova ripristino", lambda c: prova_ripristino.prova(c) if prova_ripristino.da_fare(c) else None)
        _passo("studi", lambda c: studio.rileva_e_segna(c) if studio.da_fare(c) else None)
        _passo("ginnasio", ginnasio.giro)
        _passo("eventi", lambda c: eventi.pulisci(c))
        _passo("promemoria CRM", crm_schede.promemoria)
        _passo("proposte sentinelle", lambda c: proposte_sentinelle.scansiona(c) if proposte_sentinelle.da_fare(c) else None)
    await asyncio.sleep(90)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(600)


async def _trigger_orari():
    """Ogni minuto controlla i trigger a orario accesi e li avvia; poi invia le notifiche push."""
    import asyncio
    from . import attese, trigger, webpush

    def giro():
        _passo("trigger a orario", trigger.tick)
        _passo("attese scadute e Ginnasio automatico", attese.controlla)
        _passo("notifiche push", webpush.invia_notifiche)
    await asyncio.sleep(45)
    while True:
        try:
            await asyncio.to_thread(giro)
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(60)


@asynccontextmanager
async def ciclo_vita(app: FastAPI):
    import asyncio
    apri_pool()
    try:
        from . import percorsi
        percorsi.recupera_interrotti()
    except Exception:
        pass
    try:
        from . import pm
        if pm.abilitato():
            with connessione() as conn:
                pm.crea_mancanti(conn)   # un project manager per ogni progetto esistente
    except Exception:
        pass
    try:
        from . import reparti_pronti
        with connessione() as conn:
            reparti_pronti.aggiungi_nuovi_ruoli(conn)
            from . import prezzi as _prezzi
            _prezzi.applica_listino(conn)
            from . import modello_economico as _me
            if not os.environ.get("OPIFEX_SENZA_MODELLO_ECONOMICO"):   # le prove automatiche preparano i modelli a mano
                _me.una_volta(conn)
            from . import siti_hosting as _sh
            _sh.accesso_totale_al_capo(conn)
            from . import chat_coda as _cc
            _cc.riavvio(conn)
    except Exception:
        pass
    compiti = [asyncio.create_task(_controllo_aggiornamenti()), asyncio.create_task(_canale_telegram()), asyncio.create_task(_manutenzione()), asyncio.create_task(_trigger_orari())]
    yield
    for c in compiti:
        c.cancel()
    chiudi_pool()


import mimetypes
mimetypes.add_type("application/manifest+json", ".webmanifest")
app = FastAPI(title="Piattaforma agenti AI", lifespan=ciclo_vita)
app.add_middleware(
    CORSMiddleware,
    allow_origins=impostazioni.origini,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def intestazioni_sicure(richiesta, call_next):
    risposta = await call_next(richiesta)
    risposta.headers["X-Frame-Options"] = "DENY"
    risposta.headers["X-Content-Type-Options"] = "nosniff"
    risposta.headers["Referrer-Policy"] = "no-referrer"
    risposta.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    if richiesta.url.path.startswith("/app"):
        risposta.headers["Cache-Control"] = "no-cache"   # il browser controlla sempre se c'e' una versione nuova (ETag): niente grafica vecchia dopo un aggiornamento
    return risposta


app.include_router(router_agenti)
app.include_router(router_briefing)
app.include_router(router_gestione)
app.include_router(router_documenti)
app.include_router(router_accessi)
app.include_router(router_utenti)
app.include_router(router_progetti)
app.include_router(router_scheda)
app.include_router(router_ginnasio)
app.include_router(router_squadre)
app.include_router(router_avatar)
app.include_router(router_custode)
app.include_router(router_chat)
app.include_router(gestione_utenti)
app.include_router(router_dialoghi)
app.include_router(router_richieste)
app.include_router(router_organizzazione)
app.include_router(router_aggiornamenti)
app.include_router(router_canali)
app.include_router(router_task)
app.include_router(router_percorsi)
app.include_router(router_social)
app.include_router(router_fornitori)
app.include_router(router_posta)
app.include_router(router_registro)
app.include_router(router_sistema)
app.include_router(router_voce)
app.include_router(router_memoria)
app.include_router(router_brevo)
app.include_router(router_canva)
app.include_router(router_allineamento)
app.include_router(router_sentinelle)
app.include_router(router_misure)
app.include_router(router_siti)
app.include_router(router_costi)
app.include_router(router_plaud)
app.include_router(router_iniziative)
app.include_router(router_biblioteca)
app.include_router(router_cerimoniere)
app.include_router(router_studi)
app.include_router(router_quando)
app.include_router(router_reparti)
app.include_router(router_progetto)
app.include_router(router_crm_schede)
app.include_router(router_crm_modello)
app.include_router(router_pwa)
app.include_router(router_dossier)
app.include_router(router_crm)
app.include_router(router_voce_el)


@app.get("/", include_in_schema=False)
def inizio():
    return RedirectResponse("/app/")


# Interfaccia web (pagine statiche): tutto il resto passa dall'API con il token di accesso
app.mount("/app", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="interfaccia")


class DatiLogin(BaseModel):
    email: str
    password: str


class NuovoUtente(BaseModel):
    nome: str
    email: str
    password: str
    ruolo_globale: str = "collaboratore"


@app.get("/salute")
def salute():
    """Controllo rapido: il server e il database rispondono."""
    with connessione() as conn:
        conn.execute("SELECT 1")
    from .versione import versione_corrente
    return {"stato": "ok", "versione": versione_corrente()}


@app.get("/io")
def profilo(utente: dict = Depends(utente_corrente)):
    return utente


@app.post("/utenti", status_code=201)
def crea_utente(nuovo: NuovoUtente, _: dict = Depends(solo_titolare)):
    """Solo il titolare crea i profili dei collaboratori."""
    if nuovo.ruolo_globale not in ("titolare", "collaboratore"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ruolo non valido")
    if len(nuovo.password) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password troppo corta (minimo 10 caratteri)")
    with connessione() as conn:
        esistente = conn.execute("SELECT 1 FROM utenti WHERE email = %s", (nuovo.email.strip().lower(),)).fetchone()
        if esistente:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email gia' registrata")
        riga = conn.execute(
            "INSERT INTO utenti (nome, email, password_hash, ruolo_globale) VALUES (%s, %s, %s, %s) RETURNING id",
            (nuovo.nome, nuovo.email.strip().lower(), cifra_password(nuovo.password), nuovo.ruolo_globale),
        ).fetchone()
    return {"id": riga["id"]}


@app.get("/agenti")
def elenco_agenti(utente: dict = Depends(utente_corrente)):
    """Il titolare vede tutti gli agenti (anche di sistema); i collaboratori solo le proprie divisioni."""
    visibili = divisioni_visibili(utente)
    with connessione() as conn:
        if visibili is None:
            righe = conn.execute(
                f"SELECT a.id, a.divisione_id, a.superiore_id, a.nome, a.ruolo, a.livello, a.tipo, a.modello, a.attivo, {etichetta.sql()} AS etichetta, COALESCE((SELECT round(avg(ac.livello))::int FROM agenti_competenze ac WHERE ac.agente_id = a.id), 0) AS livello_formazione "
                "FROM agenti a ORDER BY a.id"
            ).fetchall()
        else:
            righe = conn.execute(
                f"SELECT a.id, a.divisione_id, a.superiore_id, a.nome, a.ruolo, a.livello, a.tipo, a.modello, a.attivo, {etichetta.sql()} AS etichetta, COALESCE((SELECT round(avg(ac.livello))::int FROM agenti_competenze ac WHERE ac.agente_id = a.id), 0) AS livello_formazione "
                "FROM agenti a WHERE a.divisione_id = ANY(%s) ORDER BY a.id",
                (visibili,),
            ).fetchall()
    return righe


@app.get("/divisioni")
def elenco_divisioni(utente: dict = Depends(utente_corrente)):
    visibili = divisioni_visibili(utente)
    with connessione() as conn:
        if visibili is None:
            return conn.execute("SELECT id, nome, descrizione, attiva FROM divisioni ORDER BY id").fetchall()
        return conn.execute(
            "SELECT id, nome, descrizione, attiva FROM divisioni WHERE id = ANY(%s) ORDER BY id",
            (visibili,),
        ).fetchall()
