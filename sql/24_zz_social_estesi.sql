-- YouTube, Threads e X come canali nativi; rimozione di Buffer.
ALTER TABLE account_social DROP CONSTRAINT IF EXISTS account_social_provider_check;
ALTER TABLE account_social ADD CONSTRAINT account_social_provider_check CHECK (provider IN ('meta', 'linkedin', 'tiktok', 'pinterest', 'youtube', 'threads', 'x'));
ALTER TABLE canali_nativi DROP CONSTRAINT IF EXISTS canali_nativi_rete_check;
ALTER TABLE canali_nativi ADD CONSTRAINT canali_nativi_rete_check CHECK (rete IN ('instagram', 'facebook', 'linkedin', 'tiktok', 'pinterest', 'youtube', 'threads', 'x'));

-- Buffer non c'e' piu': via la chiave salvata, le assegnazioni dei suoi canali e i post che aspettavano di passare da li' (lo storico resta)
DELETE FROM impostazioni_sistema WHERE chiave IN ('buffer_chiave_cifrata', 'buffer_organizzazione_id');
UPDATE post_social SET stato = 'rifiutato', nota = 'Buffer non e'' piu'' collegato a Opifex: ricrea il post su un canale diretto'
 WHERE stato IN ('da_approvare', 'errore') AND canale_id NOT LIKE 'n:%';
