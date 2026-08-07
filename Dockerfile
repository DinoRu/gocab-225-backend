FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Dépendances d'abord (cache Docker : ne réinstalle que si requirements.txt change)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Puis le code
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]