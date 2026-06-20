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
from raspi_system_health import SystemHealthMonitor

# Import refactored modules
from controllers.state_manager import StateManager
from controllers.rod_controller import RodController
from controllers.pump_controller import PumpController
from controllers.interlock_validator import InterlockValidator
from controllers.physics_engine import PhysicsEngine
from controllers.event_processor import EventProcessor
from controllers.actuator_manager import ActuatorManager
from io_handlers.state_exporter import StateExporter
from io_handlers.ipc_listener import IPCListenerManager
from io_handlers.button_handler import ButtonEvent
from sequences.scram_sequence import SCRAMSequence
from sequences.auto_simulation import AutoSimulator
from pltn_video_display.video_player import VideoPlayer
from cpu_manager import set_realtime_priority


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
        
        # Buzzer removed as per user request
        
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
        
        # Interlock validator with callbacks
        def on_interlock_violation(reason):
            pass
        
        def on_procedure_violation(reason):
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
        
        # Physics Engine
        self.physics_engine = PhysicsEngine(trigger_scram_callback=self.trigger_emergency_scram)
        logger.info("✓ PhysicsEngine initialized")
        
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
            interlock_validator=self.interlock_validator,
            scram_sequence=self.scram_sequence,
            auto_simulator=self.auto_simulator,
            lofa_sequence=self.lofa_sequence,
            cinematic_lofa_sequence=self.cinematic_lofa_sequence
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
        
        EVENT_MAPPING = {
            ("PUMP_ON", "PRIMARY", None, None): ButtonEvent.PUMP_PRIMARY_ON,
            ("PUMP_ON", "SECONDARY", None, None): ButtonEvent.PUMP_SECONDARY_ON,
            ("PUMP_ON", "TERTIARY", None, None): ButtonEvent.PUMP_TERTIARY_ON,
            ("PUMP_OFF", "PRIMARY", None, None): ButtonEvent.PUMP_PRIMARY_OFF,
            ("PUMP_OFF", "SECONDARY", None, None): ButtonEvent.PUMP_SECONDARY_OFF,
            ("PUMP_OFF", "TERTIARY", None, None): ButtonEvent.PUMP_TERTIARY_OFF,
            ("ROD_MOVE", None, "SAFETY", "UP"): ButtonEvent.SAFETY_ROD_UP,
            ("ROD_MOVE", None, "SAFETY", "DOWN"): ButtonEvent.SAFETY_ROD_DOWN,
            ("ROD_MOVE", None, "SHIM", "UP"): ButtonEvent.SHIM_ROD_UP,
            ("ROD_MOVE", None, "SHIM", "DOWN"): ButtonEvent.SHIM_ROD_DOWN,
            ("ROD_MOVE", None, "REGULATING", "UP"): ButtonEvent.REGULATING_ROD_UP,
            ("ROD_MOVE", None, "REGULATING", "DOWN"): ButtonEvent.REGULATING_ROD_DOWN,
            ("PRESSURE", None, None, "UP"): ButtonEvent.PRESSURE_UP,
            ("PRESSURE", None, None, "DOWN"): ButtonEvent.PRESSURE_DOWN,
            ("START_AUTO", None, None, None): ButtonEvent.START_AUTO_SIMULATION,
            ("START_CINEMATIC_LOFA", None, None, None): ButtonEvent.START_CINEMATIC_LOFA,
            ("RESET", None, None, None): ButtonEvent.REACTOR_RESET,
            ("EMERGENCY", None, None, None): ButtonEvent.EMERGENCY,
            ("LOFA_SIMULATE", "PRIMARY", None, None): ButtonEvent.LOFA_SIMULATE_PRIMARY,
            ("LOFA_SIMULATE", "SECONDARY", None, None): ButtonEvent.LOFA_SIMULATE_SECONDARY,
            ("LOFA_SIMULATE", "TERTIARY", None, None): ButtonEvent.LOFA_SIMULATE_TERTIARY,
            ("LOFA_CANCEL", None, None, None): ButtonEvent.REACTOR_RESET,
        }
        
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
                                
                                button_event = EVENT_MAPPING.get((evt_type, target, rod, direction))
                                    
                                if button_event is not None:
                                    self.event_processor.process_event(button_event)
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
                                
                    # Update Unified Physics (Thermodynamics, Capacities, Turbine, LOFA)
                    if hasattr(self, 'physics_engine'):
                        self.physics_engine.update(state)

                    # Manage Video Player
                    # PENTING: cek cinematic_lofa DULU sebelum auto_sim_running
                    # agar video LOFA tidak tertimpa oleh video tutorial
                    if state.simulation_mode == 'cinematic_lofa':
                        # Gunakan versi H.264 agar bisa hardware decode (v4l2m2m) dengan mulus
                        video_path = "/home/pkm/video_pltn/simulasi_lofa_720.mp4"
                        import os
                        if not os.path.exists(video_path):
                            # Fallback ke versi asli jika file baru tidak ditemukan
                            video_path = "/home/pkm/video_pltn/simulasi_lofa.mp4"
                            logger.warning(f"[VideoPlayer] {video_path} tidak ditemukan, menggunakan versi asli")
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

                    # Physics are now fully handled by PhysicsEngine above.
                    # Actuators will read the updated state (thermal_kw, turbine_speed, etc.) directly.
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
        
        # Cleanup hardware
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
    set_realtime_priority()
    
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
