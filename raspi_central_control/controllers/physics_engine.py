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

# TODO: verify against actual MG996R + gear ratio mechanism speed
ROD_SPEED_DEG_PER_SEC = 8.0
# TODO: tune so full 0->100 drop takes ~2 seconds; verify visually against servo_controller.py physical travel limits — do not exceed the physical servo's actual max speed capability.
SCRAM_DROP_DEG_PER_SEC = 50.0

# Tunable maximum pressure generation rate (bar/s)
MAX_PRESSURE_RATE = 3.0

TRIP_DELAY_SEC = 0.5

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
        
        self.shim_rod_actual = None
        self.regulating_rod_actual = None
        
        self.trip_timer_clad = 0.0
        self.trip_timer_prim = 0.0
        self.trip_timer_condenser = 0.0
        
        self.last_update_time = time.monotonic()
        
    def update(self, state: PanelState) -> None:
        """
        Calculate new physics based on elapsed time, rod positions, and pump status.
        """
        current_time = time.monotonic()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        
        if dt <= 0:
            return

        if self.shim_rod_actual is None:
            self.shim_rod_actual = getattr(state, 'shim_rod', 0.0)
        if self.regulating_rod_actual is None:
            self.regulating_rod_actual = getattr(state, 'regulating_rod', 0.0)

        # Rate-limit rod actual positions toward their setpoints (or 0 if SCRAM)
        if getattr(state, 'emergency_active', False):
            target_shim = 0.0
            target_reg = 0.0
            current_speed = SCRAM_DROP_DEG_PER_SEC
        else:
            target_shim = getattr(state, 'shim_rod', 0.0)
            target_reg = getattr(state, 'regulating_rod', 0.0)
            current_speed = ROD_SPEED_DEG_PER_SEC

        shim_diff = target_shim - self.shim_rod_actual
        shim_step = max(-current_speed * dt, min(shim_diff, current_speed * dt))
        self.shim_rod_actual += shim_step

        reg_diff = target_reg - self.regulating_rod_actual
        reg_step = max(-current_speed * dt, min(reg_diff, current_speed * dt))
        self.regulating_rod_actual += reg_step

        # --- BYPASS FISIKA UNTUK MODE AUTO ---
        sim_mode = getattr(state, 'simulation_mode', 'manual')
        if sim_mode == 'auto':
            # Suhu, tekanan, dan SCRAM dikendalikan 100% oleh auto_simulation / lofa_sequence
            return

        # =====================================================================
        # 1. PRIMARY PHYSICS (Thermal Capacity & Turbine)
        # =====================================================================
        # Bypass manual generation logic if running an automated scripted sequence
        # (Dihapus: Logika kontrol Kecepatan Turbin dan Daya sekarang dipindahkan ke layer Logika Simulasi)


        # =====================================================================
        # 2. FLOW TRACKING
        # =====================================================================
        if state.pump_primary_status == PUMP_ON: self.primary_pump_was_on = True
        if state.pump_secondary_status == PUMP_ON: self.secondary_pump_was_on = True
        if state.pump_tertiary_status == PUMP_ON: self.tertiary_pump_was_on = True
        
        # Reset flow tracking automatically if reactor is completely cold and off, OR if already SCRAMMED
        if state.thermal_kw < 1.0 or state.emergency_active:
            if state.pump_primary_status == 0: self.primary_pump_was_on = False
            if state.pump_secondary_status == 0: self.secondary_pump_was_on = False
            if state.pump_tertiary_status == 0: self.tertiary_pump_was_on = False
            
        # =====================================================================
        # 3. MITIGATION (Pressurizer Relief & Spray) 
        # =====================================================================
        # (Dihapus: Logika kontrol perlindungan otomatis (Relief Valve & Spray)
        # dipindahkan ke layer Logika Simulasi / Control)

        # =====================================================================
        # 4. THERMODYNAMICS (Heat Generation & Cooling)
        # =====================================================================
        # Use control rod directly to define heat target so it doesn't depend on turbine
        effective_rod = (self.shim_rod_actual * 0.8) + (self.regulating_rod_actual * 0.2)
        power_fraction = effective_rod / 100.0
        
        # Power input (q_in) to fuel, arbitrary units scaled for simulator
        q_in = power_fraction * 100.0 
        
        # Heat transfer coefficients (k)
        # Fuel to Cladding is relatively constant
        k_fuel_clad = 0.116
        
        # Cladding to Primary Coolant
        if state.pump_primary_status == PUMP_ON:
            k_clad_prim = 4.0
            k_prim_sec_base = 2.857
        else:
            # DNB (Departure from Nucleate Boiling) -> film boiling drastically reduces heat transfer
            k_clad_prim = 0.2  
            # No circulation to Steam Generator
            k_prim_sec_base = 0.1 
            
        # Secondary Coolant (Steam Generator) to Environment/Tertiary
        if state.pump_secondary_status == PUMP_ON:
            k_prim_sec = k_prim_sec_base
            k_sec_env_base = 0.81
        else:
            k_prim_sec = 0.1
            k_sec_env_base = 0.05
            
        if not hasattr(state, 'temperature_coolant_tertiary'):
            state.temperature_coolant_tertiary = self.ambient_temp
            
        # Secondary Coolant (Steam Generator) to Environment/Tertiary
        if state.pump_tertiary_status == PUMP_ON:
            k_sec_env = k_sec_env_base * 0.2
            k_sec_tert = k_sec_env_base * 0.8
            k_tert_env = 0.5
        else:
            k_sec_env = 0.05
            k_sec_tert = 0.02
            k_tert_env = 0.05
            
        # Calculate heat flows (Q = k * delta_T)
        q_fuel_to_clad = k_fuel_clad * (state.temperature_core - state.temperature_fuel_cladding)
        q_clad_to_prim = k_clad_prim * (state.temperature_fuel_cladding - state.temperature_coolant_primary)
        q_prim_to_sec = k_prim_sec * (state.temperature_coolant_primary - state.temperature_coolant_secondary)
        q_sec_to_env = k_sec_env * (state.temperature_coolant_secondary - self.ambient_temp)
        q_sec_to_tert = k_sec_tert * (state.temperature_coolant_secondary - state.temperature_coolant_tertiary)
        q_tert_to_env = k_tert_env * (state.temperature_coolant_tertiary - self.ambient_temp)
        
        # Thermal capacities (C) - higher means slower temperature change
        C_fuel = 2.0
        C_clad = 1.0
        # TODO: tune berdasarkan testing visual
        C_prim = 7.0
        C_sec = 10.0
        # TODO: tune
        C_tert = 8.0
        
        # Differential equations (Lumped Capacitance Model)
        dT_fuel = (q_in - q_fuel_to_clad) / C_fuel * dt
        dT_clad = (q_fuel_to_clad - q_clad_to_prim) / C_clad * dt
        dT_prim = (q_clad_to_prim - q_prim_to_sec) / C_prim * dt
        dT_sec = (q_prim_to_sec - q_sec_to_env - q_sec_to_tert) / C_sec * dt
        dT_tert = (q_sec_to_tert - q_tert_to_env) / C_tert * dt
        
        # Pressurizer Spray cooling effect on primary coolant
        if state.spray_active:
            dT_prim -= 10.0 * dt
            
        # Base/ambient temperatures for a "Cold Shutdown" state (decay heat residual)
        base_core = 50.0
        base_clad = 45.0
        base_prim = 40.0
        base_sec = 30.0
        base_tert = 25.0
        
        # Update temperatures safely
        state.temperature_core = max(base_core, state.temperature_core + dT_fuel)
        state.temperature_fuel_cladding = max(base_clad, state.temperature_fuel_cladding + dT_clad)
        state.temperature_coolant_primary = max(base_prim, state.temperature_coolant_primary + dT_prim)
        state.temperature_coolant_secondary = max(base_sec, state.temperature_coolant_secondary + dT_sec)
        state.temperature_coolant_tertiary = max(base_tert, state.temperature_coolant_tertiary + dT_tert)
        
        state.temperature_coolant = state.temperature_coolant_primary
        
        # To affect pressure generation below
        delta_temp = dT_prim / dt
        # Abaikan fluktuasi mikroskopis akibat rambatan sisa panas saat reaktor mati (mencegah tekanan naik perlahan)
        if abs(delta_temp) < 0.01:
            delta_temp = 0.0
            
        # =====================================================================
        # 5. PRESSURE DYNAMICS
        # =====================================================================
        # 1. Thermal Expansion Surge: 
        # Air pendingin primer yang memanas akan memuai dan menekan gas di pressurizer.
        # Laju perubahan suhu (delta_temp) menghasilkan lonjakan laju tekanan (bar/s).
        # HANYA aktifkan efek ekspansi termal pada tekanan jika terdapat reaksi fisi aktif (batang kendali ditarik)
        if effective_rod > 0.0:
            pressure_rate = delta_temp * 1.5
        else:
            pressure_rate = 0.0
        
        # --- PERBAIKAN FISIKA LOFA ---
        # Matinya pompa primer memicu pendidihan lokal (film boiling) di selongsong.
        # Pemuaian uap mendadak ini akan meningkatkan tekanan sistem secara drastis.
        if effective_rod > 0:
            if state.pump_primary_status != PUMP_ON:
                rate_clad = dT_clad / dt
                if rate_clad > 0:
                    pressure_rate += (rate_clad * 1.5)
                # Akumulasi uap mendongkrak tekanan jika pompa mati
                pressure_rate += 1.0 
                
        # Batasi laju perubahan tekanan maksimal (bar/s)
        pressure_rate = max(-MAX_PRESSURE_RATE, min(pressure_rate, MAX_PRESSURE_RATE))
        
        # Kalkulasi akumulasi perubahan tekanan pada frame ini
        pressure_generation = pressure_rate * dt
        
        # Super-heating / Boiling surge:
        # T_sat pada 155 bar sekitar 345C. Jika suhu melewati T_sat nyata, air berubah wujud.
        # Ekspansi uap ini sangat masif (ribuan kali volume air), langsung mengalahkan kapasitas buang valve.
        if state.temperature_coolant_primary > 345.0:
            excess_temp = state.temperature_coolant_primary - 345.0
            # Pengali 1.5 berarti di 355C saja (+10C), tekanan +15 bar/s, setara max relief valve
            # Di atas 355C, relief valve tidak ada artinya lagi (tekanan akan terus meroket ke 200 bar)
            pressure_generation += (excess_temp * 1.5) * dt
            
        if getattr(state, 'relief_valve_open', False):
            # Relief valve membuang tekanan secara sangat cepat jika bahaya
            pressure_generation -= 15.0 * dt
            
        state.pressure = max(1.0, state.pressure + pressure_generation)

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

        # Update Timers unconditionally
        if state.temperature_fuel_cladding > 900.0:
            self.trip_timer_clad += dt
        else:
            self.trip_timer_clad = 0.0

        if state.temperature_coolant_primary > 380.0:
            self.trip_timer_prim += dt
        else:
            self.trip_timer_prim = 0.0

        if state.condenser_pressure > 0.5:
            self.trip_timer_condenser += dt
        else:
            self.trip_timer_condenser = 0.0

        # Primary
        def check_prim():
            if self.trip_timer_clad >= TRIP_DELAY_SEC: return f"Primary LOFA: Fuel Cladding Overheat ({state.temperature_fuel_cladding:.1f}°C > 900°C)"
            if self.trip_timer_prim >= TRIP_DELAY_SEC: return f"Primary LOFA: Coolant Overheat ({state.temperature_coolant_primary:.1f}°C > 380°C)"
            return None
        scram_reason = scram_reason or check_lofa(state.pump_primary_status, self.primary_pump_was_on, 'lofa_primary', 'Primary', check_prim)
        
        # Secondary
        def check_sec():
            if self.trip_timer_clad >= TRIP_DELAY_SEC or self.trip_timer_prim >= TRIP_DELAY_SEC: return "Secondary LOFA: Induced Primary Overheat"
            return None
        scram_reason = scram_reason or check_lofa(state.pump_secondary_status, self.secondary_pump_was_on, 'lofa_secondary', 'Secondary', check_sec)

        # Tertiary
        def check_tert():
            if self.trip_timer_condenser >= TRIP_DELAY_SEC: return f"Tertiary LOFA: Prolonged Condenser Overpressure ({state.condenser_pressure:.2f} > 0.5 MPa)"
            return None
        scram_reason = scram_reason or check_lofa(state.pump_tertiary_status, self.tertiary_pump_was_on, 'lofa_tertiary', 'Tertiary', check_tert)

        # General Overheat & Saturation Check
        # Realistic T_sat approximation: 100 * (P^0.245) yields ~343C at 155 bar, matching real PWR physics
        t_sat = 100.0 * (max(1.0, state.pressure) ** 0.245)
        
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
                    
        # Matikan alarm secara otomatis jika kondisi reaktor sudah kembali aman
        if state.emergency_active:
            is_safe = (state.temperature_coolant_primary < 330.0 and 
                       state.temperature_core < 1000.0 and 
                       state.pressure < 170.0)
            if is_safe:
                state.emergency_active = False

