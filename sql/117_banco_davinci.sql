-- Il banco sa anche costruire la timeline direttamente in DaVinci Resolve Studio.
ALTER TABLE banco_lavori DROP CONSTRAINT IF EXISTS banco_lavori_tipo_check;
ALTER TABLE banco_lavori ADD CONSTRAINT banco_lavori_tipo_check CHECK (tipo IN ('inventario', 'fotogrammi', 'silenzi', 'ffmpeg', 'xml', 'davinci'));
