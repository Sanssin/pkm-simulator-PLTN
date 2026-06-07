"""
Servo Controller using pigpio for hardware-timed PWM.
Maps rod percentages (0-100) to servo pulse widths.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    PIGPIO_AVAILABLE = False

class ServoController:
    # Typical standard servo pulse widths (microseconds)
    MIN_PW = 500   # 0 degrees
    MAX_PW = 2500  # 180 degrees
    
    def __init__(self, safety_pin=23, shim_pin=24, reg_pin=25):
        """
        Initialize servo controller.
        Default pins: 23, 24, 25 for Safety, Shim, and Regulating rods.
        """
        self.safety_pin = safety_pin
        self.shim_pin = shim_pin
        self.reg_pin = reg_pin
        
        self.hardware_active = False
        self.pi = None
        
        if PIGPIO_AVAILABLE:
            self.pi = pigpio.pi()
            if self.pi.connected:
                self.hardware_active = True
                logger.info(f"ServoController: pigpio connected. Pins: S={safety_pin}, Sh={shim_pin}, R={reg_pin}")
            else:
                logger.warning("ServoController: pigpio daemon (pigpiod) not running. Fallback to mock.")
                self.pi = None
        else:
            logger.warning("ServoController: pigpio library not installed. Fallback to mock.")
            
        self._last_safety = -1.0
        self._last_shim = -1.0
        self._last_reg = -1.0

    def _percent_to_pw(self, percent):
        """Convert 0-100% to pulse width in microseconds."""
        percent = max(0.0, min(100.0, float(percent)))
        # Map 0-100% to MIN_PW - MAX_PW
        pw = self.MIN_PW + (percent / 100.0) * (self.MAX_PW - self.MIN_PW)
        return int(pw)

    def set_rods(self, safety_pct, shim_pct, reg_pct):
        """Update all rod servos if their target has changed significantly."""
        if not self.hardware_active:
            return
            
        # Update Safety Rod (Threshold 0.5% to prevent micro-jitters)
        if abs(safety_pct - self._last_safety) >= 0.5:
            self.pi.set_servo_pulsewidth(self.safety_pin, self._percent_to_pw(safety_pct))
            self._last_safety = safety_pct
            
        # Update Shim Rod
        if abs(shim_pct - self._last_shim) >= 0.5:
            self.pi.set_servo_pulsewidth(self.shim_pin, self._percent_to_pw(shim_pct))
            self._last_shim = shim_pct
            
        # Update Regulating Rod
        if abs(reg_pct - self._last_reg) >= 0.5:
            self.pi.set_servo_pulsewidth(self.reg_pin, self._percent_to_pw(reg_pct))
            self._last_reg = reg_pct

    def cleanup(self):
        """Turn off PWM signals and close connection to pigpiod."""
        if self.hardware_active and self.pi is not None:
            # Turn off servos (0 means off, stopping PWM generation)
            self.pi.set_servo_pulsewidth(self.safety_pin, 0)
            self.pi.set_servo_pulsewidth(self.shim_pin, 0)
            self.pi.set_servo_pulsewidth(self.reg_pin, 0)
            self.pi.stop()
            logger.info("ServoController: Cleaned up pigpio connections.")
