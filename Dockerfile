FROM python:3.12-slim

WORKDIR /app
COPY app.py .
COPY static ./static

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/hn.db \
    PORT=8000

EXPOSE 8000
CMD ["python", "app.py"]
