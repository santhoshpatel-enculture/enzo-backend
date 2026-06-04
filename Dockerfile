FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Listen on 127.0.0.1 in dev; override HOST in production
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
