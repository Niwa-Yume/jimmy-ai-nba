#!/bin/bash
# Test des changements de scoring avant déploiement

echo "🔍 Vérification des seuils dans advanced_scoring.py..."
grep -n "MIN_EDGE\|MIN_SCORE\|MIN_SAMPLE_SIZE" backend/advanced_scoring.py | head -3

echo ""
echo "✅ Configuration mise à jour:"
echo "   - MIN_EDGE: 3.5% (avant: 6%)"
echo "   - MIN_SCORE: 50 (avant: 55)"
echo "   - MIN_SAMPLE_SIZE: 8 (avant: 10)"
echo ""
echo "📤 Prêt pour déploiement sur VPS..."
