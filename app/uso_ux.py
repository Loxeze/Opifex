"""Riepilogo anonimo dell'uso della piattaforma per l'Osservatore dell'uso: solo nomi di pagine, conteggi e tempi, mai contenuti."""
from .proposte_sentinelle import _nome_vista


def riepilogo(conn, giorni: int = 14) -> str:
    tot = conn.execute("SELECT count(*) AS n FROM uso_eventi WHERE creato_il > NOW() - make_interval(days => %s)", (giorni,)).fetchone()["n"]
    if not tot:
        return "DATI D'USO: ancora nessuna osservazione registrata (i dati si raccolgono da quando la pagina viene usata)."
    righe = conn.execute("""WITH e AS (SELECT vista, azione, LEAD(creato_il) OVER (PARTITION BY utente_id ORDER BY creato_il) - creato_il AS d FROM uso_eventi
                                       WHERE creato_il > NOW() - make_interval(days => %s))
                            SELECT vista, count(*) FILTER (WHERE azione = 'vista') AS aperture, count(*) FILTER (WHERE azione = 'errore') AS errori,
                                   percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM d)) FILTER (WHERE azione = 'vista' AND d < INTERVAL '30 minutes') AS mediana_s
                            FROM e GROUP BY vista ORDER BY aperture DESC LIMIT 25""", (giorni,)).fetchall()
    chat = conn.execute("""SELECT count(*) AS n, percentile_cont(0.5) WITHIN GROUP (ORDER BY secondi) AS med FROM chat_coda
                           WHERE stato = 'finito' AND creato_il > NOW() - make_interval(days => %s)""", (giorni,)).fetchone()
    out = [f"DATI D'USO degli ultimi {giorni} giorni (anonimi: pagine e conteggi, nessun contenuto):"]
    for r in righe:
        out.append(f"- {_nome_vista(r['vista'])}: {r['aperture']} aperture" + (f", permanenza mediana {round(float(r['mediana_s']))} s" if r["mediana_s"] is not None else "") + (f", {r['errori']} errori mostrati" if r["errori"] else ""))
    if chat["n"]:
        out.append(f"- Chat: {chat['n']} risposte ricevute, attesa mediana {round(float(chat['med'] or 0))} s")
    return "\n".join(out)
