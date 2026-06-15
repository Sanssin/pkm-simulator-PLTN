"""
Relay Controller for PLTN Simulator.
Controls the 4 relay channels for the Cooling Tower Humidifiers.
Active-LOW relay modules.
"""
import logging
import raspi_config as config

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

class RelayController:
    def __init__(self, humidifier_pins=None):
        self.hardware_active = GPIO_AVAILABLE
        
        if humidifier_pins is None:
            self.pins = getattr(config, 'HUMIDIFIER_PINS', {
                'ct1': 2,
                'ct2': 3,
                'ct3': 9,
                'ct4': 22
            })
        else:
            self.pins = humidifier_pins
            
        if self.hardware_active:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                
                for pin in self.pins.values():
                    GPIO.setup(pin, GPIO.OUT)
                    # Relay modules are Active-LOW in this setup. Default to HIGH (OFF).
                    GPIO.output(pin, GPIO.HIGH)
                    
                logger.info(f"RelayController: Initialized on pins {list(self.pins.values())}")
            except Exception as e:
                logger.warning(f"RelayController: Failed to initialize GPIO: {e}")
                self.hardware_active = False
        else:
            logger.warning("RelayController: RPi.GPIO not available. Running in mock mode.")
            
    def set_relays(self, ct1_cmd, ct2_cmd, ct3_cmd, ct4_cmd):
        """
        Update the states of the 4 CT relays.
        Expects 1 for ON, 0 for OFF.
        Since relays are Active-LOW, 1 outputs LOW, 0 outputs HIGH.
        """
        if not self.hardware_active:
            return
            
        try:
            GPIO.output(self.pins['ct1'], GPIO.LOW if ct1_cmd else GPIO.HIGH)
            GPIO.output(self.pins['ct2'], GPIO.LOW if ct2_cmd else GPIO.HIGH)
            GPIO.output(self.pins['ct3'], GPIO.LOW if ct3_cmd else GPIO.HIGH)
            GPIO.output(self.pins['ct4'], GPIO.LOW if ct4_cmd else GPIO.HIGH)
        except Exception as e:
            logger.error(f"RelayController: Failed to update relays: {e}")
            
    def cleanup(self):
        """Turn off all relays and cleanup"""
        if self.hardware_active:
            try:
                for pin in self.pins.values():
                    GPIO.output(pin, GPIO.HIGH) # Turn OFF
                logger.info("RelayController: Cleaned up relay pins.")
            except Exception as e:
                pass
