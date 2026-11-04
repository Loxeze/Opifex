-- Interruttore per agente: puo' consultare singoli contatti del CRM, fare ricerche online su di loro e preparare email personalizzate (in coda per l'approvazione).
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS crm_nominativo BOOLEAN NOT NULL DEFAULT FALSE;
