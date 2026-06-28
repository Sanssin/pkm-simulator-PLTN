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
            self.led_strip.add_segment('tersier_in', config.LED_SEGMENT_TERSIER_IN[0], config.LED_SEGMENT_TERSIER_IN[1], flow_direction=1)
            self.led_strip.add_segment('kondenser', config.LED_SEGMENT_KONDENSER[0], config.LED_SEGMENT_KONDENSER[1], flow_direction=1)
            self.led_strip.add_segment('tersier_out', config.LED_SEGMENT_TERSIER_OUT[0], config.LED_SEGMENT_TERSIER_OUT[1], flow_direction=1)
            self.led_strip.add_segment('sekunder_in', config.LED_SEGMENT_SEKUNDER_IN[0], config.LED_SEGMENT_SEKUNDER_IN[1], flow_direction=1)
            self.led_strip.add_segment('sekunder_out', config.LED_SEGMENT_SEKUNDER_OUT[0], config.LED_SEGMENT_SEKUNDER_OUT[1], flow_direction=1)
            self.led_strip.add_segment('primer', config.LED_SEGMENT_PRIMER[0], config.LED_SEGMENT_PRIMER[1])
            self.led_strip.add_segment('pressurizer', config.LED_SEGMENT_PRESSURIZER[0], config.LED_SEGMENT_PRESSURIZER[1], flow_direction=1)
            
            # PENTING: start() HARUS selalu dipanggil — tidak bergantung pada GPIO/RPi status
            # karena LED strip menggunakan DMA/PWM hardware tersendiri (rpi_ws281x)
            self.led_strip.start()
            logger.info("ActuatorManager: LedStripController started.")
        except Exception as e:
            logger.warning(f"ActuatorManager: Failed to initialize LedStripController: {e}")
            self.led_strip = None
        
        if self.hardware_active:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                
                self.led_pwms = {}
                self.use_pigpio_for_led = False
                if not self.motors.mock_mode and hasattr(self.motors, 'pi') and self.motors.pi.connected:
                    self.use_pigpio_for_led = True
                    
                led_configs = [
                    ('power', getattr(config, 'LED_POWER_PIN', None)),
                    ('cherenkov', getattr(config, 'LED_CHERENKOV_PIN', None)),
                    ('turbine', getattr(config, 'LED_TURBINE_PIN', None))
                ]
                
                for name, pin in led_configs:
                    if pin:
                        if self.use_pigpio_for_led:
                            import pigpio
                            self.motors.pi.set_mode(pin, pigpio.OUTPUT)
                            self.motors.pi.set_PWM_frequency(pin, 1000)
                            self.motors.pi.set_PWM_range(pin, 100)
                            self.motors.pi.set_PWM_dutycycle(pin, 0)
                            logger.info(f"ActuatorManager: {name.capitalize()} LED initialized on GPIO {pin} (via pigpio)")
                        else:
                            GPIO.setup(pin, GPIO.OUT)
                            pwm = GPIO.PWM(pin, 1000)
                            pwm.start(0)
                            self.led_pwms[name] = pwm
                            logger.info(f"ActuatorManager: {name.capitalize()} LED initialized on GPIO {pin} (via RPi.GPIO fallback)")
                
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
        
        # Inisialisasi ke nilai default state_manager agar tidak ada false trigger
        # saat update_actuators pertama kali dipanggil
        self._prev_sim_mode = 'manual'

    def update_actuators(self, state):
        """
        Updates all physical actuators based on the current state.
        This is called periodically (e.g., every 10ms) from the control logic thread.
        """
        # Servos are managed by pigpio independently of RPi.GPIO
        self.servos.set_rods(state.safety_rod, state.shim_rod, state.regulating_rod)
        
        # Motors are also managed by pigpio
        # Calculate smooth speed during transition (7.0 seconds duration)
        def calc_speed(status, transition_start):
            if status == 0:  # OFF
                return 0.0
            elif status == 2:  # ON
                return 100.0
            
            # For STARTING (1) and SHUTTING_DOWN (3)
            current_time = time.time()
            if transition_start == 0:
                return 0.0 if status == 1 else 100.0
                
            progress = (current_time - transition_start) / 7.0
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
            self.led_strip.set_flow_speed('sekunder_in', sec_speed / 100.0)
            self.led_strip.set_flow_speed('tersier_out', tert_speed / 100.0)
            
            # Khusus sekunder_out (uap), baru bergerak jika reaktor menghasilkan daya (hr > 0.01)
            hr_secondary_current = 0.0
            t_secondary = getattr(state, 'temperature_coolant_secondary', 25.0)
            if t_secondary > 25.0:
                hr_secondary_current = (t_secondary - 25.0) / (250.0 - 25.0)
            
            if hr_secondary_current > 0.01:
                self.led_strip.set_flow_speed('sekunder_out', sec_speed / 100.0)
            else:
                self.led_strip.set_flow_speed('sekunder_out', 0.0)
            
            sim_mode = getattr(state, 'simulation_mode', 'idle')
            is_reset = getattr(state, 'just_reset', True)

            any_pump_on = (
                getattr(state, 'pump_primary_status', 0) > 0 or
                getattr(state, 'pump_secondary_status', 0) > 0 or
                getattr(state, 'pump_tertiary_status', 0) > 0 or
                getattr(state, 'auto_sim_running', False)
            )

            # Deteksi apakah user baru saja berpindah ke mode aktif
            # Simpan sim_mode sebelumnya untuk mendeteksi perubahan
            prev_sim_mode = getattr(self, '_prev_sim_mode', None)
            if prev_sim_mode != sim_mode:
                self._prev_sim_mode = sim_mode
                # User berpindah ke mode aktif
                if sim_mode in ('manual', 'auto', 'cinematic_lofa') and is_reset:
                    state.just_reset = False
                    is_reset = False

            # Bersihkan juga saat ada pompa menyala atau auto aktif
            if any_pump_on or sim_mode in ('auto', 'cinematic_lofa'):
                if is_reset:
                    state.just_reset = False
                    is_reset = False


            if is_reset or sim_mode == 'idle':
                self.led_strip.set_active('primer', False)
                self.led_strip.set_active('sekunder_in', False)
                self.led_strip.set_active('sekunder_out', False)
                self.led_strip.set_active('tersier_in', False)
                self.led_strip.set_active('kondenser', False)
                self.led_strip.set_active('tersier_out', False)
                self.led_strip.set_active('pressurizer', False)
            else:
                if prim_speed > 0.0:
                    self.led_strip.set_active('primer', True)
                    self.led_strip.set_active('pressurizer', True)
                if sec_speed > 0.0:
                    self.led_strip.set_active('sekunder_in', True)
                    self.led_strip.set_active('sekunder_out', True)
                if tert_speed > 0.0:
                    self.led_strip.set_active('tersier_in', True)
                    self.led_strip.set_active('kondenser', True)
                    self.led_strip.set_active('tersier_out', True)
            
            # Selain kondisi idle/reset, is_active diset True sehingga lampu tetap menyala 
            # (namun tidak bergerak jika speed 0)
            
            # Update heat ratio berdasarkan suhu air aktual di tiap siklus
            ambient = 25.0
            
            # Suhu primer normal bisa mencapai 320C. Merah solid (1.0) hanya saat LOFA (suhu mendekati 380C)
            t_primary = getattr(state, 'temperature_coolant_primary', ambient)
            hr_primary = (t_primary - ambient) / (380.0 - ambient)
            hr_primary = max(0.0, min(1.0, hr_primary))
            
            # Suhu sekunder maksimal sekitar ~250C (0.7 * 380). Kita set merah solid (1.0) pada suhu 250C.
            t_secondary = getattr(state, 'temperature_coolant_secondary', ambient)
            hr_secondary = (t_secondary - ambient) / (250.0 - ambient)
            hr_secondary = max(0.0, min(1.0, hr_secondary))
            
            self.led_strip.set_heat_ratio('primer', hr_primary)
            self.led_strip.set_heat_ratio('sekunder_in', hr_secondary)
            self.led_strip.set_heat_ratio('sekunder_out', hr_secondary)
            self.led_strip.set_heat_ratio('kondenser', hr_secondary)
            self.led_strip.set_heat_ratio('tersier_out', hr_secondary)
            
            # Update Pump Indicators
            # Urutan fisik: LED 303=Tersier, LED 304=Sekunder, LED 305=Primer
            pumps = [
                (0, getattr(state, 'pump_tertiary_status', 0), getattr(state, 'lofa_tertiary', False)),
                (1, getattr(state, 'pump_secondary_status', 0), getattr(state, 'lofa_secondary', False)),
                (2, getattr(state, 'pump_primary_status', 0),  getattr(state, 'lofa_primary', False)),
            ]
            for idx, p_status, is_lofa in pumps:
                if is_lofa:
                    self.led_strip.set_pump_indicator(idx, 255, 0, 0, blink=True)      # Merah kedip (LOFA)
                elif p_status == 0:   # PUMP_OFF
                    self.led_strip.set_pump_indicator(idx, 255, 0, 0, blink=False)     # Merah solid
                elif p_status == 2:   # PUMP_ON
                    self.led_strip.set_pump_indicator(idx, 0, 255, 0, blink=False)     # Hijau solid
                elif p_status in (1, 3):  # PUMP_STARTING / SHUTTING_DOWN
                    self.led_strip.set_pump_indicator(idx, 255, 255, 0, blink=True)    # Kuning kedip
                else:
                    self.led_strip.set_pump_indicator(idx, 0, 0, 0, blink=False)       # Off
            
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
            power_ratio = max(0.0, min(1.0, getattr(state, 'thermal_kw', 0.0) / 300000.0))
            
            led_duties = {
                'power': power_ratio * 100.0,
                'cherenkov': (power_ratio ** 1.5) * 100.0,
                'turbine': power_ratio * 100.0
            }
            
            for name, duty in led_duties.items():
                pin = getattr(config, f'LED_{name.upper()}_PIN', None)
                if pin:
                    if getattr(self, 'use_pigpio_for_led', False):
                        self.motors.pi.set_PWM_dutycycle(pin, int(duty))
                    elif name in getattr(self, 'led_pwms', {}):
                        self.led_pwms[name].ChangeDutyCycle(duty)

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
                if getattr(self, 'use_pigpio_for_led', False) and hasattr(self.motors, 'pi') and self.motors.pi is not None:
                    for name in ['POWER', 'CHERENKOV', 'TURBINE']:
                        pin = getattr(config, f'LED_{name}_PIN', None)
                        if pin:
                            self.motors.pi.set_PWM_dutycycle(pin, 0)
                else:
                    for pwm in getattr(self, 'led_pwms', {}).values():
                        pwm.stop()
                GPIO.cleanup()
                logger.info("ActuatorManager: Cleaned up GPIO.")
            except Exception as e:
                logger.error(f"ActuatorManager: Cleanup error: {e}")
