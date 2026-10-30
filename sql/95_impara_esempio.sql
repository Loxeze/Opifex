-- 1.72.0: «Impara da un esempio» - Lorenzo incolla una conversazione riuscita (es. con ChatGPT), Padre Casati ne ricava un metodo di lavoro che l'agente usa dopo l'approvazione
CREATE TABLE IF NOT EXISTS esempi_appresi (
  id SERIAL PRIMARY KEY,
  richiesta_id INTEGER REFERENCES richieste_formazione(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
  competenza TEXT NOT NULL,
  obiettivo TEXT NOT NULL DEFAULT '',
  testo TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'in_studio' CHECK (stato IN ('in_studio','da_approvare','errore')),
  errore TEXT,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
