-- Casella Gmail gestita da un agente (account Google collegato con il servizio Gmail). Solo lettura e bozze: l'invio resta umano.
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS gmail_account_id INTEGER REFERENCES account_google(id) ON DELETE SET NULL;
