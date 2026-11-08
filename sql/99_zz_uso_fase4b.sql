-- Correzione 2.36.1: (1) le nuove azioni di misura devono essere ammesse anche dove 99_zz_uso_misure.sql era gia' stata applicata; (2) indici per il registro eventi,
-- che cresce senza limite e veniva letto per intero ad ogni aggiornamento dello stato degli agenti.
DO $$
DECLARE c TEXT;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid = 'uso_eventi'::regclass AND contype = 'c' LOOP
    EXECUTE format('ALTER TABLE uso_eventi DROP CONSTRAINT %I', c);
  END LOOP;
END $$;
ALTER TABLE uso_eventi ADD CONSTRAINT uso_eventi_azione_check CHECK (azione IN ('vista', 'errore', 'uscita', 'clic', 'riprova', 'attesa_inizio', 'attesa_fine', 'contatore_visto', 'contatore_aperto')) NOT VALID;
CREATE INDEX IF NOT EXISTS idx_eventi_tipo_tempo ON eventi_lavoro (tipo, creato_il DESC);
CREATE INDEX IF NOT EXISTS idx_eventi_agente_tipo ON eventi_lavoro (agente_id, tipo, id DESC);
