# PKM Simulator PLTN — Claude Context

## Project Overview
PWR Nuclear Power Plant Simulator, 300 MWe / 900 MWth.
Kompetisi PKM 2024. Branch aktif: `special-project`.

## Architecture
- Master: Raspberry Pi 4 (Python 3.7+)
- Slave 1: ESP32 ESP-BC — control rod, motor, relay
- Slave 2: ESP32 ESP-E — LED flow, LED power indicator
- Protocol: UART binary 115200 baud, CRC8, ACK/NACK

## Key Constraints (SELALU PATUHI)
- Jangan ubah GPIO mapping tanpa update GPIO_PIN_MAPPING.md
- UART0 → GPIO 14/15 (ESP-BC), UART3 → GPIO 4/5 (ESP-E)
- GPIO 5 TIDAK BISA untuk button (konflik UART3) — gunakan GPIO 11
- State sharing WAJIB pakai state_lock (threading.Lock)
- Jangan tambah thread baru tanpa review arsitektur 7-thread

## Code Style
- Python: snake_case, semua module prefix `raspi_`
- Arduino/C++: camelCase untuk fungsi, UPPER_CASE untuk konstanta
- Setiap perubahan hardware WAJIB ditest di mode simulasi dulu

## Files to Modify Carefully
- `raspi_config.py` — konfigurasi global, perubahan berdampak luas
- `raspi_uart_master.py` — protocol binary, hati-hati CRC8
- `raspi_gpio_buttons.py` — event queue pattern, jangan ubah ke polling

## Testing Without Hardware
cd pltn_video_display && python video_display_app.py --test --windowed

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
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
<!-- END BEADS INTEGRATION -->
