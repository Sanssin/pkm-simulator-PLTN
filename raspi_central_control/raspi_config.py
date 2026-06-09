"""
Raspberry Pi Central Control - Configuration
PLTN Simulator v4.0 with UART Binary Protocol Architecture
"""

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
