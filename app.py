import os
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify

from takip import (
    CHAT_ID,
    TELEGRAM_TOKEN,
    duyurulari_kontrol_et,
    telegram_bildirim_gonder,
)


app = Flask(__name__)

TR_TZ = timezone(timedelta(hours=3))
KONTROL_ARALIGI = 600  # 10 dakika

bot_durum = {
    "calisiyor": False,
    "baslangic": None,
    "son_kontrol": None,
    "son_basarili_kontrol": None,
    "son_tarama_hatasi": None,
    "son_telegram_hatasi": None,
}

_durum_kilidi = threading.Lock()
_thread_kilidi = threading.Lock()
_bot_thread = None
_bot_process_id = None


def _simdi():
    return datetime.now(TR_TZ)


def _zaman_metni(zaman=None):
    return (zaman or _simdi()).strftime("%d.%m.%Y %H:%M:%S")


def _durum_guncelle(**degerler):
    with _durum_kilidi:
        bot_durum.update(degerler)


def bot_dongusu():
    """Duyuru kontrolünü arka planda sürekli çalıştırır."""
    son_durum_tarihi = None
    _durum_guncelle(calisiyor=True, baslangic=_zaman_metni())

    try:
        baslangic_mesaji = (
            "🚀 <b>İKM Duyuru Takip Botu Başlatıldı!</b>\n"
            "Bot aktif ve her 10 dakikada bir kontrol yapacak."
        )
        if telegram_bildirim_gonder(baslangic_mesaji):
            _durum_guncelle(son_telegram_hatasi=None)
        else:
            _durum_guncelle(
                son_telegram_hatasi="Başlangıç bildirimi Telegram'a gönderilemedi."
            )

        while True:
            simdi = _simdi()
            _durum_guncelle(son_kontrol=_zaman_metni(simdi))

            try:
                sonuc = duyurulari_kontrol_et()
                _durum_guncelle(
                    son_basarili_kontrol=_zaman_metni(),
                    son_tarama_hatasi=None,
                )

                if sonuc["telegram_hatasi"]:
                    _durum_guncelle(
                        son_telegram_hatasi=sonuc["telegram_hatasi"]
                    )
                elif sonuc["bildirilen"]:
                    _durum_guncelle(son_telegram_hatasi=None)

                bugun = simdi.strftime("%Y-%m-%d")
                if son_durum_tarihi != bugun and simdi.hour == 9:
                    durum_mesaji = (
                        "🤖 <b>İKM Duyuru Takip Botu Aktif!</b>\n\n"
                        "✅ Bot sorunsuz çalışıyor.\n"
                        f"📡 Son kontrol: {_zaman_metni()}\n"
                        f"🕐 Çalışma başlangıcı: {bot_durum['baslangic']}\n"
                        "⏰ Bir sonraki durum raporu: yarın 09:00"
                    )
                    if telegram_bildirim_gonder(durum_mesaji):
                        son_durum_tarihi = bugun
                        _durum_guncelle(son_telegram_hatasi=None)
                    else:
                        _durum_guncelle(
                            son_telegram_hatasi=(
                                "Günlük durum bildirimi Telegram'a gönderilemedi."
                            )
                        )

            except Exception as hata:
                # Hata metnine token içeren bir istek URL'si yazdırmıyoruz.
                hata_metni = f"{type(hata).__name__}: {hata}"
                _durum_guncelle(son_tarama_hatasi=hata_metni)
                print(f"Bot döngüsü hatası: {hata_metni}", flush=True)

            time.sleep(KONTROL_ARALIGI)
    finally:
        _durum_guncelle(calisiyor=False)


def botu_baslat():
    """Bulunulan worker prosesinde bot thread'ini bir kez başlatır."""
    global _bot_process_id, _bot_thread

    process_id = os.getpid()

    with _thread_kilidi:
        # Preload/fork sonrasında parent'tan kopyalanmış Thread nesnesi geçersizdir.
        if _bot_process_id != process_id:
            _bot_thread = None
            _bot_process_id = None

        if _bot_thread is not None and _bot_thread.is_alive():
            return True

        if not TELEGRAM_TOKEN or not CHAT_ID:
            _durum_guncelle(
                calisiyor=False,
                son_telegram_hatasi=(
                    "TELEGRAM_TOKEN ve CHAT_ID environment variable'ları eksik."
                ),
            )
            print(
                "HATA: TELEGRAM_TOKEN ve CHAT_ID environment variable'ları ayarlanmalı!",
                flush=True,
            )
            return False

        _bot_thread = threading.Thread(
            target=bot_dongusu,
            name="duyuru-kontrol",
            daemon=True,
        )
        _bot_process_id = process_id
        _bot_thread.start()
        print(
            f"Bot arka planda başlatıldı (process: {process_id}).",
            flush=True,
        )
        return True


def _saglik_durumu():
    process_id = os.getpid()
    with _thread_kilidi:
        thread_calisiyor = (
            _bot_process_id == process_id
            and _bot_thread is not None
            and _bot_thread.is_alive()
        )
        bot_process_id = _bot_process_id

    with _durum_kilidi:
        sonuc = dict(bot_durum)

    yapilandirildi = bool(TELEGRAM_TOKEN and CHAT_ID)
    saglikli = yapilandirildi and thread_calisiyor
    uyari_var = bool(
        sonuc["son_tarama_hatasi"] or sonuc["son_telegram_hatasi"]
    )
    if not saglikli:
        durum = "hata"
    elif uyari_var:
        durum = "uyari"
    else:
        durum = "aktif"

    sonuc.update(
        {
            "durum": durum,
            "bot_calisiyor": thread_calisiyor,
            "bot_process_id": bot_process_id,
            "calisiyor": thread_calisiyor,
            "process_id": process_id,
            "yapilandirildi": yapilandirildi,
        }
    )
    return sonuc, 200 if saglikli else 503


@app.get("/")
@app.get("/health")
def saglik():
    """Render ve UptimeRobot için sağlık kontrolü."""
    veri, durum_kodu = _saglik_durumu()
    return jsonify(veri), durum_kodu


@app.before_request
def bot_threadini_hazir_tut():
    """Worker yenilenirse ilk istekte bot thread'ini tekrar hazırlar."""
    if TELEGRAM_TOKEN and CHAT_ID:
        botu_baslat()


if __name__ == "__main__":
    if not botu_baslat():
        raise SystemExit(1)

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
