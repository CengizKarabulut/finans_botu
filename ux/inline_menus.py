"""Inline keyboard factories — Hızlı aksiyon butonları."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def build_analiz_menu(sembol: str) -> InlineKeyboardMarkup:
    """Analiz sonucu için inline keyboard."""
    builder = InlineKeyboardBuilder()
    
    # Üst Satır: Analiz Tipleri
    builder.row(
        InlineKeyboardButton(text="📊 Temel", callback_data=f"analiz:temel:{sembol}"),
        InlineKeyboardButton(text="📉 Teknik", callback_data=f"analiz:teknik:{sembol}"),
        InlineKeyboardButton(text="🤖 AI", callback_data=f"analiz:ai:{sembol}"),
    )
    
    # Orta Satır: Hızlı Aksiyonlar
    builder.row(
        InlineKeyboardButton(text="📈 Grafik", callback_data=f"grafik:{sembol}"),
        InlineKeyboardButton(text="⭐ Favori", callback_data=f"favori:toggle:{sembol}"),
        InlineKeyboardButton(text="🔔 Uyarı", callback_data=f"uyari:set:{sembol}"),
    )
    
    # Alt Satır: Kapat
    builder.row(
        InlineKeyboardButton(text="✖️ Kapat", callback_data="close")
    )
    
    return builder.as_markup()

def build_close_button() -> InlineKeyboardMarkup:
    """Sadece kapat butonu."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖️ Kapat", callback_data="close"))
    return builder.as_markup()
