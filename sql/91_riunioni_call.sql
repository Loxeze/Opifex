-- 1.67.0: riunioni vocali con i manager (call) - una voce per ogni manager
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS voce_id TEXT;
ALTER TABLE tavoli ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'tavolo';
ALTER TABLE tavoli DROP CONSTRAINT IF EXISTS tavoli_tipo_check;
ALTER TABLE tavoli ADD CONSTRAINT tavoli_tipo_check CHECK (tipo IN ('tavolo','call'));
ALTER TABLE tavoli ADD COLUMN IF NOT EXISTS programmata_il TIMESTAMPTZ;
ALTER TABLE tavoli ADD COLUMN IF NOT EXISTS occupato BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tavoli DROP CONSTRAINT IF EXISTS tavoli_stato_check;
ALTER TABLE tavoli ADD CONSTRAINT tavoli_stato_check CHECK (stato IN ('programmata','in_corso','conclusa','errore'));
ALTER TABLE tavoli_interventi ADD COLUMN IF NOT EXISTS da_utente BOOLEAN NOT NULL DEFAULT FALSE;
