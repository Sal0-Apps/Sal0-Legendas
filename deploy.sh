#!/bin/bash
echo "=================================================="
echo "🎬 Iniciando Implantação do Sal0 Legendas (v1.0.0)"
echo "=================================================="

# Parar container existente se estiver rodando
docker compose down

# Recriar e iniciar container
docker compose up -d --build

echo ""
echo "✅ Sal0 Legendas implantado com sucesso!"
echo "🌐 Acesse no navegador: http://localhost:8001"
echo "=================================================="
