variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "dev | staging | prod"
  type        = string
  default     = "dev"
}

variable "instance_type" {
  description = "EC2 instance type for the ARQ worker"
  type        = string
  default     = "t3.micro"
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to SSH into the worker (e.g. your home IP: \"1.2.3.4/32\")"
  type        = string
}

variable "ssh_public_key" {
  description = "Contents of your ~/.ssh/id_ed25519.pub (or equivalent)"
  type        = string
}

# ── Secrets passed in via CI environment variables — never hardcoded ──
variable "redis_url" {
  description = "Upstash Redis DSN"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Neon Postgres connection string"
  type        = string
  sensitive   = true
}

variable "webhook_secret" {
  description = "GitHub App webhook secret"
  type        = string
  sensitive   = true
}

variable "github_app_id" {
  description = "GitHub App numeric ID"
  type        = string
  sensitive   = true
}

variable "github_private_key_b64" {
  description = "Base64-encoded contents of the GitHub App private key .pem file"
  type        = string
  sensitive   = true
}
