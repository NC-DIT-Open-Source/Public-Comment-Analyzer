terraform {
  required_version = ">= 1.5, < 2.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 4.6.0"
    }
  }
}

# Uses the selected Docker context or DOCKER_HOST. A remote daemon should be
# reached through SSH or mutually authenticated TLS, never an open TCP socket.
provider "docker" {}
