import os

bind = "127.0.0.1:8001"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
forwarded_allow_ips = "127.0.0.1"
errorlog = "-"
# Nginx owns sanitized access events; omit URL queries, cookies and tokens.
accesslog = None
capture_output = True
loglevel = "info"
