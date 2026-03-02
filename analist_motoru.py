"""
Analist Motoru — AI Yorumu
Claude API (Anthropic) kullanır.
Hisse senedi, kripto, döviz, emtia için AI yorumu üretir.
"""

import os
import json
from anthropic import Anthropic

_client = None

def _ai_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY",""))
    return _client


def _guvenli_json(veriler: dict) -> str:
    temiz = {}
    for k, v in veriler.items():
        if k.startswith("__") and k.endswith("__"):
            continue  # dahili key'leri gizle
        if isinstance(v, (str, int, float, bool, type(None))):
            temiz[k] = v
        else:
            temiz[k] = str(v)
    return json.dumps(temiz, ensure_ascii=False, indent=2)[:6000]


def ai_analist_yorumu(sembol: str, temel: dict, teknik: dict) -> str:
    """
    Hisse senedi için AI analist yorumu üretir.
    temel dict içinde '__haberler__' key'i varsa haberleri de değerlendirir.
    """
    try:
        haber_bolumu = ""
        haberler = temel.get("__haberler__", "")
        if haberler:
            haber_bolumu = f"\n\nSON HABERLER (özet):\n{haberler[:1500]}"

        temel_temiz = {k: v for k, v in temel.items()
                       if not (k.startswith("__") and k.endswith("__"))}

        sistem = (
            "Sen deneyimli bir finans analistsin. "
            "Verilen hisse senedi verilerini analiz ederek kısa, net ve yapıcı bir yorum yap. "
            "Türkçe yaz. Tavsiye değil, analiz sun. "
            "Güçlü yönler, riskler ve öne çıkan metrikler hakkında yorum yap. "
            "3-5 paragraf yaz, başlık kullanma."
        )

        kullanici = (
            f"Hisse: {sembol}\n\n"
            f"TEMEL VERİLER:\n{_guvenli_json(temel_temiz)}\n\n"
            f"TEKNİK VERİLER:\n{_guvenli_json(teknik)}"
            f"{haber_bolumu}"
        )

        yanit = _ai_client().messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=sistem,
            messages=[{"role": "user", "content": kullanici}]
        )
        return yanit.content[0].text

    except Exception as e:
        return f"AI yorumu alınamadı: {e}"


def ai_piyasa_yorumu(sembol: str, tip: str, piyasa: dict, teknik: dict) -> str:
    """
    Kripto, döviz veya emtia için AI yorumu üretir.
    """
    try:
        tip_map = {
            "kripto": "kripto para",
            "doviz":  "döviz paritesi",
            "emtia":  "emtia",
        }
        tip_ad = tip_map.get(tip, tip)

        sistem = (
            f"Sen deneyimli bir finans analistsin. "
            f"Verilen {tip_ad} verilerini analiz ederek kısa, net bir yorum yap. "
            f"Türkçe yaz. Tavsiye değil, analiz sun. "
            f"Teknik göstergeler, trend ve öne çıkan faktörler hakkında yorum yap. "
            f"2-4 paragraf yaz, başlık kullanma."
        )

        kullanici = (
            f"Sembol: {sembol} ({tip_ad})\n\n"
            f"PİYASA VERİLERİ:\n{_guvenli_json(piyasa)}\n\n"
            f"TEKNİK VERİLER:\n{_guvenli_json(teknik)}"
        )

        yanit = _ai_client().messages.create(
            model="claude-opus-4-5",
            max_tokens=800,
            system=sistem,
            messages=[{"role": "user", "content": kullanici}]
        )
        return yanit.content[0].text

    except Exception as e:
        return f"AI yorumu alınamadı: {e}"
