FROM python:3.12-slim

# Instalar dependências de sistema (FFmpeg, git, wget, tzdata)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    wget \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Definir fuso horário para América/São_Paulo
ENV TZ=America/Sao_Paulo

WORKDIR /app

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o código do aplicativo
COPY . .

# Criar diretório base para montagem de volume /data
RUN mkdir -p /data/library/videos /data/library/subtitles /data/library/history /data/output/models/whisper /data/cache

# Expor porta 8000
EXPOSE 8000

# Executar a aplicação com Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
