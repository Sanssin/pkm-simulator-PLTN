# Skills Index — pkm-simulator-PLTN

Gunakan skill files ini sebagai konteks tambahan saat bekerja di area tertentu.

**🤖 Untuk AI Agents**: Lihat **`AGENT.md` Section 10** untuk panduan lengkap tentang kapan dan bagaimana menggunakan skills ini (termasuk automatic triggers berdasarkan file pattern dan keyword).

## Daftar Skills

| Skill | File | Gunakan untuk |
|-------|------|---------------|
| Firmware & Embedded | `skills/firmware-embedded/SKILL.md` | GPIO, sensor, main loop, threading |
| Nuclear Physics Sim | `skills/nuclear-sim-physics/SKILL.md` | Parameter reaktor, rumus, model fisika |
| Safety Logic | `skills/safety-logic/SKILL.md` | SCRAM, alarm, interlock, threshold |
| HMI & Display | `skills/hmi-display/SKILL.md` | UI, display update, alarm visual/audio |
| PLTN Domain | `skills/pltn-domain-knowledge/SKILL.md` | Terminologi, konsep nuklir, skenario |

## Quick Reference

| Saya ingin... | Baca skill ini |
|---------------|----------------|
| Debug masalah sensor | firmware-embedded |
| Ubah parameter simulasi | nuclear-sim-physics |
| Tambah alarm baru | safety-logic + hmi-display |
| Tambah tampilan baru | hmi-display |
| Tidak paham istilah nuklir | pltn-domain-knowledge |
| Tambah fitur baru | AGENT.md → lalu skill yang relevan |
| Implementasi LOFA simulation | safety-logic + pltn-domain-knowledge |
| Kerja di temperature model | nuclear-sim-physics + safety-logic |
| Kerja di pressurizer logic | safety-logic + pltn-domain-knowledge |
| Kerja di touchscreen panel | hmi-display + AGENT.md Section 7 |

## Planned Development Reference

| Pengembangan | Dokumentasi | Skill Files |
|--------------|-------------|-------------|
| Touchscreen Panel | `docs/development/01-touchscreen-panel.md` | hmi-display |
| LOFA Simulation | `docs/development/03-lofa-simulation.md` | safety-logic + pltn-domain-knowledge |
