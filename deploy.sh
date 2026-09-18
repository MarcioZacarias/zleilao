#!/bin/bash
# ============================================
# ZConnect Leilão — subida LOCAL de desenvolvimento.
# --------------------------------------------
# Usa o docker-compose.override.yml (portas em 0.0.0.0 e codigo montado).
# Em PRODUCAO nao use este script. Ver DEPLOY.md.
# ============================================
set -e

if [ -d /opt/zconnect_crm ] || [ -d /opt/zconnect_suporte ] || [ -d /opt/zconnect_promo ]; then
    echo "ABORTADO: isto parece o servidor de producao compartilhado."
    echo "Use o procedimento do DEPLOY.md, nao este script."
    exit 1
fi

echo "=== ZConnect Leilão - ambiente local ==="
command -v docker >/dev/null 2>&1 || { echo "Docker nao encontrado"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose nao encontrado"; exit 1; }

if [ ! -f .env ]; then
    cp .env.example .env
    echo "[!] .env criado a partir do .env.example - edite antes de continuar"
    exit 1
fi

set -a; . ./.env; set +a

echo "[1/3] Subindo containers..."
docker compose --env-file .env -p zconnect_leilao \
  -f docker/docker-compose.yml -f docker/docker-compose.override.yml up -d --build

echo "[2/3] Aguardando banco de dados..."
until docker exec zleilao-db pg_isready -U "${POSTGRES_USER:-zleilao}" >/dev/null 2>&1; do sleep 2; done

echo "[3/3] Verificando..."
BACKEND_PORT="${BACKEND_PORT:-8005}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5177}"
sleep 3
B=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${BACKEND_PORT}/health" || echo 000)
D=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${DASHBOARD_PORT}/" || echo 000)
echo "  Backend:   $B (http://localhost:${BACKEND_PORT}/docs)"
echo "  Dashboard: $D (http://localhost:${DASHBOARD_PORT} | /admin)"
[ "$B" = "200" ] && [ "$D" = "200" ] && echo "=== Ambiente local no ar! ===" || echo "=== Verifique: docker logs zleilao-backend ==="
