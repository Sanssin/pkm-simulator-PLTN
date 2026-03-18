# Raspberry Pi Central Control - Installation & Usage Guide

## 🎯 Overview

**PLTN Simulator v4.0** - Raspberry Pi 4 sebagai master controller dengan arsitektur **UART Binary Protocol**.

**Raspberry Pi mengontrol:**
- 17x Push buttons (GPIO input dengan edge + level detection)
- 9x OLED Display SSD1306 128x32 (via I2C multiplexer TCA9548A)
- 2x ESP32 via UART (ESP-BC dan ESP-E)
- 1x Buzzer alarm (PWM)
- 4x Cooling Tower humidifiers (staged control via ESP-BC)

**⚠️ IMPORTANT:** Untuk dokumentasi lengkap, baca:
- **[../README.md](../README.md)** — Main project documentation
- **[../AGENT.md](../AGENT.md)** — Complete technical architecture (40KB)
- **[../GPIO_PIN_MAPPING.md](../GPIO_PIN_MAPPING.md)** — Detailed pin mapping & wiring

## 📁 File Structure

```
raspi_central_control/
├── raspi_main_panel.py          # ⭐ Main entry point (run this)
├── raspi_config.py              # Configuration & constants
├── raspi_gpio_buttons.py        # Button input handler (hybrid edge+level)
├── raspi_uart_master.py         # UART binary protocol (ESP-BC & ESP-E)
├── raspi_oled_manager.py        # 9× OLED display manager
├── raspi_tca9548a.py            # I2C multiplexer driver (OLEDs only)
├── raspi_buzzer_alarm.py        # PWM alarm tones (5 alarm types)
├── raspi_humidifier_control.py  # Staged CT1-4 activation logic
├── raspi_system_health.py       # 8-point health check at startup
├── raspi_i2c_master.py          # ⚠️ DEPRECATED (legacy, safe to delete)
└── raspi_README.md              # This file
```

## 🔧 Hardware Requirements

### 1. Raspberry Pi 4
- **Model:** Raspberry Pi 4 (2GB+ RAM recommended)
- **OS:** Raspberry Pi OS Bookworm/Bullseye
- **SD Card:** 16GB+ (Class 10)
- **Power:** 5V 3A USB-C power supply

### 2. Communication Architecture (v4.0 UART)
- **UART0** (`/dev/ttyAMA0`, GPIO 14/15) → ESP-BC (Control + Actuators)
- **UART3** (`/dev/ttyAMA1`, GPIO 4/5) → ESP-E (LED Visualizer)
- **I2C Bus 1** (GPIO 2/3) → TCA9548A → 9× OLED displays

### 3. Peripherals
- **9× OLED** 128×32 SSD1306 (I2C address 0x3C)
- **17× Push buttons** (see GPIO_PIN_MAPPING.md for pin assignments)
- **1× Passive buzzer** (GPIO 22)
- **1× TCA9548A** I2C multiplexer (address 0x70, for OLEDs only)

### 4. ESP32 Modules (UART Slaves)
- **ESP-BC** (UART0): Control rods (3× servo) + turbine (DC motor) + pumps (3× L298N) + humidifiers (4× relay)
- **ESP-E** (UART3): LED visualization (24 LEDs via 3× 74HC595 shift registers)

## 📌 Pin Connections Summary

**For complete wiring details, see [../GPIO_PIN_MAPPING.md](../GPIO_PIN_MAPPING.md)**

### Quick Reference

| Function | Pins | Notes |
|----------|------|-------|
| **UART0** | GPIO 14 (TX), 15 (RX) | ESP-BC |
| **UART3** | GPIO 4 (TX), 5 (RX) | ESP-E |
| **I2C Bus 1** | GPIO 2 (SDA), 3 (SCL) | TCA9548A → OLEDs |
| **17 Buttons** | GPIO 16, 20, 21, 12, 7, 8, 25, 24, 23, 11, 6, 13, 19, 26, 9, 10, 27 | See GPIO_PIN_MAPPING.md |
| **Buzzer** | GPIO 22 | Software PWM |

## 🚀 Installation

### Step 1: Update Raspberry Pi OS
```bash
sudo apt update
sudo apt upgrade -y
```

### Step 2: Enable UART3 & I2C

**Enable UART3:**
```bash
sudo nano /boot/config.txt
# Add this line:
dtoverlay=uart3

# Save and exit
```

**Enable I2C:**
```bash
sudo raspi-config
# Navigate to: 3 Interface Options → I5 I2C → Enable
```

**Reboot:**
```bash
sudo reboot
```

**Verify UART ports:**
```bash
ls -l /dev/ttyAMA*
# Expected:
# /dev/ttyAMA0 → GPIO 14/15 (ESP-BC)
# /dev/ttyAMA1 → GPIO 4/5   (ESP-E)
```

### Step 3: Install Python Dependencies
```bash
cd raspi_central_control/
pip3 install -r raspi_requirements.txt
```

**Required packages:**
- `pyserial` — UART communication
- `Adafruit-SSD1306` — OLED driver
- `RPi.GPIO` — GPIO control
- `smbus2` — I2C (for TCA9548A/OLEDs)
- `Pillow` — Image rendering for OLEDs

### Step 4: Test Hardware

**Test UART ports:**
```bash
# Check UART devices are accessible
ls -l /dev/ttyAMA*
```

**Test I2C (OLED multiplexer):**
```bash
sudo i2cdetect -y 1
# Should show: 0x70 (TCA9548A)
```

**Test GPIO:**
```bash
# Run system health check
python3 raspi_main_panel.py --health-check
```

### Step 5: Run the System
```bash
python3 raspi_main_panel.py
```

**Command-line options:**
```bash
python3 raspi_main_panel.py --help
python3 raspi_main_panel.py --health-check    # 8-point startup diagnostic
python3 raspi_main_panel.py --debug           # Enable verbose logging
```

## 🏗️ System Architecture

**For full architecture details, see [../AGENT.md](../AGENT.md) Section 2**

### Threading Model (9 threads)

| Thread | Frequency | Purpose |
|--------|-----------|---------|
| ButtonPolling | 5ms | Fast edge detection |
| ButtonHold | 50ms | Long-press detection |
| EventProcessor | 10ms | Process button events |
| ControlLogic | 50ms | Safety interlock & logic |
| ESP_UART_Comm | 50ms | Binary UART to ESP-BC & ESP-E |
| OLED_Update | 200ms | Display refresh (5 Hz) |
| StateExport | 100ms | Export to `/tmp/pltn_state.json` |
| HealthMonitor | Startup | 8-point health check |
| AutoSimulation | On-demand | Automated demo sequence |

### Communication Protocol

**UART Binary Protocol** (115200 baud, 8N1):
```
Frame: [STX 0x02][CMD][LEN][PAYLOAD...][CRC8][ETX 0x03]

ESP-BC (15 bytes): Rod positions (3) + Pump speeds (3) + Humidifier states (4)
ESP-E (8 bytes): LED flow animation states (3) + Power indicator brightness (4)

ACK/NACK responses with CRC8 error detection
Retry mechanism: 3× with exponential backoff
```

**For protocol details, see [../AGENT.md](../AGENT.md) Section 2.3**

## 🛠️ Troubleshooting

### Issue: UART devices not found
```bash
# Check UART3 is enabled
grep "dtoverlay=uart3" /boot/config.txt

# If missing, add it and reboot
echo "dtoverlay=uart3" | sudo tee -a /boot/config.txt
sudo reboot
```

### Issue: I2C devices not detected
```bash
# Check I2C is enabled
sudo raspi-config
# → 3 Interface Options → I5 I2C → Enable

# Scan I2C bus
sudo i2cdetect -y 1
# Should show 0x70 (TCA9548A)
```

### Issue: Permission denied on GPIO/UART
```bash
# Add user to gpio and dialout groups
sudo usermod -a -G gpio,dialout $USER
# Logout and login again
```

### Issue: OLED displays not working
```bash
# Test TCA9548A multiplexer
python3 -c "from raspi_tca9548a import TCA9548A; mux = TCA9548A(0x70); mux.select_channel(0); print('OK')"

# Check OLED on channel 0
sudo i2cdetect -y 1
# Should show 0x3C after selecting channel
```

## 📚 Related Documentation

| Document | Content |
|----------|---------|
| **[../README.md](../README.md)** | Project overview & features |
| **[../AGENT.md](../AGENT.md)** | Complete technical documentation (40KB) |
| **[../GPIO_PIN_MAPPING.md](../GPIO_PIN_MAPPING.md)** | Detailed wiring & pin assignments |
| **[../pltn_video_display/](../pltn_video_display/)** | Separate video display system (HDMI) |
| **[../esp_utama_uart/](../esp_utama_uart/)** | ESP-BC firmware (Arduino) |
| **[../esp_visualizer_uart/](../esp_visualizer_uart/)** | ESP-E firmware (Arduino) |

## 🎬 Video Display System

The main control panel is complemented by an **educational video display system** on a separate HDMI monitor.

**See:** `../pltn_video_display/README.md`

**Features:**
- Real-time speedometer gauge for thermal power output
- Educational video playback (IDLE mode)
- Interactive manual guide (MANUAL_GUIDE mode)
- Reads state from `/tmp/pltn_state.json` (10 Hz)

## 🧪 Testing

**Run system health check:**
```bash
python3 raspi_main_panel.py --health-check
```

**8-point health check:**
1. ✅ I2C bus availability
2. ✅ TCA9548A multiplexer detection
3. ✅ UART ports availability (ttyAMA0, ttyAMA1)
4. ✅ GPIO pins configuration
5. ✅ OLED displays detection (9×)
6. ✅ Button input test
7. ✅ Buzzer output test
8. ✅ ESP UART communication test (ping)

## 🔐 Safety Features

**For complete safety documentation, see [../AGENT.md](../AGENT.md) Section 6**

- **SCRAM (Emergency Shutdown):** Red button → all rods to 0%, pumps shutdown
- **Interlock Logic:** Prevents unsafe operations (e.g., rod movement without coolant)
- **Alarm System:** 5 alarm types (SCRAM, high temp, low pressure, low coolant, general)
- **Health Monitor:** 8-point startup diagnostic
- **Watchdog:** Thread health monitoring

## 📝 Development Notes

**For AI agent guidance, see [../AGENT.md](../AGENT.md) Section 10**

**Key skills for development:**
- `.claude/skills/firmware-embedded.md` — GPIO, threading, ESP32
- `.claude/skills/nuclear-sim-physics.md` — Reactor physics, formulas
- `.claude/skills/safety-logic.md` — SCRAM, alarms, interlocks
- `.claude/skills/hmi-display.md` — UI updates, display management

## 📄 License

This is an educational project for PKM (Program Kreativitas Mahasiswa) 2024.

---

**For questions or issues:** See [../AGENT.md](../AGENT.md) Section 11 "Known Issues"
# Reboot when prompted
```

### Step 3: Install Python Dependencies
```bash
cd ~/
git clone <your-repo-url> pltn_simulator
cd pltn_simulator/RasPi_Central_Control

# Install system packages
sudo apt install -y python3-pip python3-dev python3-pil i2c-tools

# Install Python packages
pip3 install -r raspi_requirements.txt
```

### Step 4: Test I2C Bus
```bash
# Test I2C bus 0 (Display multiplexer)
sudo i2cdetect -y 0

# Test I2C bus 1 (ESP multiplexer)
sudo i2cdetect -y 1

# You should see:
#   0x70 (TCA9548A #1 on bus 0)
#   0x71 (TCA9548A #2 on bus 1)
```

### Step 5: Test Individual Components
```bash
# Test TCA9548A
python3 raspi_tca9548a.py

# Test I2C Master (requires ESP to be connected)
python3 raspi_i2c_master.py

# Test OLED Manager
python3 raspi_oled_manager.py
```

## ▶️ Running the System

### Manual Start
```bash
cd ~/pltn_simulator/RasPi_Central_Control
python3 raspi_main.py
```

### Auto-Start on Boot (Optional)
```bash
# Create systemd service
sudo nano /etc/systemd/system/pltn-control.service
```

Add this content:
```ini
[Unit]
Description=PLTN Simulator Central Control
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pltn_simulator/RasPi_Central_Control
ExecStart=/usr/bin/python3 raspi_main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pltn-control.service
sudo systemctl start pltn-control.service

# Check status
sudo systemctl status pltn-control.service

# View logs
sudo journalctl -u pltn-control.service -f
```

## 🎮 Operating Instructions

### 1. System Startup
1. Power on Raspberry Pi
2. Wait for system to boot (~30 seconds)
3. OLED displays show startup screen
4. System ready when "NORMAL" appears on pressurizer display

### 2. Pressure Control
- Press BTN_PRES_UP to increase pressure (+5 bar)
- Press BTN_PRES_DOWN to decrease pressure (-5 bar)
- Target: 150 bar for normal operation

### 3. Pump Operation
**Primary Pump:**
- Requires pressure ≥ 40 bar
- Press BTN_PUMP_PRIM_ON to start
- Press BTN_PUMP_PRIM_OFF to stop

**Secondary & Tertiary Pumps:**
- Can start at any pressure
- Press respective ON/OFF buttons

### 4. Operating Sequence
1. Increase pressure to 150 bar
2. Start Primary pump → wait for "ON" status
3. Start Secondary pump → wait for "ON" status
4. Start Tertiary pump → wait for "ON" status
5. ESP-B interlock will release
6. Control rods can now be operated
7. ESP-C will start turbin sequence

### 5. Emergency Shutdown
- Press ESP-B emergency button
- All control rods drop to 0%
- Turbin will shutdown
- Stop all pumps manually

### 6. Normal Shutdown
1. Lower all control rods to 0% (at ESP-B)
2. Wait for ESP-C turbin shutdown
3. Stop Primary pump
4. Stop Secondary pump
5. Stop Tertiary pump
6. Lower pressure to 0 bar

## 📊 Data Logging

### CSV Data Log
- File: `pltn_data.csv` (in same directory)
- Interval: 1 second
- Columns: timestamp, pressure, pump status, PWM, rod positions, power level

### Application Log
- File: `pltn_control.log`
- Level: INFO (configurable in config.py)
- Contains system events, errors, communication status

## 🔍 Troubleshooting

### I2C Device Not Detected
```bash
# Check bus 0
sudo i2cdetect -y 0

# Check bus 1
sudo i2cdetect -y 1

# If nothing appears:
# - Check wiring (SDA/SCL)
# - Check pull-up resistors (4.7kΩ)
# - Verify I2C is enabled in raspi-config
```

### ESP Not Responding
```bash
# Check logs
tail -f pltn_control.log

# Look for:
# "ESP 0x08 not responding"
# "I2C timeout"

# Solutions:
# - Verify ESP is powered on
# - Check ESP I2C slave code is running
# - Verify correct I2C address in ESP code
# - Check cable connections
```

### Display Not Working
```bash
# Test OLED directly
sudo i2cdetect -y 0

# Should see 0x3C on one of channels 0-3
# If not:
# - Check TCA9548A channel selection
# - Verify OLED address (0x3C or 0x3D)
# - Test OLED on breadboard separately
```

### GPIO Permission Error
```bash
# Add user to gpio group
sudo usermod -a -G gpio pi

# Or run with sudo (not recommended for production)
sudo python3 raspi_main.py
```

## ⚙️ Configuration

Edit `raspi_config.py` to customize:

### I2C Addresses
```python
TCA9548A_DISPLAY_ADDRESS = 0x70
TCA9548A_ESP_ADDRESS = 0x71
ESP_B_ADDRESS = 0x08
ESP_C_ADDRESS = 0x09
# ... etc
```

### Timing
```python
I2C_UPDATE_INTERVAL_FAST = 0.05   # ESP-B polling (50ms)
I2C_UPDATE_INTERVAL_NORMAL = 0.1  # ESP-C polling (100ms)
OLED_UPDATE_INTERVAL = 0.2        # Display update (200ms)
```

### System Parameters
```python
PRESS_NORMAL_OPERATION = 150.0
PRESS_WARNING_ABOVE = 160.0
PRESS_CRITICAL_HIGH = 180.0
PWM_STARTUP_STEP = 10
```

## 🧪 Testing Mode

Run without GPIO hardware:
```python
# In raspi_main.py, GPIO_AVAILABLE will be False
# System runs in simulation mode
# No actual GPIO control, but I2C communication works
```

## 📈 Performance

- I2C Bus Speed: 100 kHz (standard mode)
- Main Loop: ~100 Hz (10ms cycle)
- I2C ESP-B: 20 Hz (50ms)
- I2C ESP-C: 10 Hz (100ms)
- I2C Visualizers: 5 Hz (200ms)
- Display Update: 5 Hz (200ms)

## 🆘 Support

Check logs:
```bash
tail -f pltn_control.log
```

Monitor I2C traffic:
```bash
sudo i2cdump -y 1 0x08  # Dump ESP-B data
```

Test components individually using test functions in each module.

## 📝 Version History

- v2.0 (2024-11) - Full I2C architecture with dual TCA9548A
- v1.0 (2024-10) - Original UART-based system (ESP-A)

---

**Ready to Run!** 🚀

For questions or issues, check `pltn_control.log` or refer to `MIGRATION_PLAN.md` for detailed architecture documentation.
