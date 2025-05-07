variable "name" {
  description = "The name of the personal access token."
  type        = string
}

variable "scopes" {
  description = "The scopes of the personal access token."
  type        = list(string)
}
