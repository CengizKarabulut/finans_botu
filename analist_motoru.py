"""
analist_motoru.py — AI tabanlı finansal analiz ve NLP asistanı.
✅ MİMARİ GÜNCELLEME - Insider & Earnings Context, Robust Fallback ve Gelişmiş Prompt.
"""
import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any
from anthropic import Anthropic
from groq import Groq
import google.generativeai as genai

log = logging.getLogger("finans_botu")

# ═══════════════════════════════════════════════════════════════
# YARDIMCILAR
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# ANA AI ÜRETİM MOTORU
# ═══════════════════════════════════════════════════════════════

async def ai_analiz_uret(sistem_prompt: str, kullanici_prompt: str, max_tokens: int = 1024) -> str:
    """Çoklu AI desteği ile analiz üretir (Anthropic -> Groq -> Gemini)."""
    
    # 1. Anthropic (Claude)
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if claude_key:
        try:
            client = Anthropic(api_key=claude_key)
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
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        # Mevcut Groq modelleri sırayla denenir
        groq_models = ["llama-3.3-70b-versatile", "llama3-70b-8192", "llama3-8b-8192"]
        for groq_model in groq_models:
            try:
                client = Groq(api_key=groq_key)
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=groq_model,
                    messages=[
                        {"role": "system", "content": sistem_prompt},
                        {"role": "user", "content": kullanici_prompt}
                    ],
                    max_tokens=max_tokens
                ))
                return response.choices[0].message.content
            except Exception as e:
                log.warning(f"Groq ({groq_model}) hatası: {e}, sıradaki deneniyor...")
        log.warning("Tüm Groq modelleri başarısız, Gemini denenecek...")

    # 3. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        # Mevcut Gemini modelleri sırayla denenir
        gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-flash-latest"]
        for gemini_model in gemini_models:
            try:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(gemini_model)
                full_prompt = f"{sistem_prompt}\n\n{kullanici_prompt}"
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: model.generate_content(full_prompt))
                return response.text
            except Exception as e:
                log.warning(f"Gemini ({gemini_model}) hatası: {e}, sıradaki deneniyor...")
        log.error("Tüm Gemini modelleri başarısız.")

    return "Üzgünüm, şu an hiçbir AI motoruna ulaşılamıyor. Lütfen API anahtarlarınızı kontrol edin."

# ═══════════════════════════════════════════════════════════════
# ANALİZ FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════

async def ai_analist_yorumu(sembol: str, temel: dict, teknik: dict, insider: dict = None, earnings: dict = None) -> str:
    """Hisse senedi için kapsamlı AI yorumu oluşturur."""
    sistem = (
        "Sen profesyonel bir borsa analisti ve trader'sın. Verilen verileri sentezleyerek derinlemesine analiz yap. "
        "Insider alım/satımları ve kazanç beklentilerini mutlaka yorumla. Türkçe yaz. Yatırım tavsiyesi verme."
    )
    kullanici = (
        f"Hisse: {sembol}\n\n"
        f"📊 TEMEL VERİLER:\n{_guvenli_json(temel)}\n\n"
        f"📉 TEKNİK VERİLER:\n{_guvenli_json(teknik)}\n\n"
        f"🕵️ INSIDER VERİLERİ:\n{_guvenli_json(insider) if insider else 'Veri bulunamadı.'}\n\n"
        f"📅 KAZANÇ TAKVİMİ:\n{_guvenli_json(earnings) if earnings else 'Veri bulunamadı.'}"
    )
    return await ai_analiz_uret(sistem, kullanici)

async def ai_tahmin_yap(sembol: str, teknik: dict) -> str:
    """Teknik verilere göre fiyat tahmini yapar."""
    sistem = "Sen bir kantitatif finans analistisin. Teknik verilere göre 1-5 günlük tahmin yap. Boğa/Ayı/Nötr belirt."
    kullanici = f"Sembol: {sembol}\n\nTEKNİK GÖSTERGELER:\n{_guvenli_json(teknik)}"
    return await ai_analiz_uret(sistem, kullanici, max_tokens=512)

async def ai_nlp_sorgu(mesaj: str) -> str:
    """Genel finansal sorular için AI asistanı."""
    sistem = "Sen bir finansal asistansın. Kullanıcının sorularını yanıtla. Yatırım tavsiyesi verme."
    return await ai_analiz_uret(sistem, mesaj)
