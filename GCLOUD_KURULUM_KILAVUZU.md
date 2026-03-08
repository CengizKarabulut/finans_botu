# Finans Botu — Google Cloud Ücretsiz Sürüm Kurulum Kılavuzu

Bu kılavuz, `finans_botu` projesini Google Cloud Platform (GCP) üzerindeki ücretsiz `e2-micro` sanal makinesinde çalıştırmak için adım adım talimatlar sunar. Bot, Docker ve Docker Compose kullanılarak izole bir ortamda çalışacak ve kaynak kısıtlamaları göz önünde bulundurularak optimize edilmiştir.

## 🚀 Başlangıç

### Ön Koşullar

Başlamadan önce aşağıdaki gereksinimleri karşıladığınızdan emin olun:

1.  **Google Cloud Hesabı**: Ücretsiz deneme sürümü veya mevcut bir GCP hesabı.
2.  **SSH Erişimi**: GCP Console üzerinden veya `gcloud` CLI ile sanal makinenize SSH erişimi.
3.  **Temel Linux Bilgisi**: Terminal komutlarını çalıştırma ve dosya düzenleme (`nano` veya `vi` gibi) konusunda temel bilgi.

### 1. Sanal Makine Hazırlığı

Google Cloud Console üzerinden yeni bir `e2-micro` sanal makine oluşturun. İşletim sistemi olarak **Ubuntu 22.04 LTS** seçmeniz önerilir.

### 2. Projeyi Klonlama

Sanal makinenize SSH ile bağlandıktan sonra, projenin GitHub deposunu klonlayın:

```bash
git clone https://github.com/CengizKarabulut/finans_botu.git
cd finans_botu
```

### 3. Kurulum Betiğini Çalıştırma

Proje dizinine girdikten sonra, Google Cloud ücretsiz sürüm için özel olarak hazırlanmış kurulum betiğini çalıştırın. Bu betik, Docker'ı kuracak, swap alanı oluşturacak (e2-micro için kritik), proje dosyalarını güncelleyecek ve `.env` dosyasını oluşturacaktır.

```bash
bash gcloud_free_setup.sh
```

Bu betik tamamlandığında, Docker ve Docker Compose yüklü olacak, 2GB'lık bir swap alanı oluşturulacak ve bot için gerekli dizinler (`logs`, `data`) hazırlanmış olacaktır.

## 🔑 API Anahtarlarını Yapılandırma

`gcloud_free_setup.sh` betiği, `.env` adında bir ortam değişkenleri dosyası oluşturur. Botun düzgün çalışması için bu dosyayı kendi API anahtarlarınızla doldurmanız gerekmektedir. En azından `BOT_TOKEN` zorunludur.

`.env` dosyasını düzenlemek için:

```bash
nano .env
```

Örnek `.env` içeriği (kendi anahtarlarınızla doldurun):

```ini
# Telegram Bot Token (Zorunlu)
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN

# AI API Keys (En az biri önerilir)
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GROQ_API_KEY=YOUR_GROQ_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY

# Finansal Veri API Keys (Önerilir)
FINNHUB_API_KEY=YOUR_FINNHUB_API_KEY
COINGECKO_API_KEY=YOUR_COINGECKO_API_KEY
FMP_API_KEY=YOUR_FMP_API_KEY
ALPHAVANTAGE_API_KEY=YOUR_ALPHAVANTAGE_API_KEY
OPENFIGI_API_KEY=YOUR_OPENFIGI_API_KEY

# Uygulama Ayarları
LOG_LEVEL=INFO
DB_PATH=data/bot.db
```

**API Anahtarlarını Nereden Alabilirsiniz?**

*   **Telegram BOT_TOKEN**: BotFather üzerinden yeni bir bot oluşturarak alabilirsiniz.
*   **GEMINI_API_KEY**: Google AI Studio adresinden alabilirsiniz.
*   **GROQ_API_KEY**: GroqCloud adresinden alabilirsiniz.
*   **ANTHROPIC_API_KEY**: Anthropic Console adresinden alabilirsiniz.
*   **FINNHUB_API_KEY**: Finnhub.io adresinden alabilirsiniz.
*   **COINGECKO_API_KEY**: CoinGecko API adresinden alabilirsiniz.
*   **FMP_API_KEY**: Financial Modeling Prep adresinden alabilirsiniz.
*   **ALPHAVANTAGE_API_KEY**: Alpha Vantage adresinden alabilirsiniz.
*   **OPENFIGI_API_KEY**: OpenFIGI adresinden alabilirsiniz.

Değişiklikleri kaydetmek için `Ctrl+X`, `Y` ve `Enter` tuşlarına basın.

## 🐳 Botu Çalıştırma

API anahtarlarınızı yapılandırdıktan sonra botu Docker Compose ile başlatabilirsiniz. Ücretsiz sürüm için optimize edilmiş `docker-compose.prod.yml` dosyasını kullanacağız.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

*   `up`: Servisleri başlatır.
*   `-d`: Botu arka planda (detached mode) çalıştırır.
*   `--build`: Docker imajını yeniden oluşturur. Kod değişiklikleri yaptığınızda bu komutu kullanmanız önemlidir.

### Bot Durumunu Kontrol Etme

Botun çalışıp çalışmadığını kontrol etmek için:

```bash
docker compose ps
```

### Logları Takip Etme

Botun loglarını gerçek zamanlı olarak izlemek için:

```bash
docker compose logs -f
```

Çıkmak için `Ctrl+C` tuşlarına basın.

### Botu Durdurma ve Yeniden Başlatma

Botu durdurmak için:

```bash
docker compose -f docker-compose.prod.yml down
```

Botu yeniden başlatmak için:

```bash
docker compose -f docker-compose.prod.yml restart
```

## 🛠️ Yapılan Kritik Düzeltmeler ve Optimizasyonlar

Bu projede, botun `e2-micro` gibi kısıtlı kaynaklara sahip bir ortamda stabil ve verimli çalışmasını sağlamak amacıyla çeşitli kritik düzeltmeler ve optimizasyonlar yapılmıştır:

1.  **`main.py` - Event Loop Hatası Düzeltmesi**: `asyncio.create_task()` çağrısının event loop başlamadan önce yapılması RuntimeWarning'a neden oluyordu. Bu düzeltme ile task, loop başladıktan sonra oluşturularak doğru asenkron davranış sağlanmıştır.
2.  **`veri_motoru.py` - Tanımsız Fonksiyonlar ve Robustluk**: `_fh_get` ve `_fh_sembol` fonksiyonlarının parametre yönetimi ve hata işleme mekanizmaları iyileştirilmiştir. Özellikle `_fh_sembol` fonksiyonu, Finnhub API'sinin beklediği sembol formatına daha uygun hale getirilmiştir.
3.  **`alert_motoru.py` - Asenkron Güvenlik**: Asenkron döngü içinde blocking çağrılar (`teknik_analiz_yap` gibi) event loop'u bloklayarak botun yanıt vermemesine neden oluyordu. Bu tür blocking çağrılar `loop.run_in_executor` kullanılarak ayrı bir thread havuzunda çalıştırılmış ve asenkron güvenlik sağlanmıştır.
4.  **`tradingview_motoru.py` - Kaynak Sızıntısı ve Stabilite**: Playwright tarayıcı bağlamının doğru yönetilmemesi kaynak sızıntılarına yol açabiliyordu. `async with` context manager kullanımı ile tarayıcı ve sayfa kaynaklarının otomatik olarak kapatılması sağlanmış, böylece bellek sızıntıları önlenmiştir. Ayrıca, grafik yükleme için daha robust bekleme mekanizmaları ve tekrar deneme (retry) mantığı eklenerek stabilite artırılmıştır.
5.  **`cache_yonetici.py` - Thread-Safety**: Cache yöneticisindeki `_ttl_gecti_mi()` gibi fonksiyonlara thread-safety sağlamak amacıyla `threading.Lock` mekanizması eklenmiştir. Bu, özellikle çoklu thread'li veya asenkron ortamlarda cache tutarlılığını garanti eder.
6.  **`docker-compose.prod.yml` - Kaynak Kısıtlamaları**: Google Cloud `e2-micro` sanal makinesinin sınırlı CPU ve RAM kaynakları göz önünde bulundurularak `finans_botu` servisine kaynak limitleri (`cpus: '0.50'`, `memory: 768M`) tanımlanmıştır. Bu, sanal makinenin aşırı yüklenmesini ve donmasını engellemeye yardımcı olur.
7.  **Swap Alanı Oluşturma**: `gcloud_free_setup.sh` betiği, `e2-micro` gibi düşük RAM'li makinelerde performans sorunlarını gidermek için 2GB'lık bir swap alanı oluşturur. Bu, özellikle Playwright gibi bellek yoğun uygulamalar için önemlidir.

Bu düzeltmeler ve optimizasyonlar sayesinde `finans_botu`, Google Cloud'un ücretsiz katmanında daha güvenilir, performanslı ve kaynak dostu bir şekilde çalışacaktır.

## 🔄 Güncelleme

Bot kodunda bir değişiklik yaptığınızda veya yeni bir sürüm çıktığında, botu güncellemek için aşağıdaki adımları izleyin:

1.  Proje dizinine gidin:
    ```bash
    cd ~/finans_botu
    ```
2.  En son kod değişikliklerini çekin:
    ```bash
    git pull
    ```
3.  Botu yeniden oluşturup başlatın:
    ```bash
    docker compose -f docker-compose.prod.yml up -d --build
    ```

## ❓ Sorun Giderme

*   **Bot Başlamıyor**: `docker compose logs -f` komutu ile logları kontrol edin. `.env` dosyasındaki API anahtarlarının doğru olduğundan emin olun.
*   **Bellek Yetersizliği**: `gcloud_free_setup.sh` betiğinin swap alanı oluşturduğundan emin olun. Eğer hala sorun yaşıyorsanız, `docker-compose.prod.yml` dosyasındaki bellek limitlerini daha da düşürmeyi deneyebilirsiniz (örn: `memory: 512M`).
*   **Playwright Hataları**: `shm_size: '1gb'` ayarının `docker-compose.prod.yml` dosyasında olduğundan emin olun. Ayrıca, `Dockerfile` içinde Playwright ve Chromium bağımlılıklarının doğru kurulduğundan emin olun.

Umarız bu kılavuz, finans botunuzu Google Cloud üzerinde başarıyla kurmanıza ve çalıştırmanıza yardımcı olur!
