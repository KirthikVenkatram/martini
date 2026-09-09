#!/usr/bin/env bash
# Deploy MARTINI to Cloud Run, building from source.
#
# Region is us-central1 to match GOOGLE_CLOUD_LOCATION for Vertex AI --
# same-region keeps Gemini calls off a cross-region hop.
#
# Secrets (GRAFANA_SERVICE_ACCOUNT_TOKEN, OTEL_EXPORTER_OTLP_HEADERS) live in
# Secret Manager and are wired in with --set-secrets, never as plain env vars
# on the service definition. This script reads their values out of the local
# .env file at run time and pushes them into Secret Manager itself -- the
# values never appear in shell history or in this script.
#
# Everything else (Grafana URL, OTLP endpoint/protocol, Gemini model/project)
# is not a secret and is passed with --set-env-vars.
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT_ID="martini-proj-508014-f8"
REGION="us-central1"
SERVICE="martini"
ENV_FILE=".env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found -- can't read secret values for Secret Manager." >&2
  exit 1
fi

# Pull a value out of .env without ever echoing it or putting it on the
# command line (dotenv-style: KEY=value, optionally "quoted").
env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
import sys
path, key = sys.argv[1], sys.argv[2]
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            print(v)
            break
PY
}

put_secret() {
  local secret_name="$1"
  local value="$2"

  if [[ -z "$value" ]]; then
    echo "error: no value found for $secret_name in $ENV_FILE" >&2
    exit 1
  fi

  if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$secret_name" \
      --project="$PROJECT_ID" --data-file=- >/dev/null
    echo "secret manager: $secret_name -- added new version"
  else
    printf '%s' "$value" | gcloud secrets create "$secret_name" \
      --project="$PROJECT_ID" --replication-policy="automatic" --data-file=- >/dev/null
    echo "secret manager: $secret_name -- created"
  fi
}

echo "==> syncing secrets from $ENV_FILE into Secret Manager"
put_secret "GRAFANA_SERVICE_ACCOUNT_TOKEN" "$(env_value GRAFANA_SERVICE_ACCOUNT_TOKEN)"
put_secret "OTEL_EXPORTER_OTLP_HEADERS" "$(env_value OTEL_EXPORTER_OTLP_HEADERS)"

echo "==> granting the Cloud Run runtime service account Vertex AI access"
# Cloud Run's default runtime service account, unless the project has been
# configured to use a different one for this service. This same account is
# also what --source deploys use to run Cloud Build, so it additionally
# needs storage.objectViewer (to read the uploaded source zip) and
# logging.logWriter (to write build logs), artifactregistry.writer (to push
# the built image), and secretmanager.secretAccessor (to read the two
# secrets wired in below at container startup) -- none of these are granted
# by default on this project.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for role in roles/aiplatform.user roles/storage.objectViewer roles/logging.logWriter roles/artifactregistry.writer roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null
  echo "iam: granted $role to ${RUNTIME_SA}"
done

echo "==> deploying $SERVICE to Cloud Run ($REGION), building from source"
# --min-instances=1 keeps one instance warm so judges never hit a cold start
# during judging. Cost: ~730 instance-hours/month on the smallest Cloud Run
# CPU/memory tier (1 vCPU / 512MiB, always-allocated CPU) is roughly
# $10-15/month in us-central1 at on-demand pricing, before any free-tier
# credit. Drop --min-instances=1 (or set it to 0) after judging ends.
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --allow-unauthenticated \
  --min-instances=1 \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GEMINI_MODEL=gemini-2.5-flash,GRAFANA_URL=$(env_value GRAFANA_URL),OTEL_EXPORTER_OTLP_ENDPOINT=$(env_value OTEL_EXPORTER_OTLP_ENDPOINT),OTEL_EXPORTER_OTLP_PROTOCOL=$(env_value OTEL_EXPORTER_OTLP_PROTOCOL)" \
  --set-secrets="GRAFANA_SERVICE_ACCOUNT_TOKEN=GRAFANA_SERVICE_ACCOUNT_TOKEN:latest,OTEL_EXPORTER_OTLP_HEADERS=OTEL_EXPORTER_OTLP_HEADERS:latest"

echo "==> done"
gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)'
