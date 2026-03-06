resource "fly_app" "inference" {
  name = var.app_name
  org  = "personal"
}

resource "fly_machine" "inference_worker" {
  app    = fly_app.inference.name
  region = var.region
  name   = "${var.app_name}-worker"

  image = "registry.fly.io/${var.app_name}:latest"

  services = [
    {
      ports = [
        {
          port     = 443
          handlers = ["tls", "http"]
        },
        {
          port     = 80
          handlers = ["http"]
        }
      ]
      protocol      = "tcp"
      internal_port = 8080
    }
  ]

  vm = {
    cpu_kind = "shared"
    cpus     = 1
    memory   = var.vm_memory
  }
}
