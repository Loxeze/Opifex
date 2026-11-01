-- Formazioni riprese dopo un'interruzione (riavvio/aggiornamento mentre Padre Casati lavorava).
ALTER TABLE richieste_formazione ADD COLUMN IF NOT EXISTS riprese INTEGER NOT NULL DEFAULT 0;
