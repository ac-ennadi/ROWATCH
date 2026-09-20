FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    ROWATCH_DISABLE_PURGE=0

WORKDIR /app
RUN addgroup --system rowatch && adduser --system --ingroup rowatch rowatch

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend
RUN mkdir -p /app/instance && chown -R rowatch:rowatch /app

USER rowatch
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)" || exit 1

WORKDIR /app/backend
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --worker-class gthread --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-4} --access-logfile - --error-logfile - 'app:create_app()'"]

