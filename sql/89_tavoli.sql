-- 1.65.0: tavoli di lavoro - riunioni fra piu' agenti convocate da Lorenzo, con moderatore e verbale
CREATE TABLE IF NOT EXISTS tavoli (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  ordine_del_giorno TEXT NOT NULL,
  moderatore_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  turni INTEGER NOT NULL DEFAULT 2 CHECK (turni BETWEEN 1 AND 3),
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','conclusa','errore')),
  verbale TEXT,
  errore TEXT,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  concluso_il TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS tavoli_partecipanti (
  tavolo_id INTEGER NOT NULL REFERENCES tavoli(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  ordine INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tavolo_id, agente_id)
);
CREATE TABLE IF NOT EXISTS tavoli_interventi (
  id SERIAL PRIMARY KEY,
  tavolo_id INTEGER NOT NULL REFERENCES tavoli(id) ON DELETE CASCADE,
  turno INTEGER NOT NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  testo TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS tavoli_interventi_t ON tavoli_interventi (tavolo_id, id);
