INSERT INTO best_practice (progetto_nome, titolo, tipo, contesto, cosa_funziona, da_evitare, checklist, parole, origine)
SELECT 'Ricetta di base', 'Email di primo contatto personalizzata', 'email',
$$Quando si scrive a un contatto del CRM (ente, impresa, persona) per un primo contatto, una proposta, una collaborazione o un bando.$$,
$$- Prima il dossier (crm_dossier): scheda del CRM + ricerca online sul contatto e sul suo ente. Poi si scrive.
- Apertura con UN riferimento concreto e verificabile al suo lavoro (un progetto, un'iniziativa, un intervento recente) collegato al motivo del contatto.
- Una proposta chiara in due frasi e UNA richiesta precisa (una telefonata di 15 minuti, un parere, un incontro).
- Breve (sotto 150 parole), tono rispettoso e diretto, firma completa con l'impresa a nome della quale si scrive.
- Oggetto specifico, non generico (cita l'ente o il tema).
- Riga finale per non ricevere altre email.
- Una email diversa per ogni contatto; se il dossier non offre un aggancio solido, apertura sobria senza inventare.$$,
$$- Complimenti generici, adulazione, frasi da modulo uguali per tutti.
- Dati, cariche o fatti non verificati nel dossier; informazioni sulla vita privata, salute, famiglia o opinioni politiche.
- Piu' richieste nella stessa email; allegati non richiesti.
- Riscrivere a chi ha negato il consenso o e' stato contattato da meno di 14 giorni.
- Scrivere a nome di un'impresa a cui il contatto non e' associato.$$,
$$- Dossier fatto e fonte dell'aggancio chiara.
- Un solo riferimento personale, concreto e vero.
- Una sola richiesta.
- Meno di 150 parole; oggetto specifico; firma; riga per non ricevere altre email.
- Impresa associata al contatto; consenso non negato.
- Email registrata nello storico del contatto.$$,
'email mail posta contatto contatti crm primo contatto outreach personalizzata ricerca dossier proposta collaborazione bando ente comune impresa invio', 'manuale'
WHERE NOT EXISTS (SELECT 1 FROM best_practice WHERE titolo = 'Email di primo contatto personalizzata');
