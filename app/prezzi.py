"""Prezzi dei modelli: listino indicativo fornito con la release (mai sopra prezzi gia' impostati) e calibrazione sul costo reale dei fornitori."""
from datetime import datetime, timezone

from . import costi

DATA_LISTINO = "2026-10-26"  # Anthropic, OpenAI e xAI da listini ufficiali
# (prefisso del nome modello, USD per milione di token in ingresso, in uscita). INDICATIVI: da verificare sulle pagine ufficiali dei fornitori.
LISTINO = [
    # Anthropic: pagina ufficiale dei prezzi (platform.claude.com/docs/en/about-claude/pricing), prezzo standard, prompt brevi
    ("claude-fable-5", 10.0, 50.0), ("claude-mythos-5", 10.0, 50.0),
    ("claude-opus-5-5", 4.0, 20.0), ("claude-opus-5", 5.0, 25.0),
    ("claude-opus-4-5", 5.0, 25.0), ("claude-opus-4-6", 5.0, 25.0), ("claude-opus-4-7", 5.0, 25.0), ("claude-opus-4-8", 5.0, 25.0),
    ("claude-opus-4-1", 15.0, 75.0), ("claude-opus-4-0", 15.0, 75.0), ("claude-opus-4-2025", 15.0, 75.0),
    ("claude-sonnet-5", 2.0, 10.0), ("claude-sonnet-4", 3.0, 15.0),
    ("claude-haiku-5", 0.10, 0.50),   # oltre 100K token di prompt: 0,50 / 2,50
    ("claude-haiku-4-5", 1.0, 5.0),
    # OpenAI: listino ufficiale (developers.openai.com/api/docs/pricing), standard, contesto breve
    ("gpt-6-luna", 0.10, 0.50), ("gpt-6.1-sol", 2.0, 10.0), ("gpt-6-astra", 10.0, 50.0),
    ("gpt-5.6-sol", 4.0, 20.0), ("gpt-5.6-cyber", 12.5, 75.0), ("gpt-rosalind", 5.0, 25.0), ("chat-latest", 5.0, 30.0), ("gpt-5.3-codex", 1.75, 14.0),
    # xAI: contesto breve
    ("grok-4.7", 2.0, 6.0), ("grok-4.6", 2.0, 6.0), ("grok-4.5", 2.0, 6.0), ("grok-4.3", 1.25, 2.5), ("grok-4.20", 1.25, 2.5), ("grok-build-0.1", 1.0, 2.0),
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
