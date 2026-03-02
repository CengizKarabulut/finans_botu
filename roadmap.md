# Finans Botu Yeni Özellikler Yol Haritası

Bu yol haritası, mevcut finans botunun yeteneklerini genişletmek ve kullanıcı deneyimini iyileştirmek için kısa, orta ve uzun vadeli hedefleri özetlemektedir. Amaç, botu daha güçlü, etkileşimli ve kullanıcı dostu bir finansal analiz aracına dönüştürmektir.

## 🎯 Kısa Vadeli Hedefler (0-3 Ay)

Bu aşamada, botun mevcut işlevselliğini güçlendirmeye ve temel kullanıcı ihtiyaçlarını karşılamaya odaklanılacaktır.

### 1. Gelişmiş Bildirim ve Uyarı Sistemi
*   **Özellik**: Kullanıcıların belirli hisse senetleri, kripto paralar veya emtialar için fiyat, hacim veya teknik gösterge (örn. RSI aşırı alım/satım) eşiklerine göre özelleştirilebilir anlık bildirimler alması. [1]
*   **Teknik Detay**: `main.py` içinde zamanlanmış görevler (örneğin `aioschedule` veya `APScheduler` kullanarak) veya TradingView webhook entegrasyonu ile tetiklenecek uyarı mekanizmaları geliştirme. Kullanıcı tercihleri için `db.py` üzerinde yeni tablolar oluşturma.

### 2. Kullanıcı Dostu Komut ve Menü Yapısı
*   **Özellik**: Botun kullanımını kolaylaştırmak için daha sezgisel `/komutlar` ve inline klavye menüleri ekleme. Özellikle sık kullanılan analizler için hızlı erişim sağlama.
*   **Teknik Detay**: `aiogram` kütüphanesinin `InlineKeyboardBuilder` ve `ReplyKeyboardBuilder` özelliklerini kullanarak `main.py` dosyasında menüleri genişletme.

### 3. Hata Yönetimi ve Kullanıcı Geri Bildirimi
*   **Özellik**: Botun beklenmedik hatalarla karşılaştığında kullanıcıya daha bilgilendirici mesajlar sunması ve hata raporlama mekanizması (örn. geliştiriciye otomatik hata mesajı gönderme) eklenmesi.
*   **Teknik Detay**: `main.py` içinde genel hata yakalama blokları (`try-except`) ve `logging` modülünü kullanarak hata detaylarını loglama ve kritik hataları Telegram üzerinden geliştiriciye bildirme.

## 🗓️ Orta Vadeli Hedefler (3-9 Ay)

Bu aşamada, botun analitik yeteneklerini derinleştirmeye ve daha fazla veri kaynağı entegrasyonu sağlamaya odaklanılacaktır.

### 1. TradingView Grafik Entegrasyonu ve Özelleştirme
*   **Özellik**: Kullanıcının istediği teknik göstergelerle (örn. Hareketli Ortalamalar, Bollinger Bantları) özelleştirilmiş TradingView grafiklerinin ekran görüntüsünü alıp gönderme. [2]
*   **Teknik Detay**: Playwright ile TradingView sayfasına giderek, kullanıcı tarafından belirtilen göstergeleri seçme ve grafiğin ekran görüntüsünü alma işlevselliğini `veri_motoru.py` veya yeni bir modülde geliştirme. Gerekirse TradingView API veya Pine Script entegrasyonu araştırma.

### 2. Portföy Takip ve Yönetimi
*   **Özellik**: Kullanıcıların bot üzerinden portföylerini tanımlamasına (hangi hisse/kriptodan ne kadar olduğu) ve anlık değerlerini, kar/zarar durumlarını takip etmesine olanak tanıma.
*   **Teknik Detay**: `db.py` üzerinde kullanıcı portföy bilgilerini saklamak için yeni tablolar oluşturma. `veri_motoru.py` üzerinden güncel fiyatları çekerek portföy değerlemesi yapma ve `main.py` üzerinden kullanıcılara sunma.

### 3. Temel Analiz Veri Kapsamını Genişletme
*   **Özellik**: Şirketlerin finansal tablolarından (gelir tablosu, bilanço, nakit akış) daha detaylı verileri çekerek temel analiz raporlarını zenginleştirme. [3]
*   **Teknik Detay**: SEC EDGAR, Finnhub veya FMP gibi API kaynaklarından daha fazla finansal veri çekmek için `finnhub_veri.py` ve `temel_analiz.py` modüllerini güncelleme.

## 🚀 Uzun Vadeli Hedefler (9+ Ay)

Bu aşamada, botu yapay zeka ve makine öğrenimi ile daha akıllı hale getirmeye ve kapsamlı bir finansal asistan olma yolunda ilerlemeye odaklanılacaktır.

### 1. Yapay Zeka Destekli Tahmin ve Öneri Modülleri
*   **Özellik**: Geçmiş verilere dayanarak fiyat hareketleri veya piyasa trendleri hakkında yapay zeka destekli tahminler sunma (yatırım tavsiyesi olmaksızın). [4]
*   **Teknik Detay**: Makine öğrenimi modelleri (örn. zaman serisi analizi için LSTM) geliştirme. Bu modelleri eğitmek için geçmiş finansal verileri kullanma. `analist_motoru.py` modülünü bu tahminleri yorumlayacak şekilde genişletme.

### 2. Doğal Dil İşleme (NLP) ile Gelişmiş Sorgular
*   **Özellik**: Kullanıcıların daha doğal bir dille soru sormasına ve botun bu soruları anlayıp ilgili finansal verileri veya analizleri sunmasına olanak tanıma.
*   **Teknik Detay**: Kullanıcı girdilerini anlamak için NLP kütüphaneleri (örn. `spaCy`, `NLTK`) veya daha gelişmiş LLM entegrasyonları kullanma. `main.py` içindeki mesaj işleme mantığını bu doğrultuda geliştirme.

### 3. Çoklu Dil Desteği
*   **Özellik**: Botun farklı dillerde (örn. İngilizce, Almanca) hizmet verebilmesi için çoklu dil desteği ekleme.
*   **Teknik Detay**: `gettext` gibi uluslararasılaştırma (i18n) kütüphaneleri kullanarak bot mesajlarını ve çıktılarını farklı dillere çevrilebilir hale getirme.

## Referanslar

[1] Top 7 AI-Powered Telegram Bots in 2025 - Gate.com: [https://www.gate.com/learn/articles/top-seven-telegram-bots/2017](https://www.gate.com/learn/articles/top-seven-telegram-bots/2017)
[2] How to Connect TradingView Alerts to Telegram Bots (100% Free): [https://www.youtube.com/watch?v=JEC5OAaomps](https://www.youtube.com/watch?v=JEC5OAaomps)
[3] AI Implementation: A Strategic Roadmap for Finance Teams - Nominal.so: [https://www.nominal.so/blog/ai-implementation](https://www.nominal.so/blog/ai-implementation)
[4] Fast Finance AI Roadmap: 30-90-365 Plan to Deliver ROI - Everworker.ai: [https://everworker.ai/blog/finance_ai_30_90_365_timeline](https://everworker.ai/blog/finance_ai_30_90_365_timeline)
