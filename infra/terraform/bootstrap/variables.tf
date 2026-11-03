# Name prefix; every Azure resource name derives from it. Storage account
# names are a global namespace, so it must be unique per deployer.
variable "prefix" {
  type = string
}

# GitHub repository (owner/name) that CD deploys from.
variable "github_repository" {
  type = string
}

# Immutable numeric IDs GitHub puts in environment-scoped OIDC subjects.
# Read them from the GitHub API (users/<owner> .id, repos/<owner>/<name>
# .id); a recreated repository gets a new ID.
variable "github_owner_id" {
  type = string
}

variable "github_repository_id" {
  type = string
}
