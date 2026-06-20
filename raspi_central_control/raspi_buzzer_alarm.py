#!/usr/bin/env python3
"""
Buzzer Alarm Control for PLTN Simulator
Passive buzzer control with PWM for different alarm tones

Alarm Conditions:
1. Procedure Warning: Primary pump start without pressure (>= 40 bar required)
   or incorrect pump sequence. (3 short beeps)
2. Pressure Warning: Pressure >= 160 bar (approaching limit)
3. Pressure Critical: Pressure >= 180 bar (near maximum)
4. Emergency SCRAM: Safety shutdown activated
5. Interlock Violation: Attempt to move rods without conditions met
"""

import logging
import threading
import time

# Try to import GPIO library
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    logging.warning("RPi.GPIO not available. Buzzer running in simulation mode.")
    GPIO_AVAILABLE = False

logger = logging.getLogger(__name__)

class BuzzerAlarm:
    """
    Passive Buzzer Control with PWM for alarm tones
    Uses GPIO 22 (software PWM since GPIO 18 is used by EMERGENCY button)
    
    Note: GPIO 22 is safe to use - no conflicts with buttons, I2C, or reserved pins.
    """
    
    # Alarm types and their frequencies
    ALARM_NONE = 0
    ALARM_PROCEDURE_WARNING = 1    # Procedure violation (e.g., pump without pressure)
    ALARM_PRESSURE_WARNING = 2     # Pressure >= 160 bar
    ALARM_PRESSURE_CRITICAL = 3    # Pressure >= 180 bar
    ALARM_EMERGENCY = 4            # SCRAM activated
    ALARM_INTERLOCK = 5            # Interlock violation
    
    # Tone configurations (frequency, pattern)
    ALARM_TONES = {
        ALARM_NONE: {'freq': 0, 'pattern': [], 'name': 'Silent'},
        ALARM_PROCEDURE_WARNING: {
            'freq': 2000,  # 2 kHz - mid tone
            'pattern': [0.3, 0.3],  # beep 0.3s, pause 0.3s
            'name': 'Procedure Warning'
        },
        ALARM_PRESSURE_WARNING: {
            'freq': 2500,  # 2.5 kHz - higher tone
            'pattern': [0.5, 0.5],  # beep 0.5s, pause 0.5s
            'name': 'Pressure Warning'
        },
        ALARM_PRESSURE_CRITICAL: {
            'freq': 3000,  # 3 kHz - high tone
            'pattern': [0.2, 0.2, 0.2, 0.6],  # double beep
            'name': 'Pressure CRITICAL'
        },
        ALARM_EMERGENCY: {
            'freq': 4000,  # 4 kHz - very high tone
            'pattern': [0.1, 0.1],  # rapid beep
            'name': 'EMERGENCY SCRAM'
        },
        ALARM_INTERLOCK: {
            'freq': 1500,  # 1.5 kHz - low tone
            'pattern': [0.2, 0.8],  # short beep, long pause
            'name': 'Interlock Violation'
        }
    }
    
    def __init__(self, buzzer_pin=22):
        """
        Initialize buzzer alarm controller
        
        Args:
            buzzer_pin: GPIO pin for buzzer (default 22 - GPIO 18 is used by EMERGENCY button)
        """
        self.buzzer_pin = buzzer_pin
        self.current_alarm = self.ALARM_NONE
        self.alarm_active = False
        self.alarm_thread = None
        self.alarm_lock = threading.Lock()
        self.stop_alarm_flag = False
        self.emergency_beep_active = False  # Flag to protect emergency beep from being cleared
        
        # Initialize GPIO
        if GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.buzzer_pin, GPIO.OUT)
                GPIO.output(self.buzzer_pin, GPIO.LOW)
                logger.info(f"Buzzer alarm initialized on GPIO {self.buzzer_pin}")
            except Exception as e:
                logger.error(f"Failed to initialize buzzer GPIO: {e}")
                self.buzzer_pin = None
        else:
            logger.info("Buzzer alarm in simulation mode")
            self.buzzer_pin = None
    
    def _alarm_thread_func(self):
        """Thread function for alarm pattern generation"""
        if not GPIO_AVAILABLE or not self.buzzer_pin:
            # Simulation mode
            while not self.stop_alarm_flag:
                if self.current_alarm != self.ALARM_NONE:
                    tone_config = self.ALARM_TONES[self.current_alarm]
                    logger.info(f"🔊 ALARM: {tone_config['name']} (simulated)")
                time.sleep(1.0)
            return
        
        try:
            # Create PWM instance
            pwm = GPIO.PWM(self.buzzer_pin, 1000)  # Start with 1kHz (will change)
            
            while not self.stop_alarm_flag:
                with self.alarm_lock:
                    alarm_type = self.current_alarm
                
                if alarm_type == self.ALARM_NONE:
                    pwm.stop()
                    time.sleep(0.1)
                    continue
                
                # Get tone configuration
                tone_config = self.ALARM_TONES[alarm_type]
                freq = tone_config['freq']
                pattern = tone_config['pattern']
                
                # Play alarm pattern
                for i, duration in enumerate(pattern):
                    if self.stop_alarm_flag:
                        break
                    
                    if i % 2 == 0:
                        # Beep ON
                        pwm.ChangeFrequency(freq)
                        pwm.start(50)  # 50% duty cycle
                    else:
                        # Beep OFF (pause)
                        pwm.stop()
                    
                    time.sleep(duration)
            
            # Stop PWM on exit
            pwm.stop()
        
        except Exception as e:
            logger.error(f"Alarm thread error: {e}")
    
    def set_alarm(self, alarm_type):
        """
        Set alarm type
        
        Args:
            alarm_type: One of ALARM_* constants
        """
        with self.alarm_lock:
            if alarm_type != self.current_alarm:
                old_alarm = self.ALARM_TONES[self.current_alarm]['name']
                new_alarm = self.ALARM_TONES[alarm_type]['name']
                
                self.current_alarm = alarm_type
                
                if alarm_type != self.ALARM_NONE:
                    logger.warning(f"🔊 ALARM ACTIVATED: {new_alarm}")
                    
                    # Start alarm thread if not running
                    if not self.alarm_active:
                        self.alarm_active = True
                        self.stop_alarm_flag = False
                        self.alarm_thread = threading.Thread(
                            target=self._alarm_thread_func,
                            daemon=True
                        )
                        self.alarm_thread.start()
                else:
                    if old_alarm != 'Silent':
                        logger.info(f"🔕 ALARM CLEARED: {old_alarm}")
    
    def clear_alarm(self):
        """Clear all alarms"""
        self.set_alarm(self.ALARM_NONE)
    
    def check_alarms(self, state):
        """
        Check system state and activate appropriate alarms
        
        Priority (highest first):
        1. PRESSURE_CRITICAL (>= 180 bar)
        2. PRESSURE_WARNING (>= 160 bar)
        3. Other alarms cleared automatically
        
        NOTE: Emergency SCRAM alarm is now handled by trigger_emergency_beep()
              and is NOT continuous - it beeps for 5 seconds then stops.
        
        Args:
            state: PanelState object
        """
        # REMOVED: Emergency check (now handled by trigger_emergency_beep)
        # Emergency SCRAM uses timed beep instead of continuous alarm
        
        # Don't clear alarm if emergency beep is active (protected)
        if self.emergency_beep_active:
            return  # Let emergency beep finish its duration
        
        # Priority 1: Pressure CRITICAL (>= 180 bar)
        if state.pressure >= 180.0:
            self.set_alarm(self.ALARM_PRESSURE_CRITICAL)
            return
        
        # Priority 2: Pressure WARNING (>= 160 bar)
        if state.pressure >= 160.0:
            self.set_alarm(self.ALARM_PRESSURE_WARNING)
            return
        
        # All clear - no continuous alarm
        self.clear_alarm()
    
    def trigger_emergency_beep(self, duration=5.0):
        """
        Trigger emergency beep for a fixed duration (non-blocking)
        Used for SCRAM - beeps for 5 seconds then stops automatically
        Protected from being cleared by check_alarms()
        
        Args:
            duration: How long to beep (default 5 seconds)
        """
        logger.info(f"🔔 trigger_emergency_beep() called (duration={duration}s)")
        
        def beep_for_duration():
            try:
                logger.info(f"🔊 Emergency beep thread started ({duration}s)")
                self.emergency_beep_active = True  # Protect from check_alarms()
                self.set_alarm(self.ALARM_EMERGENCY)
                time.sleep(duration)
                self.emergency_beep_active = False  # Release protection
                self.clear_alarm()
                logger.info(f"✅ Emergency beep completed ({duration}s)")
            except Exception as e:
                self.emergency_beep_active = False  # Release on error
                logger.error(f"❌ Emergency beep error: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Run in separate thread (non-blocking)
        beep_thread = threading.Thread(target=beep_for_duration, daemon=True)
        beep_thread.start()
        logger.info(f"✓ Emergency beep thread created and started")
    
    def sound_procedure_warning(self, duration=2.0):
        """
        Sound procedure warning (non-blocking)
        Used for violations like starting pump without pressure
        
        Args:
            duration: How long to sound alarm (seconds)
        """
        def alarm_for_duration():
            self.set_alarm(self.ALARM_PROCEDURE_WARNING)
            time.sleep(duration)
            # Don't clear here - let check_alarms() handle it
        
        threading.Thread(target=alarm_for_duration, daemon=True).start()
    
    def sound_interlock_warning(self, duration=1.5):
        """
        Sound interlock violation warning (non-blocking)
        Used when trying to move rods without meeting conditions
        
        Args:
            duration: How long to sound alarm (seconds)
        """
        def alarm_for_duration():
            self.set_alarm(self.ALARM_INTERLOCK)
            time.sleep(duration)
            # Don't clear here - let check_alarms() handle it
        
        threading.Thread(target=alarm_for_duration, daemon=True).start()
    
    def cleanup(self):
        """Cleanup buzzer resources"""
        logger.info("Cleaning up buzzer alarm...")
        self.stop_alarm_flag = True
        self.alarm_active = False
        
        if self.alarm_thread and self.alarm_thread.is_alive():
            self.alarm_thread.join(timeout=2.0)
        
        if GPIO_AVAILABLE and self.buzzer_pin:
            try:
                GPIO.output(self.buzzer_pin, GPIO.LOW)
                GPIO.cleanup(self.buzzer_pin)
            except Exception as e:
                logger.error(f"Buzzer cleanup error: {e}")
        
        logger.info("Buzzer alarm cleaned up")

# ============================================
# Test Function
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("="*60)
    print("  Buzzer Alarm Controller Test")
    print("="*60)
    
    # Create buzzer instance
    buzzer = BuzzerAlarm(buzzer_pin=18)
    
    print("\nTest 1: Procedure Warning (2 kHz, 2 seconds)")
    buzzer.sound_procedure_warning(duration=2.0)
    time.sleep(3)
    
    print("\nTest 2: Pressure Warning (2.5 kHz)")
    buzzer.set_alarm(BuzzerAlarm.ALARM_PRESSURE_WARNING)
    time.sleep(3)
    
    print("\nTest 3: Pressure CRITICAL (3 kHz, double beep)")
    buzzer.set_alarm(BuzzerAlarm.ALARM_PRESSURE_CRITICAL)
    time.sleep(3)
    
    print("\nTest 4: EMERGENCY (4 kHz, rapid beep)")
    buzzer.set_alarm(BuzzerAlarm.ALARM_EMERGENCY)
    time.sleep(3)
    
    print("\nTest 5: Interlock Warning (1.5 kHz)")
    buzzer.sound_interlock_warning(duration=1.5)
    time.sleep(2)
    
    print("\nTest 6: Clear alarm")
    buzzer.clear_alarm()
    time.sleep(1)
    
    print("\nCleaning up...")
    buzzer.cleanup()
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)
