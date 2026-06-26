"""
Physics Engine Module for PLTN Simulator
Calculates thermal capacity, turbine speed, thermodynamics, and LOFA conditions.
Provides a single source of truth for all physical values.
"""

import time
import logging
from typing import Callable, Optional
from .state_manager import PanelState
from .interlock_validator import PUMP_ON

logger = logging.getLogger(__name__)

class PhysicsEngine:
    """
    Simulates thermodynamics and mechanical physics for the reactor.
    
    Heat generation: Proportional to control rods -> thermal_kw.
    Turbine: Speed proportional to thermal_kw.
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
        
        # Track if flow was established to prevent false LOFA on startup
        self.primary_pump_was_on = False
        self.secondary_pump_was_on = False
        self.tertiary_pump_was_on = False
        
        self.last_update_time = time.time()
        
    def update(self, state: PanelState) -> None:
        """
        Calculate new physics based on elapsed time, rod positions, and pump status.
        """
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        if dt <= 0:
            return

        # =====================================================================
        # 1. PRIMARY PHYSICS (Thermal Capacity & Turbine)
        # =====================================================================
        # Bypass manual generation logic if running an automated scripted sequence
        if state.simulation_mode not in ('auto', 'cinematic_lofa') and not getattr(state, 'auto_sim_running', False):
            effective_rod = (state.shim_rod * 0.8) + (state.regulating_rod * 0.2)
            
            if effective_rod > 10.0:
                reactor_thermal_capacity = (effective_rod**2) * 90.0
                reactor_thermal_capacity = min(reactor_thermal_capacity, 900000.0)
            else:
                reactor_thermal_capacity = 0.0
                    
            if not state.emergency_active:
                temp_sec = getattr(state, 'temperature_coolant_secondary', 25.0)
                if temp_sec > 50.0 and getattr(state, 'pump_secondary_status', 0) == PUMP_ON:
                    # Turbine speed matches secondary temperature (from 50C to 200C)
                    target_speed = ((temp_sec - 50.0) / 150.0) * 100.0
                    target_speed = min(max(target_speed, 10.0), 100.0)
                    
                    if state.turbine_speed < target_speed:
                        state.turbine_speed = min(state.turbine_speed + (4.0 * dt), target_speed)
                    else:
                        state.turbine_speed = max(state.turbine_speed - (10.0 * dt), target_speed)
                else:
                    state.turbine_speed = max(state.turbine_speed - (10.0 * dt), 0.0)
            else:
                state.turbine_speed = max(state.turbine_speed - (40.0 * dt), 0.0)
                    
            target_thermal_kw = min(reactor_thermal_capacity * 0.34 * (state.turbine_speed / 100.0), 300000.0)
            
            # Mencegah daya turun menjadi 0 seketika saat SCRAM atau control rod diturunkan paksa.
            # Turbin masih memiliki gaya inersia/potensial yang perlahan melambat.
            if target_thermal_kw < state.thermal_kw:
                decay_rate = 300000.0 / 2.5 # Turun dari max ke 0 dalam ~2.5 detik
                state.thermal_kw = max(state.thermal_kw - (decay_rate * dt), target_thermal_kw)
            else:
                state.thermal_kw = target_thermal_kw


        # =====================================================================
        # 2. FLOW TRACKING
        # =====================================================================
        if state.pump_primary_status == PUMP_ON: self.primary_pump_was_on = True
        if state.pump_secondary_status == PUMP_ON: self.secondary_pump_was_on = True
        if state.pump_tertiary_status == PUMP_ON: self.tertiary_pump_was_on = True
        
        # Reset flow tracking automatically if reactor is completely cold and off
        if state.thermal_kw < 1.0:
            if state.pump_primary_status == 0: self.primary_pump_was_on = False
            if state.pump_secondary_status == 0: self.secondary_pump_was_on = False
            if state.pump_tertiary_status == 0: self.tertiary_pump_was_on = False
            
        # =====================================================================
        # 3. MITIGATION (Pressurizer Relief & Spray)
        # =====================================================================
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

        # =====================================================================
        # 4. THERMODYNAMICS (Heat Generation & Cooling)
        # =====================================================================
        # Use control rod directly to define heat target so it doesn't depend on turbine
        effective_rod = (getattr(state, 'shim_rod', 0) * 0.8) + (getattr(state, 'regulating_rod', 0) * 0.2)
        
        # Target core temperature based on rod (0 to 100%) -> (25C to 1200C)
        target_core_temp = 25.0 + (effective_rod / 100.0) * 1175.0
        
        # LOFA / Cooling adjustments (Only apply if reactor is active / rods are pulled)
        if effective_rod > 0:
            if state.pump_primary_status != PUMP_ON: target_core_temp += 600.0 * (effective_rod / 100.0) + 100.0
            if state.pump_secondary_status != PUMP_ON: target_core_temp += 150.0
            
        if state.spray_active: target_core_temp -= 100.0
        
        # Pressurizer heating effect adds slightly to target
        target_core_temp += state.pressure * 0.1
        
        target_core_temp = max(self.ambient_temp, target_core_temp)
        
        # Linear Temperature change
        # Kecepatan naik turunnya suhu disesuaikan dengan posisi batang kendali (0.5 hingga 10 deg/sec)
        heat_up_rate = 0.5 + (effective_rod / 100.0) * 9.5
        
        if state.temperature_core < target_core_temp:
            delta_temp = heat_up_rate * dt
            if state.temperature_core + delta_temp > target_core_temp:
                delta_temp = target_core_temp - state.temperature_core
        else:
            delta_temp = -15.0 * dt # Linear cool down rate (15 deg/sec)
            if state.temperature_core + delta_temp < target_core_temp:
                delta_temp = target_core_temp - state.temperature_core
                
        state.temperature_core += delta_temp
        
        # Normal heat transfer factor from fuel centerline to cladding
        clad_factor = 0.27
        if state.pump_primary_status != PUMP_ON:
            # During LOFA, heat cannot escape cladding to coolant, so cladding heats up towards fuel temp
            clad_factor = 0.85
            
        state.temperature_fuel_cladding = self.ambient_temp + (state.temperature_core - self.ambient_temp) * clad_factor
        
        if state.pump_primary_status == PUMP_ON:
            state.temperature_coolant_primary = self.ambient_temp + (state.temperature_fuel_cladding - self.ambient_temp) * 0.9
        else:
            # DNB (Departure from Nucleate Boiling) effect: 
            # Heat transfer drops sharply, cladding overheats without raising coolant temp as much
            state.temperature_coolant_primary = self.ambient_temp + (state.temperature_fuel_cladding - self.ambient_temp) * 0.25
            
        if state.pump_secondary_status == PUMP_ON:
            state.temperature_coolant_secondary = self.ambient_temp + (state.temperature_coolant_primary - self.ambient_temp) * 0.9
        else:
            state.temperature_coolant_secondary = self.ambient_temp + (state.temperature_coolant_primary - self.ambient_temp) * 0.15
            
        state.temperature_coolant = state.temperature_coolant_primary
        
        # =====================================================================
        # 5. PRESSURE DYNAMICS
        # =====================================================================
        pressure_generation = (delta_temp * 0.1) if delta_temp > 0 else (delta_temp * 0.2)
        if state.relief_valve_open:
            pressure_generation -= 1.5 * dt  # Relieve pressure more slowly
            
        state.pressure = max(0.0, state.pressure + pressure_generation)

        # Condenser pressure logic
        if state.pump_tertiary_status != PUMP_ON and state.thermal_kw > 10.0:
            state.condenser_pressure += 0.01 * dt
        else:
            state.condenser_pressure = max(0.0, state.condenser_pressure - 0.05 * dt)

        # =====================================================================
        # 6. SAFETY & LOFA CHECKS
        # =====================================================================
        scram_reason = None
        if state.thermal_kw > 5.0:
            state.reactor_active = True
        reactor_active = getattr(state, 'reactor_active', False)
        
        def check_lofa(pump_status, was_on, lofa_flag_attr, name, check_scram):
            if reactor_active and was_on:
                if pump_status != PUMP_ON:
                    # Do NOT auto-set LOFA flag immediately on manual shutdown.
                    # Wait to see if it causes a dangerous condition.
                    reason = check_scram()
                    if reason:
                        # It overheated/overpressured! Now it's a real LOFA failure.
                        setattr(state, lofa_flag_attr, True)
                        logger.warning(f"⚠️ LOFA {name.upper()} TRIGGERED due to dangerous conditions: {reason}")
                    return reason
                else:
                    # Clear the LOFA flag if the pump is successfully turned back ON
                    setattr(state, lofa_flag_attr, False)
            else:
                if pump_status == PUMP_ON:
                    setattr(state, lofa_flag_attr, False)
            return None

        # Primary
        def check_prim():
            if state.temperature_fuel_cladding > 900.0: return f"Primary LOFA: Fuel Cladding Overheat ({state.temperature_fuel_cladding:.1f}°C > 900°C)"
            if state.temperature_coolant_primary > 380.0: return f"Primary LOFA: Coolant Overheat ({state.temperature_coolant_primary:.1f}°C > 380°C)"
        scram_reason = scram_reason or check_lofa(state.pump_primary_status, self.primary_pump_was_on, 'lofa_primary', 'Primary', check_prim)
        
        # Secondary
        def check_sec():
            if state.temperature_fuel_cladding > 900.0 or state.temperature_coolant_primary > 380.0: return "Secondary LOFA: Induced Primary Overheat"
        scram_reason = scram_reason or check_lofa(state.pump_secondary_status, self.secondary_pump_was_on, 'lofa_secondary', 'Secondary', check_sec)

        # Tertiary
        def check_tert():
            if state.condenser_pressure > 0.5: return f"Tertiary LOFA: Prolonged Condenser Overpressure ({state.condenser_pressure:.2f} > 0.5 MPa)"
        scram_reason = scram_reason or check_lofa(state.pump_tertiary_status, self.tertiary_pump_was_on, 'lofa_tertiary', 'Tertiary', check_tert)

        # General Overheat & Saturation Check
        t_sat = 100.0 * (max(1.0, state.pressure) ** 0.25)
        
        if state.temperature_coolant_primary >= t_sat and not scram_reason:
            scram_reason = f"Primary Boiling! T_coolant {state.temperature_coolant_primary:.1f}°C >= T_sat {t_sat:.1f}°C at {state.pressure:.1f} bar"
        
        if state.temperature_core >= 1800.0 and not scram_reason:
            scram_reason = f"General Overheat: Core Temp {state.temperature_core:.1f}°C >= 1800.0°C"
            
        # Overpressure
        if state.pressure >= 200.0 and not scram_reason:
            scram_reason = f"Overpressure: Pressure {state.pressure:.1f} bar >= 200.0 bar"

        # Execute SCRAM
        if scram_reason and not state.emergency_active:
            if getattr(state, 'simulation_mode', '') == 'cinematic_lofa':
                pass
            else:
                logger.critical(f"Initiating EMERGENCY SCRAM: {scram_reason}")
                if self.trigger_scram:
                    self.trigger_scram()
