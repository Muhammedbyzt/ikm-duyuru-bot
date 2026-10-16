import os


bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
threads = 2
worker_class = "gthread"
preload_app = False
accesslog = "-"
errorlog = "-"


def post_worker_init(worker):
    """Botu master proseste değil, fork tamamlandıktan sonra worker'da başlatır."""
    from app import botu_baslat

    if not botu_baslat():
        worker.log.error("Telegram environment variable'ları eksik; bot başlatılamadı.")
