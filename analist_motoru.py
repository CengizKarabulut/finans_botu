"""
Analist Motoru — AI Yorumu
Claude (Anthropic), Gemini (Google) ve Groq (Llama3) desteği.
✅ PROFESYONEL VERSİYON - Proxy hatası giderildi, fallback mekanizması güçlendirildi.
"""
import os
import json
import logging
import asyncio
from typing import Optional
from anthropic import Anthropic
import google.generativeai as genai
from groq import Groq

log = logging.getLogger("finans_botu")

_anthropic_client = None
_gemini_model = None
_groq_client = None

def _get_anthropic_client():
    global _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key: return None
    if _anthropic_client is None:
        try:
            # FIX: Anthropic client'da proxy hatasını önlemek için temiz başlatma
            # 'proxies' argümanı gönderilmiyor.
            _anthropic_client = Anthropic(api_key=api_key)
        except Exception as e:
            log.error(f"Anthropic client başlatılamadı: {e}")
            return None
    return _anthropic_client

def _get_gemini_model():
    global _gemini_model
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: return None
    if _gemini_model is None:
        try:
            genai.configure(api_key=api_key)
            _gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            log.error(f"Gemini başlatılamadı: {e}")
            return None
    return _gemini_model

def _get_groq_client():
    global _groq_client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key: return None
    if _groq_client is None:
        try:
            _groq_client = Groq(api_key=api_key)
        except Exception as e:
            log.error(f"Groq başlatılamadı: {e}")
            return None
    return _groq_client

def _guvenli_json(veriler: dict) -> str:
    if not veriler: return "{}"
    temiz = {}
    for k, v in veriler.items():
        if k.startswith("__") and k.endswith("__"): continue
        if isinstance(v, (str, int, float, bool, type(None))):
            temiz[k] = v
        else:
            temiz[k] = str(v)
    return json.dumps(temiz, ensure_ascii=False, indent=2)[:6000]

async def ai_analiz_uret(sistem_prompt: str, kullanici_prompt: str, max_tokens: int = 1024) -> str:
    """Çoklu AI desteği ile analiz üretir (Anthropic -> Groq -> Gemini)."""
    
    # 1. Anthropic (Claude)
    client = _get_anthropic_client()
    if client:
        try:
            # Anthropic kütüphanesi senkron çalışır, executor ile sarmalayalım
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=max_tokens,
                system=sistem_prompt,
                messages=[{"role": "user", "content": kullanici_prompt}]
            ))
            return response.content[0].text
        except Exception as e:
            log.warning(f"Anthropic hatası: {e}, Groq denenecek...")

    # 2. Groq (Llama 3)
    groq = _get_groq_client()
    if groq:
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: groq.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": sistem_prompt},
                    {"role": "user", "content": kullanici_prompt}
                ],
                max_tokens=max_tokens
            ))
            return response.choices[0].message.content
        except Exception as e:
            log.warning(f"Groq hatası: {e}, Gemini denenecek...")

    # 3. Gemini
    gemini = _get_gemini_model()
    if gemini:
        try:
            full_prompt = f"{sistem_prompt}\n\n{kullanici_prompt}"
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: gemini.generate_content(full_prompt))
            return response.text
        except Exception as e:
            log.error(f"Gemini hatası: {e}")

    return "Üzgünüm, şu an hiçbir AI motoruna ulaşılamıyor. Lütfen API anahtarlarınızı kontrol edin."

async def ai_analist_yorumu(sembol: str, temel: dict, teknik: dict) -> str:
    sistem = (
        "Sen deneyimli bir finans analistsin. Verilen verileri analiz ederek profesyonel bir yorum yap. "
        "Türkçe yaz. Tavsiye değil, analiz sun. 3-5 paragraf yaz, başlık kullanma."
    )
    kullanici = f"Hisse: {sembol}\n\nTEMEL VERİLER:\n{_guvenli_json(temel)}\n\nTEKNİK VERİLER:\n{_guvenli_json(teknik)}"
    return await ai_analiz_uret(sistem, kullanici)

async def ai_piyasa_yorumu(sembol: str, tip: str, piyasa: dict, teknik: dict) -> str:
    tip_ad = {"kripto": "kripto para", "doviz": "döviz paritesi", "emtia": "emtia"}.get(tip, tip)
    sistem = f"Sen deneyimli bir finans analistsin. Verilen {tip_ad} verilerini analiz et. Türkçe yaz. 2-4 paragraf."
    kullanici = f"Sembol: {sembol} ({tip_ad})\n\nPİYASA VERİLERİ:\n{_guvenli_json(piyasa)}\n\nTEKNİK VERİLER:\n{_guvenli_json(teknik)}"
    return await ai_analiz_uret(sistem, kullanici)

async def ai_tahmin_yap(sembol: str, teknik: dict) -> str:
    sistem = "Sen bir kantitatif finans analistisin. Teknik verilere göre 1-5 günlük tahmin yap. Boğa/Ayı/Nötr belirt."
    kullanici = f"Sembol: {sembol}\n\nTEKNİK GÖSTERGELER:\n{_guvenli_json(teknik)}"
    return await ai_analiz_uret(sistem, kullanici, max_tokens=512)

async def ai_nlp_sorgu(mesaj: str) -> str:
    sistem = "Sen bir finansal asistansın. Kullanıcının sorularını yanıtla. Yatırım tavsiyesi verme."
    return await ai_analiz_uret(sistem, mesaj)
