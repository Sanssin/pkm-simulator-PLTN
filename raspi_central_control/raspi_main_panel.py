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
import os
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
from raspi_humidifier_control import HumidifierController
from raspi_buzzer_alarm import BuzzerAlarm
from raspi_system_health import SystemHealthMonitor

# Import refactored modules
from controllers.cpu_manager import CpuManager
from controllers import StateManager, PanelState, InterlockValidator, EventProcessor, PumpController
from controllers.interlock_validator import PUMP_ON
from sequences import SCRAMSequence, AutoSimulator
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


class PLTNPanelController:
    """
    Main PLTN Panel Controller Class (Refactored)
    
    Orchestrates all modules:
    - StateManager: Thread-safe state management
    - InterlockValidator: Safety interlock checks
    - EventProcessor: Button event handling
    - SCRAMSequence: Emergency shutdown
    - AutoSimulator: Automated startup
    - ButtonIOHandler: Button input handling
    """
    
    def __init__(self):
        """Initialize PLTN Panel Controller"""
        logger.info("=" * 60)
        logger.info("PLTN Simulator v5.0 - Refactored Architecture (ESP Removed)")
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
        
        # Initialize video player (Thread 9 concept, non-blocking)

        
        logger.info("=" * 60)
        logger.info("PLTN Panel Controller initialized successfully")
        logger.info("=" * 60)
    
    def _init_hardware(self):
        """Initialize hardware components with graceful degradation."""
        logger.info("Phase 1: Core hardware initialization...")
        
        # Initialize Unified Actuator Manager
        self.actuator_manager = ActuatorManager()
        logger.info("✓ Actuator Manager initialized")
        
        # Initialize buzzer
        try:
            self.buzzer = BuzzerAlarm(buzzer_pin=config.BUZZER_PIN if hasattr(config, 'BUZZER_PIN') else 22)
            logger.info("✓ Buzzer alarm initialized")
        except Exception as e:
            logger.warning(f"✗ Buzzer failed: {e}")
            self.buzzer = None
        
        # Initialize humidifier controller
        try:
            self.humidifier = HumidifierController()
            logger.info("✓ Humidifier controller initialized")
        except Exception as e:
            logger.warning(f"✗ Humidifier failed: {e}")
            self.humidifier = None
        
        # Initialize health monitor
        try:
            self.health_monitor = SystemHealthMonitor()
            logger.info("✓ Health monitor initialized")
        except Exception as e:
            logger.warning(f"✗ Health monitor failed: {e}")
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
        logger.info("✓ InterlockValidator initialized")
        
        # SCRAM sequence
        self.scram_sequence = SCRAMSequence(
            state_manager=self.state_manager
        )
        logger.info("✓ SCRAMSequence initialized")
        
        # LOFA Simulator
        from controllers.lofa_simulator import LOFASimulator
        self.lofa_simulator = LOFASimulator(
            max_core_temp=self.interlock_validator.MAX_CORE_TEMPERATURE_LOFA,
            trigger_scram_callback=self.scram_sequence.execute
        )
        logger.info("✓ LOFASimulator initialized")
        
        # Auto simulator
        self.auto_simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        logger.info("✓ AutoSimulator initialized")
        
        # LOFA Sequence
        from sequences.lofa_sequence import LOFASequence
        self.lofa_sequence = LOFASequence(self.state_manager)
        logger.info("✓ LOFASequence initialized")
        
        # Cinematic LOFA Sequence
        from sequences.cinematic_lofa_sequence import CinematicLOFASequence
        self.cinematic_lofa_sequence = CinematicLOFASequence(self.state_manager)
        logger.info("✓ CinematicLOFASequence initialized")
        
        # Pump controller
        self.pump_controller = PumpController(startup_time=7.0, shutdown_time=7.0)
        logger.info("✓ PumpController initialized")
        
        # Event processor
        self.event_processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.button_event_queue,
            interlock_validator=self.interlock_validator,
            scram_sequence=self.scram_sequence,
            auto_simulator=self.auto_simulator,
            lofa_sequence=self.lofa_sequence,
            cinematic_lofa_sequence=self.cinematic_lofa_sequence,
            buzzer=self.buzzer
        )
        logger.info("✓ EventProcessor initialized")
        
        # (ESP communication removed)
    
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
                                elif evt_type == "START_CINEMATIC_LOFA":
                                    button_event = ButtonEvent.START_CINEMATIC_LOFA
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
                    # PENTING: cek cinematic_lofa DULU sebelum auto_sim_running
                    # agar video LOFA tidak tertimpa oleh video tutorial
                    if state.simulation_mode == 'cinematic_lofa':
                        # Gunakan versi H.264 agar bisa hardware decode (v4l2m2m) dengan mulus
                        video_path = "/home/pkm/video_pltn/simulasi_lofa_h264.mp4"
                        import os
                        if not os.path.exists(video_path):
                            # Fallback ke versi asli jika h264 dihapus
                            video_path = "/home/pkm/video_pltn/simulasi_lofa.mp4"
                            logger.warning("[VideoPlayer] simulasi_lofa_h264.mp4 tidak ditemukan, menggunakan versi asli")
                        if not self.video_player.is_playing() or self.video_player.current_video != video_path:
                            # Hapus extra_mpv_args agar menggunakan default dmabuf-wayland hwdec
                            self.video_player.play(filename=video_path, loop=False)
                    elif state.auto_sim_running or state.simulation_mode == 'auto':
                        video_path = "/home/pkm/video_pltn/pwr_tutorial_ver.mp4"
                        if not self.video_player.is_playing() or self.video_player.current_video != video_path:
                            self.video_player.play(filename=video_path, loop=True)
                    else:
                        if hasattr(self, 'video_player') and self.video_player.is_playing():
                            self.video_player.stop()

                    # Primary Physics Simulation (hanya berjalan saat mode manual, agar tidak bertabrakan dengan animasi auto/lofa)
                    if state.simulation_mode not in ('auto', 'cinematic_lofa') and not getattr(state, 'auto_sim_running', False):
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
                    logger.info(f"Status: P={state.pressure:.1f}bar, "
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
