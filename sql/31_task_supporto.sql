-- Task: manager di supporto (consiglia come svolgere l'attivita' e come alleggerire il lavoro)
ALTER TABLE task ADD COLUMN IF NOT EXISTS supporto_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL;
ALTER TABLE task_documenti ADD COLUMN IF NOT EXISTS caricato_qui BOOLEAN NOT NULL DEFAULT FALSE;
