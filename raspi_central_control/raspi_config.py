"""
Raspberry Pi Central Control - Configuration
PLTN Simulator v4.0 with UART Binary Protocol Architecture
"""

# ============================================
# UART Configuration (NEW - Replaces I2C for ESP)
# ============================================
# UART Ports for ESP Communication
UART_ESP_BC_PORT = '/dev/ttyAMA0'    # GPIO 14/15 (Built-in UART0)
UART_ESP_E_PORT = '/dev/ttyAMA1'     # GPIO 4/5 (UART3) - Fixed: was ttyAMA3
UART_BAUDRATE = 115200               # Standard baudrate
UART_TIMEOUT = 0.5                   # Read timeout in seconds
UART_UPDATE_INTERVAL = 0.1           # Update interval (100ms)

# ============================================
# I2C Configuration (OLEDs ONLY now)
# ============================================
# TCA9548A Multiplexer Addresses (OLEDs ONLY)
TCA9548A_DISPLAY_ADDRESS = 0x70  # For OLED displays only
TCA9548A_ESP_ADDRESS = 0x71      # For OLED displays only (ESP now on UART)

# I2C Bus Configuration
# NOTE: Raspberry Pi typically only has I2C bus 1 available
# Both multiplexers will share the same I2C bus
# ESPs are now on UART, not I2C!
I2C_BUS = 1          # I2C Bus 1 (GPIO 2=SDA, GPIO 3=SCL)
I2C_BUS_DISPLAY = 1  # Same bus for displays

# OLED Configuration
OLED_ADDRESS = 0x3C
OLED_CHANNEL_PRESSURIZER = 0
OLED_CHANNEL_PUMP_PRIMARY = 1
OLED_CHANNEL_PUMP_SECONDARY = 2
OLED_CHANNEL_PUMP_TERTIARY = 3
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 32

# ESP32 Slave Addresses (2-ESP Architecture MERGED)
ESP_BC_ADDRESS = 0x08  # ESP-BC: Control Rods + Turbine + Humidifier + Pumps (MERGED B+C)
ESP_E_ADDRESS = 0x0A   # ESP-E: 3-Flow Visualizer (Primer, Sekunder, Tersier)

# TCA9548A Channel Mapping for ESP
# ESP-BC is on TCA9548A #1 (0x70), Channel 0
# ESP-E is on TCA9548A #2 (0x71), Channel 0
ESP_BC_CHANNEL = 0     # ESP-BC on multiplexer #1 (0x70)
ESP_E_CHANNEL = 0      # ESP-E on multiplexer #2 (0x71)

# ============================================
# GPIO Pin Configuration
# ============================================
# NOTE: Button pins are now defined in raspi_gpio_buttons.py ButtonPin enum
# Only hardware output pins are defined here (buzzer, etc.)

# Output Pins
BUZZER_PIN = 22          # GPIO 22 for passive buzzer alarm (software PWM)

# ❌ DEPRECATED - Motor control via ESP32, NOT Raspberry Pi!
# These pins are NOT used - motor control is done by ESP32 Utama via L298N
# MOTOR_PRIM_PWM = 12      # NOT USED
# MOTOR_SEC_PWM = 13       # NOT USED
# MOTOR_TER_PWM = 19       # NOT USED

# ============================================
# System Parameters
# ============================================
# Pressurizer Settings
PRESS_MIN = 0.0
PRESS_MAX = 200.0
PRESS_MIN_ACTIVATE_PUMP1 = 40.0
PRESS_NORMAL_OPERATION = 150.0
PRESS_WARNING_ABOVE = 160.0
PRESS_CRITICAL_HIGH = 180.0
PRESS_INCREMENT_FAST = 5.0
PRESS_INCREMENT_SLOW = 1.0

# Pump Status Enum
PUMP_OFF = 0
PUMP_STARTING = 1
PUMP_ON = 2
PUMP_SHUTTING_DOWN = 3

# PWM Settings
PWM_FREQUENCY = 1000     # 1kHz
PWM_MIN = 0
PWM_MAX = 100            # Percentage
PWM_STARTUP_STEP = 10
PWM_SHUTDOWN_STEP = 5

# ============================================
# Timing Configuration (seconds)
# ============================================
DEBOUNCE_DELAY = 0.1
PWM_UPDATE_INTERVAL = 0.1
I2C_UPDATE_INTERVAL_FAST = 0.05    # ESP-B (critical)
I2C_UPDATE_INTERVAL_NORMAL = 0.1   # ESP-C, ESP-E
OLED_UPDATE_INTERVAL = 0.2
BLINK_INTERVAL = 0.25

# I2C Timeout
I2C_TIMEOUT = 1.0
I2C_RETRY_COUNT = 3

# ============================================
# Logging Configuration
# ============================================
LOG_FILE = "pltn_control.log"
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATA_INTERVAL = 5.0  # Log data setiap 5 detik

# Data Logging
ENABLE_CSV_LOGGING = True
CSV_LOG_FILE = "pltn_data.csv"
CSV_LOG_INTERVAL = 1.0   # Log setiap 1 detik
