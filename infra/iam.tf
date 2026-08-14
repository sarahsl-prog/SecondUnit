# infra/iam.tf — SecondUnit GCP IAM configuration (Terraform)
# Provider and project configuration is injected by Cloud Build / gcloud.

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

# ── Service Account ──────────────────────────────────────────────────────────

resource "google_service_account" "secondunit" {
  project = var.project_id
  account_id   = "secondunit"
  display_name = "SecondUnit Agent Service Account"
  description  = "Service account for SecondUnit Cloud Run services"
}

# ── Secret Manager ─────────────────────────────────────────────────────────────

resource "google_project_iam_member" "secretmanager_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

# ── Cloud Run ─────────────────────────────────────────────────────────────────

resource "google_project_iam_member" "cloudrun_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

# ── Cloud Scheduler ────────────────────────────────────────────────────────────

resource "google_project_iam_member" "cloud_scheduler_invoker" {
  project = var.project_id
  role    = "roles/cloudscheduler.invoker"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

# ── Logs Writer ───────────────────────────────────────────────────────────────

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

# ── Artifact Registry ─────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "secondunit" {
  project       = var.project_id
  location      = var.region
  repository_id = "secondunit"
  description   = "Container images for SecondUnit render farm agent"
  format        = "DOCKER"
}

resource "google_project_iam_member" "artifact_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

resource "google_project_iam_member" "artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.secondunit.email}"
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "service_account_email" {
  value = google_service_account.secondunit.email
}

output "artifact_registry_url" {
  value = google_artifact_registry_repository.secondunit.repository_url
}
