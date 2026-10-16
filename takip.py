import os
import time
import unicodedata
from html import escape
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

URL = "https://balikesir.adalet.gov.tr/Arsiv/duyuru"
PROJE_DIZINI = Path(__file__).resolve().parent
KAYIT_DOSYASI = Path(
    os.environ.get(
        "DUYURU_KAYIT_DOSYASI",
        str(PROJE_DIZINI / "gonderilen_duyurular.txt"),
    )
)

UNVAN_KELIMELERI = ("infaz", "ikm", "koruma")
SONUC_KELIMELERI = ("sozlu", "sonuc", "mulakat")


def _arama_metni(metin):
    """Türkçe büyük İ/ı ve aksanları aramaya uygun hale getirir."""
    metin = metin.replace("ı", "i").casefold()
    ayrilmis = unicodedata.normalize("NFKD", metin)
    return "".join(
        karakter for karakter in ayrilmis if not unicodedata.combining(karakter)
    )


def _url_anahtari(href):
    """Göreli URL'yi güvenli ve karşılaştırılabilir bir Adalet URL'sine çevirir."""
    mutlak_url, _ = urldefrag(urljoin(URL, href.strip()))
    parcalar = urlparse(mutlak_url)
    hostname = (parcalar.hostname or "").lower()

    if parcalar.scheme != "https":
        return None
    if hostname != "adalet.gov.tr" and not hostname.endswith(".adalet.gov.tr"):
        return None

    return mutlak_url.rstrip("/")


def telegram_bildirim_gonder(mesaj):
    """Telegram'a HTML biçiminde mesaj gönderir ve başarı durumunu döndürür."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram ayarları eksik; mesaj gönderilmedi.", flush=True)
        return False

    send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mesaj,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(send_url, json=payload, timeout=15)
    except requests.RequestException as hata:
        # Exception metni istek URL'sini (ve tokeni) içerebilir.
        print(
            f"Telegram mesajı gönderilemedi ({type(hata).__name__}).",
            flush=True,
        )
        return False

    try:
        yanit = response.json()
    except ValueError:
        yanit = {}

    if not response.ok or yanit.get("ok") is not True:
        aciklama = yanit.get("description", "Bilinmeyen Telegram API hatası")
        print(
            f"Telegram mesajı reddedildi: HTTP {response.status_code} - {aciklama}",
            flush=True,
        )
        return False

    print("Telegram bildirimi gönderildi.", flush=True)
    return True


def _kayitli_duyurulari_oku():
    try:
        satirlar = KAYIT_DOSYASI.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()

    return {
        anahtar
        for satir in satirlar
        if satir.strip() and (anahtar := _url_anahtari(satir)) is not None
    }


def _duyuruyu_kaydet(href):
    KAYIT_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    with KAYIT_DOSYASI.open("a", encoding="utf-8") as dosya:
        dosya.write(href + "\n")


def duyurulari_kontrol_et():
    """Adliye sitesini tarar, yeni hedef duyuruları Telegram'a bildirir."""
    print("Duyurular taranıyor...", flush=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(URL, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.RequestException as hata:
        raise RuntimeError(
            f"Adliye sitesine erişilemedi ({type(hata).__name__})."
        ) from None

    soup = BeautifulSoup(response.content, "html.parser")
    kayitli_duyurular = _kayitli_duyurulari_oku()
    aday_duyurular = {}

    for link in soup.find_all("a", href=True):
        baslik = link.get_text(" ", strip=True)
        if not baslik:
            continue

        href = _url_anahtari(link["href"])
        if href is None or href in kayitli_duyurular:
            continue

        arama_metni = _arama_metni(baslik)
        unvan_sarti = any(kelime in arama_metni for kelime in UNVAN_KELIMELERI)
        sonuc_sarti = any(kelime in arama_metni for kelime in SONUC_KELIMELERI)

        if unvan_sarti and sonuc_sarti:
            # Aynı bağlantı sayfada birden fazla kez geçse de yalnızca bir kez işle.
            aday_duyurular.setdefault(href, baslik)

    bildirilen = 0
    basarisiz_bildirim = 0

    for href, baslik in aday_duyurular.items():
        mesaj = (
            "📢 <b>BEKLENEN DUYURU GELDİ!</b>\n\n"
            f"📌 <b>Başlık:</b> {escape(baslik)}\n\n"
            f'🔗 <a href="{escape(href, quote=True)}">Duyuruya Gitmek İçin Tıkla</a>'
        )

        basarili_gonderim = 0
        for sira in range(1, 6):
            if telegram_bildirim_gonder(f"🔔 [{sira}/5]\n{mesaj}"):
                basarili_gonderim += 1
                print(
                    f"Bildirim {sira}/5 gönderildi: {baslik}",
                    flush=True,
                )
            if sira < 5:
                time.sleep(5)

        if basarili_gonderim:
            _duyuruyu_kaydet(href)
            kayitli_duyurular.add(href)
            bildirilen += 1
        else:
            basarisiz_bildirim += 1
            print(
                f"Duyuru gönderilemedi, sonraki kontrolde yeniden denenecek: {baslik}",
                flush=True,
            )

    if not aday_duyurular:
        print("Yeni hedef duyuru bulunamadı.", flush=True)

    telegram_hatasi = None
    if basarisiz_bildirim:
        telegram_hatasi = (
            f"{basarisiz_bildirim} duyuru Telegram'a gönderilemedi; yeniden denenecek."
        )

    return {
        "bildirilen": bildirilen,
        "telegram_hatasi": telegram_hatasi,
    }


if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(
            "HATA: TELEGRAM_TOKEN ve CHAT_ID environment variable'ları ayarlanmalı!",
            flush=True,
        )
        raise SystemExit(1)

    print("İKM Duyuru Takip - Tek seferlik kontrol başlatılıyor...", flush=True)
    try:
        sonuc = duyurulari_kontrol_et()
    except Exception as hata:
        print(f"Kontrol başarısız: {type(hata).__name__}: {hata}", flush=True)
        raise SystemExit(1) from None

    if sonuc["telegram_hatasi"]:
        print(sonuc["telegram_hatasi"], flush=True)
        raise SystemExit(1)

    print("Kontrol tamamlandı.", flush=True)
