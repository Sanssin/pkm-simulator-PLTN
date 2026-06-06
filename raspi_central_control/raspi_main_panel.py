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
from typing import Optional
from queue import Queue

# Import our modules
import raspi_config as config
from raspi_tca9548a import DualMultiplexerManager
from raspi_uart_master import UARTMaster
from raspi_humidifier_control import HumidifierController
from raspi_buzzer_alarm import BuzzerAlarm
from raspi_system_health import SystemHealthMonitor
import cpu_manager

# Import refactored modules
from controllers import StateManager, PanelState, InterlockValidator, EventProcessor
from controllers.interlock_validator import PUMP_ON
from sequences import SCRAMSequence, AutoSimulator
from communication import ESPProtocol
from io_handlers import ButtonIOHandler, ButtonEvent

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
        
        # ESP communication trigger
        self.esp_send_immediate = threading.Event()
        
        # State export file for video display
        self.state_export_file = Path("/tmp/pltn_state.json")
        
        # Initialize hardware components
        self._init_hardware()
        
        # Initialize refactored modules
        self._init_modules()
        
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
            logger.info("✓ UART master initialized")
        except Exception as e:
            logger.warning(f"✗ UART master failed: {e}")
            self.uart_master = None
            self.uart_lock = threading.Lock()
        
        # Initialize buzzer
        try:
            self.buzzer = BuzzerAlarm(pin=config.BUZZER_PIN if hasattr(config, 'BUZZER_PIN') else 22)
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
        
        # Initialize OLED manager
        try:
            self.mux_manager = DualMultiplexerManager()
            from raspi_oled_manager import OLEDManager
            self.oled_manager = OLEDManager(self.mux_manager)
            logger.info("✓ OLED manager initialized")
        except Exception as e:
            logger.warning(f"✗ OLED manager failed: {e}")
            self.mux_manager = None
            self.oled_manager = None
        
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
            state_manager=self.state_manager,
            esp_trigger=self.esp_send_immediate.set
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
            state_manager=self.state_manager,
            esp_trigger=self.esp_send_immediate.set
        )
        logger.info("✓ AutoSimulator initialized")
        
        # Event processor
        self.event_processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.button_event_queue,
            interlock_validator=self.interlock_validator,
            scram_sequence=self.scram_sequence,
            auto_simulator=self.auto_simulator,
            buzzer=self.buzzer,
            esp_trigger=self.esp_send_immediate.set,
            oled_reset=self.oled_manager.reset_all_interpolators if self.oled_manager else None
        )
        logger.info("✓ EventProcessor initialized")
        
        # ESP protocol (uses uart_master directly for now)
        # Note: Full ESPProtocol integration would replace esp_communication_thread
        logger.info("✓ ESP communication ready")
    
    # ============================================
    # Thread Functions
    # ============================================
    
    def touch_input_polling_thread(self):
        """Thread for polling touch inputs from /tmp/pltn_input.json (50ms cycle)."""
        logger.info("Touch input polling thread started")
        
        # CPU-012: Configure Touch affinity (Core 1)
        if hasattr(os, 'gettid'):
            cpu_manager.set_cpu_affinity(os.gettid(), [1])
        
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
                                    
                                if button_event is not None:
                                    self.button_event_queue.put(button_event)
                                    logger.info(f"Touch event received from HMI: {button_event.name}")
                                    
                            last_processed_timestamp = newest_timestamp
                            
                    except json.JSONDecodeError:
                        pass # Ignore partially written file
            except Exception as e:
                logger.debug(f"Touch polling error: {e}")
                
            time.sleep(0.05)
            
        logger.info("Touch input polling thread stopped")
    
    def control_logic_thread(self):
        """Thread for control logic (50ms cycle)."""
        logger.info("Control logic thread started")
        
        # Configure Controller affinity (Core 1)
        if hasattr(os, 'gettid'):
            cpu_manager.set_cpu_affinity(os.gettid(), [1])
        
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
                    current_time = time.time()
                    pump_transition_time = 3.0
                    
                    for pump_name in ['primary', 'secondary', 'tertiary']:
                        status_attr = f'pump_{pump_name}_status'
                        transition_attr = f'pump_{pump_name}_transition_start'
                        
                        status = getattr(state, status_attr)
                        transition_start = getattr(state, transition_attr)
                        
                        if status == 1:  # STARTING
                            if transition_start == 0:
                                setattr(state, transition_attr, current_time)
                            elif current_time - transition_start >= pump_transition_time:
                                setattr(state, status_attr, PUMP_ON)
                                setattr(state, transition_attr, 0)
                        elif status == 3:  # SHUTTING_DOWN
                            if transition_start == 0:
                                setattr(state, transition_attr, current_time)
                            elif current_time - transition_start >= pump_transition_time:
                                setattr(state, status_attr, 0)  # OFF
                                setattr(state, transition_attr, 0)
                                
                    # Update LOFA thermodynamics
                    if hasattr(self, 'lofa_simulator'):
                        self.lofa_simulator.update(state)
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"Control logic error: {e}")
                time.sleep(0.1)
        
        logger.info("Control logic thread stopped")
    
    def esp_communication_thread(self):
        """Thread for ESP communication (50ms cycle)."""
        logger.info("ESP communication thread started")
        
        # CPU-010: Configure Controller/ESP affinity (Core 3 - Highest Priority)
        if hasattr(os, 'gettid'):
            tid = os.gettid()
            cpu_manager.set_cpu_affinity(tid, [3])
            cpu_manager.set_realtime_priority(tid)
        
        if not self.uart_master:
            logger.warning("UART master not available, exiting ESP thread")
            return
        
        last_esp_e_update = 0
        ESP_E_INTERVAL = 0.2
        
        while self.state_manager.running:
            try:
                triggered = self.esp_send_immediate.wait(timeout=0.05)
                if triggered:
                    self.esp_send_immediate.clear()
                
                with self.uart_lock:
                    with self.state_manager as state:
                        if self.uart_master.esp_bc_connected:
                            success = self.uart_master.update_esp_bc(
                                state.safety_rod,
                                state.shim_rod,
                                state.regulating_rod,
                                state.pump_primary_status,
                                state.pump_secondary_status,
                                state.pump_tertiary_status,
                                state.humid_ct1_cmd,
                                state.humid_ct2_cmd,
                                state.humid_ct3_cmd,
                                state.humid_ct4_cmd
                            )
                            
                            if success:
                                esp_bc_data = self.uart_master.get_esp_bc_data()
                                state.thermal_kw = esp_bc_data.kw_thermal
                                state.turbine_speed = esp_bc_data.turbine_speed
                
                # ESP-E update (throttled)
                current_time = time.time()
                if current_time - last_esp_e_update >= ESP_E_INTERVAL:
                    with self.uart_lock:
                        with self.state_manager as state:
                            display_power = state.thermal_kw if state.turbine_speed > 50 else 0.0
                            self.uart_master.update_esp_e(
                                thermal_power_kw=display_power,
                                pump_primary_status=state.pump_primary_status,
                                pump_secondary_status=state.pump_secondary_status,
                                pump_tertiary_status=state.pump_tertiary_status
                            )
                    last_esp_e_update = current_time
                
            except Exception as e:
                logger.error(f"ESP communication error: {e}")
                time.sleep(0.1)
        
        logger.info("ESP communication thread stopped")
    
    def oled_update_thread(self):
        """Thread for OLED display updates."""
        logger.info("OLED update thread started")
        
        # CPU-011: Configure Video/OLED affinity (Core 2)
        if hasattr(os, 'gettid'):
            cpu_manager.set_cpu_affinity(os.gettid(), [2])
        
        if not self.oled_manager:
            logger.warning("OLED manager not available")
            return
        
        first_update = True
        
        while self.state_manager.running:
            try:
                with self.state_manager as state:
                    if first_update:
                        self.oled_manager.sync_interpolators_to_state(state)
                        first_update = False
                    else:
                        self.oled_manager.update_all(state)
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"OLED update error: {e}")
                time.sleep(0.5)
        
        logger.info("OLED update thread stopped")
    
    def state_export_thread(self):
        """Export state to JSON for video display."""
        logger.info("State export thread started")
        
        # CPU-013: Configure System IO affinity (Core 0)
        if hasattr(os, 'gettid'):
            cpu_manager.set_cpu_affinity(os.gettid(), [0])
        
        while self.state_manager.running:
            try:
                with self.state_manager as state:
                    state_dict = {
                        "timestamp": time.time(),
                        "mode": state.simulation_mode,
                        "auto_running": state.auto_sim_running,
                        "auto_phase": state.auto_sim_phase,
                        "pressure": float(state.pressure),
                        "safety_rod": int(state.safety_rod),
                        "shim_rod": int(state.shim_rod),
                        "regulating_rod": int(state.regulating_rod),
                        "pump_primary": int(state.pump_primary_status),
                        "pump_secondary": int(state.pump_secondary_status),
                        "pump_tertiary": int(state.pump_tertiary_status),
                        "thermal_kw": float(state.thermal_kw),
                        "temperature_core": float(state.temperature_core),
                        "temperature_coolant": float(state.temperature_coolant),
                        "turbine_speed": float(state.turbine_speed),
                        "emergency": bool(state.emergency_active)
                    }
                
                temp_file = self.state_export_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(state_dict, f, indent=2)
                temp_file.replace(self.state_export_file)
                
            except Exception as e:
                logger.error(f"State export error: {e}")
            
            time.sleep(0.1)
        
        logger.info("State export thread stopped")
    
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
            threading.Thread(target=self.control_logic_thread, daemon=True, name="ControlThread"),
            threading.Thread(target=self.esp_communication_thread, daemon=True, name="ESPCommThread"),
            threading.Thread(target=self.oled_update_thread, daemon=True, name="OLEDThread"),
            threading.Thread(target=self.state_export_thread, daemon=True, name="StateExportThread"),
        ]
        
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
        if self.buzzer:
            self.buzzer.cleanup()
        
        if self.uart_master:
            self.uart_master.update_esp_bc(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            self.uart_master.update_esp_e(0.0)
            self.uart_master.close()
        
        if self.mux_manager:
            self.mux_manager.close()
        
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
