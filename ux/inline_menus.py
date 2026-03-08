"""
ux/inline_menus.py — Bot içi interaktif menüler.
✅ PROFESYONEL VERSİYON - Callback data formatı main.py ile uyumlu hale getirildi.
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def build_analiz_menu(sembol: str) -> InlineKeyboardMarkup:
    """Analiz özeti altındaki ana menü."""
    builder = InlineKeyboardBuilder()
    
    # 1. Satır: Analizler
    builder.row(
        InlineKeyboardButton(text="📊 Temel", callback_data=f"analiz:temel:{sembol}"),
        InlineKeyboardButton(text="📉 Teknik", callback_data=f"analiz:teknik:{sembol}"),
        InlineKeyboardButton(text="🤖 AI Yorum", callback_data=f"analiz:ai:{sembol}")
    )
    
    # 2. Satır: Grafik ve Favori
    builder.row(
        InlineKeyboardButton(text="📈 Grafik", callback_data=f"grafik:{sembol}"),
        InlineKeyboardButton(text="⭐ Favori", callback_data=f"favori:toggle:{sembol}")
    )
    
    # 3. Satır: Kapat
    builder.row(
        InlineKeyboardButton(text="❌ Kapat", callback_data="close")
    )
    
    return builder.as_markup()

def build_close_button() -> InlineKeyboardMarkup:
    """Sadece kapat butonu."""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="❌ Kapat", callback_data="close"))
    return builder.as_markup()
