variable "project_name" {
  description = "Lowercase project identifier used in resource names."
  type        = string
  default     = "pacific-bioarchive"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.project_name))
    error_message = "project_name must be a lowercase DNS-style identifier."
  }
}

variable "environment" {
  type    = string
  default = "development"

  validation {
    condition     = contains(["local", "test", "development", "production"], var.environment)
    error_message = "environment must be one of the values accepted by AppSettings: local, test, development, or production."
  }
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "frontend_callback_urls" {
  type    = list(string)
  default = ["http://localhost:5173/auth/callback"]
}

variable "frontend_logout_urls" {
  type    = list(string)
  default = ["http://localhost:5173/login"]
}

variable "frontend_origins" {
  description = "Exact browser origins allowed by API Gateway CORS (no path component)."
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "cognito_domain_prefix" {
  description = "Globally unique Cognito hosted UI prefix."
  type        = string
}

variable "google_client_id" {
  description = "Optional Google OAuth client ID. Keep the paired secret outside version control."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "enable_google_provider" {
  type    = bool
  default = false
}

variable "google_client_secret" {
  description = "Optional Google OAuth secret supplied only through TF_VAR_google_client_secret."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "microsoft_client_id" {
  description = "Optional Microsoft Entra application ID."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "enable_microsoft_provider" {
  type    = bool
  default = false
}

variable "microsoft_client_secret" {
  description = "Optional Microsoft Entra secret supplied only through TF_VAR_microsoft_client_secret."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "microsoft_tenant" {
  description = "Entra tenant ID, or common for multi-tenant development."
  type        = string
  default     = "common"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "api_package_path" {
  description = "Path to the deterministic AWS API zip built by scripts/build-aws-api-package.ps1."
  type        = string
  default     = "../../build/aws-api.zip"
}

variable "worker_package_path" {
  description = "Path to the media worker Lambda zip."
  type        = string
  default     = "../../build/aws-worker.zip"
}

variable "worker_image_uri" {
  description = "Optional immutable ECR image URI (repository@sha256:digest) for the ML worker."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.worker_image_uri == null || can(regex("^[0-9]+\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/.+@sha256:[a-f0-9]{64}$", var.worker_image_uri))
    error_message = "worker_image_uri must be an immutable ECR repository@sha256:digest URI."
  }
}

variable "worker_enabled" {
  description = "Enable SQS delivery only after the worker image and Cosmos credential are verified."
  type        = bool
  default     = false
}

variable "worker_layer_arns" {
  description = "Optional Lambda layer ARNs containing ffmpeg and the ML runtime/model."
  type        = list(string)
  default     = []
}

variable "worker_cosmos_endpoint" {
  description = "Cosmos endpoint reachable by the worker workload identity."
  type        = string
  default     = ""
}

variable "worker_cosmos_database" {
  type    = string
  default = "bioarchive"
}

variable "worker_cosmos_media_container" {
  type    = string
  default = "media"
}

variable "worker_cosmos_subscriptions_container" {
  type    = string
  default = "subscriptions"
}

variable "worker_cosmos_delivery_ledger_container" {
  type    = string
  default = "delivery-ledger"
}

variable "worker_cosmos_deletion_operations_container" {
  type    = string
  default = "deletion-operations"
}

variable "worker_ml_model_dir" {
  description = "Mounted Lambda layer path containing mdv5a.pt, model.pt and labels.txt."
  type        = string
  default     = "/opt/pba-model"
}

variable "azure_data_api_base_url" {
  description = "Public base URL of the Azure Function data API, without a trailing slash."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+$", var.azure_data_api_base_url))
    error_message = "azure_data_api_base_url must be an HTTPS origin without a path or trailing slash."
  }
}
