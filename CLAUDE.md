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