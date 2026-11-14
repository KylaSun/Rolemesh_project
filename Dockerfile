FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROLEMESH_ENV=rolemesh-test \
    PORT=8000

COPY requirements.txt ./
COPY vendor/ ./vendor/
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod 755 /app/docker-entrypoint.sh

EXPOSE 8000

CMD ["/app/docker-entrypoint.sh"]
