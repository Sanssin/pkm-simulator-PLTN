import logging
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    PIGPIO_AVAILABLE = False
    logger.warning("pigpio library not installed. Fallback to mock.")


class MotorController:
    """
    Control 4 DC motors via VNH2SP30 menggunakan pigpio PWM.
    Modul VNH2SP30 dikonfigurasi secara hardware untuk berputar satu arah (INA/INB tetap).
    Sehingga kita hanya perlu memberikan sinyal PWM.
    """
    
    # Frekuensi PWM untuk VNH2SP30 bisa diatur (5kHz is typical for these motors to avoid whining noise)
    PWM_FREQUENCY = 5000 
    
    try:
        import raspi_config as config
        MOTOR_PINS = getattr(config, 'MOTOR_PINS', {
            'pump_primary': 17,
            'pump_secondary': 20,
            'pump_tertiary': 27,
            'turbine': 26
        })
    except ImportError:
        MOTOR_PINS = {
            'pump_primary': 17,
            'pump_secondary': 20,
            'pump_tertiary': 27,
            'turbine': 26
        }
    
    def __init__(self, pi_instance=None):
        self.mock_mode = not PIGPIO_AVAILABLE
        
        if not self.mock_mode:
            self.pi = pi_instance if pi_instance else pigpio.pi()
            if not self.pi.connected:
                logger.error("MotorController: pigpio daemon not running. Falling back to mock mode.")
                self.mock_mode = True
        
        if not self.mock_mode:
            # Initialize PWM untuk semua motor
            for name, pin in self.MOTOR_PINS.items():
                try:
                    self.pi.set_mode(pin, pigpio.OUTPUT)
                    freq = 100 if name == 'turbine' else self.PWM_FREQUENCY
                    self.pi.set_PWM_frequency(pin, freq)
                    self.pi.set_PWM_range(pin, 100)  # 0-100% duty cycle
                    self.pi.set_PWM_dutycycle(pin, 0)
                    logger.info(f"Initialized motor '{name}' on GPIO {pin} at {freq}Hz")
                except Exception as e:
                    logger.error(f"Error initializing motor '{name}' on GPIO {pin}: {e}")
        else:
            logger.info("MotorController running in MOCK mode.")
            
        self.current_speeds = {
            'pump_primary': 0.0,
            'pump_secondary': 0.0,
            'pump_tertiary': 0.0,
            'turbine': 0.0
        }

    def set_speed(self, motor_name: str, speed_percent: float):
        """
        Set motor speed (0-100%).
        
        Args:
            motor_name: Name of the motor ('pump_primary', 'pump_secondary', 'pump_tertiary', 'turbine')
            speed_percent: Speed percentage from 0.0 to 100.0
        """
        if motor_name not in self.MOTOR_PINS:
            logger.error(f"Unknown motor: {motor_name}")
            return
            
        # Constrain speed between 0 and 100
        speed_percent = max(0.0, min(100.0, float(speed_percent)))
        
        # Software speed calibration: Cap and map turbine motor to prevent overspeed
        if motor_name == 'turbine':
            if speed_percent > 0.0:
                # Map 0-100% input to a narrow 8%-15% PWM output (Adjustable)
                speed_percent = 8.0 + (speed_percent / 100.0) * 7.0
            else:
                speed_percent = 0.0
        
        self.current_speeds[motor_name] = speed_percent
        
        if not self.mock_mode:
            try:
                pin = self.MOTOR_PINS[motor_name]
                # pigpio range is 0-100 as set during initialization
                self.pi.set_PWM_dutycycle(pin, int(speed_percent))
            except Exception as e:
                logger.error(f"Error setting speed for {motor_name}: {e}")
        else:
            logger.debug(f"[MOCK] Motor '{motor_name}' set to {speed_percent}%")

    def stop_all(self):
        """Stop all motors gracefully."""
        for motor_name in self.MOTOR_PINS.keys():
            self.set_speed(motor_name, 0)
            
    def cleanup(self):
        """Cleanup GPIO pins on exit."""
        self.stop_all()
        if not self.mock_mode:
            try:
                if self.pi and self.pi.connected:
                    self.pi.stop()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
