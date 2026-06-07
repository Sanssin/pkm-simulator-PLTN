# Copilot Instructions — pkm-simulator-PLTN

## 📖 Project Context

**ALWAYS read these files first:**
- `AGENT.md` — Full technical documentation (architecture, protocols, file structure)
- `.claude/SKILLS.md` — Specialized knowledge index for specific domains

**Available Skills** (in `.claude/skills/`):
- `firmware-embedded.md` — GPIO, sensors, threading, ESP32/Raspberry Pi
- `nuclear-sim-physics.md` — Reactor physics, formulas, simulation parameters
- `safety-logic.md` — SCRAM, alarms, interlocks, safety thresholds
- `hmi-display.md` — UI updates, display management, visual/audio feedback
- `pltn-domain-knowledge.md` — Nuclear terminology, concepts, operating scenarios

## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready` - Find unblocked work
- `bd create "Title" --type task --priority 2` - Create issue
- `bd show <id>` - View issue details
- `bd update <id> --status in_progress` - Claim work
- `bd close <id>` - Complete work
- `bd sync` - Sync with git (run at session end)

For full workflow details: `bd prime`

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
