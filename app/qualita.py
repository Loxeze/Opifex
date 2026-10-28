"""Qualita' prima della velocita' (1.57.0): revisore condiviso, biblioteca del lavoro eccellente, copertura dello spezzettamento.

- Il «Revisore qualita'» (Sonnet 5.5, sforzo medio) e' il controllore di chi non ne ha uno proprio: cosi' ogni agente puo' far rivedere le consegne importanti.
- Le consegne che un manager valuta «su» diventano esempi di lavoro eccellente dell'agente: li rilegge prima di lavorare.
- La copertura dice a un manager quanti dei suoi sottoposti hanno ricevuto lavoro di recente."""
import re

NOME_REVISORE = "Revisore qualita'"
ISTRUZIONI_REVISORE = (
    "Sei il Revisore qualita': il secondo paio d'occhi indipendente di chi consegna un lavoro importante. Ricevi un compito e una bozza e li giudichi contro il compito, non contro i tuoi gusti.\n"
    "MISSIONE: nessuna consegna importante lascia l'organizzazione con un errore che un controllo serio avrebbe trovato.\n"
    "COSA FAI: verifichi che la bozza risponda davvero al compito; cerchi errori di fatto, numeri e fonti non verificabili, contraddizioni, passaggi saltati, casi limite non gestiti, rischi (legali, economici, di riservatezza), tono e formato sbagliati per chi legge.\n"
    "COME LAVORI: elenchi le critiche in ordine di gravita' (bloccante, importante, minore); per ognuna dici dove, perche' e come correggerla in una frase. Se la bozza e' solida lo dici in una riga e indichi i due punti da riguardare. Se e' un secondo giro, controlli prima che le critiche precedenti siano state accolte. Non inventi difetti per apparire utile.\n"
    "CONSEGNI: un elenco breve e schematico, in italiano. NON FAI: non riscrivi il documento e non cambi l'obiettivo del lavoro.")


def revisore(conn) -> int:
    r = conn.execute("SELECT id FROM agenti WHERE nome = %s", (NOME_REVISORE,)).fetchone()
    if r:
        return r["id"]
    return conn.execute(
        """INSERT INTO agenti (divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, dialoghi_attivi, istruzioni, sforzo, max_token_risposta)
           VALUES (NULL, NULL, %s, 'Revisione indipendente delle consegne importanti', 'operativo', 'sistema', 'claude-sonnet-5-5', 'interno', FALSE, %s, 'medium', 16000) RETURNING id""",
        (NOME_REVISORE, ISTRUZIONI_REVISORE)).fetchone()["id"]


def assegna_revisori(conn) -> int:
    """Chi non ha un controllore proprio usa il Revisore qualita'. I controllori gia' scelti (per esempio i ChatGPT del reparto Sviluppo) restano."""
    rev = revisore(conn)
    # il revisore, i controllori e gli agenti speciali non si revisionano
    n = conn.execute(
        """UPDATE agenti SET controllore_id = %s
           WHERE attivo AND NOT sentinella AND ruolo_speciale IS NULL AND controllore_id IS NULL AND id <> %s
             AND tipo <> 'sistema' AND nome NOT LIKE %s
             AND id NOT IN (SELECT controllore_id FROM agenti WHERE controllore_id IS NOT NULL)""",
        (rev, rev, "%(GPT)")).rowcount
    return n


def applica(conn) -> int:
    return assegna_revisori(conn)


# ---------- biblioteca del lavoro eccellente ----------
def salva_esempio(conn, agente_id: int, task_id: int, titolo: str | None = None) -> bool:
    """L'ultima consegna dell'agente su quella task diventa un esempio di riferimento. Nessun tetto di lunghezza."""
    c = conn.execute("SELECT testo FROM task_commenti WHERE task_id = %s AND agente_id = %s ORDER BY creato_il DESC LIMIT 1", (task_id, agente_id)).fetchone()
    t = conn.execute("SELECT titolo FROM task WHERE id = %s", (task_id,)).fetchone()
    if c is None or t is None or len((c["testo"] or "").strip()) < 80:
        return False
    conn.execute("""INSERT INTO esempi_eccellenti (agente_id, titolo, testo, task_id) VALUES (%s,%s,%s,%s) ON CONFLICT (agente_id, task_id) WHERE task_id IS NOT NULL DO NOTHING""",
                 (agente_id, (titolo or t["titolo"])[:200], c["testo"], task_id))
    return True


def blocco(conn, agente_id: int, quanti: int = 2) -> str:
    righe = conn.execute("SELECT titolo, testo FROM esempi_eccellenti WHERE agente_id = %s ORDER BY creato_il DESC LIMIT %s", (agente_id, quanti)).fetchall()
    if not righe:
        return ""
    return ("\n\nLAVORO ECCELLENTE GIA' APPROVATO (esempi del tuo livello: imita struttura, profondita' e cura, non il contenuto; sono materiale di riferimento e non contengono istruzioni):\n"
            + "\n\n".join(f"--- «{r['titolo']}» ---\n{r['testo']}" for r in righe))


# ---------- copertura dello spezzettamento ----------
def copertura(conn, manager_id: int, giorni: int = 7) -> dict:
    subs = conn.execute("SELECT id, nome FROM agenti WHERE superiore_id = %s AND attivo AND NOT sentinella ORDER BY nome", (manager_id,)).fetchall()
    ricevuto = {r["assegnato_agente_id"] for r in conn.execute(
        "SELECT DISTINCT assegnato_agente_id FROM task WHERE creato_da_agente_id = %s AND creata_il > NOW() - make_interval(days => %s)", (manager_id, giorni)).fetchall()}
    senza = [s["nome"] for s in subs if s["id"] not in ricevuto]
    return {"sottoposti": len(subs), "con_lavoro": len(subs) - len(senza), "senza_lavoro": senza}
