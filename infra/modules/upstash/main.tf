resource "upstash_redis_database" "behavioral" {
  database_name = "behavioral-stream"
  region        = var.region
  tls           = true
}

resource "upstash_vector_index" "fingerprints" {
  index_name        = "behavioral-fingerprints"
  region            = var.region
  dimension_count   = var.vector_dimensions
  similarity_function = var.vector_similarity
}
