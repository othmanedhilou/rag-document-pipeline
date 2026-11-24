variable "project" {
  type    = string
  default = "docpipe"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "location" {
  type    = string
  default = "francecentral"
}

variable "openai_location" {
  description = "Region where the embedding and chat models are available"
  type        = string
  default     = "swedencentral"
}

variable "search_sku" {
  description = "free allows one index of 50 MB, basic is the smallest paid tier"
  type        = string
  default     = "basic"
}
