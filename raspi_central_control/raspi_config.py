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
LED_POWER_PIN = 13       # GPIO 13 for Power Output LED indicator (PWM)
LED_CHERENKOV_PIN = 16   # GPIO 16 for Cherenkov Blue LED effect via 74HC245N (PWM)
LED_TURBINE_PIN = 12     # GPIO 12 for Turbine decorative LED effect via 74HC245N (PWM)
LED_RELIEF_GREEN_PIN = 5  # GPIO 5 for Relief Valve Safe (Green)
LED_RELIEF_RED_PIN = 6    # GPIO 6 for Relief Valve Open (Red)

# ============================================
# Actuator Configuration
# ============================================
# Servos
SERVO_PIN_SAFETY = 23
SERVO_PIN_SHIM = 24
SERVO_PIN_REG = 25

# Motors (VNH2SP30)
MOTOR_PINS = {
    'pump_primary': 17,
    'pump_secondary': 20,
    'pump_tertiary': 27,
    'turbine': 26
}

# Humidifier Relays
HUMIDIFIER_PINS = {
    'ct1': 2,
    'ct2': 3,
    'ct3': 9,
    'ct4': 22
}

# ============================================
# LED Strip Configuration (WS2812)
# ============================================
LED_STRIP_PIN = 18       # Pin for WS2812 (PWM0) - Daisy Chained
LED_STRIP_COUNT = 315    # Total number of LEDs yang FISIKNYA SUDAH TERPASANG (197 + 118 primer)

# Segments: (start_index, length) - Disusun BERURUTAN sesuai fisik kabel
LED_SEGMENT_TERSIER_IN  = (0, 84)     # Baru: Pipa tersier masuk (Biru)
LED_SEGMENT_KONDENSER   = (84, 46)    # Kondenser
LED_SEGMENT_TERSIER_OUT = (130, 21)   # Keluaran kondenser ke cooling tower (Merah/Hot)
LED_SEGMENT_SEKUNDER_IN = (151, 46)   # Baru: Gabungan aliran sekunder dari kondenser (19 + 27)
LED_SEGMENT_PRIMER      = (197, 118)  # Pipa Primer (disambung dari keluaran sekunder)

# Segmen yang BELUM dipasang fisik (dibuat dummy di index 1000 ke atas)
LED_SEGMENT_SEKUNDER    = (1200, 190) # Pipa Sekunder Utama (Belum ada fisik)
LED_SEGMENT_TERSIER     = (1400, 191) # Pipa Tersier Keluar Utama (Belum ada fisik)
LED_SEGMENT_PRESSURIZER = (1600, 21)  # Dummy index (dicopot sementara / belum dipakai)

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
BLINK_INTERVAL = 0.25

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
