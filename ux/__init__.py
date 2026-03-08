"""UX modülleri — Kullanıcı arayüzü bileşenleri."""
from .inline_menus import build_analiz_menu, build_close_button
from .i18n import get_text, MESSAGES
from .pagination import paginate, format_paged_list, Page
from .user_prefs import get_user_prefs, set_user_pref

__all__ = [
    "build_analiz_menu", "build_close_button",
    "get_text", "MESSAGES",
    "paginate", "format_paged_list", "Page",
    "get_user_prefs", "set_user_pref",
]
