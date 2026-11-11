"""Radar: tiene d'occhio notizie, articoli di giornale, blog e comunicati alla ricerca di potenziali clienti, collaboratori, partner e opportunita' per le attivita' di Lorenzo.
Lavora sopra il Ricercatore contatti: ogni tema ha la sua frequenza; quando tocca, parte una ricerca in «modalita' radar» e le segnalazioni finiscono nella stessa lista da approvare
del CRM, con l'articolo da cui nascono e il motivo. Nulla entra nel CRM da solo e nessuno viene contattato. Solo informazioni professionali pubbliche, sempre con la fonte."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import crm_ricerca
from .db import connessione
from .permessi import solo_titolare

router = APIRouter(prefix="/gestione/radar", tags=["radar"])
TIPI = {"cliente": "potenziali CLIENTI (enti, aziende, istituzioni che potrebbero comprare servizi o partecipare a progetti)",
        "collaboratore": "potenziali COLLABORATORI (professionisti, studiosi, creativi, tecnici con cui lavorare)",
        "partner": "potenziali PARTNER (enti, universita', imprese, fondazioni con cui costruire progetti o candidature)",
        "opportunita": "OPPORTUNITA' (bandi, gare, premi, investimenti, eventi, nuovi progetti annunciati) e chi le promuove"}
FINESTRA = {1: 3, 2: 7, 3: 7, 7: 14}   # giorni del tema -> quanto indietro guardare nelle notizie


def criteri(t: dict) -> str:
    indietro = FINESTRA.get(t["giorni"], max(7, t["giorni"] * 2))
    return (f"MODALITA' RADAR · tema «{t['nome']}». Cerca {TIPI[t['tipo']]}.\n"
            f"Cosa interessa a Lorenzo: {t['descrizione']}\n"
            f"DOVE CERCARE: notizie, articoli di giornale (anche locali), blog, comunicati stampa, pagine «news» di enti, annunci di progetti, nomine, finanziamenti ottenuti, nuove sedi o iniziative, "
            f"pubblicati negli ultimi {indietro} giorni (indica la data dell'articolo). Ignora articoli piu' vecchi.\n"
            f"PER OGNI SEGNALE chiama crm_proponi_contatto con: ente (o persona e ruolo), fonte_url = l'articolo o la pagina della notizia, segnale = che cosa dice la notizia in una frase con la data, "
            f"motivo = perche' e' un'occasione concreta per Lorenzo (quale sua attivita', che cosa potrebbe proporre). Recapiti solo se pubblicati; non sono obbligatori in modalita' radar.\n"
            f"Meglio pochi segnali concreti e recenti che molti generici.")


def da_fare(conn) -> list[dict]:
    return conn.execute("""SELECT * FROM radar_temi WHERE attivo AND (ultima_il IS NULL OR ultima_il < NOW() - make_interval(days => giorni) + interval '30 minutes')
                           ORDER BY ultima_il NULLS FIRST, id""").fetchall()


def avvia(conn, t: dict) -> int:
    rid = crm_ricerca.avvia(conn, criteri(t), t["quantita"], tema_id=t["id"])
    conn.execute("UPDATE radar_temi SET ultima_il = NOW() WHERE id = %s", (t["id"],))
    return rid


def giro(conn) -> None:
    """Nella manutenzione: al piu' un tema per volta, e solo se non c'e' gia' una ricerca in corso."""
    for t in da_fare(conn)[:1]:
        try:
            avvia(conn, t)
        except HTTPException:
            return   # ricercatore spento o ricerca gia' in corso: si riprova al giro successivo


class Tema(BaseModel):
    nome: str = Field(min_length=3, max_length=80)
    tipo: str = Field(pattern="^(cliente|collaboratore|partner|opportunita)$")
    descrizione: str = Field(min_length=20, max_length=1500)
    giorni: int = Field(default=1, ge=1, le=30)
    quantita: int = Field(default=10, ge=1, le=40)
    attivo: bool = True


@router.get("")
def elenco(_: dict = Depends(solo_titolare)):
    with connessione() as conn:
        temi = conn.execute("""SELECT t.*, (SELECT count(*) FROM crm_proposte p JOIN crm_ricerche r ON r.id = p.ricerca_id WHERE r.tema_id = t.id) AS segnalazioni,
                                      (SELECT count(*) FROM crm_proposte p JOIN crm_ricerche r ON r.id = p.ricerca_id WHERE r.tema_id = t.id AND p.stato = 'approvata') AS approvate
                               FROM radar_temi t ORDER BY t.id""").fetchall()
        return {"temi": temi, "attivo": conn.execute("SELECT 1 FROM agenti WHERE nome=%s AND attivo", (crm_ricerca.NOME_AGENTE,)).fetchone() is not None}


@router.post("", status_code=201)
def nuovo(d: Tema, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        return conn.execute("INSERT INTO radar_temi (nome, tipo, descrizione, giorni, quantita, attivo) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                            (d.nome.strip(), d.tipo, d.descrizione.strip(), d.giorni, d.quantita, d.attivo)).fetchone()


@router.put("/{tid}")
def modifica(tid: int, d: Tema, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        r = conn.execute("UPDATE radar_temi SET nome=%s, tipo=%s, descrizione=%s, giorni=%s, quantita=%s, attivo=%s WHERE id=%s RETURNING *",
                         (d.nome.strip(), d.tipo, d.descrizione.strip(), d.giorni, d.quantita, d.attivo, tid)).fetchone()
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tema inesistente")
        return r


@router.delete("/{tid}")
def elimina(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        conn.execute("DELETE FROM radar_temi WHERE id = %s", (tid,))
    return {"stato": "eliminato"}


@router.post("/{tid}/ora", status_code=202)
def ora(tid: int, _: dict = Depends(solo_titolare)):
    with connessione() as conn:
        t = conn.execute("SELECT * FROM radar_temi WHERE id = %s", (tid,)).fetchone()
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tema inesistente")
        return {"ricerca": avvia(conn, t)}
