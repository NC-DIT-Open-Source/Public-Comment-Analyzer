locals {
  settings = merge(var.configuration, {
    APP_RUNTIME               = "local"
    APP_DATA_DIR              = "/data"
    APP_STATIC_DIR            = "/app/static"
    APP_ALLOWED_HOSTS         = join(",", var.allowed_hosts)
    ACCESS_PASSWORD_HASH_FILE = "/run/secrets/access_password_hash"
    LLM_KILL_SWITCH_FILE      = "/data/STOP_LLM"
  }, { for key, path in var.secret_files : key => "/run/secrets/${lower(key)}" })
}

data "docker_image" "app" {
  name = var.image
}

resource "docker_volume" "data" {
  name = "${var.name}-data"
  labels {
    label = "application"
    value = var.name
  }
  # Removing the application must not delete uploaded comments or job history.
  lifecycle {
    prevent_destroy = true
  }
}

resource "docker_container" "app" {
  name           = var.name
  image          = data.docker_image.app.id
  init           = true
  user           = "10001:10001"
  read_only      = true
  restart        = "unless-stopped"
  memory         = 4096
  cpu_period     = 100000
  cpu_quota      = 200000
  stop_timeout   = 60
  security_opts  = ["no-new-privileges:true"]
  env            = [for key, value in local.settings : "${key}=${value}"]
  tmpfs          = { "/tmp" = "rw,noexec,nosuid,size=512m,mode=1777" }
  log_driver     = "json-file"
  log_opts       = { "max-size" = "10m", "max-file" = "3" }
  remove_volumes = false
  wait           = true
  wait_timeout   = 120

  capabilities {
    drop = ["ALL"]
  }
  ulimit {
    name = "nproc"
    soft = 128
    hard = 128
  }
  ports {
    internal = 8000
    external = var.port
    ip       = "127.0.0.1"
  }
  mounts {
    type   = "volume"
    source = docker_volume.data.name
    target = "/data"
  }
  mounts {
    type      = "bind"
    source    = var.password_hash_file
    target    = "/run/secrets/access_password_hash"
    read_only = true
  }
  dynamic "mounts" {
    for_each = var.secret_files
    content {
      type      = "bind"
      source    = mounts.value
      target    = "/run/secrets/${lower(mounts.key)}"
      read_only = true
    }
  }
  labels {
    label = "application"
    value = var.name
  }
}
