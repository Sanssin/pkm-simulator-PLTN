# Raspberry Pi GPIO Pin Mapping - PLTN Simulator

> **✅ STATUS:** This document shows the CURRENT PRODUCTION pin mapping (v4.0)
> 
> The "BEFORE Changes" section is kept for historical reference only.

## Pin Usage History (BEFORE v4.0 Migration)

### Reserved Pins (DO NOT USE)
```
GPIO 0, 1    - ID EEPROM (Reserved)
GPIO 2, 3    - AVAILABLE (Previously I2C/OLEDs)
GPIO 14, 15  - UART0 (TXD, RXD) - ESP-BC Communication
```

### Button Pins (17 buttons)
```
GPIO 5  - PUMP_PRIMARY_ON          ⚠️ CONFLICT! (Need for UART3 RXD)
GPIO 6  - PUMP_PRIMARY_OFF
GPIO 13 - PUMP_SECONDARY_ON
GPIO 19 - PUMP_SECONDARY_OFF
GPIO 26 - PUMP_TERTIARY_ON
GPIO 21 - PUMP_TERTIARY_OFF

GPIO 20 - SAFETY_ROD_UP
GPIO 16 - SAFETY_ROD_DOWN
GPIO 12 - SHIM_ROD_UP
GPIO 7  - SHIM_ROD_DOWN
GPIO 8  - REGULATING_ROD_UP
GPIO 25 - REGULATING_ROD_DOWN

GPIO 24 - PRESSURE_UP
GPIO 23 - PRESSURE_DOWN

GPIO 17 - REACTOR_START (GREEN)
GPIO 27 - REACTOR_RESET (YELLOW)
GPIO 18 - EMERGENCY (RED)
```

### Output Pins
```
GPIO 22 - BUZZER (Software PWM)
```

### UART Pins (Planned)
```
GPIO 14, 15 - UART0 (Built-in) → ESP-BC      [ALREADY USED]
GPIO 4, 5   - UART3 → ESP-E (Visualizer)     [NEED TO FREE GPIO 5]
```

---

## ✅ CURRENT PIN MAPPING (v4.0 Production)

### Reserved Pins (DO NOT USE)
```
GPIO 0, 1    - ID EEPROM (Reserved)
GPIO 2, 3    - AVAILABLE (Previously I2C/OLEDs)
GPIO 4, 5    - UART3 (TXD, RXD) - ESP-E Communication  ✅ NEW
GPIO 14, 15  - UART0 (TXD, RXD) - ESP-BC Communication
```

### Button Pins - DEPRECATED (Moved to Touchscreen HMI)
```
# All 17 pins previously used for buttons are now FREE for Actuators
# GPIO 11, 6, 13, 19, 26, 21 (Pumps) -> FREE
# GPIO 20, 16, 12, 7, 8, 25 (Rods) -> FREE
# GPIO 24, 23 (Pressure) -> FREE
# GPIO 17, 27, 18 (System) -> FREE
```

### Output Pins
```
GPIO 22 - BUZZER (Software PWM)
```

### Available for Future Use
```
GPIO 9, 10, 11 - SPI0 (if SPI not needed, can use as GPIO)
```

---

## Pin Summary Table

| GPIO | Function (BEFORE) | Function (AFTER) | Notes |
|------|-------------------|------------------|-------|
| 0 | Reserved (EEPROM) | Reserved (EEPROM) | Don't use |
| 1 | Reserved (EEPROM) | Reserved (EEPROM) | Don't use |
| 2 | Available | Available | Don't use |
| 3 | Available | Available | Don't use |
| **4** | **Available** | **UART3 TXD (ESP-E)** | ✅ NEW |
| **5** | **PUMP_PRIMARY_ON** | **UART3 RXD (ESP-E)** | ✅ MOVED |
| 6 | PUMP_PRIMARY_OFF | PUMP_PRIMARY_OFF | Same |
| 7 | SHIM_ROD_DOWN | SHIM_ROD_DOWN | Same |
| 8 | REGULATING_ROD_UP | REGULATING_ROD_UP | Same |
| 9 | Available | Available | - |
| 10 | Available | Available | - |
| **11** | **Available** | **PUMP_PRIMARY_ON** | ✅ NEW |
| 12 | SHIM_ROD_UP | SHIM_ROD_UP | Same |
| 13 | PUMP_SECONDARY_ON | PUMP_SECONDARY_ON | Same |
| 14 | UART0 TXD (ESP-BC) | UART0 TXD (ESP-BC) | Don't use |
| 15 | UART0 RXD (ESP-BC) | UART0 RXD (ESP-BC) | Don't use |
| 16 | SAFETY_ROD_DOWN | SAFETY_ROD_DOWN | Same |
| 17 | REACTOR_START | REACTOR_START | Same |
| 18 | EMERGENCY | EMERGENCY | Same |
| 19 | PUMP_SECONDARY_OFF | PUMP_SECONDARY_OFF | Same |
| 20 | SAFETY_ROD_UP | SAFETY_ROD_UP | Same |
| 21 | PUMP_TERTIARY_OFF | PUMP_TERTIARY_OFF | Same |
| 22 | BUZZER | BUZZER | Same |
| 23 | PRESSURE_DOWN | PRESSURE_DOWN | Same |
| 24 | PRESSURE_UP | PRESSURE_UP | Same |
| 25 | REGULATING_ROD_DOWN | REGULATING_ROD_DOWN | Same |
| 26 | PUMP_TERTIARY_ON | PUMP_TERTIARY_ON | Same |
| 27 | REACTOR_RESET | REACTOR_RESET | Same |

---

## UART Port Configuration

### Raspberry Pi UART Ports

```
UART0 (/dev/ttyAMA0)  - GPIO 14/15  → ESP-BC (Control Rods + Turbine + Humid)
UART3 (/dev/ttyAMA1)  - GPIO 4/5    → ESP-E (LED Visualizer)  ✅ NEW
```

### Enable UART3 on Raspberry Pi

Edit `/boot/config.txt`:
```bash
# Enable UART3 on GPIO 4/5
dtoverlay=uart3
```

Or use device tree overlay:
```bash
sudo dtoverlay uart3
```

Check available UARTs:
```bash
ls -l /dev/ttyAMA*
```

Expected output:
```
/dev/ttyAMA0 -> GPIO 14/15  (ESP-BC)
/dev/ttyAMA1 -> GPIO 4/5    (ESP-E)   ✅ NEW
```

---

## Wiring Changes

### Button Wiring
```
BEFORE:
  [PUMP PRIMARY ON Button] → GPIO 5 → GND

AFTER:
  [PUMP PRIMARY ON Button] → GPIO 11 → GND  ✅ MOVED
```

### UART3 Wiring (NEW)
```
Raspberry Pi         ESP-E (Visualizer)
GPIO 4 (TXD3)   →   GPIO 16 (RX2)
GPIO 5 (RXD3)   ←   GPIO 17 (TX2)
GND             →   GND
```

---

## Changes Required

### 1. raspi_config.py
```python
# Button Pins - OLD
BTN_PUMP_PRIM_ON = 5  # ❌ CONFLICT with UART3

# Button Pins - NEW
BTN_PUMP_PRIM_ON = 11  # ✅ MOVED

# UART Configuration - NEW
UART_ESP_BC_PORT = '/dev/ttyAMA0'    # GPIO 14/15
UART_ESP_E_PORT = '/dev/ttyAMA1'     # GPIO 4/5  ✅ NEW (was /dev/ttyUSB0)
```

### 2. raspi_gpio_buttons.py
```python
class ButtonPin(IntEnum):
    # Pump Control
    PUMP_PRIMARY_ON = 11   # ✅ CHANGED from 5
    PUMP_PRIMARY_OFF = 6
    # ... rest unchanged
```

### 3. raspi_uart_master.py
```python
# UART port update
def __init__(self, 
             esp_bc_port: str = '/dev/ttyAMA0',  # GPIO 14/15
             esp_e_port: str = '/dev/ttyAMA1',   # GPIO 4/5  ✅ CHANGED
             baudrate: int = 115200):
```

---

## Testing After Changes

### 1. Test Button (GPIO 11)
```python
python3 -c "
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(11, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print('Press PUMP PRIMARY ON button (GPIO 11)...')
while True:
    if GPIO.input(11) == GPIO.LOW:
        print('✅ Button pressed!')
        time.sleep(0.5)
    time.sleep(0.1)
"
```

### 2. Test UART3 (GPIO 4/5)
```bash
# Check UART3 device
ls -l /dev/ttyAMA1

# Test with minicom
sudo minicom -D /dev/ttyAMA1 -b 115200
```

---

## Summary of Changes

| Item | BEFORE | AFTER | Status |
|------|--------|-------|--------|
| PUMP_PRIMARY_ON Button | GPIO 5 | GPIO 11 | ✅ Moved |
| ESP-E UART Port | /dev/ttyUSB0 (USB) | /dev/ttyAMA1 (GPIO 4/5) | ✅ Hardware UART |
| UART3 Enable | Not enabled | Enabled via dtoverlay | ✅ Required |

---

## Files to Modify

1. `raspi_config.py` - Update button pin and UART port
2. `raspi_gpio_buttons.py` - Update ButtonPin enum
3. `raspi_uart_master.py` - Update default ESP-E port
4. `/boot/config.txt` - Enable UART3

---

**Migration Date**: 2025-12-17  
**Current Version**: v4.0  
**Status**: ✅ IMPLEMENTED & IN PRODUCTION
