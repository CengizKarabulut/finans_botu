"""
Analist Motoru — AI Yorumu
Claude API (Anthropic) kullanır.
Hisse senedi, kripto, döviz, emtia için AI yorumu üretir.
"""

import os
import json
from typing import Optional
from anthropic import Anthropic
import google.generativeai as genai

_anthropic_client = None
_gemini_model = None

def _get_anthropic_client() -> Optional[Anthropic]:
    global _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client

def _get_gemini_model():
    global _gemini_model
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    if _gemini_model is None:
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel('gemini-pro')
    return _gemini_model


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

        # Önce Anthropic dene
        client = _get_anthropic_client()
        if client:
            try:
                yanit = client.messages.create(
                    model="claude-3-haiku-20240307", # Daha hızlı ve ucuz model
                    max_tokens=1024,
                    system=sistem,
                    messages=[{"role": "user", "content": kullanici}]
                )
                return yanit.content[0].text
            except Exception as ae:
                log.warning(f"Anthropic hatası: {ae}, Gemini denenecek...")

        # Anthropic yoksa veya hata verdiyse Gemini dene
        model = _get_gemini_model()
        if model:
            full_prompt = f"{sistem}\n\n{kullanici}"
            response = model.generate_content(full_prompt)
            return response.text

        return "AI yorumu için geçerli bir API anahtarı (Anthropic veya Gemini) bulunamadı."

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

        client = _get_anthropic_client()
        if client:
            try:
                yanit = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=800,
                    system=sistem,
                    messages=[{"role": "user", "content": kullanici}]
                )
                return yanit.content[0].text
            except Exception as ae:
                log.warning(f"Anthropic hatası: {ae}, Gemini denenecek...")

        model = _get_gemini_model()
        if model:
            full_prompt = f"{sistem}\n\n{kullanici}"
            response = model.generate_content(full_prompt)
            return response.text

        return "AI yorumu için geçerli bir API anahtarı bulunamadı."

    except Exception as e:
        return f"AI yorumu alınamadı: {e}"


def ai_tahmin_yap(sembol: str, teknik: dict) -> str:
    """Teknik verilere dayanarak kısa vadeli bir AI tahmini üretir."""
    try:
        sistem = (
            "Sen bir kantitatif finans analistisin. "
            "Verilen teknik göstergeleri analiz ederek kısa vadeli (1-5 gün) bir fiyat tahmini yap. "
            "Tahminini 'Boğa', 'Ayı' veya 'Nötr' olarak belirt ve nedenlerini açıkla. "
            "Türkçe yaz. Kesinlik bildirme, olasılıklar üzerinden konuş. "
            "2-3 paragraf yaz."
        )

        kullanici = (
            f"Sembol: {sembol}\n\n"
            f"TEKNİK GÖSTERGELER:\n{_guvenli_json(teknik)}"
        )

        client = _get_anthropic_client()
        if client:
            try:
                yanit = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=512,
                    system=sistem,
                    messages=[{"role": "user", "content": kullanici}]
                )
                return yanit.content[0].text
            except Exception as ae:
                log.warning(f"Anthropic hatası: {ae}, Gemini denenecek...")

        model = _get_gemini_model()
        if model:
            full_prompt = f"{sistem}\n\n{kullanici}"
            response = model.generate_content(full_prompt)
            return response.text

        return "AI tahmini için geçerli bir API anahtarı bulunamadı."
    except Exception as e:
        return f"AI tahmini alınamadı: {e}"


def ai_nlp_sorgu(mesaj: str) -> str:
    """Kullanıcının doğal dildeki finansal sorusunu yanıtlar."""
    try:
        sistem = (
            "Sen bir finansal asistansın. Kullanıcının finansal sorularını yanıtla. "
            "Eğer soru belirli bir hisse veya piyasa verisi gerektiriyorsa, "
            "kullanıcıya ilgili komutları (/analiz, /teknik vb.) kullanmasını öner. "
            "Genel finansal kavramlar, piyasa terimleri ve stratejiler hakkında bilgi ver. "
            "Türkçe yaz. Yatırım tavsiyesi verme."
        )

        client = _get_anthropic_client()
        if client:
            try:
                yanit = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    system=sistem,
                    messages=[{"role": "user", "content": mesaj}]
                )
                return yanit.content[0].text
            except Exception as ae:
                log.warning(f"Anthropic hatası: {ae}, Gemini denenecek...")

        model = _get_gemini_model()
        if model:
            full_prompt = f"{sistem}\n\n{mesaj}"
            response = model.generate_content(full_prompt)
            return response.text

        return "AI yanıtı için geçerli bir API anahtarı bulunamadı."
    except Exception as e:
        return f"AI yanıtı alınamadı: {e}"
