-- Gestione agenti da interfaccia: limiti, accesso al web, connessioni ad app e siti
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS max_token_risposta INTEGER NOT NULL DEFAULT 1500
  CHECK (max_token_risposta BETWEEN 100 AND 8000);
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS budget_token_mensile BIGINT CHECK (budget_token_mensile > 0);
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS accesso_web BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS siti_consentiti TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS max_ricerche INTEGER NOT NULL DEFAULT 3
  CHECK (max_ricerche BETWEEN 1 AND 10);

-- Ricerca web attiva di default per chi cerca bandi e opportunita' (dati pubblici per natura)
UPDATE agenti SET accesso_web = TRUE WHERE nome IN ('Scout', 'Radar', 'Tendenze');

-- App e siti collegabili agli agenti (Canva, siti web, ecc.)
CREATE TABLE IF NOT EXISTS connessioni (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,
  tipo TEXT NOT NULL DEFAULT 'sito' CHECK (tipo IN ('sito', 'app', 'altro')),
  indirizzo TEXT,
  descrizione TEXT,
  stato TEXT NOT NULL DEFAULT 'da_configurare' CHECK (stato IN ('da_configurare', 'attiva', 'spenta')),
  creata_il TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agenti_connessioni (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  connessione_id INTEGER NOT NULL REFERENCES connessioni(id) ON DELETE CASCADE,
  PRIMARY KEY (agente_id, connessione_id)
);
