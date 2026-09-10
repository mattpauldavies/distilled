export interface WorkspaceInstallation {
  installation_id: number
  account_login: string
  account_type: string
  repo_count: number
  removed: boolean
}

export interface AvailableRepo {
  github_id: number
  full_name: string
  default_branch: string | null
  tracked: boolean
}
