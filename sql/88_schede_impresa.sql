-- 1.64.0: scheda d'impresa - la memoria condivisa di ogni attivita' di Lorenzo (chi siamo, offerta, clienti, tono, regole, numeri...)
CREATE TABLE IF NOT EXISTS schede_impresa (
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  campo TEXT NOT NULL,
  testo TEXT NOT NULL,
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_da TEXT,
  PRIMARY KEY (azienda_id, campo)
);
CREATE TABLE IF NOT EXISTS schede_impresa_versioni (
  id BIGSERIAL PRIMARY KEY,
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  campo TEXT NOT NULL,
  testo TEXT NOT NULL,
  sostituito_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sostituito_da TEXT
);
CREATE INDEX IF NOT EXISTS schede_impresa_versioni_az ON schede_impresa_versioni (azienda_id, campo, id DESC);
CREATE TABLE IF NOT EXISTS schede_impresa_proposte (
  id SERIAL PRIMARY KEY,
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  campo TEXT NOT NULL,
  testo TEXT NOT NULL,
  motivo TEXT,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta','approvata','respinta')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ
);
