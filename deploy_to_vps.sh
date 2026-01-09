#!/bin/bash

# 🚀 Script de déploiement automatique sur le VPS
# Usage: ./deploy_to_vps.sh

set -e

COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'
COLOR_NC='\033[0m'

VPS_HOST="juju@192.168.1.134"
VPS_PATH="/home/juju/jimmy-ai-nba"
LOCAL_PATH="/Users/niwa/PycharmProjects/jimmy-ai-nba"

echo -e "${COLOR_BLUE}🚀 Déploiement sur le VPS${COLOR_NC}"
echo "========================================="
echo ""

# Étape 1: Vérifier la connexion SSH
echo -e "${COLOR_YELLOW}[1/7] Test de connexion SSH...${COLOR_NC}"
if ssh -o ConnectTimeout=5 $VPS_HOST "echo 'Connexion OK'" > /dev/null 2>&1; then
    echo -e "${COLOR_GREEN}✅ Connexion SSH réussie${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ Impossible de se connecter au VPS${COLOR_NC}"
    exit 1
fi
echo ""

# Étape 2: Sauvegarder les fichiers modifiés
echo -e "${COLOR_YELLOW}[2/7] Transfert des fichiers backend...${COLOR_NC}"
scp "$LOCAL_PATH/backend/advanced_scoring.py" "$VPS_HOST:$VPS_PATH/backend/" > /dev/null 2>&1
scp "$LOCAL_PATH/backend/betting_service.py" "$VPS_HOST:$VPS_PATH/backend/" > /dev/null 2>&1
scp "$LOCAL_PATH/backend/main.py" "$VPS_HOST:$VPS_PATH/backend/" > /dev/null 2>&1
echo -e "${COLOR_GREEN}✅ Fichiers backend transférés${COLOR_NC}"
echo ""

# Étape 3: Transférer data-pipeline
echo -e "${COLOR_YELLOW}[3/7] Transfert du data-pipeline...${COLOR_NC}"
scp "$LOCAL_PATH/data-pipeline/fetch_odds_snapshots.py" "$VPS_HOST:$VPS_PATH/data-pipeline/" > /dev/null 2>&1
echo -e "${COLOR_GREEN}✅ Data-pipeline transféré${COLOR_NC}"
echo ""

# Étape 4: Transférer check_data_health
echo -e "${COLOR_YELLOW}[4/7] Transfert du script de vérification...${COLOR_NC}"
scp "$LOCAL_PATH/check_data_health.py" "$VPS_HOST:$VPS_PATH/" > /dev/null 2>&1
echo -e "${COLOR_GREEN}✅ Script de vérification transféré${COLOR_NC}"
echo ""

# Étape 5: Rebuild et redémarrage
echo -e "${COLOR_YELLOW}[5/7] Rebuild et redémarrage des conteneurs...${COLOR_NC}"
ssh $VPS_HOST << 'ENDSSH'
cd /home/juju/jimmy-ai-nba
echo "🔧 Arrêt des conteneurs..."
docker compose down
echo "🏗️  Rebuild du backend..."
docker compose build backend
echo "🚀 Redémarrage des services..."
docker compose up -d
echo "⏳ Attente du démarrage complet (10s)..."
sleep 10
ENDSSH
echo -e "${COLOR_GREEN}✅ Conteneurs redémarrés${COLOR_NC}"
echo ""

# Étape 6: Vérifier les logs pour erreurs
echo -e "${COLOR_YELLOW}[6/7] Vérification des logs...${COLOR_NC}"
ERRORS=$(ssh $VPS_HOST "docker logs jimmy_backend --tail 50 2>&1" | grep -i "error\|exception" | grep -v "404 Not Found" | wc -l)
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${COLOR_GREEN}✅ Aucune erreur détectée${COLOR_NC}"
else
    echo -e "${COLOR_YELLOW}⚠️  $ERRORS erreurs dans les logs (à vérifier)${COLOR_NC}"
fi
echo ""

# Étape 7: Test rapide
echo -e "${COLOR_YELLOW}[7/7] Test de l'API...${COLOR_NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://192.168.1.134:8000/games/week")
if [ "$HTTP_CODE" == "200" ]; then
    echo -e "${COLOR_GREEN}✅ API répond correctement${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ API ne répond pas (code: $HTTP_CODE)${COLOR_NC}"
    exit 1
fi
echo ""

# Résumé
echo "========================================="
echo -e "${COLOR_GREEN}✅ DÉPLOIEMENT RÉUSSI !${COLOR_NC}"
echo ""
echo "📋 Prochaines étapes:"
echo "  1. Teste le déploiement: ./test_deployment.sh vps"
echo "  2. Accède au frontend: http://192.168.1.134"
echo "  3. Vérifie les logs: ssh $VPS_HOST 'docker logs -f jimmy_backend'"
echo ""

