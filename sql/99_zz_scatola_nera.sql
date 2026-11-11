-- Scatola nera: per ogni lavoro di un agente, la traccia di che cosa e' successo (chiamate al modello, strumenti, adattamenti, errori)
CREATE TABLE IF NOT EXISTS tracce (
  id BIGSERIAL PRIMARY KEY,
  padre_id BIGINT REFERENCES tracce(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  utente_id INTEGER,
  origine TEXT,
  richiesta TEXT,
  risposta TEXT,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','riuscita','errore')),
  errore TEXT,
  token_input INTEGER NOT NULL DEFAULT 0,
  token_output INTEGER NOT NULL DEFAULT 0,
  costo NUMERIC(10,5),
  passi INTEGER NOT NULL DEFAULT 0,
  voto SMALLINT,
  iniziata_il TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  finita_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS tracce_agente ON tracce (agente_id, id DESC);
CREATE INDEX IF NOT EXISTS tracce_padre ON tracce (padre_id);
CREATE INDEX IF NOT EXISTS tracce_data ON tracce (iniziata_il);
CREATE TABLE IF NOT EXISTS tracce_passi (
  id BIGSERIAL PRIMARY KEY,
  traccia_id BIGINT NOT NULL REFERENCES tracce(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('modello','strumento','nota','errore')),
  nome TEXT,
  ingresso TEXT,
  uscita TEXT,
  token_input INTEGER,
  token_output INTEGER,
  millisecondi INTEGER,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS tracce_passi_traccia ON tracce_passi (traccia_id, id);
