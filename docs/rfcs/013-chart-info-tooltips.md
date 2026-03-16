# RFC 013: Chart Info Tooltips

## Summary

Add contextual `(i)` info buttons to each chart panel header. Clicking the button opens a small popover explaining what the graph is showing and how to interpret it. The button should appear in the top right of the panel.

## Decisions

- **Trigger:** Click to open, click outside or Escape to dismiss (not hover — deliberate interaction)
- **Placement:** `CardAction` slot in `ChartPanel` header (top-right of card)
- **Popover library:** Radix UI (already installed, used by Select component)
- **Icon:** `InfoIcon` from lucide-react (already installed and used in the codebase)
- **Scope:** Purely presentational — no data logic, no API changes

## Component Design

### New: `client/src/components/ui/popover.tsx`

Thin wrapper around the `Popover` primitive from the `"radix-ui"` package (the unified package already used by `select.tsx` — no new installation needed), styled to match the dark theme:

- Background: `bg-popover text-popover-foreground` (uses the dedicated `--color-popover` token, consistent with `SelectContent`)
- Text: `text-foreground`
- Border: `border`
- Shadow: `shadow-lg`
- Max width: `max-w-xs` (~320px)
- Padding: `p-3`
- Font size: `text-sm`

### New: `client/src/components/InfoButton.tsx`

Self-contained component combining the trigger button and popover content.

**Props:**

```ts
interface InfoButtonProps {
  content: string;
}
```

Renders a small ghost icon button (`size="icon-xs"`, `variant="ghost"`) with `InfoIcon` (16px, muted foreground colour). Wraps `Popover`, `PopoverTrigger`, and `PopoverContent`.

### Updated: `client/src/components/ChartPanel.tsx`

Add optional `info?: string` prop. When present, add a `<CardAction>` element to the `CardHeader` JSX (not currently present in the component) containing `<InfoButton content={info} />`.

### Updated: `client/src/components/Dashboard.tsx`

Pass `info` prop to each of the four `ChartPanel` instances.

## Tooltip Content

| Chart       | Content                                                                                                                                                     |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deployments | "The number of deployments to production per day. A core DORA metric — higher frequency means smaller, safer changes shipped more often."                   |
| Lead Time   | "Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops." |
| Cycle Time  | "Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."              |
| PR Ageing   | "Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."               |

## File Changes

| File                                   | Change                               |
| -------------------------------------- | ------------------------------------ |
| `client/src/components/ui/popover.tsx` | New — Radix UI Popover wrapper       |
| `client/src/components/InfoButton.tsx` | New — (i) button + popover component |
| `client/src/components/ChartPanel.tsx` | Add optional `info?: string` prop    |
| `client/src/components/Dashboard.tsx`  | Pass `info` to each ChartPanel       |

## Testing

- Update `ChartPanel.test.tsx` to cover the `info` prop: assert `InfoButton` renders when `info` is provided, and does not render when absent.
- Add a unit test for `InfoButton` verifying the popover content is shown after clicking the trigger.

## Out of Scope

- Metric cards (only charts in scope)
- Hover tooltips
- Animated transitions
- Multi-line rich content (plain text only)

---

# Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clickable `(i)` info buttons to all four chart panel headers that open a popover explaining what the graph shows.

**Architecture:** Create a thin `popover.tsx` UI wrapper (matching the existing `select.tsx` pattern), a self-contained `InfoButton` component, then wire it into `ChartPanel` via an optional `info` prop.

**Tech Stack:** React, TypeScript, Tailwind CSS, `radix-ui` (already installed), `lucide-react` (already installed), `vitest` + `@testing-library/react`

---

## Chunk 1: Popover primitive + InfoButton

### Task 1: Create `popover.tsx` UI wrapper

**Files:**
- Create: `client/src/components/ui/popover.tsx`

- [ ] **Step 1: Write the file**

```tsx
import { Popover as PopoverPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

function Popover({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root {...props} />
}

function PopoverTrigger({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger {...props} />
}

function PopoverContent({
  className,
  align = "end",
  sideOffset = 6,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-md border bg-popover p-3 text-sm text-popover-foreground shadow-lg outline-none",
          className
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
}

export { Popover, PopoverTrigger, PopoverContent }
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/ui/popover.tsx
git commit -m "feat: add Popover UI primitive"
```

---

### Task 2: Create `InfoButton` component with tests (TDD)

**Files:**
- Create: `client/src/components/InfoButton.tsx`
- Create: `client/src/components/InfoButton.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// client/src/components/InfoButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InfoButton } from "./InfoButton";

describe("InfoButton", () => {
  it("does not show content before clicking", () => {
    render(<InfoButton content="Explanation text" />);
    expect(screen.queryByText("Explanation text")).not.toBeInTheDocument();
  });

  it("shows content after clicking the trigger", async () => {
    const user = userEvent.setup();
    render(<InfoButton content="Explanation text" />);
    await user.click(screen.getByRole("button", { name: /more information/i }));
    expect(screen.getByText("Explanation text")).toBeInTheDocument();
  });

  it("closes after clicking trigger again", async () => {
    const user = userEvent.setup();
    render(<InfoButton content="Explanation text" />);
    await user.click(screen.getByRole("button", { name: /more information/i }));
    await user.click(screen.getByRole("button", { name: /more information/i }));
    // Radix Popover sets data-state="closed" rather than unmounting from DOM
    expect(screen.getByText("Explanation text")).toHaveAttribute("data-state", "closed");
  });
});
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/components/InfoButton.test.tsx
```
Expected: FAIL — `InfoButton` not found

- [ ] **Step 3: Implement `InfoButton`**

```tsx
// client/src/components/InfoButton.tsx
import { InfoIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

interface InfoButtonProps {
  content: string
}

export function InfoButton({ content }: InfoButtonProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="More information"
          className="text-muted-foreground"
        >
          <InfoIcon className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent>{content}</PopoverContent>
    </Popover>
  )
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/components/InfoButton.test.tsx
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add client/src/components/InfoButton.tsx client/src/components/InfoButton.test.tsx
git commit -m "feat: add InfoButton component with popover"
```

---

## Chunk 2: ChartPanel + Dashboard wiring

### Task 3: Wire `InfoButton` into `ChartPanel` (TDD)

**Files:**
- Modify: `client/src/components/ChartPanel.tsx`
- Modify: `client/src/components/ChartPanel.test.tsx`

- [ ] **Step 1: Write the failing tests** — add to `ChartPanel.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { ChartPanel } from "./ChartPanel";

// Add these two new test cases inside the existing describe block:

it("renders InfoButton when info prop is provided", () => {
  render(
    <ChartPanel title="Deployments" caption="Daily count" info="Some info">
      <div>chart</div>
    </ChartPanel>
  );
  // aria-label="More information" on the InfoButton trigger — use regex for case-insensitive match
  expect(screen.getByRole("button", { name: /more information/i })).toBeInTheDocument();
});

it("does not render InfoButton when info prop is absent", () => {
  render(
    <ChartPanel title="Deployments" caption="Daily count">
      <div>chart</div>
    </ChartPanel>
  );
  expect(screen.queryByRole("button", { name: /more information/i })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/components/ChartPanel.test.tsx
```
Expected: 2 new tests FAIL

- [ ] **Step 3: Update `ChartPanel.tsx`**

```tsx
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoButton } from "@/components/InfoButton";
import type { ReactNode } from "react";

interface Props {
  title: string;
  caption: string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  info?: string;
  children: ReactNode;
}

export function ChartPanel({ title, caption, loading, empty, emptyMessage = "No data available", info, children }: Props) {
  return (
    <Card className="gap-2 py-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{caption}</p>
        {info && (
          <CardAction>
            <InfoButton content={info} />
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-[220px] w-full" />
        ) : empty ? (
          <div className="flex h-[220px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              {emptyMessage}
            </p>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run all ChartPanel tests to confirm they pass (including the 3 pre-existing tests)**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run src/components/ChartPanel.test.tsx
```
Expected: 5 tests PASS (3 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add client/src/components/ChartPanel.tsx client/src/components/ChartPanel.test.tsx
git commit -m "feat: add info prop to ChartPanel"
```

---

### Task 4: Pass `info` to each ChartPanel in Dashboard

**Files:**
- Modify: `client/src/components/Dashboard.tsx`

- [ ] **Step 1: Add `info` prop to each of the four `ChartPanel` instances**

Deployments panel — add:
```tsx
info="The number of deployments to production per day. A core DORA metric — higher frequency means smaller, safer changes shipped more often."
```

Lead Time panel — add:
```tsx
info="Time from first commit to production deploy, shown as median and 75th percentile (P75). Lower lead time means faster delivery and shorter feedback loops."
```

PR Cycle Time panel — add:
```tsx
info="Time from PR opened to merged, shown as median and 75th percentile (P75). High cycle time often indicates bottlenecks in the review process."
```

PR Ageing panel — add:
```tsx
info="Age distribution of currently open PRs. A healthy team keeps most PRs in the green bucket — older PRs signal review delays or blocked work."
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```bash
cd client && source ~/.nvm/nvm.sh && nvm use && npx vitest run
```
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add client/src/components/Dashboard.tsx
git commit -m "feat: add info tooltips to all chart panels"
```
