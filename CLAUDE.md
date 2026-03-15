# CLAUDE.md

## Workflow

For most tasks, our default work process is:

1. Read a PRD or create a lightweight PRD in `/docs/prds`
2. Read relevant documentation in `/docs` for context
3. Read relevant code in either `/server` or `/client` for context
4. Create a technical design and create an RFC in `/docs/rfcs`
5. Allow user to review and approve the technical design
6. Once approved, create an implementation plan and append this to the same RFC document. **Never save plans to `docs/superpowers/plans/` — always append to the RFC.**
7. When the plan is agreed, begin implementation following red/green test driven development
8. Note any architectural decisions or technical decisions outside of the RFC in ADR documents in `/docs/adrs`

Note you may be asked for ad-hoc tasks, such as UI design changes, that fall outside of this workflow.

I might say to you something like "tackle <file path>" with the file being a Product Requirements Document. What I mean is "Read the PRD @<file path> and build a solution that meets the requirements laid out in the document"

## Superpowers Skill Overrides

These project conventions override superpowers skill defaults:

- **Spec location** (`brainstorming` skill default: `docs/superpowers/specs/`): Save specs as the next numbered RFC in `docs/rfcs/NNN-topic.md` and match the existing RFC format.
- **Plan location** (`writing-plans` skill default: `docs/superpowers/plans/`): Append the implementation plan to the **bottom of the same RFC file**. Never create a separate plan file.
- **Commit messages**: No `Co-Authored-By: Claude` lines — see "No Promo" below.

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **No Promo:** Don't include any references to yourself (Claude Code) when writing commit messages or PR descriptions.

## Engineering Context

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One goal per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update `/docs/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 7. Write excellent documentation

- After every bit of code that is create or updated write or update our documentation
- Most documentation should live in `/docs` as .md markdown files
- There are three README files to keep up to date: `/README.md`, `/server/README.md`, and `/client/README.md`
- Try to avoid other README files preferring to add files in `/docs`
- If we make adjustments that change the way people would contribute to the project make sure to update `/CONTRIBUTING.md`

## Design Context

### Users

Engineering leaders (CTOs, VPs, engineering managers) who need fast, trustworthy visibility into software delivery health. They open Distilled to get answers — not to explore dashboards. Their context: high cognitive load, little patience for noise, high trust requirements. The job to be done: "Tell me what's actually happening in my team's delivery, without me having to dig."

### Brand Personality

**Bold, direct, powerful.** Distilled doesn't hedge. It presents data with confidence and gets out of the way. The product should feel like a precision instrument — authoritative without being cold, intelligent without being showy.

### Emotional Goal

**Quiet control.** Users should feel "I'm on top of it" — a calm reassurance that delivery is being watched and understood. Not anxiety-inducing, not over-exciting. The calm confidence of a well-maintained system.

### Aesthetic Direction

- **References:** Linear (dark, sharp, premium dev-tool feel) and Raycast (fast, focused, beautiful power-user tool)
- **Theme:** Dark by default — dark surfaces as the primary experience
- **Anti-references:** Avoid anything that feels like a generic SaaS dashboard, BI tool, or colorful chart-fest
- **Palette:** Deep neutral backgrounds (near-black), high-contrast foreground text, restrained accent usage, semantic color only for data status
- **Typography:** Tight, precise, no decorative fonts — system or geometric sans-serif
- **Motion:** Minimal. If animated, purposeful and fast (no bouncy transitions)

### Design Principles

1. **Signal over noise** — Every pixel must earn its place. Remove anything that doesn't help the user understand their delivery.
2. **Data is the hero** — Charts and metrics take center stage; chrome, borders, and decoration recede.
3. **Dark, precise, premium** — The interface should feel like a tool built for serious people. Dark surfaces, tight spacing, confident typography.
4. **Semantic color only** — Color is reserved for status communication (healthy/warning/critical). Never decorative.
5. **Immediate comprehension** — Layouts, labels, and hierarchy must allow the user to understand the key story within 3 seconds of opening the page.
