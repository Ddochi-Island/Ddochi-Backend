# Django(gunicorn) 배포용 이미지 — data_router는 별도 컨테이너(docker-compose.prod.yml)로 뜸.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
