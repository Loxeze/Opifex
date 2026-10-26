ALTER TABLE notifiche ADD COLUMN IF NOT EXISTS critica BOOLEAN NOT NULL DEFAULT FALSE;   -- 1.24.3: passa anche nelle ore di silenzio
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('silenzio_attivo','true'), ('silenzio_da','23:00'), ('silenzio_a','08:00') ON CONFLICT (chiave) DO NOTHING;
