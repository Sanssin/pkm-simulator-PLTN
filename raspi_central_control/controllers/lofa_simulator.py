"""
LOFA (Loss of Flow Accident) Simulator Module
Calculates core and coolant temperatures based on thermal power and pump states.
If temperatures exceed safety thresholds, it triggers an EMERGENCY SCRAM.
"""

import time
import logging
from typing import Callable, Optional
from .state_manager import PanelState
from .interlock_validator import PUMP_ON

logger = logging.getLogger(__name__)

class LOFASimulator:
    """
    Simulates thermodynamics for Loss of Flow Accident (LOFA).
    
    Heat generation: Proportional to thermal_kw.
    Cooling: Proportional to active pumps.
    """
    
    def __init__(self, 
                 max_core_temp: float = 300.0,
                 ambient_temp: float = 25.0,
                 trigger_scram_callback: Optional[Callable[[], None]] = None):
        self.max_core_temp = max_core_temp
        self.ambient_temp = ambient_temp
        self.trigger_scram = trigger_scram_callback
        self.lofa_power_threshold = 50.0  # kW threshold to trigger LOFA if pump fails
        
        self.last_update_time = time.time()
        
    def update(self, state: PanelState) -> None:
        """
        Calculate new temperatures based on elapsed time, thermal power, and pump status.
        Should be called periodically (e.g., every 50ms in the control logic thread).
        """
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        if dt <= 0:
            return
            
        # 0. LOFA Mitigation: Pressurizer Relief & Spray
        if state.pressure > 165.0:
            if not state.relief_valve_open:
                state.relief_valve_open = True
                logger.warning("🔺 Pressurizer Relief Valve OPENED (Pressure > 165 bar)")
        elif state.pressure < 155.0:
            if state.relief_valve_open:
                state.relief_valve_open = False
                logger.info("✅ Pressurizer Relief Valve CLOSED (Pressure < 155 bar)")

        if state.temperature_coolant_primary > 340.0:
            if not state.spray_active:
                state.spray_active = True
                logger.warning("💦 Pressurizer Spray ACTIVATED (Coolant > 340°C)")
        elif state.temperature_coolant_primary < 320.0:
            if state.spray_active:
                state.spray_active = False
                logger.info("✅ Pressurizer Spray DEACTIVATED (Coolant < 320°C)")

        # 1. Heat Generation from Core
        # thermal_kw typically reaches up to 300,000 kW in full power simulation.
        heat_generation_rate = state.thermal_kw * 0.00038
        
        # 2. Cooling from Pumps
        cooling_efficiency = 0.005  # Passive ambient cooling
        if state.pump_primary_status == PUMP_ON: cooling_efficiency += 0.25
        if state.pump_secondary_status == PUMP_ON: cooling_efficiency += 0.12
        if state.pump_tertiary_status == PUMP_ON: cooling_efficiency += 0.08
        
        if state.spray_active:
            cooling_efficiency += 0.15  # Extra cooling from spray

        cooling_rate = (state.temperature_core - self.ambient_temp) * cooling_efficiency
        
        # 3. Calculate Core Temperature change
        delta_temp = (heat_generation_rate - cooling_rate) * dt
        
        new_core_temp = max(self.ambient_temp, state.temperature_core + delta_temp)
        state.temperature_core = new_core_temp
        
        state.temperature_fuel_cladding = state.temperature_core * 0.95 + self.ambient_temp * 0.05
        
        if state.pump_primary_status == PUMP_ON:
            state.temperature_coolant_primary = self.ambient_temp + (state.temperature_fuel_cladding - self.ambient_temp) * 0.85
        else:
            state.temperature_coolant_primary = self.ambient_temp + (state.temperature_fuel_cladding - self.ambient_temp) * 0.4
            
        if state.pump_secondary_status == PUMP_ON:
            state.temperature_coolant_secondary = self.ambient_temp + (state.temperature_coolant_primary - self.ambient_temp) * 0.7
        else:
            state.temperature_coolant_secondary = self.ambient_temp + (state.temperature_coolant_primary - self.ambient_temp) * 0.2
            
        state.temperature_coolant = state.temperature_coolant_primary
        
        # 4. Pressure Dynamics
        pressure_generation = (delta_temp * 0.5) if delta_temp > 0 else (delta_temp * 0.2)
        if state.relief_valve_open:
            pressure_generation -= 1.5 * dt  # Relieve pressure more slowly (1.5 bar/sec)
            
        state.pressure = max(0.0, state.pressure + pressure_generation)

        # 5. Condenser pressure logic for tertiary pump
        if state.pump_tertiary_status != PUMP_ON and state.thermal_kw > 10.0:
            state.condenser_pressure += 0.01 * dt
        else:
            state.condenser_pressure = max(0.0, state.condenser_pressure - 0.05 * dt)

        # 6. Check for LOFA condition & Auto-SCRAM Triggers (per pump logic)
        scram_reason = None
        
        # Primary Pump Failure -> Overheat check
        if state.pump_primary_status != PUMP_ON:
            if not state.lofa_primary:
                state.lofa_primary = True
                logger.warning("⚠️ LOFA PRIMARY DETECTED! Primary pump failed.")
            
            if state.temperature_fuel_cladding > 900.0:
                scram_reason = f"Primary LOFA: Fuel Cladding Overheat ({state.temperature_fuel_cladding:.1f}°C > 900°C)"
            elif state.temperature_coolant_primary > 380.0:
                scram_reason = f"Primary LOFA: Coolant Overheat ({state.temperature_coolant_primary:.1f}°C > 380°C)"
        else:
            state.lofa_primary = False

        # Secondary Pump Failure -> Overheat check
        if state.pump_secondary_status != PUMP_ON:
            if not state.lofa_secondary:
                state.lofa_secondary = True
                logger.warning("⚠️ LOFA SECONDARY DETECTED! Secondary pump failed.")
            
            # SCRAM naturally triggers when primary overheats due to lack of secondary cooling
            if state.temperature_fuel_cladding > 900.0 or state.temperature_coolant_primary > 380.0:
                scram_reason = "Secondary LOFA: Induced Primary Overheat"
        else:
            state.lofa_secondary = False

        # Tertiary Pump Failure -> Prolonged effect check
        if state.pump_tertiary_status != PUMP_ON:
            if not state.lofa_tertiary:
                state.lofa_tertiary = True
                logger.warning("⚠️ LOFA TERTIARY DETECTED! Tertiary pump failed.")
            
            if state.condenser_pressure > 0.5:
                scram_reason = f"Tertiary LOFA: Prolonged Condenser Overpressure ({state.condenser_pressure:.2f} > 0.5 MPa)"
        else:
            state.lofa_tertiary = False

        # General Core Overheat
        if state.temperature_core >= self.max_core_temp and not scram_reason:
            scram_reason = f"General Overheat: Core Temp {state.temperature_core:.1f}°C >= {self.max_core_temp}°C"

        # Execute SCRAM if needed
        if scram_reason and not state.emergency_active:
            logger.critical(f"Initiating EMERGENCY SCRAM: {scram_reason}")
            if self.trigger_scram:
                self.trigger_scram()
