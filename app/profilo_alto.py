"""Profilo alto (2.11.0): mette un agente nelle condizioni di lavorare come Claude Code - modello migliore, molti piu' passaggi con gli strumenti,
sforzo di ragionamento alto, e un METODO scritto (capire, pianificare, eseguire a piccoli passi, riguardare, riprovare in altro modo, dichiarare i limiti)."""
from fastapi import APIRouter, Depends, HTTPException

from . import fornitori
from .db import connessione
from .permessi import solo_titolare
from .riservatezza import puo_uscire

PASSI_ALTO = 40
TOKEN_ALTO = 32000
MARCA = "METODO DI LAVORO AVANZATO"
METODO = (
    "\n\n" + MARCA + ". Risultato, non chiacchiere.\n"
    "1) Capisci: leggi brief e file; i dati che puoi trovare con gli strumenti li cerchi, non li chiedi.\n"
    "2) Piano: poche righe numerate + criterio di riuscita.\n"
    "3) Esegui: un passo alla volta, controlla l'esito di ogni strumento. Lavori lunghi: avvia e richiama banco_risultato.\n"
    "4) Verifica: guarda il risultato (banco_fotogrammi sui punti chiave, durata, 4K, audio) contro il criterio; registra con consegna_verifica.\n"
    "5) Errore: cambia approccio e riprova; ti fermi solo dopo due strade diverse.\n"
    "6) Blocco vero: passaggio fallito + messaggio dello strumento + cosa serve (una cosa).\n"
    "RISPARMIO: non rileggere cio' che hai gia' in contesto; non rielencare inventari; chiedi allo strumento solo cio' che serve; niente passaggi di prova inutili.\n"
    "STILE: frasi assertive e corte. Vietati ringraziamenti, premesse, riepiloghi dei passi, scuse, ripetizioni. Consegna: cosa e' fatto, dove sono i file, cosa hai verificato, cosa resta da vedere."
)


def scegli_modello(conn, a: dict) -> str | None:
    righe = conn.execute(
        """SELECT m.nome, f.nome AS fornitore, f.fascia_dati_max AS ff, f.non_conservazione_attiva AS nc, f.dpa_firmato AS dpa
           FROM modelli_ai m JOIN fornitori_ai f ON f.id = m.fornitore_id WHERE m.fascia = 'avanzato' AND f.nome = 'anthropic' ORDER BY m.nome""").fetchall()
    ok = [r for r in righe if fornitori.chiave(r["fornitore"]) and puo_uscire(a["fascia_dati_max"], a["fascia_dati_max"], r["ff"], r["nc"], r["dpa"])[0]]
    if not ok:
        return None
    for chiave in ("opus", "fable", ""):
        for r in sorted(ok, key=lambda x: x["nome"], reverse=True):
            if chiave in r["nome"]:
                return r["nome"]
    return None


def applica(conn, agente_id: int) -> dict:
    a = conn.execute("SELECT id, nome, modello, sforzo, max_token_risposta, istruzioni, fascia_dati_max, profilo_alto, usa_biblioteca, sandbox_attivo, drive_attivo FROM agenti WHERE id = %s", (agente_id,)).fetchone()
    if not a:
        raise LookupError("agente inesistente")
    modello = scegli_modello(conn, a)
    if not a["profilo_alto"]:
        conn.execute("UPDATE agenti SET profilo_prima = %s::jsonb WHERE id = %s", (
            __import__("json").dumps({"modello": a["modello"], "sforzo": a["sforzo"], "max_token_risposta": a["max_token_risposta"], "istruzioni": a["istruzioni"],
                                      "usa_biblioteca": a["usa_biblioteca"], "sandbox_attivo": a["sandbox_attivo"], "drive_attivo": a["drive_attivo"]}), agente_id))
    istr = a["istruzioni"] if MARCA in (a["istruzioni"] or "") else (a["istruzioni"] or "") + METODO
    conn.execute("""UPDATE agenti SET profilo_alto = TRUE, passi_max = %s, sforzo = 'high', max_token_risposta = GREATEST(max_token_risposta, %s), istruzioni = %s,
                    modello = COALESCE(%s, modello), modello_dialogo = NULL, usa_biblioteca = TRUE, sandbox_attivo = TRUE, drive_attivo = TRUE WHERE id = %s""",
                 (PASSI_ALTO, TOKEN_ALTO, istr, modello, agente_id))
    conn.execute("INSERT INTO registro_azioni (agente_id, azione, dettagli) VALUES (%s, 'profilo_alto', %s::jsonb)", (agente_id, __import__("json").dumps({"modello": modello or a["modello"]})))
    return {"agente": a["nome"], "modello": modello or a["modello"], "modello_cambiato": bool(modello and modello != a["modello"]), "passi": PASSI_ALTO,
            "avviso": None if modello else "Nessun modello avanzato Anthropic utilizzabile (manca la chiave, il modello non e' nel catalogo o la riservatezza non lo permette): resta il modello attuale."}


def ripristina(conn, agente_id: int) -> bool:
    a = conn.execute("SELECT profilo_prima FROM agenti WHERE id = %s AND profilo_alto", (agente_id,)).fetchone()
    p = (a or {}).get("profilo_prima") or {}
    if not a:
        return False
    conn.execute("""UPDATE agenti SET profilo_alto = FALSE, passi_max = NULL, profilo_prima = NULL, modello = COALESCE(%s, modello), sforzo = %s,
                    max_token_risposta = COALESCE(%s, max_token_risposta), istruzioni = COALESCE(%s, istruzioni), usa_biblioteca = COALESCE(%s, usa_biblioteca),
                    sandbox_attivo = COALESCE(%s, sandbox_attivo), drive_attivo = COALESCE(%s, drive_attivo) WHERE id = %s""",
                 (p.get("modello"), p.get("sforzo"), p.get("max_token_risposta"), p.get("istruzioni"), p.get("usa_biblioteca"), p.get("sandbox_attivo"), p.get("drive_attivo"), agente_id))
    return True


router = APIRouter(prefix="/gestione")


@router.post("/agenti/{agente_id}/profilo-alto")
def rotta_applica(agente_id: int, _=Depends(solo_titolare)):
    with connessione() as conn:
        try:
            return applica(conn, agente_id)
        except LookupError:
            raise HTTPException(404, "Agente non trovato") from None


@router.delete("/agenti/{agente_id}/profilo-alto")
def rotta_ripristina(agente_id: int, _=Depends(solo_titolare)):
    with connessione() as conn:
        if not ripristina(conn, agente_id):
            raise HTTPException(404, "L'agente non ha il profilo alto")
    return {"ok": True}
