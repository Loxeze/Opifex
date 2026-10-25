"""Registro delle decisioni: chi ha approvato, respinto o autorizzato cosa. Si scrive qui da ogni punto in cui una persona decide."""
import json

TIPI = {
    "proposta_sviluppo": "Proposta di sviluppo",
    "fase_percorso": "Fase di un percorso",
    "post_social": "Post social",
    "richiesta_info": "Risposta a richiesta degli agenti",
    "garanzie_fornitore": "Garanzie del fornitore AI",
    "chiave_fornitore": "Chiave di un fornitore AI",
    "collegamento": "Collegamento a un servizio",
    "task": "Task",
    "tetto_spesa": "Tetto di spesa",
    "backup": "Backup",
    "memoria": "Memoria di lavoro",
}


def registra(conn, utente: dict, tipo: str, esito: str, oggetto: str = "", oggetto_tipo: str | None = None,
             oggetto_id=None, nota: str = "", dettagli: dict | None = None):
    """Aggiunge una riga al registro. Mai segreti nei dettagli."""
    conn.execute(
        """INSERT INTO registro_decisioni (utente_id, utente_nome, utente_email, tipo, esito, oggetto_tipo, oggetto_id, oggetto, nota, dettagli)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (utente.get("id"), utente.get("nome") or "?", utente.get("email"), tipo, esito, oggetto_tipo,
         None if oggetto_id is None else str(oggetto_id), (oggetto or "")[:300], (nota or "")[:1000], json.dumps(dettagli or {}, default=str)))
