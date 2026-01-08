#!/bin/bash

# 🚀 Script de déploiement complet sur le VPS
# Usage: ./deploy_prod.sh

set -e  # Arrêter si erreur

echo "=================================================="
echo "🚀 DÉPLOIEMENT JIMMY.AI SUR VPS"
echo "=================================================="

# 1️⃣ Pull les dernières modifs depuis GitHub
echo ""
echo "📥 1/5 : Récupération du code depuis GitHub..."
git pull origin main

# 2️⃣ Rebuild les images Docker
echo ""
echo "🔨 2/5 : Rebuild des images Docker..."
docker compose down
docker compose build --no-cache

# 3️⃣ Redémarrage des services
echo ""
echo "🚢 3/5 : Lancement des containers..."
docker compose up -d

# Attendre que la DB soit prête
echo "   ⏳ Attente de la DB (10s)..."
sleep 10

# 4️⃣ Initialisation de la base de données
echo ""
echo "💾 4/5 : Initialisation de la base de données..."
docker compose exec -T backend python /app/data-pipeline/init_db_prod.py

# 5️⃣ Vérification finale
echo ""
echo "✅ 5/5 : Vérification des services..."
docker compose ps

echo ""
echo "=================================================="
echo "✅ DÉPLOIEMENT TERMINÉ !"
echo "=================================================="
echo ""
echo "📊 Vérifications :"
echo "   Backend  : curl -I http://localhost:8000/health"
echo "   Frontend : curl -I http://localhost:8501"
echo "   Caddy    : curl -I http://localhost/health"
echo ""
echo "🌍 URLs publiques :"
echo "   → http://jimmyainba.duckdns.org (HTTP)"
echo "   → https://jimmyainba.duckdns.org (HTTPS - en cours de config)"
echo ""
echo "📋 Logs :"
echo "   docker compose logs -f backend"
echo "   docker compose logs -f frontend"
echo "   docker compose logs -f caddy"
echo ""

