"""Inline keyboard factories for quick actions."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def build_analiz_menu(sembol: str, komut: str = "analiz") -> InlineKeyboardMarkup:
    """Analiz sonucu için inline keyboard."""
    builder = InlineKeyboardBuilder()
    
    # Temel/Teknik/AI switch
    builder.row(
        InlineKeyboardButton(text="📊 Temel", callback_data=f"analiz:temel:{sembol}"),
        InlineKeyboardButton(text="📉 Teknik", callback_data=f"analiz:teknik:{sembol}"),
        InlineKeyboardButton(text="🤖 AI", callback_data=f"analiz:ai:{sembol}"),
    )
    
    # Aksiyon butonları
    builder.row(
        InlineKeyboardButton(text="⭐ Favori", callback_data=f"favori:toggle:{sembol}"),
        InlineKeyboardButton(text="🔔 Uyarı", callback_data=f"uyari:set:{sembol}"),
        InlineKeyboardButton(text="📈 Grafik", callback_data=f"grafik:{sembol}"),
    )
    
    # Haber & Insider
    builder.row(
        InlineKeyboardButton(text="📰 Haberler", callback_data=f"haber:{sembol}"),
        InlineKeyboardButton(text="🔍 Insider", callback_data=f"insider:{sembol}"),
    )
    
    return builder.as_markup()

def build_piyasa_menu(tip: str, sembol: str) -> InlineKeyboardMarkup:
    """Kripto/döviz/emtia için inline keyboard."""
    builder = InlineKeyboardBuilder()
    
    emoji = {"kripto": "₿", "doviz": "💱", "emtia": "🏭"}.get(tip, "📊")
    
    builder.row(
        InlineKeyboardButton(text=f"{emoji} Analiz", callback_data=f"piyasa:analiz:{tip}:{sembol}"),
        InlineKeyboardButton(text="🔔 Uyarı", callback_data=f"uyari:set:{sembol}"),
    )
    
    if tip == "kripto":
        builder.row(
            InlineKeyboardButton(text="🌐 CoinGecko", url=f"https://coingecko.com/coins/{sembol.lower()}"),
        )
    
    return builder.as_markup()

def build_pagination_menu(current_page: int, total_pages: int, 
                         callback_prefix: str, extra_data: str = "") -> InlineKeyboardMarkup:
    """Sayfalama için inline keyboard."""
    builder = InlineKeyboardBuilder()
    
    if total_pages > 1:
        # Önceki buton
        if current_page > 1:
            builder.add(InlineKeyboardButton(
                text="⬅️", 
                callback_data=f"{callback_prefix}:prev:{current_page-1}:{extra_data}"
            ))
        
        # Sayfa bilgisi
        builder.add(InlineKeyboardButton(
            text=f"{current_page}/{total_pages}", 
            callback_data="noop"
        ))
        
        # Sonraki buton
        if current_page < total_pages:
            builder.add(InlineKeyboardButton(
                text="➡️", 
                callback_data=f"{callback_prefix}:next:{current_page+1}:{extra_data}"
            ))
        
        builder.adjust(3)
    
    # Kapat butonu
    builder.row(InlineKeyboardButton(text="✖️ Kapat", callback_data="close"))
    
    return builder.as_markup()

def build_user_prefs_menu() -> InlineKeyboardMarkup:
    """Kullanıcı tercihleri menüsü."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="💱 Para Birimi: TL", callback_data="pref:currency:TRY"),
        InlineKeyboardButton(text="💱 Para Birimi: USD", callback_data="pref:currency:USD"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Varsayılan: Temel", callback_data="pref:default:temel"),
        InlineKeyboardButton(text="📊 Varsayılan: Teknik", callback_data="pref:default:teknik"),
    )
    builder.row(
        InlineKeyboardButton(text="🔔 Bildirim: Açık", callback_data="pref:notify:on"),
        InlineKeyboardButton(text="🔔 Bildirim: Kapalı", callback_data="pref:notify:off"),
    )
    builder.row(InlineKeyboardButton(text="✅ Kaydet", callback_data="prefs:save"))
    
    return builder.as_markup()
