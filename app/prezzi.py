"""Prezzi dei modelli: listino indicativo fornito con la release (mai sopra prezzi gia' impostati) e calibrazione sul costo reale dei fornitori."""
from datetime import datetime, timezone

from . import costi

DATA_LISTINO = "2026-10-26"
# (prefisso del nome modello, USD per milione di token in ingresso, in uscita). INDICATIVI: da verificare sulle pagine ufficiali dei fornitori.
LISTINO = [
    ("claude-sonnet-5-5", 2.0, 10.0),
    ("gpt-6-luna", 0.10, 0.50),
    ("gpt-6.1-sol", 2.0, 10.0),
    ("gpt-6-astra", 10.0, 50.0),
]


def prezzo_listino(nome: str):
    c = [r for r in LISTINO if nome.startswith(r[0])]
    return max(c, key=lambda r: len(r[0])) if c else None


def applica_listino(conn) -> int:
    """Imposta il prezzo indicativo ai soli modelli senza prezzo. Non tocca nulla di impostato dall'utente o gia' presente."""
    n = 0
    for m in conn.execute("SELECT nome FROM modelli_ai WHERE costo_input_per_milione IS NULL AND costo_output_per_milione IS NULL").fetchall():
        p = prezzo_listino(m["nome"])
        if p:
            conn.execute("UPDATE modelli_ai SET costo_input_per_milione=%s, costo_output_per_milione=%s, prezzo_origine='indicativo' WHERE nome=%s", (p[1], p[2], m["nome"]))
            n += 1
    return n


def segna_manuale(conn, nome: str):
    conn.execute("UPDATE modelli_ai SET prezzo_origine='manuale' WHERE nome=%s", (nome,))


def calibra(conn, giorni: int = 14, reali: dict | None = None) -> dict:
    """Confronta il costo reale per fornitore (API admin) con quello stimato dai token registrati. Salva il fattore di correzione
    (reale/stimato) in impostazioni_sistema e lo restituisce: serve per capire quanto i prezzi usati si discostano dalla realta'."""
    reali = reali if reali is not None else costi.dai_fornitori(conn, giorni)
    out: dict = {}
    for f, dati in reali.items():
        if "errore" in dati:
            out[f] = {"errore": dati["errore"]}
            continue
        reale = sum(dati["usd_per_giorno"].values())
        stimato = float(conn.execute(
            """SELECT COALESCE(SUM(c.costo_stimato),0) AS t FROM costi_api c JOIN modelli_ai m ON m.nome=c.modello JOIN fornitori_ai fa ON fa.id=m.fornitore_id
               WHERE fa.nome=%s AND c.creato_il > NOW() - make_interval(days => %s)""", (f, giorni)).fetchone()["t"])
        if stimato <= 0 or reale <= 0:
            out[f] = {"reale": round(reale, 4), "stimato": round(stimato, 4), "fattore": None}
            continue
        fat = round(reale / stimato, 3)
        for k, v in ((f"calibrazione_{f}", str(fat)), (f"calibrazione_{f}_data", datetime.now(timezone.utc).isoformat())):
            conn.execute("INSERT INTO impostazioni_sistema (chiave, valore) VALUES (%s,%s) ON CONFLICT (chiave) DO UPDATE SET valore=EXCLUDED.valore", (k, v))
        out[f] = {"reale": round(reale, 4), "stimato": round(stimato, 4), "fattore": fat}
    return out
