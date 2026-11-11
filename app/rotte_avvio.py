"""Avvio guidato della 3.0: primo accesso, importazione dalla 2 e i nove passi con le verifiche vere."""
import hmac

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import edizione, fornitori, memoria_pc
from .config import impostazioni
from .db import connessione
from .permessi import solo_titolare
from .sicurezza import cifra_password

router_pubblico = APIRouter(prefix="/avvio", tags=["avvio"])
router = APIRouter(prefix="/gestione/avvio", tags=["avvio"])


def _senza_utenti(conn) -> bool:
    return conn.execute("SELECT count(*) AS n FROM utenti").fetchone()["n"] == 0


@router_pubblico.get("")
def pubblico():
    """Alla pagina di accesso: serve solo a sapere se mostrare «crea il tuo accesso» (prima volta della 3.0)."""
    with connessione() as conn:
        primo = edizione.tre() and _senza_utenti(conn)
    return {"edizione": 3 if edizione.tre() else 2, "primo_accesso": primo}


class PrimoUtente(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    codice: str = Field(min_length=6, max_length=80)


@router_pubblico.post("/primo-utente", status_code=201)
def primo_utente(d: PrimoUtente):
    """Solo nella 3.0, solo finche' non esiste nessun utente, e solo con il codice d'avvio mostrato dall'installatore sul server."""
    atteso = str(getattr(impostazioni, "opifex_codice_avvio", "") or "")
    if not edizione.tre() or not atteso:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Non disponibile")
    if not hmac.compare_digest(d.codice.strip(), atteso):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Codice d'avvio non corretto: lo trovi nel messaggio finale dell'installazione")
    with connessione() as conn:
        conn.execute("LOCK TABLE utenti IN EXCLUSIVE MODE")
        if not _senza_utenti(conn):
            raise HTTPException(status.HTTP_409_CONFLICT, "L'accesso e' gia' stato creato: entra con email e password")
        conn.execute("INSERT INTO utenti (nome, email, password_hash, ruolo_globale) VALUES (%s,%s,%s,'titolare')",
                     (d.nome.strip(), d.email.strip().lower(), cifra_password(d.password)))
        edizione.prepara(conn)
    return {"stato": "ok"}


def _verifiche(conn) -> dict:
    """Per ogni passo, che cosa risulta gia' a posto adesso (prove vere, non spunte)."""
    chiavi = {n: bool(fornitori.chiave(n)) for n in ("anthropic", "openai", "xai")}
    try:
        macchine = fornitori.macchine_locali()
    except Exception:  # noqa: BLE001
        macchine = []
    goo = conn.execute("SELECT etichetta, email, servizi FROM account_google ORDER BY id").fetchall()
    servizi = {s for g in goo for s in (g["servizi"] or [])}
    agenti = conn.execute("SELECT nome, modello, gmail_account_id FROM agenti WHERE attivo ORDER BY id").fetchall()
    posta = next((a for a in agenti if a["nome"] == "Posta"), None)
    n = lambda q: conn.execute(q).fetchone()["n"]  # noqa: E731
    return {
        "ia": {"chiavi": chiavi, "computer": [m.get("nome") for m in macchine if isinstance(m, dict)], "pronto": chiavi["anthropic"]},
        "chi": {"attivita": n("SELECT count(*) AS n FROM aziende"), "pronto": n("SELECT count(*) AS n FROM aziende") > 0},
        "posta": {"caselle": [g["email"] for g in goo if "gmail" in (g["servizi"] or [])], "affidata": bool(posta and posta["gmail_account_id"]),
                  "pronto": bool(posta and posta["gmail_account_id"])},
        "calendario": {"calendar": "calendar" in servizi, "drive": "drive" in servizi, "pronto": "calendar" in servizi or "drive" in servizi},
        "memoria": {"collegata": memoria_pc.collegata(), "pronto": memoria_pc.collegata()},
        "telefono": {"telegram": n("SELECT count(*) AS n FROM canale_telegram WHERE chat_id IS NOT NULL"), "app": n("SELECT count(*) AS n FROM push_iscrizioni"),
                     "pronto": n("SELECT count(*) AS n FROM canale_telegram WHERE chat_id IS NOT NULL") + n("SELECT count(*) AS n FROM push_iscrizioni") > 0},
        "radar": {"temi": n("SELECT count(*) AS n FROM radar_temi"), "pronto": n("SELECT count(*) AS n FROM radar_temi") > 0},
        "squadra": {"agenti": [{"nome": a["nome"], "modello": a["modello"]} for a in agenti], "pronto": posta is not None},
        "benvenuto": {"pronto": False},
    }


@router.get("")
def stato(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        s = edizione.stato_avvio(conn)
        ver = _verifiche(conn)
    passi = s.get("passi", {})
    elenco = [{"id": p, "titolo": t, "esito": passi.get(p, ""), "verifica": ver.get(p, {})} for p, t in edizione.PASSI]
    completati = sum(1 for x in elenco if x["esito"] or x["verifica"].get("pronto"))
    return {"edizione": 3 if edizione.tre() else 2, "passi": elenco, "completati": completati, "totale": len(elenco),
            "importato": s.get("importato", []), "importabile": bool(getattr(impostazioni, "opifex_importa_da", ""))}


@router.get("/dalla-2")
def dalla_2(_: dict = Depends(solo_titolare)):
    return edizione.anteprima()


class Scelte(BaseModel):
    cose: list[str] = Field(default_factory=list, max_length=10)


@router.post("/dalla-2")
def importa(d: Scelte, _: dict = Depends(solo_titolare)):
    scelte = [c for c in d.cose if c in edizione.COSE]
    if not scelte:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli che cosa copiare")
    try:
        with connessione() as conn:
            fatto = edizione.importa(conn, scelte)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "La 2 non risponde (" + type(e).__name__ + ")") from None
    return {"copiato": fatto}


class Passo(BaseModel):
    esito: str = Field(pattern="^(fatto|saltato|)$")


@router.put("/passo/{passo}")
def segna(passo: str, d: Passo, _: dict = Depends(solo_titolare)):
    try:
        with connessione() as conn:
            edizione.segna(conn, passo, d.esito)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    return {"stato": "ok"}


class Attivita(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    territorio: str = Field(default="", max_length=200)
    profilo: str = Field(min_length=10, max_length=3000)
    clienti: str = Field(default="", max_length=2000)


@router.post("/attivita", status_code=201)
def attivita(d: Attivita, _: dict = Depends(solo_titolare)):
    """Passo 3: chi sei e che cosa fai. Diventa una scheda d'impresa, che leggono Aurora e il Radar."""
    with connessione() as conn:
        r = conn.execute("INSERT INTO aziende (nome, territorio, profilo, criteri_interesse) VALUES (%s,%s,%s,%s) RETURNING id",
                         (d.nome.strip(), d.territorio.strip(), d.profilo.strip(), d.clienti.strip())).fetchone()
    return {"id": r["id"]}


@router.post("/radar")
def radar(_: dict = Depends(solo_titolare)):
    """Passo 8: il Radar ha bisogno del suo ricercatore; nella 3.0 nasce solo quando lo chiedi. Propone un primo tema dalle tue attivita'."""
    from . import crm_ricerca
    with connessione() as conn:
        if conn.execute("SELECT 1 FROM divisioni WHERE nome='CRM'").fetchone() is None:
            conn.execute("INSERT INTO divisioni (nome, descrizione) VALUES ('CRM', 'Contatti e Radar')")
        rid = crm_ricerca.crea_agente(conn)
        if rid:
            conn.execute("UPDATE agenti SET superiore_id=(SELECT id FROM agenti WHERE nome='Aurora' ORDER BY id LIMIT 1) WHERE id=%s AND superiore_id IS NULL", (rid,))
        if conn.execute("SELECT count(*) AS n FROM radar_temi").fetchone()["n"] == 0:
            az = conn.execute("SELECT nome, profilo, criteri_interesse, territorio FROM aziende ORDER BY id LIMIT 3").fetchall()
            if az:
                desc = "; ".join(f"{a['nome']}: {a['profilo'][:300]}" + (f" — clienti ideali: {a['criteri_interesse'][:300]}" if a["criteri_interesse"] else "")
                                 + (f" — zona: {a['territorio']}" if a["territorio"] else "") for a in az)
                conn.execute("INSERT INTO radar_temi (nome, tipo, descrizione, giorni, quantita, attivo) VALUES (%s,'cliente',%s,1,10,FALSE)",
                             ("Clienti per " + az[0]["nome"][:60], ("Potenziali clienti e collaboratori per: " + desc)[:1500]))
    return {"stato": "ok"}


@router.post("/memoria-agenti")
def memoria_agenti(_: dict = Depends(solo_titolare)):
    """Passo 6: Aurora e Posta possono cercare nella memoria del computer."""
    with connessione() as conn:
        conn.execute("UPDATE agenti SET archivio_attivo=TRUE WHERE nome IN ('Aurora','Posta')")
    return {"stato": "ok", "collegata": memoria_pc.collegata()}

