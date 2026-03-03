"""Pagination helper for long lists."""
from typing import List, Any, Callable, Optional
from dataclasses import dataclass

@dataclass
class Page:
    """Sayfalama sonucu."""
    items: List[Any]
    current_page: int
    total_pages: int
    total_items: int
    page_size: int
    
    @property
    def has_prev(self) -> bool:
        return self.current_page > 1
    
    @property
    def has_next(self) -> bool:
        return self.current_page < self.total_pages

def paginate(items: List[Any], page: int = 1, page_size: int = 10) -> Page:
    """Listeyi sayfalara böl."""
    if page < 1:
        page = 1
    
    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size  # Ceiling division
    
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    return Page(
        items=items[start_idx:end_idx],
        current_page=page,
        total_pages=total_pages,
        total_items=total_items,
        page_size=page_size,
    )

def format_paged_list(items: List[Any], 
                     formatter: Callable[[Any, int], str],
                     page: Page,
                     header: str = "",
                     footer: str = "") -> str:
    """Sayfalı listeyi formatla."""
    lines = [header] if header else []
    
    for i, item in enumerate(items, start=(page.current_page - 1) * page.page_size + 1):
        lines.append(formatter(item, i))
    
    if page.total_pages > 1:
        lines.append(f"\n📄 Sayfa {page.current_page}/{page.total_pages} ({page.total_items} öğe)")
    
    if footer:
        lines.append(footer)
    
    return "\n".join(lines)
