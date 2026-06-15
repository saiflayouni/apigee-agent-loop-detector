#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env if present (so users don't need to export manually)
[ -f "$SCRIPT_DIR/.env" ] && source "$SCRIPT_DIR/.env"
BUNDLE="$SCRIPT_DIR/proxy-bundle.zip"
IMAGE="gcr.io/apigee-release/hybrid/apigee-emulator:1.9.2"
CONTAINER="loop-detector"
APIGEE_ORG="hybrid"
APIGEE_ENV="test"
MGMT="http://localhost:8080"
RUNTIME="http://localhost:8998"

# ── 0. Gemini API key (Phase 3 semantic detection) ──────────────────────────

GEMINI_KEY="${GEMINI_API_KEY:-disabled}"
mkdir -p "$SCRIPT_DIR/apiproxy/resources/properties"
echo "gemini_api_key=$GEMINI_KEY" > "$SCRIPT_DIR/apiproxy/resources/properties/config.properties"

if [ "$GEMINI_KEY" = "disabled" ]; then
  echo "ℹ  GEMINI_API_KEY not set — Phase 3 semantic detection disabled"
  echo "   To enable: export GEMINI_API_KEY=your_key && bash deploy.sh"
else
  echo "✓ Gemini API key configured (Phase 3 semantic detection enabled)"
fi

# ── 1. Build proxy bundle (SDLC format) ─────────────────────────────────────

echo "▶ Building proxy bundle..."
SDLC_TMP="$(mktemp -d)/sdlc"
SDLC_ROOT="$SDLC_TMP/src/main/apigee"
PROXY_SRC="$SCRIPT_DIR/apiproxy"

mkdir -p \
  "$SDLC_ROOT/environments/test" \
  "$SDLC_ROOT/apiproxies/loop-detector/apiproxy/policies" \
  "$SDLC_ROOT/apiproxies/loop-detector/apiproxy/proxies" \
  "$SDLC_ROOT/apiproxies/loop-detector/apiproxy/targets" \
  "$SDLC_ROOT/apiproxies/loop-detector/apiproxy/resources/jsc" \
  "$SDLC_ROOT/apiproxies/loop-detector/apiproxy/resources/properties"

echo '{"proxies": [{"name": "loop-detector"}]}' \
  > "$SDLC_ROOT/environments/test/deployments.json"

DEST="$SDLC_ROOT/apiproxies/loop-detector/apiproxy"
cp "$PROXY_SRC/loop-detector.xml"                  "$DEST/"
cp "$PROXY_SRC/policies/"*.xml                     "$DEST/policies/"
cp "$PROXY_SRC/proxies/default.xml"                "$DEST/proxies/"
cp "$PROXY_SRC/targets/default.xml"                "$DEST/targets/"
cp "$PROXY_SRC/resources/jsc/"*.js                 "$DEST/resources/jsc/"
cp "$PROXY_SRC/resources/properties/config.properties" "$DEST/resources/properties/"

(cd "$SDLC_TMP" && zip -r "$BUNDLE" src/ -q)
echo "✓ Bundle built ($(du -h "$BUNDLE" | cut -f1))"

# ── 2. Start emulator ────────────────────────────────────────────────────────

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "✓ Emulator already running"
else
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "▶ Restarting existing container..."
    docker start "$CONTAINER"
  else
    echo "▶ Starting emulator..."
    docker run -d \
      --name "$CONTAINER" \
      -p 8080:8080 \
      -p 8998:8998 \
      -e APIGEE_ORG="$APIGEE_ORG" \
      -e APIGEE_ENV="$APIGEE_ENV" \
      -e LISTEN_ADDRESS=127.0.0.1 \
      -e GOOGLE_APPLICATION_CREDENTIALS="" \
      -e microkernel_installType=hybrid \
      -e microkernel_application=emulator \
      "$IMAGE"
  fi
fi

# ── 3. Wait for emulator to be ready ────────────────────────────────────────

echo -n "⏳ Waiting for emulator"
READY=false
for i in $(seq 1 60); do
  if curl -sf "$MGMT/v1/emulator/version" > /dev/null 2>&1; then
    READY=true
    break
  fi
  echo -n "."
  sleep 2
done
echo ""

if [ "$READY" = false ]; then
  echo "✗ Emulator did not start within 120s"
  docker logs "$CONTAINER" --tail 20
  exit 1
fi
echo "✓ Emulator ready"

# ── 4. Deploy proxy bundle ───────────────────────────────────────────────────

echo "▶ Deploying proxy bundle..."
RESPONSE=$(curl -sf -X POST \
  "$MGMT/v1/emulator/deploy?environment=$APIGEE_ENV" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@$BUNDLE")

REVISION=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('revision','?'))" 2>/dev/null || echo "?")
echo "✓ Deployed revision $REVISION"

# ── 5. Smoke test ────────────────────────────────────────────────────────────

echo "▶ Smoke testing..."

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RUNTIME/ai-agent")
if [ "$STATUS" != "200" ]; then
  echo "✗ Normal request returned $STATUS (expected 200)"
  exit 1
fi
echo "✓ Normal request → 200"

LOOP_BODY=$(curl -s -w "\n%{http_code}" "$RUNTIME/ai-agent" -H "X-Agent-Loop-Count: 10")
LOOP_STATUS=$(echo "$LOOP_BODY" | tail -1)
LOOP_JSON=$(echo "$LOOP_BODY" | head -1)

if [ "$LOOP_STATUS" != "429" ]; then
  echo "✗ Loop request returned $LOOP_STATUS (expected 429)"
  exit 1
fi
echo "✓ Structural loop → 429"

COST=$(echo "$LOOP_JSON" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'  detection_type={d.get(\"detection_type\",\"?\")}  cost_saved_usd={d[\"cost_saved_usd\"]}  calls_prevented={d[\"calls_prevented\"]}')" \
  2>/dev/null || echo "  (could not parse JSON)")
echo "$COST"

echo ""
if [ "$GEMINI_KEY" = "disabled" ]; then
  echo "🚀 Demo ready! (Phase 1+2)"
else
  echo "🚀 Demo ready! (Phase 1+2+3 — Gemini semantic detection active)"
fi
echo "   Runtime : $RUNTIME/ai-agent"
echo "   Org/Env : $APIGEE_ORG / $APIGEE_ENV"

# ── 6. Start UI server ───────────────────────────────────────────────────────

UI_PORT=3000

if lsof -ti tcp:$UI_PORT > /dev/null 2>&1; then
  echo "✓ UI server already running"
else
  echo "▶ Starting UI server..."
  cd "$SCRIPT_DIR" && python3 server.py > /tmp/apigee-ui.log 2>&1 &
  UI_PID=$!
  sleep 1
  if kill -0 "$UI_PID" 2>/dev/null; then
    echo "✓ UI server started (pid $UI_PID)"
  else
    echo "✗ UI server failed to start — check /tmp/apigee-ui.log"
  fi
fi

echo ""
echo "   Open: http://localhost:$UI_PORT"

# Open browser (macOS / Linux)
if command -v open > /dev/null 2>&1; then
  open "http://localhost:$UI_PORT"
elif command -v xdg-open > /dev/null 2>&1; then
  xdg-open "http://localhost:$UI_PORT"
fi
