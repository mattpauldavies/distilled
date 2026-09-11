export type Role = "owner" | "member"

export interface WorkspaceMembership {
  id: string
  name: string
  slug: string | null
  role: Role
}

export interface Member {
  user_id: string
  email: string | null
  github_username: string | null
  role: Role
}

export interface PendingInvitation {
  id: string
  email: string
  invited_at: string
  expires_at: string
}

export interface WorkspaceSummary {
  id: string
  name: string
  slug: string | null
  role: Role
  is_default_name: boolean
}

export interface TeamResponse {
  workspace: WorkspaceSummary
  rename_prompt_dismissed: boolean
  members: Member[]
  pending_invitations: PendingInvitation[]
}

export interface MyInvitation {
  id: string
  workspace_id: string
  workspace_name: string
  inviter_name: string | null
  expires_at: string
}
