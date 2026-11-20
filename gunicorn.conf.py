import os

workers = int(os.environ.get('GUNICORN_WORKERS', '1'))
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
timeout = 60
