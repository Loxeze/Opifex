-- Agente con cui Lorenzo sta parlando su Telegram (NULL = Aurora)
ALTER TABLE canale_telegram ADD COLUMN IF NOT EXISTS agente_corrente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL;
