"""Avanzamento di un lavoro dell'agente: la chat mostra cosa sta facendo (fase) e permette di annullare.
Chi esegue chiama fase("..."); se e' stato impostato un ascoltatore lo avvisa e, se l'utente ha annullato, solleva Annullata."""
import contextvars

ASCOLTATORE: contextvars.ContextVar = contextvars.ContextVar("progresso_ascoltatore", default=None)


class Annullata(Exception):
    pass


LEGGIBILI = {"chiedi_a_agente": "chiede a un collega", "web_search": "cerca sul web", "formazione_richiedi": "chiede una formazione", "crm_proponi_contatto": "propone un contatto",
             "prova_codice": "prova il codice", "revisione_incrociata": "chiede una revisione"}


def fase(testo: str) -> None:
    cb = ASCOLTATORE.get()
    if cb is not None:
        cb(testo)


def strumento(nome: str) -> None:
    fase(LEGGIBILI.get(nome) or ("usa lo strumento " + nome.replace("_", " ")))
