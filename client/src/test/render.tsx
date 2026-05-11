/* eslint-disable react-refresh/only-export-components */
import { render, type RenderOptions } from "@testing-library/react"
import type { ReactElement, ReactNode } from "react"
import { TenantProvider } from "@/lib/tenantContext"

interface ProvidersProps {
  children: ReactNode
}

export function TestProviders({ children }: ProvidersProps) {
  return <TenantProvider>{children}</TenantProvider>
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: TestProviders, ...options })
}
