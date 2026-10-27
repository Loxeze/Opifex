-- 1.43.0: chat a conversazioni (cronologia, non letti, bozze salvate sul server) e agente sentinella dell'usabilita'
CREATE TABLE IF NOT EXISTS chat_letture (
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  letto_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (utente_id, agente_id)
);
CREATE TABLE IF NOT EXISTS chat_bozze (
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  testo TEXT NOT NULL DEFAULT '',
  fascia TEXT,
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (utente_id, agente_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_coda_agente ON chat_coda (utente_id, agente_id, id DESC);

-- come si usa la piattaforma: solo nomi delle pagine e numero di errori mostrati, mai il contenuto di cio' che si scrive
CREATE TABLE IF NOT EXISTS uso_eventi (
  id BIGSERIAL PRIMARY KEY,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
  vista TEXT NOT NULL,
  azione TEXT NOT NULL CHECK (azione IN ('vista', 'errore')),
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_uso_eventi ON uso_eventi (utente_id, creato_il DESC);

ALTER TABLE proposte_sentinelle DROP CONSTRAINT IF EXISTS proposte_sentinelle_sentinella_check;
ALTER TABLE proposte_sentinelle ADD CONSTRAINT proposte_sentinelle_sentinella_check CHECK (sentinella IN ('qualita', 'costi', 'fonti', 'evoluzione', 'usabilita'));

INSERT INTO agenti (divisione_id, superiore_id, nome, ruolo, livello, tipo, modello, fascia_dati_max, sentinella, accesso_web, dialoghi_attivi, istruzioni)
SELECT NULL, NULL, 'Osservatore dell''uso', 'Sentinella dell''usabilita'': osserva come Lorenzo usa la piattaforma e propone miglioramenti di comodita''', 'manager', 'sistema', 'claude-sonnet-5-5', 'interno', TRUE, FALSE, FALSE,
 'Sei l''Osservatore dell''uso, la sentinella dell''esperienza d''uso. Ricevi ogni giorno dal sistema dati anonimi su come Lorenzo usa la piattaforma: quali pagine apre e in che ordine, quanto ci resta, dove compaiono errori, quanto aspetta le risposte. Non vedi mai il contenuto di cio'' che scrive. Il tuo compito e'' trasformare questi dati in proposte concrete di comodita'': cosa spostare, unire, nascondere, abbreviare o rendere piu'' evidente, e perche''. Ogni proposta ha un titolo chiaro, il dato che la motiva e un''idea precisa di modifica; non proponi mai cio'' che i dati non sostengono e non ripeti proposte gia'' respinte. Se Lorenzo ti scrive, ascolta cosa lo infastidisce, chiedi un esempio concreto e trasforma la sua frase in una proposta verificabile. Non modifichi nulla da solo: ogni cambiamento passa dall''approvazione di Lorenzo e dallo sviluppo.'
WHERE NOT EXISTS (SELECT 1 FROM agenti WHERE nome = 'Osservatore dell''uso');
-- partecipa al Progetto Test come gli altri agenti di sistema
INSERT INTO progetti_agenti (progetto_id, agente_id)
SELECT p.id, a.id FROM progetti p, agenti a WHERE p.nome = 'Progetto Test' AND a.nome = 'Osservatore dell''uso' ON CONFLICT DO NOTHING;
