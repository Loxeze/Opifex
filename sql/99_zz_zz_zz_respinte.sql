-- 2.71: email respinte, ricerca di un'email nuova, tetto per casella
CREATE TABLE IF NOT EXISTS email_bloccate (
  email_hash TEXT PRIMARY KEY,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  campagna_id INTEGER REFERENCES campagne_posta(id) ON DELETE SET NULL,
  motivo TEXT NOT NULL DEFAULT '',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS cerca_email_nuova BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS ricerca_email TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest DROP CONSTRAINT IF EXISTS campagne_posta_dest_stato_check;
ALTER TABLE campagne_posta_dest ADD CONSTRAINT campagne_posta_dest_stato_check CHECK (stato IN (
  'in_attesa', 'in_studio', 'da_approvare', 'approvata', 'inviata', 'scartata', 'errore',
  'risposto', 'interessato', 'non_interessato', 'rimosso', 'nessuna_risposta', 'respinto'));
CREATE INDEX IF NOT EXISTS campagne_posta_dest_ricerca ON campagne_posta_dest (ricerca_email) WHERE ricerca_email <> '';
ALTER TABLE crm_ricerche ADD COLUMN IF NOT EXISTS dest_ids INTEGER[];
-- gli inviti del calendario gia' raccolti escono dalle email da vedere
UPDATE posta_vaglio SET categoria='scartabile', imparata='invito del calendario (va gia'' nel calendario)'
 WHERE categoria IN ('da_vagliare','importante','normale') AND NOT letta
   AND oggetto ~* '^\s*(invito|invitation|invito aggiornato|updated invitation|accettato|accepted|rifiutato|declined|tentative|proposta di nuovo orario|new time proposed|evento annullato|canceled event|cancelled event)\M.*(@|\d{1,2}[:.]\d{2})';
