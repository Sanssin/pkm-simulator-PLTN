"""
Main Control Program for PLTN Simulator - 2 ESP Architecture
Refactored version using extracted modules.

Supports 17 buttons, humidifier control, buzzer alarm, optimized for 2 ESP32.
Target: ~500 lines (down from ~2000 lines).
"""

import time
import logging
import signal
import sys
import threading
import json
from pathlib import Path

# Add current directory to sys.path to ensure absolute imports work regardless of working directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)

from typing import Optional
from queue import Queue

# Import our modules
import raspi_config as config
from raspi_tca9548a import DualMultiplexerManager
from raspi_uart_master import UARTMaster
from raspi_gpio_buttons import ButtonHandler as ButtonManager, ButtonPin
from raspi_humidifier_control import HumidifierController
from raspi_buzzer_alarm import BuzzerAlarm
from raspi_system_health import SystemHealthMonitor

# Import refactored modules
from controllers.cpu_manager import CpuManager
from controllers import StateManager, PanelState, InterlockValidator, EventProcessor, PumpController
from controllers.interlock_validator import PUMP_ON
from sequences import SCRAMSequence, AutoSimulator
from communication import ESPProtocol
from io_handlers import ButtonIOHandler, ButtonEvent
from controllers.actuator_manager import ActuatorManager
from pltn_video_display.video_player import VideoPlayer

# Try to import GPIO library
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    logging.warning("RPi.GPIO not available. Running in simulation mode.")
    GPIO_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# Duplicate ButtonEvent and PanelState definitions removed (imported from controllers/io_handlers instead)



class PLTNPanelController:
    """
    Main PLTN Panel Controller Class (Refactored)
    
    Orchestrates all modules:
    - StateManager: Thread-safe state management
    - InterlockValidator: Safety interlock checks
    - EventProcessor: Button event handling
    - SCRAMSequence: Emergency shutdown
    - AutoSimulator: Automated startup
    - ESPProtocol: ESP communication
    - ButtonIOHandler: Button input handling
    """
    
    def __init__(self):
        """Initialize PLTN Panel Controller"""
        logger.info("=" * 60)
        logger.info("PLTN Simulator v5.0 - Refactored Architecture")
        logger.info("ESP-BC (Rods+Turbine+Humid) | ESP-E (LED Visualizer)")
        logger.info("=" * 60)
        
        # Core state management
        self.state_manager = StateManager()
        self.state_lock = self.state_manager.lock  # Alias for compatibility
        
        # Event queue for button presses
        self.button_event_queue = Queue(maxsize=100)
        

        from io_handlers.state_exporter import StateExporter
        self.state_exporter = StateExporter(self.state_manager)
        
        # Initialize hardware components
        self._init_hardware()
        
        # Initialize refactored modules
        self._init_modules()
        
        # Initialize video player (Thread 9 concept, non-blocking)
        self.video_player = VideoPlayer()
        
        logger.info("=" * 60)
        logger.info("PLTN Panel Controller initialized successfully")
        logger.info("=" * 60)
    
    def _init_hardware(self):
        """Initialize hardware components with graceful degradation."""
        logger.info("Phase 1: Core hardware initialization...")
        
        # Initialize UART master
        try:
            self.uart_master = UARTMaster()
            self.uart_lock = threading.Lock()
            logger.info("Ô£ô UART master initialized")
        except Exception as e:
            logger.warning(f"Ô£ù UART master failed: {e}")
            self.uart_master = None
            self.uart_lock = threading.Lock()
        
        # Initialize button manager
        try:
            self.button_manager = ButtonManager()
            logger.info("Ô£ô Button manager initialized")
        except Exception as e:
            logger.warning(f"Ô£ù Button manager failed: {e}")
            self.button_manager = None
        
        # Initialize buzzer
        try:
            self.buzzer = BuzzerAlarm(buzzer_pin=config.BUZZER_PIN if hasattr(config, 'BUZZER_PIN') else 22)
            logger.info("✓ Buzzer alarm initialized")
        except Exception as e:
            logger.warning(f"Ô£ù Buzzer failed: {e}")
            self.buzzer = None
            # Don't raise - make it non-critical
    
    def init_oled_displays(self):
        """Initialize 9 OLED displays (0.91 inch 128x32) with timeout"""
        try:
            from raspi_oled_manager import OLEDManager
            import threading
            
            self.oled_manager = OLEDManager(
                mux_manager=self.mux_manager,
                width=128,
                height=32  # 0.91 inch OLED
            )
            
            # Initialize displays in separate thread with timeout
            logger.info("Initializing 9 OLED displays (max 5s timeout)...")
            
            def init_displays():
                try:
                    self.oled_manager.init_all_displays()
                except Exception as e:
                    logger.warning(f"OLED init error: {e}")
            
            init_thread = threading.Thread(target=init_displays, daemon=True)
            init_thread.start()
            init_thread.join(timeout=5.0)  # Max 5 seconds total
            
            if init_thread.is_alive():
                logger.warning("OLED initialization timeout - continuing without displays")
                self.oled_manager = None
            else:
                logger.info("OLED displays initialization complete")
                logger.info("   Startup screen will be cleared by OLED update thread")
                
                # NOTE: sync_interpolators_to_state() moved to oled_update_thread()
                # This fixes race condition where sync was called before thread started
            
        except Exception as e:
            logger.warning(f"Failed to initialize OLED displays: {e}")
            logger.warning("Continuing without OLED displays...")
            self.oled_manager = None
    
    # ============================================
    # Lightweight Button Callbacks (NO LOCK, NO HEAVY WORK)
    # ============================================
    
    def on_pressure_up(self, is_held=False):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PRESSURE_UP)
        logger.info(f"Button event queued: PRESSURE_UP (held={is_held})")
    
    def on_pressure_down(self, is_held=False):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PRESSURE_DOWN)
        logger.info(f"Button event queued: PRESSURE_DOWN (held={is_held})")
    
    def on_pump_primary_on(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_PRIMARY_ON)
        logger.info("Button event queued: PUMP_PRIMARY_ON")
    
    def on_pump_primary_off(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_PRIMARY_OFF)
        logger.info("Button event queued: PUMP_PRIMARY_OFF")
    
    def on_pump_secondary_on(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_SECONDARY_ON)
        logger.info("Button event queued: PUMP_SECONDARY_ON")
    
    def on_pump_secondary_off(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_SECONDARY_OFF)
        logger.info("Button event queued: PUMP_SECONDARY_OFF")
    
    def on_pump_tertiary_on(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_TERTIARY_ON)
        logger.info("Button event queued: PUMP_TERTIARY_ON")
    
    def on_pump_tertiary_off(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.PUMP_TERTIARY_OFF)
        logger.info("Button event queued: PUMP_TERTIARY_OFF")
    
    def on_safety_rod_up(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.SAFETY_ROD_UP)
        logger.info("Button event queued: SAFETY_ROD_UP")
    
    def on_safety_rod_down(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.SAFETY_ROD_DOWN)
        logger.info("Button event queued: SAFETY_ROD_DOWN")
    
    def on_shim_rod_up(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.SHIM_ROD_UP)
        logger.info("Event queued: SHIM_ROD_UP")
    
    def on_shim_rod_down(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.SHIM_ROD_DOWN)
        logger.info("Button event queued: SHIM_ROD_DOWN")
    
    def on_regulating_rod_up(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.REGULATING_ROD_UP)
        logger.info("Button event queued: REGULATING_ROD_UP")
    
    def on_regulating_rod_down(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.REGULATING_ROD_DOWN)
        logger.info("Button event queued: REGULATING_ROD_DOWN")
    
    def on_emergency(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.EMERGENCY)
        logger.critical("Button event queued: EMERGENCY")
    
    def on_reactor_reset(self):
        """Lightweight callback - just enqueue event"""
        self.button_event_queue.put(ButtonEvent.REACTOR_RESET)
        logger.info("Button event queued: REACTOR_RESET")
    
    def on_start_auto_simulation(self):
        """Lightweight callback - start auto simulation"""
        self.button_event_queue.put(ButtonEvent.START_AUTO_SIMULATION)
        logger.info("Event queued: START_AUTO_SIMULATION")
    
    
    # ============================================
    # Sequential SCRAM Execution
    # ============================================
    
    def _execute_scram_sequence(self):
        """
        Execute SCRAM sequence: drop ALL rods simultaneously with smooth animation
        All three rods (Safety, Shim, Regulating) drop together
        Duration: 3 seconds (smooth descent)
        Runs in separate thread (non-blocking)
        """
        def scram_thread():
            try:
                logger.critical("SCRAM SEQUENCE INITIATED")
                logger.critical("Emergency rod insertion: ALL RODS DROPPING SIMULTANEOUSLY")
                
                # Capture initial turbine speed for spin-down
                with self.state_lock:
                    initial_turbine_speed = self.state.turbine_speed
                    # Capture initial rod positions
                    start_safety = self.state.safety_rod
                    start_shim = self.state.shim_rod
                    start_regulating = self.state.regulating_rod
                
                # Start turbine spin-down immediately (runs in parallel)
                if initial_turbine_speed > 0:
                    turbine_thread = threading.Thread(
                        target=self._turbine_spindown,
                        args=(initial_turbine_speed,),
                        daemon=True
                    )
                    turbine_thread.start()
                
                # Drop ALL rods simultaneously (3 seconds, smooth)
                logger.critical("Lowering all control rods...")
                start_time = time.time()
                duration = 3.0  # 3 seconds total
                
                while time.time() - start_time < duration:
                    elapsed = time.time() - start_time
                    progress = elapsed / duration  # 0.0 to 1.0
                    
                    # Calculate current positions for all rods (dropping together)
                    current_safety = int(start_safety * (1 - progress))
                    current_shim = int(start_shim * (1 - progress))
                    current_regulating = int(start_regulating * (1 - progress))
                    
                    # Update all rods in single lock
                    with self.state_lock:
                        self.state.safety_rod = max(0, current_safety)
                        self.state.shim_rod = max(0, current_shim)
                        self.state.regulating_rod = max(0, current_regulating)
                    
                    self.esp_send_immediate.set()
                    time.sleep(0.05)  # 50ms update rate = smooth animation
                
                # Ensure all rods are at 0%
                with self.state_lock:
                    self.state.safety_rod = 0
                    self.state.shim_rod = 0
                    self.state.regulating_rod = 0
                
                self.esp_send_immediate.set()
                
                logger.critical("Safety rod inserted (0%)")
                logger.critical("Shim rod inserted (0%)")
                logger.critical("Regulating rod inserted (0%)")
                logger.critical("SCRAM SEQUENCE COMPLETE - All rods inserted (3 seconds total)")
                logger.critical("Turbine spin-down continues (~12 seconds total)")
                
            except Exception as e:
                logger.error(f"SCRAM sequence error: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Run in separate thread (non-blocking)
        scram_thread_obj = threading.Thread(target=scram_thread, daemon=True)
        scram_thread_obj.start()
    
    def _turbine_spindown(self, initial_speed):
        """
        Gradually reduce turbine speed to 0 (realistic spin-down)
        Simulates turbine inertia and residual steam energy
        Duration: ~12 seconds (linear deceleration)
        
        Args:
            initial_speed: Starting turbine speed (%)
        """
        try:
            logger.info(f"Turbine spin-down started (initial: {initial_speed:.1f}%)")
            
            duration = 12.0  # 12 seconds total spin-down
            start_time = time.time()
            
            while True:
                elapsed = time.time() - start_time
                if elapsed >= duration:
                    break
                
                # Linear deceleration (could use exponential for more realism)
                progress = elapsed / duration
                current_speed = initial_speed * (1 - progress)
                
                with self.state_lock:
                    self.state.turbine_speed = max(0, current_speed)
                
                self.esp_send_immediate.set()  # Trigger immediate ESP update
                time.sleep(0.1)  # 100ms update rate (smooth animation)
            
            # Ensure final speed is exactly 0
            with self.state_lock:
                self.state.turbine_speed = 0
            self.esp_send_immediate.set()
            
            logger.info("Turbine spin-down complete (0%)")
            
        except Exception as e:
            logger.error(f"Turbine spin-down error: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    
    # ============================================
    # Event Processing (Heavy Work with Lock)
    # ============================================
    
    def process_button_event(self, event: ButtonEvent):
        """
        Process button event with proper locking and state update
        This runs in dedicated thread, NOT in interrupt context
        """
        # Update last button time for inactivity tracking
        self.last_button_time = time.time()
        
        with self.state_lock:
            
            if event == ButtonEvent.PRESSURE_UP:
                self.state.pressure = min(self.state.pressure + config.PRESS_INCREMENT_SLOW, 200.0)  # Detailed increment
            elif event == ButtonEvent.PRESSURE_UP_FAST:
                self.state.pressure = min(self.state.pressure + config.PRESS_INCREMENT_FAST, 200.0)  # Fast increment
            elif event == ButtonEvent.PRESSURE_DOWN:
                self.state.pressure = max(self.state.pressure - config.PRESS_INCREMENT_SLOW, 0.0)  # Detailed decrement
            elif event == ButtonEvent.PRESSURE_DOWN_FAST:
                self.state.pressure = max(self.state.pressure - config.PRESS_INCREMENT_FAST, 0.0)  # Fast decrement
            
            elif event == ButtonEvent.PUMP_PRIMARY_ON:
                if self.state.pump_primary_status == 0:
                    # Check safety conditions before starting
                    if self._check_pump_start_safe("Primary"):
                        self.state.pump_primary_status = 1
                        logger.info("Primary pump starting (safety checks passed)")
                    # else: already logged and buzzed by _check_pump_start_safe()
            
            elif event == ButtonEvent.PUMP_PRIMARY_OFF:
                if self.state.pump_primary_status == 2:
                    self.state.pump_primary_status = 3
            
            elif event == ButtonEvent.PUMP_SECONDARY_ON:
                if self.state.pump_secondary_status == 0:
                    # Check safety conditions before starting
                    if self._check_pump_start_safe("Secondary"):
                        self.state.pump_secondary_status = 1
                        logger.info("Secondary pump starting (safety checks passed)")
                    # else: already logged and buzzed by _check_pump_start_safe()
            
            elif event == ButtonEvent.PUMP_SECONDARY_OFF:
                if self.state.pump_secondary_status == 2:
                    self.state.pump_secondary_status = 3
            
            elif event == ButtonEvent.PUMP_TERTIARY_ON:
                if self.state.pump_tertiary_status == 0:
                    # Check safety conditions before starting
                    if self._check_pump_start_safe("Tertiary"):
                        self.state.pump_tertiary_status = 1
                        logger.info("Tertiary pump starting (safety checks passed)")
                    # else: already logged and buzzed by _check_pump_start_safe()
            
            elif event == ButtonEvent.PUMP_TERTIARY_OFF:
                if self.state.pump_tertiary_status == 2:
                    self.state.pump_tertiary_status = 3
            
            elif event == ButtonEvent.SAFETY_ROD_UP:
                if not self._check_interlock_internal():
                    logger.warning("INTERLOCK VIOLATION: Cannot raise safety rod!")
                    logger.warning(f"   Pressure: {self.state.pressure:.2f} bar (need >= 140 bar)")
                    logger.warning(f"   Pumps: Primary={self.state.pump_primary_status}, "
                                 f"Secondary={self.state.pump_secondary_status}, "
                                 f"Tertiary={self.state.pump_tertiary_status} (need all = 2)")
                    
                    # Trigger interlock violation buzzer (1.5 second beep)
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    
                    return
                self.state.safety_rod = min(self.state.safety_rod + 1, 100)  # 1% increment
                # Removed logging for performance
            
            elif event == ButtonEvent.SAFETY_ROD_DOWN:
                # Guard proporsional: safety rod harus selalu >= shim dan >= regulating
                new_pos = self.state.safety_rod - 1
                if new_pos < self.state.shim_rod or new_pos < self.state.regulating_rod:
                    logger.warning("Cannot lower Safety Rod below Shim/Regulating rod position!")
                    logger.warning(f"   Safety={self.state.safety_rod}%, Shim={self.state.shim_rod}%, Reg={self.state.regulating_rod}%")
                    logger.warning(f"   Lower Shim/Regulating first, then Safety can follow")
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    return

                self.state.safety_rod = max(new_pos, 0)  # 1% decrement
                # Removed logging for performance
            
            elif event == ButtonEvent.SHIM_ROD_UP:
                # Check safety rod priority: safety rod must be 100% before raising shim
                if self.state.safety_rod < 100:
                    logger.warning("SAFETY ROD PRIORITY: Cannot raise shim rod!")
                    logger.warning(f"   Safety rod must be at 100% first (currently: {self.state.safety_rod}%)")
                    logger.warning(f"   Correct sequence: Safety rod to 100% ÔåÆ Then shim/regulating rods")
                    
                    # Trigger buzzer warning
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    
                    return
                
                # Check interlock conditions
                if not self._check_interlock_internal():
                    logger.warning("INTERLOCK VIOLATION: Cannot raise shim rod!")
                    logger.warning(f"   Pressure: {self.state.pressure:.2f} bar (need >= 140 bar)")
                    logger.warning(f"   Pumps: Primary={self.state.pump_primary_status}, "
                                 f"Secondary={self.state.pump_secondary_status}, "
                                 f"Tertiary={self.state.pump_tertiary_status} (need all = 2)")
                    
                    # Trigger interlock violation buzzer
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    
                    return
                self.state.shim_rod = min(self.state.shim_rod + 1, 100)  # 1% increment
                # Removed logging for performance
            
            elif event == ButtonEvent.SHIM_ROD_DOWN:
                self.state.shim_rod = max(self.state.shim_rod - 1, 0)  # 1% decrement
                # Removed logging for performance
            
            elif event == ButtonEvent.REGULATING_ROD_UP:
                # Check safety rod priority: safety rod must be 100% before raising regulating
                if self.state.safety_rod < 100:
                    logger.warning("SAFETY ROD PRIORITY: Cannot raise regulating rod!")
                    logger.warning(f"   Safety rod must be at 100% first (currently: {self.state.safety_rod}%)")
                    logger.warning(f"   Correct sequence: Safety rod to 100% ÔåÆ Then shim/regulating rods")
                    
                    # Trigger buzzer warning
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    
                    return
                
                # Check interlock conditions
                if not self._check_interlock_internal():
                    logger.warning("INTERLOCK VIOLATION: Cannot raise regulating rod!")
                    logger.warning(f"   Pressure: {self.state.pressure:.2f} bar (need >= 140 bar)")
                    logger.warning(f"   Pumps: Primary={self.state.pump_primary_status}, "
                                 f"Secondary={self.state.pump_secondary_status}, "
                                 f"Tertiary={self.state.pump_tertiary_status} (need all = 2)")
                    
                    # Trigger interlock violation buzzer
                    if self.buzzer:
                        try:
                            self.buzzer.sound_interlock_warning(duration=1.5)
                        except Exception:
                            pass
                    
                    return
                self.state.regulating_rod = min(self.state.regulating_rod + 1, 100)  # 1% increment
                # Removed logging for performance
            
            elif event == ButtonEvent.REGULATING_ROD_DOWN:
                self.state.regulating_rod = max(self.state.regulating_rod - 1, 0)  # 1% decrement
                # Removed logging for performance
            
            elif event == ButtonEvent.EMERGENCY:
                self.state.emergency_active = True
                
                # Execute sequential SCRAM (non-blocking, smooth animation)
                logger.critical("EMERGENCY SCRAM ACTIVATED!")
                logger.critical("   Pumps remain ON for decay heat removal")
                self._execute_scram_sequence()
                
                # Trigger emergency buzzer (will beep for 5 seconds then stop)
                if self.buzzer:
                    logger.critical("   Triggering emergency buzzer...")
                    try:
                        self.buzzer.trigger_emergency_beep()
                        logger.critical("Emergency buzzer triggered")
                    except Exception as e:
                        logger.error(f"Buzzer trigger failed: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.warning("Buzzer not available")
                    
            elif event == ButtonEvent.REACTOR_RESET:
                # Stop auto simulation if running
                self.state.auto_sim_running = False
                self.state.simulation_mode = 'manual'
                self.state.emergency_active = False
                self.state.pressure = 0.0
                self.state.thermal_kw = 0.0
                self.state.pump_primary_status = 0
                self.state.pump_secondary_status = 0
                self.state.pump_tertiary_status = 0
                self.state.pump_primary_transition_start = 0.0
                self.state.pump_secondary_transition_start = 0.0
                self.state.pump_tertiary_transition_start = 0.0
                self.state.safety_rod = 0
                self.state.shim_rod = 0
                self.state.regulating_rod = 0
                self.state.humid_ct1_cmd = 0
                self.state.humid_ct2_cmd = 0
                self.state.humid_ct3_cmd = 0
                self.state.humid_ct4_cmd = 0
                self.state.interlock_satisfied = False
                
                # Reset OLED interpolators to zero (instant display update)
                if self.oled_manager:
                    self.oled_manager.reset_all_interpolators()
                
                logger.info("=" * 60)
                logger.info("SIMULATION RESET")
                logger.info("All parameters reset. Press START to begin.")
                logger.info("=" * 60)
            
            elif event == ButtonEvent.START_AUTO_SIMULATION:
                if self.state.auto_sim_running:
                    logger.warning("Auto simulation already running!")
                    return
                
                # Start auto simulation
                self.state.simulation_mode = 'auto'
                self.state.auto_sim_running = True
                logger.info("=" * 60)
                logger.info("AUTO SIMULATION MODE ACTIVATED")
                logger.info("Simulasi akan berjalan otomatis dengan kecepatan lambat")
                logger.info("untuk memudahkan pemahaman cara kerja PLTN")
                logger.info("=" * 60)
            
            # Log if event not recognized
            else:
                logger.warning(f"Unknown event: {event}")
    
    def button_event_processor_thread(self):
        """
        Process button events from queue
        This thread can safely use locks and do heavy work
        """
        try:
            logger.info("Button event processor thread STARTING...")
            
            # Verify queue exists
            if not hasattr(self, 'button_event_queue'):
                logger.error("button_event_queue not initialized!")
                return
            
            logger.info(f"Event queue initialized (max size: 100)")
            logger.info("Button event processor thread started - waiting for events...")
            
            loop_count = 0
            while self.state.running:
                try:
                    # Heartbeat every 60 seconds (reduced logging)
                    loop_count += 1
                    if loop_count >= 6000:  # 6000 * 0.01s = 60s
                        logger.info(f"Event processor alive - Queue size: {self.button_event_queue.qsize()}")
                        loop_count = 0
                    
                    # Wait for event (blocking, with timeout) - optimized to 10ms for fast response
                    event = self.button_event_queue.get(timeout=0.01)
                    
                    # Removed event processing log for performance (too verbose)
                    
                    # Process event with lock
                    self.process_button_event(event)
                    
                    # Trigger immediate ESP communication for fast response
                    self.esp_send_immediate.set()
                    
                    # Mark task done
                    self.button_event_queue.task_done()
                    
                except Empty:
                    # No events, continue loop
                    pass
                except Exception as e:
                    logger.error(f"Event processor error: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info("Button event processor thread stopped")
            
        except Exception as e:
            logger.critical(f"FATAL: Event processor thread crashed on startup: {e}")
            import traceback
            logger.critical(traceback.format_exc())
    
    # ============================================
    # Interlock Logic
    # ============================================
    
    def check_interlock(self) -> bool:
        """
        Check if interlock conditions are satisfied for rod movement
        PUBLIC version - acquires lock
        
        Returns:
            True if safe to move rods, False otherwise
        """
        with self.state_lock:
            return self._check_interlock_internal()
    
    def _check_interlock_internal(self) -> bool:
        """
        Check if interlock conditions are satisfied for rod movement
        INTERNAL version - assumes caller already holds state_lock
        
        INTERLOCK LOGIC v3.4 (UPDATED):
        Berdasarkan alur simulasi 8-phase PWR startup yang realistis:
        
        Phase 1-3: Reactor START ÔåÆ Raise pressure to operating level ÔåÆ Raise rods
        - Allow: Pressure >= 140 bar (operating pressure)
        - Allow: Reactor started
        - Allow: No emergency
        - Require: All three pumps in ON state (status == 2)
        - NO NEED: Turbine running (turbine belum jalan saat initial rod raise)
        
        Phase 4+: Normal operation
        - Same checks as above
        - Turbine akan auto-start dari ESP-BC ketika thermal > 50 MWth
        
        Returns:
            True if safe to move rods, False otherwise
        """
        
        # Check 2: Pressure >= 140 bar (operating pressure for rod withdrawal)
        # Pressure harus mencapai tekanan operasi penuh sebelum rod movement
        if self.state.pressure < 140.0:
            logger.debug(f"Interlock: Pressure too low ({self.state.pressure:.2f} bar < 140 bar)")
            return False
        
        # Check 3: No emergency active
        if self.state.emergency_active:
            logger.debug("Interlock: Emergency shutdown active")
            return False
        
        # Check 4: All pumps must be ON (status == 2)
        # Status codes: 0=OFF,1=STARTING,2=ON,3=SHUTTING_DOWN
        if self.state.pump_primary_status != 2:
            logger.debug(f"Interlock: Primary pump not ON (status={self.state.pump_primary_status})")
            return False
        if self.state.pump_secondary_status != 2:
            logger.debug(f"Interlock: Secondary pump not ON (status={self.state.pump_secondary_status})")
            return False
        if self.state.pump_tertiary_status != 2:
            logger.debug(f"Interlock: Tertiary pump not ON (status={self.state.pump_tertiary_status})")
            return False
        
        # All checks passed - safe to move rods
        return True
    
    def _check_pump_start_safe(self, pump_name: str) -> bool:
        """
        Check if it's safe to start pump (INTERNAL - assumes caller holds state_lock)
        
        Safety requirements:
        1. Pressure >= 40 bar (prevent pump cavitation)
        2. Correct startup sequence: Tertiary ÔåÆ Secondary ÔåÆ Primary
        
        Args:
            pump_name: Name of pump ("Tertiary", "Secondary", or "Primary")
        
        Returns:
            True if safe to start, False otherwise (with buzzer warning)
        """
        # ============================================
        # CHECK 1: Pressure must be >= 40 bar
        # ============================================
        if self.state.pressure < 40.0:
            logger.warning(f"PUMP START BLOCKED: {pump_name} pump")
            logger.warning(f"   Reason: Pressure too low!")
            logger.warning(f"   Current: {self.state.pressure:.2f} bar, Required: >= 40 bar")
            logger.warning(f"   Action: Raise pressure to 40 bar before starting pumps")
            
            # Trigger buzzer warning (procedure violation - 2 seconds)
            if self.buzzer:
                try:
                    self.buzzer.sound_procedure_warning(duration=2.0)
                except Exception:
                    pass  # Silent fail
            
            return False
        
        # ============================================
        # CHECK 2: Enforce correct pump sequence
        # Sequence: Tertiary ÔåÆ Secondary ÔåÆ Primary
        # ============================================
        if pump_name == "Secondary":
            # Secondary can only start if Tertiary is already ON
            if self.state.pump_tertiary_status != 2:
                logger.warning(f"PUMP SEQUENCE VIOLATION: Cannot start Secondary pump")
                logger.warning(f"   Reason: Tertiary pump must be ON first!")
                logger.warning(f"   Tertiary status: {self.state.pump_tertiary_status} (2=ON)")
                logger.warning(f"   Correct sequence: Tertiary ÔåÆ Secondary ÔåÆ Primary")
                
                # Trigger sequence violation buzzer (procedure warning)
                if self.buzzer:
                    try:
                        self.buzzer.sound_procedure_warning(duration=1.5)
                    except Exception:
                        pass
                
                return False
        
        elif pump_name == "Primary":
            # Primary can only start if BOTH Tertiary AND Secondary are ON
            if self.state.pump_tertiary_status != 2:
                logger.warning(f"PUMP SEQUENCE VIOLATION: Cannot start Primary pump")
                logger.warning(f"   Reason: Tertiary pump must be ON first!")
                logger.warning(f"   Tertiary status: {self.state.pump_tertiary_status} (2=ON)")
                logger.warning(f"   Correct sequence: Tertiary ÔåÆ Secondary ÔåÆ Primary")
                
                # Trigger buzzer
                if self.buzzer:
                    try:
                        self.buzzer.sound_procedure_warning(duration=1.5)
                    except Exception:
                        pass
                
                return False
            
            if self.state.pump_secondary_status != 2:
                logger.warning(f"PUMP SEQUENCE VIOLATION: Cannot start Primary pump")
                logger.warning(f"   Reason: Secondary pump must be ON first!")
                logger.warning(f"   Secondary status: {self.state.pump_secondary_status} (2=ON)")
                logger.warning(f"   Correct sequence: Tertiary ÔåÆ Secondary ÔåÆ Primary")
                
                # Trigger buzzer
                if self.buzzer:
                    try:
                        self.buzzer.sound_procedure_warning(duration=1.5)
                    except Exception:
                        pass
                
                return False
        
        # Tertiary pump has no prerequisites (can start anytime if P >= 40)
        # All checks passed
        logger.info(f"Pump start authorized: {pump_name}")
        return True
    
    # ============================================
    # Control Logic Thread
    # ============================================
        
        # Initialize humidifier controller
        try:
            self.humidifier = HumidifierController()
            logger.info("Ô£ô Humidifier controller initialized")
        except Exception as e:
            logger.warning(f"Ô£ù Humidifier failed: {e}")
            self.humidifier = None
        
        # Initialize OLED manager
        try:
            self.mux_manager = DualMultiplexerManager()
            from raspi_oled_manager import OLEDManager
            self.oled_manager = OLEDManager(self.mux_manager)
            logger.info("Ô£ô OLED manager initialized")
        except Exception as e:
            logger.warning(f"Ô£ù OLED manager failed: {e}")
            self.mux_manager = None
            self.oled_manager = None
        
        # Initialize health monitor
        try:
            self.health_monitor = SystemHealthMonitor()
            logger.info("Ô£ô Health monitor initialized")
        except Exception as e:
            logger.warning(f"Ô£ù Health monitor failed: {e}")
            self.health_monitor = None
    
    def _init_modules(self):
        """Initialize refactored modules."""
        logger.info("Phase 2: Module initialization...")
        
        # Interlock validator with buzzer callbacks
        def on_interlock_violation(reason):
            if self.buzzer:
                try:
                    self.buzzer.sound_interlock_warning(duration=1.5)
                except Exception:
                    pass
        
        def on_procedure_violation(reason):
            if self.buzzer:
                try:
                    self.buzzer.sound_procedure_warning(duration=2.0)
                except Exception:
                    pass
        
        self.interlock_validator = InterlockValidator(
            on_interlock_violation=on_interlock_violation,
            on_procedure_violation=on_procedure_violation
        )
        logger.info("Ô£ô InterlockValidator initialized")
        
        # SCRAM sequence
        self.scram_sequence = SCRAMSequence(
            state_manager=self.state_manager,
            esp_trigger=self.esp_send_immediate.set
        )
        logger.info("Ô£ô SCRAMSequence initialized")
        
        # Auto simulator
        self.auto_simulator = AutoSimulator(
            state_manager=self.state_manager,
            esp_trigger=self.esp_send_immediate.set
        )
        logger.info("Ô£ô AutoSimulator initialized")
        
        # LOFA Sequence
        from sequences.lofa_sequence import LOFASequence
        self.lofa_sequence = LOFASequence(self.state_manager)
        logger.info("✓ LOFASequence initialized")
        
        # Pump controller
        self.pump_controller = PumpController(transition_time=3.0)
        logger.info("✓ PumpController initialized")
        
        # Event processor
        self.event_processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.button_event_queue,
            interlock_validator=self.interlock_validator,
            scram_sequence=self.scram_sequence,
            auto_simulator=self.auto_simulator,
            lofa_sequence=self.lofa_sequence,
            buzzer=self.buzzer
        )
        logger.info("Ô£ô EventProcessor initialized")
        
        # ESP protocol (uses uart_master directly for now)
        # Note: Full ESPProtocol integration would replace esp_communication_thread
        logger.info("Ô£ô ESP communication ready")
    
    def _setup_button_callbacks(self):
        """Setup button callbacks to queue events."""
        if not self.button_manager:
            return
        
        # Map buttons to event queue
        button_event_map = {
            ButtonPin.PUMP_PRIMARY_ON: ButtonEvent.PUMP_PRIMARY_ON,
            ButtonPin.PUMP_PRIMARY_OFF: ButtonEvent.PUMP_PRIMARY_OFF,
            ButtonPin.PUMP_SECONDARY_ON: ButtonEvent.PUMP_SECONDARY_ON,
            ButtonPin.PUMP_SECONDARY_OFF: ButtonEvent.PUMP_SECONDARY_OFF,
            ButtonPin.PUMP_TERTIARY_ON: ButtonEvent.PUMP_TERTIARY_ON,
            ButtonPin.PUMP_TERTIARY_OFF: ButtonEvent.PUMP_TERTIARY_OFF,
            ButtonPin.EMERGENCY: ButtonEvent.EMERGENCY,
            ButtonPin.REACTOR_RESET: ButtonEvent.REACTOR_RESET,
            ButtonPin.START_AUTO_SIMULATION: ButtonEvent.START_AUTO_SIMULATION,
        }
        
        for pin, event in button_event_map.items():
            def make_callback(evt):
                return lambda: self.button_event_queue.put(evt)
            self.button_manager.register_callback(pin, make_callback(event))
        
        logger.info("Ô£ô Button callbacks registered")
    
    # ============================================
    # Thread Functions
    # ============================================
    
    def touch_input_polling_thread(self):
        """Thread for polling touch inputs from /tmp/pltn_input.json (50ms cycle)."""
        logger.info("Touch input polling thread started")
        
        # Configure Touch affinity natively via psutil if possible
        try:
            import psutil
            if hasattr(os, 'gettid'):
                p = psutil.Process(os.gettid())
                if hasattr(p, 'cpu_affinity'): p.cpu_affinity([1])
        except Exception:
            pass
        
        touch_input_file = Path("/tmp/pltn_input.json")
        last_processed_timestamp = time.time()  # Ignore old events on startup
        
        while self.state_manager.running:
            try:
                if touch_input_file.exists():
                    try:
                        with open(touch_input_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            
                        file_timestamp = data.get("timestamp", 0.0)
                        if file_timestamp > last_processed_timestamp:
                            events = data.get("events", [])
                            newest_timestamp = last_processed_timestamp
                            
                            for evt in events:
                                evt_ts = evt.get("timestamp", 0.0)
                                if evt_ts <= last_processed_timestamp:
                                    continue
                                    
                                if evt_ts > newest_timestamp:
                                    newest_timestamp = evt_ts
                                    
                                evt_type = evt.get("type")
                                target = evt.get("target")
                                rod = evt.get("rod")
                                direction = evt.get("direction")
                                
                                button_event = None
                                
                                if evt_type == "PUMP_ON":
                                    if target == "PRIMARY": button_event = ButtonEvent.PUMP_PRIMARY_ON
                                    elif target == "SECONDARY": button_event = ButtonEvent.PUMP_SECONDARY_ON
                                    elif target == "TERTIARY": button_event = ButtonEvent.PUMP_TERTIARY_ON
                                elif evt_type == "PUMP_OFF":
                                    if target == "PRIMARY": button_event = ButtonEvent.PUMP_PRIMARY_OFF
                                    elif target == "SECONDARY": button_event = ButtonEvent.PUMP_SECONDARY_OFF
                                    elif target == "TERTIARY": button_event = ButtonEvent.PUMP_TERTIARY_OFF
                                elif evt_type == "ROD_MOVE":
                                    if rod == "SAFETY" and direction == "UP": button_event = ButtonEvent.SAFETY_ROD_UP
                                    elif rod == "SAFETY" and direction == "DOWN": button_event = ButtonEvent.SAFETY_ROD_DOWN
                                    elif rod == "SHIM" and direction == "UP": button_event = ButtonEvent.SHIM_ROD_UP
                                    elif rod == "SHIM" and direction == "DOWN": button_event = ButtonEvent.SHIM_ROD_DOWN
                                    elif rod == "REGULATING" and direction == "UP": button_event = ButtonEvent.REGULATING_ROD_UP
                                    elif rod == "REGULATING" and direction == "DOWN": button_event = ButtonEvent.REGULATING_ROD_DOWN
                                elif evt_type == "PRESSURE":
                                    if direction == "UP": button_event = ButtonEvent.PRESSURE_UP
                                    elif direction == "DOWN": button_event = ButtonEvent.PRESSURE_DOWN
                                elif evt_type == "START_AUTO":
                                    button_event = ButtonEvent.START_AUTO_SIMULATION
                                elif evt_type == "RESET":
                                    button_event = ButtonEvent.REACTOR_RESET
                                elif evt_type == "EMERGENCY":
                                    button_event = ButtonEvent.EMERGENCY
                                elif evt_type == "LOFA_SIMULATE":
                                    if target == "PRIMARY": button_event = ButtonEvent.LOFA_SIMULATE_PRIMARY
                                    elif target == "SECONDARY": button_event = ButtonEvent.LOFA_SIMULATE_SECONDARY
                                    elif target == "TERTIARY": button_event = ButtonEvent.LOFA_SIMULATE_TERTIARY
                                elif evt_type == "LOFA_CANCEL":
                                    button_event = ButtonEvent.REACTOR_RESET
                                    
                                if button_event is not None:
                                    self.button_event_queue.put(button_event)
                                    # --- Latency Measurement ---
                                    latency_ms = (time.time() - evt_ts) * 1000.0
                                    try:
                                        with open("/tmp/latency_log.txt", "a") as f:
                                            f.write(f"{evt_ts:.3f},{time.time():.3f},{latency_ms:.2f},{button_event.name}\n")
                                    except Exception:
                                        pass
                                    logger.info(f"Touch event received from HMI: {button_event.name} (Latency: {latency_ms:.2f}ms)")
                                    
                            last_processed_timestamp = newest_timestamp
                            
                    except json.JSONDecodeError:
                        pass # Ignore partially written file
            except Exception as e:
                logger.debug(f"Touch polling error: {e}")
                
            time.sleep(0.05)  # 20 FPS is enough for touch polling
            
        logger.info("Touch input polling thread stopped")
    
    def control_logic_thread(self):
        """Thread for control logic (50ms cycle)."""
        logger.info("Control logic thread started")
        
        # Configure Control Logic affinity natively via psutil if possible
        try:
            import psutil
            if hasattr(os, 'gettid'):
                p = psutil.Process(os.gettid())
                if hasattr(p, 'cpu_affinity'): p.cpu_affinity([1])
        except Exception:
            pass
        
        while self.state_manager.running:
            try:
                with self.state_manager as state:
                    # Update interlock status
                    satisfied, _ = self.interlock_validator.get_interlock_status(state)
                    state.interlock_satisfied = satisfied
                    
                    # Update humidifier commands
                    if self.humidifier:
                        sg_on, ct1, ct2, ct3, ct4 = self.humidifier.update(
                            state.shim_rod,
                            state.regulating_rod,
                            state.thermal_kw
                        )
                        state.humid_ct1_cmd = 1 if ct1 else 0
                        state.humid_ct2_cmd = 1 if ct2 else 0
                        state.humid_ct3_cmd = 1 if ct3 else 0
                        state.humid_ct4_cmd = 1 if ct4 else 0
                    
                    # Update pump transition states
                    self.pump_controller.update(state)
                                
                    # Update LOFA thermodynamics
                    if hasattr(self, 'lofa_simulator'):
                        self.lofa_simulator.update(state)

                    # Manage Video Player
                    if state.auto_sim_running or state.simulation_mode == 'auto':
                        if not self.video_player.is_playing():
                            self.video_player.play(loop=True)
                    else:
                        if self.video_player.is_playing():
                            self.video_player.stop()

                    # Primary Physics Simulation (runs every 10ms)
                    if True:
                        # Shim rod has 80% worth, Regulating rod has 20% worth
                        effective_rod = (state.shim_rod * 0.8) + (state.regulating_rod * 0.2)
                        
                        if effective_rod > 10.0:
                            reactor_thermal_capacity = (effective_rod**2) * 90.0
                            reactor_thermal_capacity = min(reactor_thermal_capacity, 900000.0)
                        else:
                            reactor_thermal_capacity = 0.0
                            
                        # Turbine starts spinning when thermal power exceeds threshold (e.g. 50000 kW)
                        # Speed is proportional to the power generated
                        if not state.emergency_active:
                            if reactor_thermal_capacity > 50000.0:
                                # Map thermal capacity (50000 - 900000) to target speed (10 - 100%)
                                # We start at 10% minimum so it visually spins when just crossing threshold
                                target_speed = 10.0 + ((reactor_thermal_capacity - 50000.0) / 850000.0) * 90.0
                                target_speed = min(max(target_speed, 10.0), 100.0)
                                
                                # Smooth acceleration / deceleration
                                if state.turbine_speed < target_speed:
                                    state.turbine_speed = min(state.turbine_speed + 0.2, target_speed)
                                else:
                                    state.turbine_speed = max(state.turbine_speed - 0.5, target_speed)
                            else:
                                state.turbine_speed = max(state.turbine_speed - 0.5, 0.0)
                        else:
                            # Emergency: stop turbine quickly
                            state.turbine_speed = max(state.turbine_speed - 2.0, 0.0)
                                
                        state.thermal_kw = min(reactor_thermal_capacity * 0.34 * (state.turbine_speed / 100.0), 300000.0)
                        
                    # Update hardware actuators
                    self.actuator_manager.update_actuators(state)
                
                time.sleep(0.05)  # 20Hz logic cycle (down from 100Hz) to save huge CPU
                
            except Exception as e:
                logger.error(f"Control logic error: {e}")
                time.sleep(0.1)
        
        logger.info("Control logic thread stopped")
    
    # ============================================
    # Background Threads (Moved to modules)
    # ============================================
    
    # ============================================
    # Main Loop
    # ============================================
    
    def run(self):
        """Main control loop."""
        logger.info("Starting PLTN Controller (Refactored)...")
        
        # Start event processor
        self.event_processor.start()
        
        # Start all threads
        threads = [
            threading.Thread(target=self.touch_input_polling_thread, daemon=True, name="TouchInputThread"),
            threading.Thread(target=self.control_logic_thread, daemon=True, name="ControlThread")
        ]
        
        # Start state exporter natively
        self.state_exporter.start()
        
        for t in threads:
            t.start()
            logger.info(f"Thread started: {t.name}")
        
        try:
            while self.state_manager.running:
                time.sleep(1.0)
                
                # Print status
                with self.state_manager as state:
                    logger.info(f"Status: P={state.pressure:.2f}bar, "
                              f"Rods=[{state.safety_rod},{state.shim_rod},{state.regulating_rod}]%, "
                              f"Thermal={state.thermal_kw:.1f}kW")
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown system gracefully."""
        logger.info("=" * 60)
        logger.info("Shutting down PLTN Panel Controller...")
        logger.info("=" * 60)
        
        self.state_manager.running = False
        time.sleep(0.5)
        
        # Stop event processor
        self.event_processor.stop()
        
        # Cleanup hardware
        if hasattr(self, 'buzzer') and self.buzzer:
            self.buzzer.cleanup()
        
        if hasattr(self, "actuator_manager") and self.actuator_manager:
            self.actuator_manager.cleanup()
        
        logger.info("=" * 60)
        logger.info("PLTN Panel Controller shutdown complete")
        logger.info("=" * 60)


# ============================================
# Main Entry Point
# ============================================

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    logger.info("Signal received, shutting down...")
    sys.exit(0)


def main():
    """Main entry point."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Optimize CPU for this hardware node (Core 0,1 + High Priority)
    CpuManager.setup_hardware_node()
    
    try:
        controller = PLTNPanelController()
        controller.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()