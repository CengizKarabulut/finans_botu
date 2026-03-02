# Finans Botu

Bu proje, bir Telegram finans botunu Dockerize ederek Google Cloud Compute Engine üzerinde production-ready, stabil ve 7/24 çalışabilir bir sisteme dönüştürmeyi amaçlamaktadır.

## 🚀 Kurulum Rehberi

### 1. Google Cloud Compute Engine VM Kurulumu

1.  **Google Cloud Console'a Giriş Yapın**: [console.cloud.google.com](https://console.cloud.google.com/)
2.  **Yeni Bir Proje Oluşturun veya Mevcut Bir Projeyi Seçin**.
3.  **Compute Engine API'sini Etkinleştirin**: "Compute Engine" araması yaparak veya menüden "Compute Engine" seçeneğine giderek API'yi etkinleştirin.
4.  **VM Örneği Oluşturun**:
    *   **Makine Yapılandırması**: Botun sorunsuz çalışması için en az `e2-medium` (2 vCPU, 4 GB bellek) veya `e2-standard-2` (2 vCPU, 8 GB bellek) önerilir. Özellikle Playwright ve Chromium için yeterli bellek kritik öneme sahiptir.
    *   **Önyükleme Diski**: `Ubuntu 22.04 LTS` işletim sistemini seçin. Disk boyutu olarak en az 20 GB SSD önerilir.
    *   **Güvenlik Duvarı**: `HTTP trafiğine izin ver` ve `HTTPS trafiğine izin ver` seçeneklerini işaretleyebilirsiniz, ancak bot doğrudan web trafiği almadığı için zorunlu değildir. SSH erişimi için varsayılan kurallar yeterlidir.
    *   **Erişim Kapsamları**: Varsayılan hizmet hesabı erişim kapsamlarını bırakın.
5.  **VM Örneğine SSH ile Bağlanın**: Google Cloud Console üzerinden veya `gcloud compute ssh` komutu ile VM'inize bağlanın.

### 2. Docker Kurulumu

VM'inize bağlandıktan sonra aşağıdaki komutları çalıştırarak Docker ve Docker Compose'u kurun:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Mevcut kullanıcıyı docker grubuna ekle (sudo kullanmadan docker komutlarını çalıştırmak için)
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Proje Kurulumu

1.  **GitHub Reposunu Klonlayın**:
    ```bash
gh repo clone CengizKarabulut/finans_botu
cd finans_botu
    ```
2.  **.env Dosyasını Oluşturun**: `.env.example` dosyasını kopyalayarak `.env` adında yeni bir dosya oluşturun ve gerekli API anahtarlarını ve bot token'ını doldurun.
    ```bash
cp .env.example .env
nano .env
    ```
    `.env` dosyasının içeriği aşağıdaki gibi olmalıdır (kendi anahtarlarınızla doldurun):
    ```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN

# Optional: API keys for AI services
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GROQ_API_KEY=YOUR_GROQ_API_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY

# Optional: API keys for financial data services
FINNHUB_API_KEY=YOUR_FINNHUB_API_KEY
COINGECKO_API_KEY=YOUR_COINGECKO_API_KEY
FMP_API_KEY=YOUR_FMP_API_KEY
ALPHAVANTAGE_API_KEY=YOUR_ALPHAVANTAGE_API_KEY
OPENFIGI_API_KEY=YOUR_OPENFIGI_API_KEY

# Optional: TradingView login credentials (if needed for screenshot functionality)
# TRADINGVIEW_USERNAME=YOUR_TRADINGVIEW_USERNAME
# TRADINGVIEW_PASSWORD=YOUR_TRADINGVIEW_PASSWORD
    ```
3.  **Docker Build & Run**: Projeyi Docker Compose ile başlatın.
    ```bash
docker compose up --build -d
    ```
    Bu komut, `Dockerfile`'ı kullanarak botun Docker imajını oluşturacak ve `docker-compose.yml` dosyasındaki ayarlara göre botu bir container içinde başlatacaktır. `--build` imajı yeniden oluşturur, `-d` ise botu arka planda çalıştırır.

### 4. Bot Yönetimi

*   **Başlatma**: `docker compose start finans_botu`
*   **Durdurma**: `docker compose stop finans_botu`
*   **Yeniden Başlatma**: `docker compose restart finans_botu`
*   **Log İzleme**: `docker compose logs -f finans_botu`
*   **Container'a Bağlanma**: `docker exec -it finans_botu bash`

### 5. Olası Hatalar ve Çözümleri

*   **Playwright/Chromium Sorunları**: `shm_size: '1gb'` ayarı `docker-compose.yml` dosyasında mevcuttur. Eğer hala sorun yaşanıyorsa, Dockerfile içindeki Chromium bağımlılıklarının doğru kurulduğundan emin olun.
*   **RAM Yetersizliği**: Compute Engine VM'inizin bellek miktarını artırmayı düşünün (örneğin `e2-medium` yerine `e2-standard-2`).
*   **TradingView Login Sorunları**: Eğer TradingView ekran görüntüsü alma özelliği login gerektiriyorsa ve `storage_state.json` kullanılıyorsa, `docker-compose.yml` dosyasındaki ilgili volume satırının yorum satırı olmaktan çıkarıldığından ve `storage_state.json` dosyasının projenin ana dizininde bulunduğundan emin olun.

## 📝 Geliştirici Notları

*   Bu bot, `unless-stopped` restart politikası ile yapılandırılmıştır, bu sayede VM yeniden başlatılsa bile bot otomatik olarak tekrar çalışmaya başlayacaktır.
*   Tüm hassas bilgiler `.env` dosyası üzerinden yönetilmektedir. `.env` dosyasını asla Git'e eklemeyin.
*   Loglar hem STDOUT'a ( `docker logs` ile izlenebilir) hem de `/app/logs/bot.log` dosyasına yazılmaktadır. `/app/logs` dizini bir Docker volume olarak bağlandığı için loglar container yeniden oluşturulsa bile kalıcı olacaktır.
