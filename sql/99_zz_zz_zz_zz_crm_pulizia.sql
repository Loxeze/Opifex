-- 2.76: responsabili, contatti simili
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS cerca_responsabile BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS cerca_simili BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS ricerca_resp TEXT NOT NULL DEFAULT '';
ALTER TABLE crm_ricerche ADD COLUMN IF NOT EXISTS modo TEXT NOT NULL DEFAULT '';
ALTER TABLE crm_ricerche ADD COLUMN IF NOT EXISTS campagna_id INTEGER REFERENCES campagne_posta(id) ON DELETE SET NULL;
UPDATE crm_ricerche SET modo='email' WHERE dest_ids IS NOT NULL AND modo='';
