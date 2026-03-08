# 🔍 Finans Botu — Kapsamlı Kod İnceleme ve Düzeltme Raporu

**Tarih:** 2026-03-07  
**Analist:** Senior Staff Software Architect — FinTech Security  
**Repo:** CengizKarabulut/finans_botu  
**Toplam Satır:** ~5827 LOC (Python)  
**Mimari:** Telegram Bot (aiogram 3.x) + yFinance + Multi-AI Backend + SQLite

---

## 📋 1. GENEL MİMARİ DEĞERLENDİRME

Proje, Telegram üzerinden çalışan bir finans analiz botudur. Temel analiz, teknik analiz, AI yorumlama, portföy takibi, fiyat uyarıları ve TradingView grafik çekimi gibi kapsamlı özellikler içerir.

**Güçlü Yönler:**
- Modüler yapı (security/, monitoring/, ux/ paketleri)
- Pydantic Settings ile tip güvenli konfigürasyon
- Circuit Breaker deseni ile API dayanıklılığı
- Sliding Window rate limiting
- Audit logging altyapısı
- Decimal hassasiyeti ile finansal veri saklama

**Kritik Sorunlar (Düzeltildi):**
- `ux/__init__.py` dosyasında `build_analiz_menu` ve `build_close_button` iki kez tanımlanıyor (inline_menus.py ile çakışma)
- `security/__init__.py`'den `log_query` export'u eksik
- `veri_motoru.py`'de `coingecko_fiyat` fonksiyonu tanımlı değil ama `piyasa_analiz.py`'den import ediliyor
- `config.py` modül düzeyinde `Settings()` çağrısı `.env` olmadan crash ediyor
- `conftest.py`'de deprecated `event_loop` fixture kullanımı
- `db.py`'de `_lock = asyncio.Lock()` modül düzeyinde çağrılıyor — event loop yokken sorun yaratır
- `backtest_motoru.py`'de `yf.download` MultiIndex column hatası
- `cache_yonetici.py`'de SQL Injection riski (table name validation zayıf)
- `tradingview_motoru.py` credential'ları environment'tan çekerken güvenlik riski

---

## 🔐 2. GÜVENLİK ANALİZİ

### 2.1 KRİTİK — SQL Injection Riski (cache_yonetici.py)

```python
# ÖNCEKİ (ZAYIF):
if not tablo.isidentifier():
    continue
cur.execute(f'DELETE FROM "{tablo}" WHERE UPPER(symbol) LIKE ?', (f"%{temiz}%",))
```

`isidentifier()` kontrolü Türkçe karakterleri kabul eder ve tablo adı doğrulaması yeterli değildir. `"{tablo}"` hâlâ injection vektörü olabilir.

**DÜZELTİLDİ:** Regex-based tablo adı validasyonu eklendi.

### 2.2 ORTA — Callback Data Injection (main.py)

```python
sembol = callback.data.split(":")[2]  # Kullanıcı manipüle edebilir
```

Callback data'dan gelen sembol doğrulanmadan kullanılıyor.

**DÜZELTİLDİ:** Callback handler'larda `validate_symbol` kontrolü eklendi.

### 2.3 ORTA — Uyarı Silme Yetkilendirme Eksikliği (main.py)

```python
# ÖNCEKİ: Herhangi bir kullanıcı herhangi bir uyarı ID'sini silebilir
async def komut_uyari_sil(message: Message):
    uyari_id = int(parcalar[1])
    await uyari_sil(uyari_id)  # Yetkilendirme YOK!
```

**DÜZELTİLDİ:** `uyari_sil` fonksiyonuna `user_id` parametresi eklendi.

### 2.4 DÜŞÜK — BOT_TOKEN Log'lanma Riski

`config.py`'deki `startup_log()` BOT_TOKEN'un varlığını `✅/❌` ile logluyor, ama token'ın kendisi asla loglanmıyor — bu doğru. Ancak `Settings` modeli `.env`'den token'ı okurken hata mesajlarında token sızabilir.

### 2.5 DÜŞÜK — Rate Limiter Memory Leak

`SlidingWindowRateLimiter.user_requests` dictionary'si hiçbir zaman temizlenmiyor. Uzun süreli çalışmada tüm user_id'ler bellekte kalır.

**DÜZELTİLDİ:** Periyodik temizleme mekanizması eklendi.

---

## ⚡ 3. PERFORMANS ANALİZİ

### 3.1 KRİTİK — Senkron yFinance Çağrıları Thread Pool'da

`teknik_analiz_yap` ve `temel_analiz_yap` fonksiyonları senkron olmasına rağmen `run_in_executor`'da çalıştırılıyor. Bu doğru bir yaklaşım, ancak `ThreadPoolExecutor` default pool boyutu limitsiz olduğundan, yoğun trafikte thread exhaustion riski var.

**DÜZELTİLDİ:** Global bounded executor eklendi.

### 3.2 ORTA — Tekrarlayan API Çağrıları (alert_motoru.py)

Uyarı döngüsünde `teknik_analiz_yap` tam teknik analiz hesaplıyor — sadece RSI gerektiğinde bile. Bu gereksiz CPU ve API kullanımı demek.

**Öneri:** RSI-only hesaplama fonksiyonu ayrılmalı.

### 3.3 ORTA — Singleton DB Connection Riski

`aiosqlite` single connection concurrent write'larda `database is locked` hatası verebilir. WAL mode etkinleştirilmeli.

**DÜZELTİLDİ:** `PRAGMA journal_mode=WAL` ve `busy_timeout` eklendi.

### 3.4 DÜŞÜK — yFinance 3 Yıllık Veri Çekimi

`teknik_analiz_yap` `period="3y"` çekiyor ama 610 bar'dan fazlasına ihtiyaç yok. Bu gereksiz network ve memory kullanımı.

---

## 🐛 4. HATA DÜZELTMELERİ (Diff Analizi)

### 4.1 `ux/__init__.py` — Çift Tanımlama Sorunu

**Sorun:** Dosya, `inline_menus.py`'nin tamamını (fonksiyon tanımlarıyla birlikte) içeriyor. `from ux.inline_menus import build_analiz_menu` ile `ux/__init__.py`'deki tanımlar çakışıyor.

**Düzeltme:** `__init__.py` yalnızca re-export yapmalı.

### 4.2 `veri_motoru.py` — Eksik `coingecko_fiyat` Fonksiyonu

`piyasa_analiz.py` satır 166'da `from veri_motoru import coingecko_fiyat` yapıyor ama bu fonksiyon tanımlı değil.

**Düzeltme:** Fonksiyon eklendi (CoinGecko Free API).

### 4.3 `config.py` — `.env` Olmadan Crash

`settings = Settings()` modül import edildiğinde çalışır. `.env` yoksa ve `BOT_TOKEN` env'de yoksa `ValidationError` fırlatır ve tüm modüller import edilemez.

**Düzeltme:** Default BOT_TOKEN değeri eklendi, `validate_startup()` ile kontrol ayrıldı.

### 4.4 `db.py` — Event Loop'suz Lock Oluşturma

```python
class DBPool:
    _lock = asyncio.Lock()  # Modül yüklendiğinde event loop yoksa hata!
```

Python 3.10+'da bu deprecated ve uyarı veriyor.

**Düzeltme:** Lazy initialization pattern.

### 4.5 `backtest_motoru.py` — MultiIndex Column Hatası

`yf.download()` yfinance >= 0.2.x'te MultiIndex column döner. `df['Close']` doğrudan erişim hata verir.

**Düzeltme:** `auto_adjust=True` ve column flattening.

### 4.6 `conftest.py` — Deprecated Fixture

`event_loop` fixture pytest-asyncio >= 0.21'de deprecated.

**Düzeltme:** Kaldırıldı, `asyncio_mode = auto` yeterli.

---

## 🧪 5. EK UNIT TEST'LER

Aşağıdaki kritik fonksiyonlar için eksik testler eklendi:

- `validate_symbol` — Edge case'ler (6 harfli BIST, GOOGL vs ASELS ayrımı)
- `sanitize_text` — SQL injection karakterleri
- `_parse_fiyat` — Büyük Türk formatı (1.000.000,99)
- `CircuitBreaker` — HALF_OPEN → CLOSED recovery
- `Rate Limiter` — Window expiry sonrası reset

---

## 📊 6. DÜZELTME ÖZETİ

| Dosya | Sorun | Ciddiyet | Durum |
|-------|-------|----------|-------|
| `ux/__init__.py` | Çift fonksiyon tanımı | KRİTİK | ✅ Düzeltildi |
| `veri_motoru.py` | Eksik coingecko_fiyat | KRİTİK | ✅ Eklendi |
| `config.py` | .env olmadan crash | KRİTİK | ✅ Düzeltildi |
| `db.py` | Event loop'suz Lock | YÜKSEK | ✅ Düzeltildi |
| `db.py` | WAL mode eksik | ORTA | ✅ Eklendi |
| `db.py` | Uyarı silme yetki eksik | ORTA | ✅ Düzeltildi |
| `cache_yonetici.py` | SQL injection riski | YÜKSEK | ✅ Düzeltildi |
| `main.py` | Callback data injection | ORTA | ✅ Düzeltildi |
| `backtest_motoru.py` | MultiIndex column | YÜKSEK | ✅ Düzeltildi |
| `conftest.py` | Deprecated fixture | DÜŞÜK | ✅ Düzeltildi |
| `rate_limiter.py` | Memory leak | DÜŞÜK | ✅ Düzeltildi |
| `requirements.txt` | Versiyon pinleme eksik | ORTA | ✅ Düzeltildi |
