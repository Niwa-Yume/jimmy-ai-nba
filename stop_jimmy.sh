#!/bin/bash

echo "🛑 Arrêt forcé de tous les processus Jimmy.AI..."

# 1. Arrêter le Backend (Uvicorn)
# On cherche tout processus contenant "uvicorn"
count_backend=$(pgrep -f "uvicorn" | wc -l)
if [ "$count_backend" -gt 0 ]; then
    pkill -f "uvicorn"
    echo "✅ $count_backend processus Backend (uvicorn) tués."
else
    echo "👌 Aucun processus Backend trouvé."
fi

# 2. Arrêter le Frontend (Streamlit)
# On cherche tout processus contenant "streamlit"
count_frontend=$(pgrep -f "streamlit" | wc -l)
if [ "$count_frontend" -gt 0 ]; then
    pkill -f "streamlit"
    echo "✅ $count_frontend processus Frontend (streamlit) tués."
else
    echo "👌 Aucun processus Frontend trouvé."
fi

# 3. Vérification des ports
echo "🔍 Vérification des ports..."
lsof -i :8000 >/dev/null && echo "⚠️ ATTENTION : Le port 8000 est toujours occupé !" || echo "✨ Port 8000 libéré."
lsof -i :8501 >/dev/null && echo "⚠️ ATTENTION : Le port 8501 est toujours occupé !" || echo "✨ Port 8501 libéré."

echo "🧹 Nettoyage terminé."
