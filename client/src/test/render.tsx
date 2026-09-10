/* eslint-disable react-refresh/only-export-components */
import { render, type RenderOptions } from "@testing-library/react"
import type { ReactElement, ReactNode } from "react"
import { WorkspaceProvider } from "@/lib/workspaceContext"

interface ProvidersProps {
  children: ReactNode
}

export function TestProviders({ children }: ProvidersProps) {
  return <WorkspaceProvider>{children}</WorkspaceProvider>
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: TestProviders, ...options })
}
