-- Misure d'uso senza contenuti: uscita dalla pagina con durata misurata dal browser, categoria dell'errore e durata della richiesta.
DO $$
DECLARE c TEXT;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid = 'uso_eventi'::regclass AND contype = 'c' LOOP
    EXECUTE format('ALTER TABLE uso_eventi DROP CONSTRAINT %I', c);
  END LOOP;
END $$;
ALTER TABLE uso_eventi ADD CONSTRAINT uso_eventi_azione_check CHECK (azione IN ('vista', 'errore', 'uscita'));
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS categoria TEXT;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS durata_s INTEGER;
ALTER TABLE uso_eventi ADD COLUMN IF NOT EXISTS durata_ms INTEGER;
