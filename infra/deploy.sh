#!/bin/bash
# infra/deploy.sh — SecondUnit GCP deployment script
set -e

PROJECT_ID="${GCP_PROJECT_ID:?Error: GCP_PROJECT_ID must be set}"
REGION="us-central1"
TAG="latest"

# Color output helpers
info()  { echo -e "\033[34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[33m[WARN]\033[0m  $*"; }
fatal() { echo -e "\033[31m[FATAL]\033[0m $*"; exit 1; }

# Pre-flight checks
command -v gcloud >/dev/null 2>&1 || fatal "gcloud CLI not found. Install Google Cloud SDK."
command -v docker >/dev/null 2>&1 || fatal "docker CLI not found."
command -v curl  >/dev/null 2>&1 || fatal "curl not found."

info "Configuring gcloud project to: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
info "Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  iam.googleapis.com \
  --quiet

# Create secrets
info "Creating Secret Manager secrets..."
create_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "$name" --quiet 2>/dev/null; then
    gcloud secrets versions add "$name" --data-file=<(echo -n "$value") --quiet
    ok "Updated secret: $name"
  else
    echo -n "$value" | gcloud secrets create "$name" --data-file=- --replication-policy="automatic" --quiet
    ok "Created secret: $name"
  fi
}

# Check for required env vars and create secrets
if [[ -n "${GEMINI_API_KEY:-}" ]]; then
  create_secret "secondunit-gemini-api-key" "$GEMINI_API_KEY"
else
  warn "GEMINI_API_KEY not set — skipping secret creation"
fi

if [[ -n "${GRAFANA_API_KEY:-}" ]]; then
  create_secret "secondunit-grafana-api-key" "$GRAFANA_API_KEY"
else
  warn "GRAFANA_API_KEY not set — skipping secret creation"
fi

if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  create_secret "secondunit-slack-webhook" "$SLACK_WEBHOOK_URL"
else
  warn "SLACK_WEBHOOK_URL not set — skipping secret creation"
fi

# Build and deploy via Cloud Build
info "Submitting Cloud Build for build + deploy..."
gcloud builds submit \
  --config=infra/cloudbuild.yaml \
  --substitutions="_REGION=$REGION,_PROJECT_ID=$PROJECT_ID" \
  --quiet

# Set up Cloud Scheduler — Sentry polling job
info "Setting up Cloud Scheduler (Sentry poll every minute)..."
SCHEDULER_JOB_ID="secondunit-sentry-poll"
if gcloud scheduler jobs describe "$SCHEDULER_JOB_ID" --location="$REGION" 2>/dev/null; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB_ID" \
    --location="$REGION" \
    --schedule="*/1 * * * *" \
    --uri="https://brain-${REGION}.run.app/sentry/poll" \
    --http-method=GET \
    --time-zone="America/New_York" \
    --quiet
  ok "Updated scheduler job: $SCHEDULER_JOB_ID"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB_ID" \
    --location="$REGION" \
    --schedule="*/1 * * * *" \
    --uri="https://brain-${REGION}.run.app/sentry/poll" \
    --http-method=GET \
    --time-zone="America/New_York" \
    --quiet
  ok "Created scheduler job: $SCHEDULER_JOB_ID"
fi

# Set up IAM service accounts (best-effort)
info "Setting up service accounts..."
SVC="secondunit@$PROJECT_ID.iam.gserviceaccount.com"
if gcloud iam service-accounts describe "$SVC" --quiet 2>/dev/null; then
  ok "Service account exists: $SVC"
else
  gcloud iam service-accounts create secondunit \
    --display-name="SecondUnit Agent" \
    --quiet 2>/dev/null || true
  ok "Service account ready: $SVC"
fi

# Grant Secret Manager access to the service account
if gcloud iam service-accounts describe "$SVC" --quiet 2>/dev/null; then
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SVC" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet 2>/dev/null || warn "Could not bind Secret Manager IAM role"
  ok "Granted Secret Manager access to service account"
fi

ok "SecondUnit deployed successfully!"
ok "Brain service:   https://brain-${REGION}.run.app"
ok "Hands service:   https://hands-${REGION}.run.app"
ok "Simulator:       https://simulator-${REGION}.run.app"
info "Check Cloud Run console: https://console.cloud.google.com/run"
