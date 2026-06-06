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
            
        # 0. Check LOFA Conditions per pump
        lofa_detected_now = False
        
        if state.pump_primary_status != PUMP_ON and state.thermal_kw > self.lofa_power_threshold:
            if not state.lofa_primary:
                state.lofa_primary = True
                logger.critical("⚠️ LOFA PRIMARY DETECTED! Primary pump failed while reactor is active!")
                lofa_detected_now = True
        else:
            state.lofa_primary = False
            
        if state.pump_secondary_status != PUMP_ON and state.thermal_kw > self.lofa_power_threshold:
            if not state.lofa_secondary:
                state.lofa_secondary = True
                logger.critical("⚠️ LOFA SECONDARY DETECTED! Secondary pump failed while reactor is active!")
                lofa_detected_now = True
        else:
            state.lofa_secondary = False
            
        if state.pump_tertiary_status != PUMP_ON and state.thermal_kw > self.lofa_power_threshold:
            if not state.lofa_tertiary:
                state.lofa_tertiary = True
                logger.critical("⚠️ LOFA TERTIARY DETECTED! Tertiary pump failed while reactor is active!")
                lofa_detected_now = True
        else:
            state.lofa_tertiary = False
            
        # If any new LOFA is detected, trigger SCRAM immediately
        if lofa_detected_now and not state.emergency_active:
            logger.critical("Initiating EMERGENCY SCRAM due to immediate LOFA condition!")
            if self.trigger_scram:
                self.trigger_scram()
                
        # 1. Heat Generation from Core
        # thermal_kw typically reaches up to ~3000 kW in full power simulation.
        # We use a scaling factor to make the temperature rise visible but not instant.
        heat_generation_rate = state.thermal_kw * 0.02
        
        # 2. Cooling from Pumps
        # Each pump provides a certain amount of cooling capacity
        active_pumps = 0
        if state.pump_primary_status == PUMP_ON: active_pumps += 1
        if state.pump_secondary_status == PUMP_ON: active_pumps += 1
        if state.pump_tertiary_status == PUMP_ON: active_pumps += 1
        
        # Cooling rate is proportional to temperature difference (Newton's law of cooling)
        # Heavily influenced by active pumps. If 0 pumps, only passive ambient cooling (very low).
        cooling_efficiency = 0.005 + (active_pumps * 0.15)
        cooling_rate = (state.temperature_core - self.ambient_temp) * cooling_efficiency
        
        # 3. Calculate Core Temperature change
        delta_temp = (heat_generation_rate - cooling_rate) * dt
        
        # Update state (assuming caller holds the lock via StateManager)
        new_core_temp = max(self.ambient_temp, state.temperature_core + delta_temp)
        state.temperature_core = new_core_temp
        
        # Coolant temperature follows core temperature but with some lag and lower max
        state.temperature_coolant = self.ambient_temp + (state.temperature_core - self.ambient_temp) * 0.8
        
        # 4. Check for LOFA condition (SCRAM Trigger)
        if state.temperature_core >= self.max_core_temp:
            if not state.emergency_active:
                logger.critical(f"⚠️ LOFA DETECTED! Core Temp {state.temperature_core:.1f}°C > {self.max_core_temp}°C")
                logger.critical("Initiating EMERGENCY SCRAM due to Loss of Flow Accident!")
                if self.trigger_scram:
                    self.trigger_scram()
