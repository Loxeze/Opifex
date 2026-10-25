"""Assistente prompt: nella scheda di un agente Lorenzo descrive cosa vuole e riceve un prompt scritto o migliorato.
Usa il modello di Aurora, vede solo i dati della scheda (nessun documento, nessuna chat), e il costo e' registrato come quello di Aurora."""
from . import fornitori
from .db import connessione
from .riservatezza import puo_uscire

ISTRUZIONI = (
    "Sei l'assistente che aiuta Lorenzo a scrivere e migliorare i prompt degli agenti AI di Opifex, una piattaforma di agenti organizzati per dipartimento "
    "(bandi, marketing, CRM, ricerca e sviluppo...) con un manager per dipartimento. Rispondi in italiano.\n"
    "Un buon prompt per un agente dice: chi e' e a quale azienda e dipartimento appartiene; il compito specifico e cosa NON fa (e a chi rimanda); "
    "da dove prende le informazioni; cosa produce e in che forma; quando chiede a un collega o al manager invece di indovinare; i limiti (non scrive all'esterno "
    "senza approvazione, niente invenzioni, dichiara cio' che non sa); il tono. Deve essere concreto, senza frasi vuote.\n"
    "Se la richiesta e' ambigua fai al massimo due domande brevi prima di scrivere. Quando scrivi il prompt completo, mettilo tra le righe <<<PROMPT e PROMPT>>> "
    "(le due righe da sole) e fuori da quelle righe spiega in poche frasi le scelte fatte o cosa e' cambiato. Non inserire mai password o chiavi nel prompt.")


class AssistenteNonDisponibile(Exception):
    pass


def chiedi(richiesta: str, scheda: dict, conversazione: list[dict]) -> dict:
    with connessione() as conn:
        a = conn.execute(
            """SELECT a.id, m.nome AS modello, m.costo_input_per_milione, m.costo_output_per_milione, f.nome AS fornitore, f.fascia_dati_max AS fascia_f,
                      f.non_conservazione_attiva, f.dpa_firmato, a.fascia_dati_max
               FROM agenti a JOIN modelli_ai m ON m.nome = a.modello JOIN fornitori_ai f ON f.id = m.fornitore_id
               WHERE a.nome = 'Aurora' AND a.tipo = 'sistema'""").fetchone()
        if a is None:
            raise AssistenteNonDisponibile("Serve l'agente Aurora per usare l'assistente")
        ok, motivo = puo_uscire("interno", a["fascia_dati_max"], a["fascia_f"], a["non_conservazione_attiva"], a["dpa_firmato"])
        if not ok:
            raise AssistenteNonDisponibile("L'assistente usa il modello di Aurora, che non ha le garanzie per dati interni: " + str(motivo))
        colleghi = conn.execute(
            """SELECT concat_ws(' — ', nome, ruolo) AS riga FROM agenti WHERE attivo AND NOT sentinella ORDER BY id LIMIT 40""").fetchall()
    righe = ["Scheda dell'agente che si sta modificando:"]
    for k, t in (("nome", "Nome"), ("ruolo", "Compito specifico"), ("divisione", "Dipartimento"), ("aziende", "Aziende"), ("livello", "Livello"), ("rimanda_a", "Cosa non fa / a chi rimanda")):
        if scheda.get(k):
            righe.append(f"- {t}: {str(scheda[k])[:300]}")
    if scheda.get("istruzioni"):
        righe.append("Prompt attuale:\n" + str(scheda["istruzioni"])[:8000])
    righe.append("Altri agenti della piattaforma (per sapere a chi rimandare): " + "; ".join(c["riga"] for c in colleghi))
    storia = "\n".join(f"{'Lorenzo' if m.get('ruolo') == 'utente' else 'Assistente'}: {str(m.get('testo', ''))[:3000]}" for m in conversazione[-8:])
    msg = "\n".join(righe) + ("\n\nConversazione fin qui:\n" + storia if storia else "") + "\n\nRichiesta di Lorenzo:\n" + richiesta[:4000]
    ris = fornitori.chiama_modello(a["fornitore"], a["modello"], ISTRUZIONI, msg, 3000)
    costo = round(ris.token_input / 1e6 * float(a["costo_input_per_milione"] or 0) + ris.token_output / 1e6 * float(a["costo_output_per_milione"] or 0), 4)
    with connessione() as conn:
        conn.execute("INSERT INTO costi_api (agente_id, modello, token_input, token_output, costo_stimato) VALUES (%s,%s,%s,%s,%s)",
                     (a["id"], a["modello"], ris.token_input, ris.token_output, costo))
    testo = ris.testo
    prompt = None
    if "<<<PROMPT" in testo and "PROMPT>>>" in testo:
        prompt = testo.split("<<<PROMPT", 1)[1].split("PROMPT>>>", 1)[0].strip()
        testo = (testo.split("<<<PROMPT", 1)[0] + "\n" + testo.split("PROMPT>>>", 1)[1]).strip()
    return {"risposta": testo, "prompt": prompt}
