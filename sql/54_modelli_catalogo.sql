-- 1.24.3: catalogo modelli completo, scelta automatica del modello piu' economico per i dialoghi
ALTER TABLE modelli_ai ADD COLUMN IF NOT EXISTS usa_per_dialoghi BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE modelli_ai ADD COLUMN IF NOT EXISTS importato BOOLEAN NOT NULL DEFAULT FALSE;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_modello_automatico', 'true') ON CONFLICT (chiave) DO NOTHING;
-- una sola volta: i dialoghi tornano al modello automatico (il piu' economico) dove era stato scelto uno non economico
UPDATE agenti a SET modello_dialogo = NULL
 WHERE modello_dialogo IS NOT NULL AND modello_dialogo <> ''
   AND EXISTS (SELECT 1 FROM modelli_ai m WHERE m.nome = a.modello_dialogo AND m.fascia <> 'economico')
   AND NOT EXISTS (SELECT 1 FROM impostazioni_sistema WHERE chiave = 'dialoghi_auto_1_24_3');
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('dialoghi_auto_1_24_3', '1') ON CONFLICT (chiave) DO NOTHING;
