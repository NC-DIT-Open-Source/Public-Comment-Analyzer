output "url" {
  description = "Application URL on the Docker host; remote hosts require an SSH tunnel or HTTPS reverse proxy."
  value       = "http://127.0.0.1:${var.port}"
}

output "data_volume" {
  description = "Persistent data volume protected against accidental Terraform destruction."
  value       = docker_volume.data.name
}
