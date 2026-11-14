FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
COPY matching/ matching/
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "start_cloud_test.sh"]
