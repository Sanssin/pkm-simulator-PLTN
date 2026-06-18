"""
Unified Actuator Manager for PLTN Simulator.
Handles direct control of all Raspberry Pi hardware actuators:
- Servos (for control rods)
- PWM Motors (for pumps)
- Relays (for other systems)

Implements graceful degradation: if hardware is not connected or libraries are missing,
it will print debug messages instead of crashing.
"""

import logging
import time
import sys
import os
import raspi_config as config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.servo_controller import ServoController
from controllers.motor_controller import MotorController
from controllers.led_strip_controller import LedStripController
from controllers.raspi_relay_controller import RelayController

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

class ActuatorManager:
    def __init__(self):
        self.hardware_active = GPIO_AVAILABLE
        
        # Initialize sub-controllers
        self.servos = ServoController(
            safety_pin=getattr(config, 'SERVO_PIN_SAFETY', 23),
            shim_pin=getattr(config, 'SERVO_PIN_SHIM', 24),
            reg_pin=getattr(config, 'SERVO_PIN_REG', 25)
        )
        self.motors = MotorController()
        
        # Initialize WS2812 LED Strip (Pipa & Pressurizer Daisy-Chained)
        try:
            self.led_strip = LedStripController(
                pin=getattr(config, 'LED_STRIP_PIN', 18),
                count=getattr(config, 'LED_STRIP_COUNT', 638),
                channel=0, dma=10
            )
            self.led_strip.add_segment('tersier_in', getattr(config, 'LED_SEGMENT_TERSIER_IN', (0, 84))[0], getattr(config, 'LED_SEGMENT_TERSIER_IN', (0, 84))[1], flow_direction=1)
            self.led_strip.add_segment('kondenser', getattr(config, 'LED_SEGMENT_KONDENSER', (84, 46))[0], getattr(config, 'LED_SEGMENT_KONDENSER', (84, 46))[1], flow_direction=1)
            self.led_strip.add_segment('primer', getattr(config, 'LED_SEGMENT_PRIMER', (130, 190))[0], getattr(config, 'LED_SEGMENT_PRIMER', (130, 190))[1])
            self.led_strip.add_segment('sekunder', config.LED_SEGMENT_SEKUNDER[0], config.LED_SEGMENT_SEKUNDER[1])
            self.led_strip.add_segment('tersier', config.LED_SEGMENT_TERSIER[0], config.LED_SEGMENT_TERSIER[1], flow_direction=1)
            self.led_strip.add_segment('tersier_out', config.LED_SEGMENT_TERSIER_OUT[0], config.LED_SEGMENT_TERSIER_OUT[1], flow_direction=1)
            self.led_strip.add_segment('sekunder_in', config.LED_SEGMENT_SEKUNDER_IN[0], config.LED_SEGMENT_SEKUNDER_IN[1], flow_direction=1)
            self.led_strip.add_segment('pressurizer', config.LED_SEGMENT_PRESSURIZER[0], config.LED_SEGMENT_PRESSURIZER[1], flow_direction=1)
            
            if self.hardware_active:
                self.led_strip.start()
        except Exception as e:
            logger.warning(f"ActuatorManager: Failed to initialize LedStripController: {e}")
            self.led_strip = None
        
        if self.hardware_active:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                
                # Initialize Power LED
                if hasattr(config, 'LED_POWER_PIN'):
                    if not self.motors.mock_mode and hasattr(self.motors, 'pi') and self.motors.pi.connected:
                        import pigpio
                        self.motors.pi.set_mode(config.LED_POWER_PIN, pigpio.OUTPUT)
                        self.motors.pi.set_PWM_frequency(config.LED_POWER_PIN, 1000)
                        self.motors.pi.set_PWM_range(config.LED_POWER_PIN, 100) # 0-100% duty cycle
                        self.motors.pi.set_PWM_dutycycle(config.LED_POWER_PIN, 0)
                        self.use_pigpio_for_led = True
                        logger.info(f"ActuatorManager: Power LED initialized on GPIO {config.LED_POWER_PIN} (via pigpio)")
                    else:
                        GPIO.setup(config.LED_POWER_PIN, GPIO.OUT)
                        self.led_pwm = GPIO.PWM(config.LED_POWER_PIN, 1000)  # 1kHz
                        self.led_pwm.start(0)
                        self.use_pigpio_for_led = False
                        logger.info(f"ActuatorManager: Power LED initialized on GPIO {config.LED_POWER_PIN} (via RPi.GPIO fallback)")
                else:
                    self.use_pigpio_for_led = None
                
                # Initialize Cherenkov LED
                if hasattr(config, 'LED_CHERENKOV_PIN'):
                    if self.use_pigpio_for_led:
                        import pigpio
                        self.motors.pi.set_mode(config.LED_CHERENKOV_PIN, pigpio.OUTPUT)
                        self.motors.pi.set_PWM_frequency(config.LED_CHERENKOV_PIN, 1000)
                        self.motors.pi.set_PWM_range(config.LED_CHERENKOV_PIN, 100)
                        self.motors.pi.set_PWM_dutycycle(config.LED_CHERENKOV_PIN, 0)
                        logger.info(f"ActuatorManager: Cherenkov LED initialized on GPIO {config.LED_CHERENKOV_PIN} (via pigpio)")
                    else:
                        GPIO.setup(config.LED_CHERENKOV_PIN, GPIO.OUT)
                        self.cherenkov_pwm = GPIO.PWM(config.LED_CHERENKOV_PIN, 1000)
                        self.cherenkov_pwm.start(0)
                        logger.info(f"ActuatorManager: Cherenkov LED initialized on GPIO {config.LED_CHERENKOV_PIN} (via RPi.GPIO fallback)")

                # Initialize Turbine LED
                if hasattr(config, 'LED_TURBINE_PIN'):
                    if getattr(self, 'use_pigpio_for_led', False):
                        import pigpio
                        self.motors.pi.set_mode(config.LED_TURBINE_PIN, pigpio.OUTPUT)
                        self.motors.pi.set_PWM_frequency(config.LED_TURBINE_PIN, 1000)
                        self.motors.pi.set_PWM_range(config.LED_TURBINE_PIN, 100)
                        self.motors.pi.set_PWM_dutycycle(config.LED_TURBINE_PIN, 0)
                        logger.info(f"ActuatorManager: Turbine LED initialized on GPIO {config.LED_TURBINE_PIN} (via pigpio)")
                    else:
                        GPIO.setup(config.LED_TURBINE_PIN, GPIO.OUT)
                        self.turbine_pwm = GPIO.PWM(config.LED_TURBINE_PIN, 1000)
                        self.turbine_pwm.start(0)
                        logger.info(f"ActuatorManager: Turbine LED initialized on GPIO {config.LED_TURBINE_PIN} (via RPi.GPIO fallback)")
                
                # Initialize Relief Valve LEDs
                if hasattr(config, 'LED_RELIEF_GREEN_PIN'):
                    GPIO.setup(config.LED_RELIEF_GREEN_PIN, GPIO.OUT)
                    GPIO.output(config.LED_RELIEF_GREEN_PIN, GPIO.HIGH) # Default Green ON
                if hasattr(config, 'LED_RELIEF_RED_PIN'):
                    GPIO.setup(config.LED_RELIEF_RED_PIN, GPIO.OUT)
                    GPIO.output(config.LED_RELIEF_RED_PIN, GPIO.LOW)  # Default Red OFF

                logger.info(f"ActuatorManager: Hardware mode active.")
            except Exception as e:
                logger.warning(f"ActuatorManager: Failed to initialize hardware GPIO: {e}")
                self.hardware_active = False
        else:
            logger.info("ActuatorManager: Running in MOCK mode (No RPi.GPIO)")
            
        # Initialize relays
        self.relays = RelayController()

    def update_actuators(self, state):
        """
        Updates all physical actuators based on the current state.
        This is called periodically (e.g., every 10ms) from the control logic thread.
        """
        # Servos are managed by pigpio independently of RPi.GPIO
        self.servos.set_rods(state.safety_rod, state.shim_rod, state.regulating_rod)
        
        # Motors are also managed by pigpio
        # Calculate smooth speed during transition (3.0 seconds duration, as in raspi_main_panel)
        def calc_speed(status, transition_start):
            if status == 0:  # OFF
                return 0.0
            elif status == 2:  # ON
                return 100.0
            
            # For STARTING (1) and SHUTTING_DOWN (3)
            current_time = time.time()
            if transition_start == 0:
                return 0.0 if status == 1 else 100.0
                
            progress = (current_time - transition_start) / 3.0
            progress = max(0.0, min(1.0, progress))
            
            if status == 1:  # STARTING: 0 to 100%
                return progress * 100.0
            elif status == 3:  # SHUTTING_DOWN: 100 to 0%
                return (1.0 - progress) * 100.0
            return 0.0

        prim_speed = calc_speed(state.pump_primary_status, state.pump_primary_transition_start)
        sec_speed = calc_speed(state.pump_secondary_status, state.pump_secondary_transition_start)
        tert_speed = calc_speed(state.pump_tertiary_status, state.pump_tertiary_transition_start)
        
        self.motors.set_speed('pump_primary', prim_speed)
        self.motors.set_speed('pump_secondary', sec_speed)
        self.motors.set_speed('pump_tertiary', tert_speed)
        self.motors.set_speed('turbine', state.turbine_speed)
        
        # Update LED Strip speeds (0.0 to 1.0 multiplier)
        if self.led_strip is not None:
            self.led_strip.set_flow_speed('tersier_in', tert_speed / 100.0)
            self.led_strip.set_flow_speed('kondenser', tert_speed / 100.0)
            self.led_strip.set_flow_speed('primer', prim_speed / 100.0)
            self.led_strip.set_flow_speed('sekunder', sec_speed / 100.0)
            self.led_strip.set_flow_speed('sekunder_in', sec_speed / 100.0)
            self.led_strip.set_flow_speed('tersier', tert_speed / 100.0)
            self.led_strip.set_flow_speed('tersier_out', tert_speed / 100.0)
            
            # Update heat ratio berdasarkan daya termal (0 kW hingga 10.000 kW / 10 MW)
            # Jika daya melebihi 10 MW, warna akan langsung mentok merah (1.0)
            thermal_power_kw = getattr(state, 'thermal_kw', 0.0)
            heat_ratio = thermal_power_kw / 10000.0
            heat_ratio = max(0.0, min(1.0, heat_ratio))
            
            self.led_strip.set_heat_ratio('kondenser', heat_ratio)
            self.led_strip.set_heat_ratio('primer', heat_ratio)
            self.led_strip.set_heat_ratio('sekunder', heat_ratio)
            self.led_strip.set_heat_ratio('sekunder_in', heat_ratio)
            self.led_strip.set_heat_ratio('tersier', heat_ratio)
            self.led_strip.set_heat_ratio('tersier_out', heat_ratio)
            
        # Update Pressurizer WS2812 Fill Level based on Pressure
        if hasattr(self, 'led_strip') and self.led_strip is not None and 'pressurizer' in self.led_strip.segments:
            pressure_val = getattr(state, 'pressure', 0.0)
            # Batasi nilai ratio dari 0.0 hingga 1.0 (0 hingga 200 bar)
            pressure_ratio = max(0.0, min(1.0, pressure_val / 200.0))
            
            # Gradasi warna:
            if pressure_val <= 155.0:
                # Normal: Putih Terang (agar tembus filamen biru menjadi Biru Terang)
                r, g, b = 255, 255, 255
            elif pressure_val <= 165.0:
                # Warning: 155 - 165. Transisi Putih(255,255,255) ke Biru Terang / Cyan (0,255,255)
                ratio = (pressure_val - 155.0) / 10.0
                r = int(255 - (255 * ratio))
                g = 255
                b = 255
            else:
                # Critical: > 165. Biru Terang / Cyan (0, 255, 255)
                r, g, b = 0, 255, 255

            self.led_strip.set_fill_level('pressurizer', pressure_ratio, r, g, b)
            # Berikan animasi ombak naik (kecepatan proporsional dengan rasio tekanan)
            self.led_strip.set_flow_speed('pressurizer', 0.5 + (pressure_ratio * 2.0))
        
        if not self.hardware_active:
            # In mock mode, we don't do anything physical for standard GPIO.
            return

        try:
            # Update Power LED based on thermal_kw (0-300000 kW)
            if hasattr(self, 'use_pigpio_for_led') and self.use_pigpio_for_led is not None:
                power_ratio = getattr(state, 'thermal_kw', 0.0) / 300000.0
                power_ratio = max(0.0, min(1.0, power_ratio))
                duty_cycle = power_ratio * 100.0
                
                if self.use_pigpio_for_led:
                    self.motors.pi.set_PWM_dutycycle(config.LED_POWER_PIN, int(duty_cycle))
                elif hasattr(self, 'led_pwm') and self.led_pwm is not None:
                    self.led_pwm.ChangeDutyCycle(duty_cycle)
                    
            # Update Cherenkov LED based on thermal_kw (0-300000 kW)
            if hasattr(config, 'LED_CHERENKOV_PIN'):
                # Glow brightness is proportional to reactor thermal power
                # Adding a small curve so it looks more dramatic at high power
                power_ratio = getattr(state, 'thermal_kw', 0.0) / 300000.0
                power_ratio = max(0.0, min(1.0, power_ratio))
                cherenkov_duty = (power_ratio ** 1.5) * 100.0  # Non-linear brightness curve
                
                if getattr(self, 'use_pigpio_for_led', False):
                    self.motors.pi.set_PWM_dutycycle(config.LED_CHERENKOV_PIN, int(cherenkov_duty))
                elif hasattr(self, 'cherenkov_pwm') and self.cherenkov_pwm is not None:
                    self.cherenkov_pwm.ChangeDutyCycle(cherenkov_duty)

            # Update Turbine LED based on thermal_kw (0-300000 kW)
            if hasattr(config, 'LED_TURBINE_PIN'):
                # Cahaya turbin menyala proporsional dengan daya yang dihasilkan
                power_ratio = getattr(state, 'thermal_kw', 0.0) / 300000.0
                power_ratio = max(0.0, min(1.0, power_ratio))
                # Kurva linier biasa untuk turbin
                turbine_duty = power_ratio * 100.0
                
                if getattr(self, 'use_pigpio_for_led', False):
                    self.motors.pi.set_PWM_dutycycle(config.LED_TURBINE_PIN, int(turbine_duty))
                elif hasattr(self, 'turbine_pwm') and self.turbine_pwm is not None:
                    self.turbine_pwm.ChangeDutyCycle(turbine_duty)

            # Physical relay control for Humidifiers
            self.relays.set_relays(
                getattr(state, 'humid_ct1_cmd', 0),
                getattr(state, 'humid_ct2_cmd', 0),
                getattr(state, 'humid_ct3_cmd', 0),
                getattr(state, 'humid_ct4_cmd', 0)
            )

            # Relief Valve LEDs
            if hasattr(config, 'LED_RELIEF_GREEN_PIN') and hasattr(config, 'LED_RELIEF_RED_PIN'):
                if getattr(state, 'relief_valve_open', False):
                    # Relief Valve Open -> Red ON, Green OFF
                    GPIO.output(config.LED_RELIEF_RED_PIN, GPIO.HIGH)
                    GPIO.output(config.LED_RELIEF_GREEN_PIN, GPIO.LOW)
                else:
                    # Safe -> Green ON, Red OFF
                    GPIO.output(config.LED_RELIEF_RED_PIN, GPIO.LOW)
                    GPIO.output(config.LED_RELIEF_GREEN_PIN, GPIO.HIGH)
        except Exception as e:
            logger.error(f"ActuatorManager: Error updating hardware: {e}")

    def cleanup(self):
        """Cleanup GPIO pins on exit."""
        if hasattr(self, 'servos') and self.servos:
            self.servos.cleanup()
        if hasattr(self, 'motors') and self.motors:
            self.motors.cleanup()
        if hasattr(self, 'relays') and self.relays:
            self.relays.cleanup()
        
        if hasattr(self, 'led_strip') and self.led_strip is not None:
            self.led_strip.stop()
        
        if self.hardware_active:
            try:
                if hasattr(self, 'use_pigpio_for_led'):
                    if self.use_pigpio_for_led and hasattr(self.motors, 'pi') and self.motors.pi is not None:
                        self.motors.pi.set_PWM_dutycycle(config.LED_POWER_PIN, 0)
                        if hasattr(config, 'LED_CHERENKOV_PIN'):
                            self.motors.pi.set_PWM_dutycycle(config.LED_CHERENKOV_PIN, 0)
                        if hasattr(config, 'LED_TURBINE_PIN'):
                            self.motors.pi.set_PWM_dutycycle(config.LED_TURBINE_PIN, 0)
                    elif not self.use_pigpio_for_led and hasattr(self, 'led_pwm') and self.led_pwm is not None:
                        self.led_pwm.stop()
                        if hasattr(self, 'cherenkov_pwm') and self.cherenkov_pwm is not None:
                            self.cherenkov_pwm.stop()
                        if hasattr(self, 'turbine_pwm') and self.turbine_pwm is not None:
                            self.turbine_pwm.stop()
                GPIO.cleanup()
                logger.info("ActuatorManager: Cleaned up GPIO.")
            except Exception as e:
                logger.error(f"ActuatorManager: Cleanup error: {e}")
