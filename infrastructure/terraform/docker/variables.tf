variable "name" {
  description = "Application prefix for the container, volume, and labels."
  type        = string
  default     = "public-comment-analyzer"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,50}$", var.name))
    error_message = "Use 3-51 lowercase letters, digits, or hyphens, starting with a letter."
  }
}

variable "image" {
  description = "Existing image on the Docker host. Use a registry digest for releases."
  type        = string
  default     = "public-comment-analyzer:local"
}

variable "port" {
  description = "Loopback-only host port. Put a trusted HTTPS reverse proxy in front for public access."
  type        = number
  default     = 8000
  validation {
    condition     = var.port >= 1024 && var.port <= 65535 && floor(var.port) == var.port
    error_message = "The host port must be an integer between 1024 and 65535."
  }
}

variable "password_hash_file" {
  description = "Absolute path on the Docker HOST to a bcrypt hash file readable by UID 10001. Only this path enters Terraform state."
  type        = string
  validation {
    condition     = startswith(var.password_hash_file, "/")
    error_message = "Provide an absolute file path on the Docker host."
  }
}

variable "allowed_hosts" {
  description = "Allowed HTTP Host values, including localhost and 127.0.0.1 for health checks."
  type        = list(string)
  default     = ["localhost", "127.0.0.1", "[::1]"]
  validation {
    condition     = contains(var.allowed_hosts, "127.0.0.1") && !contains(var.allowed_hosts, "*")
    error_message = "Include 127.0.0.1 for health checks and do not use a wildcard."
  }
}

variable "configuration" {
  description = "Non-secret application settings. Supply credential file paths through secret_files instead of values."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([
      for key in keys(var.configuration) :
      !can(regex("(?i)(^|_)(password|secret|token|api_key|credentials?)(_|$)", key))
    ])
    error_message = "Do not put credentials in configuration; use secret_files with *_FILE variables."
  }
}

variable "secret_files" {
  description = "Map of application *_FILE environment names to absolute files on the Docker host. Secret values are never read by Terraform."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([
      for key, path in var.secret_files :
      can(regex("^[A-Z][A-Z0-9_]*_FILE$", key)) && startswith(path, "/") && key != "ACCESS_PASSWORD_HASH_FILE"
    ])
    error_message = "Use uppercase *_FILE names and absolute host paths. The password hash has its own input."
  }
}
