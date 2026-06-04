"""
ESPProtocol - ESP communication handling for PLTN Panel Simulator.

This module handles:
- State encoding for ESP-BC and ESP-E
- Communication thread management
- ESP connection status monitoring
"""

import time
import logging
import threading
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from controllers.state_manager import StateManager
    from raspi_uart_master import UARTMaster

logger = logging.getLogger(__name__)


class ESPProtocol:
    """
    Manages communication with ESP32 devices.
    
    Handles:
    - ESP-BC: Control rods, pumps, humidifiers, turbine
    - ESP-E: LED visualization (power indicator, flow animation)
    
    Usage:
        protocol = ESPProtocol(
            state_manager=state_manager,
            uart_master=uart_master,
            uart_lock=uart_lock
        )
        
        # Start communication thread
        protocol.start()
        
        # Trigger immediate update
        protocol.trigger_immediate()
        
        # Stop
        protocol.stop()
    """
    
    # Update intervals
    ESP_BC_INTERVAL = 0.05   # 50ms (20 Hz)
    ESP_E_INTERVAL = 0.2     # 200ms (5 Hz) - throttled to prevent buffer overflow
    
    def __init__(self,
                 state_manager: 'StateManager',
                 uart_master: 'UARTMaster',
                 uart_lock: threading.Lock,
                 immediate_event: Optional[threading.Event] = None):
        """
        Initialize ESP protocol handler.
        
        Args:
            state_manager: StateManager instance for state access
            uart_master: UARTMaster instance for UART communication
            uart_lock: Lock for UART access (shared with other components)
            immediate_event: Optional event for triggering immediate updates
        """
        self._state_manager = state_manager
        self._uart_master = uart_master
        self._uart_lock = uart_lock
        self._immediate_event = immediate_event or threading.Event()
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    @property
    def immediate_event(self) -> threading.Event:
        """Access to immediate trigger event."""
        return self._immediate_event
    
    def trigger_immediate(self) -> None:
        """Trigger immediate ESP communication."""
        self._immediate_event.set()
    
    def start(self) -> threading.Thread:
        """
        Start ESP communication thread.
        
        Returns:
            Thread object running the communication loop
        """
        self._running = True
        self._thread = threading.Thread(
            target=self._communication_thread, 
            daemon=True
        )
        self._thread.start()
        return self._thread
    
    def stop(self) -> None:
        """Stop ESP communication thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _communication_thread(self) -> None:
        """Main ESP communication thread."""
        logger.info("ESP communication thread started")
        
        # Verify UART master
        if not self._uart_master:
            logger.error("UART master not available!")
            return
        
        logger.info("UART master verified, starting communication loop...")
        
        last_esp_e_update = 0
        
        while self._running:
            try:
                # Wait for timeout or immediate trigger
                triggered = self._immediate_event.wait(timeout=self.ESP_BC_INTERVAL)
                
                if triggered:
                    logger.debug("Immediate ESP send triggered by button event")
                    self._immediate_event.clear()
                
                # Update ESP-BC
                self._update_esp_bc()
                
                # Update ESP-E (throttled)
                current_time = time.time()
                if current_time - last_esp_e_update >= self.ESP_E_INTERVAL:
                    self._update_esp_e()
                    last_esp_e_update = current_time
                
            except Exception as e:
                logger.error(f"Error in ESP communication thread: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(0.1)
        
        logger.info("ESP communication thread stopped")
    
    def _update_esp_bc(self) -> bool:
        """
        Send update to ESP-BC (Control + Actuators).
        
        Returns:
            True if successful, False otherwise
        """
        with self._uart_lock:
            with self._state_manager as state:
                # Log transmission
                logger.info(f"TX /dev/ttyAMA0: {{'cmd':'update', "
                           f"'rods':[{state.safety_rod},{state.shim_rod},{state.regulating_rod}], "
                           f"'pumps':[{state.pump_primary_status},{state.pump_secondary_status},{state.pump_tertiary_status}], "
                           f"'humid_ct':[{state.humid_ct1_cmd},{state.humid_ct2_cmd},{state.humid_ct3_cmd},{state.humid_ct4_cmd}]}}")
                
                if not self._uart_master.esp_bc_connected:
                    logger.warning("ESP-BC not connected, skipping UART send")
                    return False
                
                success = self._uart_master.update_esp_bc(
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
                    logger.debug("✓ ESP-BC update success")
                    # Get feedback data
                    esp_bc_data = self._uart_master.get_esp_bc_data()
                    state.thermal_kw = esp_bc_data.kw_thermal
                    state.turbine_speed = esp_bc_data.turbine_speed
                    time.sleep(0.005)  # 5ms gap before ESP-E
                else:
                    logger.warning("ESP-BC update failed")
                
                return success
    
    def _update_esp_e(self) -> bool:
        """
        Send update to ESP-E (LED Visualizer).
        
        Returns:
            True if successful, False otherwise
        """
        with self._uart_lock:
            try:
                with self._state_manager as state:
                    # Only show power when turbine PWM > 50%
                    display_power = state.thermal_kw if state.turbine_speed > 50 else 0.0
                    
                    logger.debug(f"Sending to ESP-E: Thermal={state.thermal_kw:.1f}kW "
                               f"(Display={display_power:.1f}kW, Turbine={state.turbine_speed:.1f}%), "
                               f"Pumps: P={state.pump_primary_status} "
                               f"S={state.pump_secondary_status} T={state.pump_tertiary_status}")
                    
                    self._uart_master.update_esp_e(
                        thermal_power_kw=display_power,
                        pump_primary_status=state.pump_primary_status,
                        pump_secondary_status=state.pump_secondary_status,
                        pump_tertiary_status=state.pump_tertiary_status
                    )
                
                logger.debug("ESP-E update success")
                return True
                
            except Exception as e:
                logger.debug(f"ESP-E communication error (non-critical): {e}")
                return False
    
    def encode_esp_bc_state(self) -> dict:
        """
        Encode current state for ESP-BC transmission.
        
        Returns:
            Dictionary with ESP-BC command data
        """
        with self._state_manager as state:
            return {
                'rods': [state.safety_rod, state.shim_rod, state.regulating_rod],
                'pumps': [state.pump_primary_status, state.pump_secondary_status, 
                         state.pump_tertiary_status],
                'humid_ct': [state.humid_ct1_cmd, state.humid_ct2_cmd,
                            state.humid_ct3_cmd, state.humid_ct4_cmd]
            }
    
    def encode_esp_e_state(self) -> dict:
        """
        Encode current state for ESP-E transmission.
        
        Returns:
            Dictionary with ESP-E command data
        """
        with self._state_manager as state:
            display_power = state.thermal_kw if state.turbine_speed > 50 else 0.0
            return {
                'thermal_power_kw': display_power,
                'pump_primary_status': state.pump_primary_status,
                'pump_secondary_status': state.pump_secondary_status,
                'pump_tertiary_status': state.pump_tertiary_status
            }
