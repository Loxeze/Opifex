-- 1.33.0: agenti che vedono tutti i siti e hosting salvati (es. il Capo sviluppo), senza doverli assegnare uno per uno
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS siti_tutti BOOLEAN NOT NULL DEFAULT FALSE;
