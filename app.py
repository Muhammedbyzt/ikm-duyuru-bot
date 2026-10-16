import os
import time
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify
from takip import duyurulari_kontrol_et, telegram_bildirim_gonder, TELEGRAM_TOKEN, CHAT_ID

app = Flask(__name__)

# Türkiye saat dilimi (UTC+3)
TR_TZ = timezone(timedelta(hours=3))

# Bot durumu
bot_durum = {
    "son_kontrol": None,
    "calisiyor": False,
    "baslangic": None
}

def bot_dongusu():
    """Bot'un ana döngüsü - arka planda sürekli çalışır."""
    KONTROL_ARALIGI = 600  # 10 dakika
    son_durum_tarihi = None

    bot_durum["calisiyor"] = True
    bot_durum["baslangic"] = datetime.now(TR_TZ).strftime("%d.%m.%Y %H:%M")

    # Başlangıç bildirimi
    telegram_bildirim_gonder("🚀 *İKM Duyuru Takip Botu Başlatıldı!*\nBot aktif ve çalışıyor. Her 10 dakikada bir kontrol edilecek.")

    while True:
        try:
            simdi = datetime.now(TR_TZ)
            bot_durum["son_kontrol"] = simdi.strftime("%H:%M:%S")

            # Duyuru kontrolü
            duyurulari_kontrol_et()

            # Günlük durum bildirimi (her gün saat 09:00-09:10 arasında bir kez)
            bugun = simdi.strftime("%Y-%m-%d")
            if son_durum_tarihi != bugun and simdi.hour == 9:
                telegram_bildirim_gonder(
                    "🤖 *İKM Duyuru Takip Botu Aktif!*\n\n"
                    "✅ Bot sorunsuz çalışıyor.\n"
                    f"📡 Son kontrol: {bot_durum['son_kontrol']}\n"
                    f"🕐 Çalışma başlangıcı: {bot_durum['baslangic']}\n"
                    "⏰ Bir sonraki durum raporu: yarın 09:00"
                )
                son_durum_tarihi = bugun

        except Exception as e:
            print(f"Bot döngüsü hatası: {e}")

        time.sleep(KONTROL_ARALIGI)

@app.route("/")
def anasayfa():
    """Sağlık kontrolü endpoint'i - Render ve UptimeRobot için."""
    return jsonify({
        "durum": "aktif",
        "bot_calisiyor": bot_durum["calisiyor"],
        "son_kontrol": bot_durum["son_kontrol"],
        "baslangic": bot_durum["baslangic"]
    })

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("HATA: TELEGRAM_TOKEN ve CHAT_ID environment variable'ları ayarlanmalı!")
        exit(1)

    # Bot thread'ini başlat
    bot_thread = threading.Thread(target=bot_dongusu, daemon=True)
    bot_thread.start()

    # Flask sunucusunu başlat
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
