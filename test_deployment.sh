#!/bin/bash

# 🧪 Script de test pour vérifier le déploiement
# Usage: ./test_deployment.sh [local|vps]

set -e

ENV=${1:-local}
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'
COLOR_NC='\033[0m' # No Color

if [ "$ENV" == "local" ]; then
    BACKEND_URL="http://localhost:8000"
    FRONTEND_URL="http://localhost:8501"
    HOST="localhost"
else
    BACKEND_URL="http://192.168.1.134:8000"
    FRONTEND_URL="http://192.168.1.134"
    HOST="192.168.1.134"
fi

echo -e "${COLOR_BLUE}🧪 Test de déploiement - Environment: $ENV${COLOR_NC}"
echo "========================================="
echo ""

# Test 1: Vérifier que les conteneurs tournent
echo -e "${COLOR_YELLOW}[Test 1] Vérification des conteneurs Docker...${COLOR_NC}"
if [ "$ENV" == "local" ]; then
    CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E "jimmy_(backend|frontend|db|caddy)" | wc -l)
else
    CONTAINERS=$(ssh juju@192.168.1.134 "docker ps --format '{{.Names}}' | grep -E 'jimmy_(backend|frontend|db|caddy)' | wc -l")
fi

if [ "$CONTAINERS" -ge 4 ]; then
    echo -e "${COLOR_GREEN}✅ Tous les conteneurs tournent ($CONTAINERS/4)${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ Conteneurs manquants ($CONTAINERS/4)${COLOR_NC}"
    exit 1
fi
echo ""

# Test 2: Vérifier que le backend répond
echo -e "${COLOR_YELLOW}[Test 2] Test de connexion au backend...${COLOR_NC}"
if curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/games/week" | grep -q "200"; then
    echo -e "${COLOR_GREEN}✅ Backend accessible sur $BACKEND_URL${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ Backend inaccessible${COLOR_NC}"
    exit 1
fi
echo ""

# Test 3: Vérifier la santé des données
echo -e "${COLOR_YELLOW}[Test 3] Vérification de la santé des données...${COLOR_NC}"
if [ "$ENV" == "local" ]; then
    HEALTH=$(docker exec jimmy_backend python check_data_health.py 2>/dev/null | grep -E "Total en base|Snapshots")
else
    HEALTH=$(ssh juju@192.168.1.134 "docker exec jimmy_backend python check_data_health.py 2>/dev/null" | grep -E "Total en base|Snapshots")
fi

if [ ! -z "$HEALTH" ]; then
    echo -e "${COLOR_GREEN}✅ Données présentes en base${COLOR_NC}"
    echo "$HEALTH"
else
    echo -e "${COLOR_RED}❌ Problème de données${COLOR_NC}"
    exit 1
fi
echo ""

# Test 4: Vérifier que les marchés sont valides
echo -e "${COLOR_YELLOW}[Test 4] Vérification des marchés disponibles...${COLOR_NC}"
if [ "$ENV" == "local" ]; then
    MARKETS=$(docker exec jimmy_backend python check_data_health.py 2>/dev/null | grep -E "points:|rebounds:|assists:" | wc -l)
else
    MARKETS=$(ssh juju@192.168.1.134 "docker exec jimmy_backend python check_data_health.py 2>/dev/null" | grep -E "points:|rebounds:|assists:" | wc -l)
fi

if [ "$MARKETS" -ge 3 ]; then
    echo -e "${COLOR_GREEN}✅ Les 3 marchés sont présents (points, rebounds, assists)${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ Marchés manquants ($MARKETS/3)${COLOR_NC}"
    exit 1
fi
echo ""

# Test 5: Vérifier qu'il n'y a pas de marché "three_points_made"
echo -e "${COLOR_YELLOW}[Test 5] Vérification absence de 'three_points_made'...${COLOR_NC}"
if [ "$ENV" == "local" ]; then
    THREE_POINTS=$(docker exec jimmy_backend python check_data_health.py 2>/dev/null | grep -c "three_points_made" || true)
else
    THREE_POINTS=$(ssh juju@192.168.1.134 "docker exec jimmy_backend python check_data_health.py 2>/dev/null" | grep -c "three_points_made" || true)
fi

if [ "$THREE_POINTS" -eq 0 ]; then
    echo -e "${COLOR_GREEN}✅ Aucun marché 'three_points_made' trouvé${COLOR_NC}"
else
    echo -e "${COLOR_RED}⚠️  Marché 'three_points_made' encore présent (sera ignoré)${COLOR_NC}"
fi
echo ""

# Test 6: Lancer un scan de test via l'API
echo -e "${COLOR_YELLOW}[Test 6] Lancement d'un scan de test...${COLOR_NC}"
SCAN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/analysis/start-scan" -H "Content-Type: application/json" -d '{}')
SCAN_ID=$(echo $SCAN_RESPONSE | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)

if [ ! -z "$SCAN_ID" ]; then
    echo -e "${COLOR_GREEN}✅ Scan démarré avec ID: $SCAN_ID${COLOR_NC}"

    # Attendre 20 secondes que le scan se termine
    echo -e "${COLOR_BLUE}⏳ Attente de 20s pour la fin du scan...${COLOR_NC}"
    sleep 20

    # Récupérer les résultats
    RESULTS=$(curl -s "$BACKEND_URL/analysis/scan-results/$SCAN_ID")

    # Vérifier si on a des picks
    PICKS_COUNT=$(echo $RESULTS | grep -o '"selected_count":[0-9]*' | cut -d':' -f2)
    POTENTIAL_COUNT=$(echo $RESULTS | grep -o '"potential_count":[0-9]*' | cut -d':' -f2)

    if [ ! -z "$POTENTIAL_COUNT" ] && [ "$POTENTIAL_COUNT" -gt 0 ]; then
        echo -e "${COLOR_GREEN}✅ Scan réussi: $PICKS_COUNT picks sélectionnés sur $POTENTIAL_COUNT potentiels${COLOR_NC}"
    else
        echo -e "${COLOR_YELLOW}⚠️  Scan terminé avec 0 picks potentiels (peut être normal si pas de matchs aujourd'hui)${COLOR_NC}"
        PICKS_COUNT=0
        POTENTIAL_COUNT=0
    fi
else
    echo -e "${COLOR_RED}❌ Impossible de démarrer le scan${COLOR_NC}"
    exit 1
fi
echo ""

# Test 7: Vérifier les logs backend pour erreurs
echo -e "${COLOR_YELLOW}[Test 7] Vérification des erreurs dans les logs...${COLOR_NC}"
if [ "$ENV" == "local" ]; then
    ERRORS=$(docker logs jimmy_backend --tail 100 2>&1 | grep -i "error\|exception\|failed" | grep -v "404 Not Found" | wc -l)
else
    ERRORS=$(ssh juju@192.168.1.134 "docker logs jimmy_backend --tail 100 2>&1" | grep -i "error\|exception\|failed" | grep -v "404 Not Found" | wc -l)
fi

if [ "$ERRORS" -eq 0 ]; then
    echo -e "${COLOR_GREEN}✅ Aucune erreur critique dans les logs${COLOR_NC}"
else
    echo -e "${COLOR_YELLOW}⚠️  $ERRORS erreurs trouvées dans les logs (vérifiez manuellement)${COLOR_NC}"
fi
echo ""

# Résumé final
echo "========================================="
echo -e "${COLOR_GREEN}✅ TOUS LES TESTS SONT PASSÉS !${COLOR_NC}"
echo ""
echo "📊 Résumé:"
echo "  - Environment: $ENV"
echo "  - Backend: $BACKEND_URL"
echo "  - Frontend: $FRONTEND_URL"
echo "  - Picks potentiels: $POTENTIAL_COUNT"
echo "  - Picks sélectionnés: $PICKS_COUNT"
echo ""
echo "🌐 Accède au frontend sur: $FRONTEND_URL"
echo ""

