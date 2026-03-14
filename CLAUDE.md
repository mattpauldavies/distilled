# CLAUDE.md

## Workflow

For most tasks, our default work process is:

1. Read a PRD or create a lightweight PRD in `/docs/prds`
2. Read relevant documentation in `/docs` for context
3. Read relevant code in either `/server` or `/client` for context
4. Create a technical design and create an RFC in `/docs/rfcs`
5. Allow user to review and approve the technical design
6. Once approved, create an implementation plan and append this to the same RFC document
7. When the plan is agreed, begin implementation following red/green test driven development
8. Note any architectural decisions or technical decisions outside of the RFC in ADR documents in `/docs/adrs`

Note you may be asked for ad-hoc tasks, such as UI design changes, that fall outside of this workflow.

## Rules

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

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Tips

- I might say to you something like "tackle <file path>" with the file being a Product Requirements Document. What I mean is "Read the PRD @<file path> and build a solution that meets the requirements laid out in the document"
- Don't include any references to yourself (Claude Code) when writing commit messages or PR descriptions.
