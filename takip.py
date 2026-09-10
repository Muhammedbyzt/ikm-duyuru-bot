import os
import time
import requests
from bs4 import BeautifulSoup

# --- AYARLAR (GitHub Secrets'tan gelecek) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

URL = "https://balikesir.adalet.gov.tr/Arsiv/duyuru"

def telegram_bildirim_gonder(mesaj):
    """Telegram üzerinden kullanıcıya mesaj iletir."""
    send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(send_url, json=payload, timeout=10)
        print(f"Telegram yanıtı: {response.status_code}")
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

def duyurulari_kontrol_et():
    """Adliye sitesini tarar ve yeni duyuru varsa bildirir."""
    print("Duyurular taranıyor...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"Siteye ulaşılamadı. Hata Kodu: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        duyuru_linkleri = soup.find_all("a")

        try:
            with open("gonderilen_duyurular.txt", "r", encoding="utf-8") as f:
                kayitli_duyurular = f.read().splitlines()
        except FileNotFoundError:
            kayitli_duyurular = []

        yeni_duyuru_bulundu = False

        for link in duyuru_linkleri:
            baslik = link.get_text(strip=True)
            href = link.get("href")

            if not baslik or not href:
                continue

            if not href.startswith("http"):
                href = "https://balikesir.adalet.gov.tr" + href

            baslik_kucuk = baslik.lower()

            # --- FİLTRELEME MANTIĞI ---
            # 1. Başlıkta unvan geçiyor mu?
            unvan_sarti = "infaz" in baslik_kucuk or "ikm" in baslik_kucuk or "koruma" in baslik_kucuk

            # 2. Başlıkta mülakat/sonuç kelimeleri geçiyor mu?
            sonuc_sarti = "sözlü" in baslik_kucuk or "sonuç" in baslik_kucuk or "mülakat" in baslik_kucuk

            # Eğer her iki şart da sağlanıyorsa bildir
            if unvan_sarti and sonuc_sarti and href not in kayitli_duyurular:
                mesaj = (
                    f"📢 *BEKLENEN DUYURU GELDİ!*\n\n"
                    f"📌 *Başlık:* {baslik}\n\n"
                    f"🔗 [Duyuruya Gitmek İçin Tıkla]({href})"
                )

                # 5 kez 5 saniye arayla bildirim gönder (kaçırılmasın diye)
                for i in range(5):
                    telegram_bildirim_gonder(f"🔔 [{i+1}/5] {mesaj}")
                    print(f"Bildirim {i+1}/5 gönderildi: {baslik}")
                    if i < 4:
                        time.sleep(5)

                with open("gonderilen_duyurular.txt", "a", encoding="utf-8") as f:
                    f.write(href + "\n")

                yeni_duyuru_bulundu = True

        if not yeni_duyuru_bulundu:
            print("Yeni hedef duyuru bulunamadı.")
            telegram_bildirim_gonder("✅ *Kontrol tamamlandı.* Yeni İKM/sözlü sınav duyurusu bulunamadı. Bot çalışmaya devam ediyor.")

    except Exception as e:
        print(f"Hata oluştu: {e}")

def test_bildirimi_gonder():
    """Test amaçlı sahte duyuru bildirimi gönderir."""
    print("TEST MODU: Sahte duyuru bildirimi gönderiliyor...")
    mesaj = (
        "📢 *BEKLENEN DUYURU GELDİ!*\n\n"
        "📌 *Başlık:* 2026 Yılı İKM Sözlü Sınav Sonuçları (TEST)\n\n"
        "🔗 [Duyuruya Gitmek İçin Tıkla](https://balikesir.adalet.gov.tr/test-duyuru)"
    )
    for i in range(5):
        telegram_bildirim_gonder(f"🔔 [{i+1}/5] {mesaj}")
        print(f"Test bildirim {i+1}/5 gönderildi")
        if i < 4:
            time.sleep(5)

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("HATA: TELEGRAM_TOKEN ve CHAT_ID environment variable'ları ayarlanmalı!")
        exit(1)

    # TEST_MODE=true ise sahte duyuru gönder
    if os.environ.get("TEST_MODE", "").lower() == "true":
        test_bildirimi_gonder()
    else:
        print("İKM Duyuru Takip - Tek seferlik kontrol başlatılıyor...")
        duyurulari_kontrol_et()
        print("Kontrol tamamlandı.")