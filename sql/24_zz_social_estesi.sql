-- YouTube, Threads e X come canali nativi; rimozione di Buffer.
ALTER TABLE account_social DROP CONSTRAINT IF EXISTS account_social_provider_check;
ALTER TABLE account_social ADD CONSTRAINT account_social_provider_check CHECK (provider IN ('meta', 'linkedin', 'tiktok', 'pinterest', 'youtube', 'threads', 'x'));
ALTER TABLE canali_nativi DROP CONSTRAINT IF EXISTS canali_nativi_rete_check;
ALTER TABLE canali_nativi ADD CONSTRAINT canali_nativi_rete_check CHECK (rete IN ('instagram', 'facebook', 'linkedin', 'tiktok', 'pinterest', 'youtube', 'threads', 'x'));

-- (Buffer: in 2.14.0 era stato tolto, dalla 2.16.1 e' di nuovo disponibile come alternativa; nessuna pulizia da fare qui)
