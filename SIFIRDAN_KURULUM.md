# 🧹 Google Cloud Sıfırdan Kurulum ve Temizlik Kılavuzu

Google Cloud üzerindeki eski dosyaları tamamen temizlemek ve güncellenmiş botu en baştan kurmak için aşağıdaki adımları sırasıyla terminale kopyalayıp yapıştırın.

### 1. Adım: Mevcut Botu Durdurun ve Eski Dosyaları Silin

Bu komut, çalışan botu durdurur, Docker konteynerlerini temizler ve `finans_botu` klasörünü tamamen siler.

```bash
# Eğer bot çalışıyorsa durdurun
sudo systemctl stop finans-botu 2>/dev/null
docker compose down 2>/dev/null

# Eski proje klasörünü tamamen silin
cd ~
rm -rf finans_botu
```

### 2. Adım: Güncel Projeyi Klonlayın

Şimdi, yaptığım tüm düzeltmeleri içeren güncel kodu GitHub'dan çekiyoruz:

```bash
git clone https://github.com/CengizKarabulut/finans_botu.git
cd finans_botu
```

### 3. Adım: Otomatik Kurulum Betiğini Çalıştırın

Bu betik, Google Cloud ücretsiz sürüm için gerekli olan Docker kurulumunu yapacak ve 2GB Swap alanı oluşturacaktır:

```bash
bash gcloud_free_setup.sh
```

### 4. Adım: API Anahtarlarınızı Girin

Botun çalışması için en azından Telegram Bot Token'ınızı girmeniz gerekir. Dosyayı açın ve ilgili yerleri doldurun:

```bash
nano .env
```

*   `BOT_TOKEN` kısmına botunuzun token'ını yapıştırın.
*   Diğer API anahtarlarınız varsa (Gemini, Finnhub vb.) onları da ekleyin.
*   Kaydetmek için: `Ctrl + O` sonra `Enter`.
*   Çıkmak için: `Ctrl + X`.

### 5. Adım: Botu Başlatın

Her şey hazır! Botu arka planda çalışacak şekilde başlatın:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 6. Adım: Çalıştığını Kontrol Edin

Botun loglarını izleyerek hata olup olmadığını görebilirsiniz:

```bash
docker compose logs -f
```

---

### 💡 Önemli İpuçları

*   **Loglardan Çıkmak İçin**: `Ctrl + C` tuşlarına basın (bu botu durdurmaz, sadece log izlemeyi kapatır).
*   **Botu Durdurmak İçin**: `docker compose -f docker-compose.prod.yml down`
*   **Botu Yeniden Başlatmak İçin**: `docker compose -f docker-compose.prod.yml restart`

Bu adımları tamamladığınızda botunuz Google Cloud üzerinde en güncel ve hatasız haliyle çalışıyor olacaktır.
