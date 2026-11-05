"""XML letto da file/siti esterni: stesso uso di ElementTree, ma senza entita' esterne ne' «bombe» di espansione."""
import types
import xml.etree.ElementTree as _ET

try:
    from defusedxml import ElementTree as _D
    _fromstring = _D.fromstring
except ImportError:   # senza defusedxml (non dovrebbe succedere) si rifiutano le dichiarazioni DTD a mano
    def _fromstring(testo, *a, **k):
        t = testo if isinstance(testo, (bytes, bytearray)) else str(testo).encode("utf-8", "ignore")
        if b"<!ENTITY" in t or b"<!DOCTYPE" in t:
            raise _ET.ParseError("XML con DTD/entita' rifiutato")
        return _ET.fromstring(testo, *a, **k)

ET = types.SimpleNamespace(**{k: getattr(_ET, k) for k in dir(_ET) if not k.startswith("__")})
ET.fromstring = _fromstring
