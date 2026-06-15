"""
AutoSimulator - Automated PWR startup sequence for PLTN Panel Simulator.

This module handles the automatic startup simulation that demonstrates
the correct procedure for starting a PWR nuclear reactor.

Phases:
1. System Initialization
2. Pressurizer to 45 bar
3. Pump Startup (Tertiary → Secondary → Primary)
4A. Pressure to 140 bar
4B. Safety Rod Withdrawal
4C. Shim Rod to 50%
4D. Regulating Rod to 50%
4E. Power Ramp to 100%
5. Steam Generator Operation
6. Turbine-Generator Startup
7. Power Generation
8. Cooling Tower Activation
9. Stable Operation
"""

import time
import logging
import threading
from enum import Enum, auto
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from controllers.state_manager import StateManager

logger = logging.getLogger(__name__)


class SimPhase(Enum):
    """Simulation phases for auto startup sequence."""
    IDLE = auto()
    INIT = auto()
    PRESSURE_45 = auto()
    PUMPS = auto()
    PRESSURE_140 = auto()
    SAFETY_ROD = auto()
    SHIM_ROD_50 = auto()
    REG_ROD_50 = auto()
    MAX_POWER = auto()
    STEAM_GEN = auto()
    TURBINE = auto()
    POWER_GEN = auto()
    COOLING_TOWER = auto()
    STABLE = auto()
    COMPLETE = auto()


class AutoSimulator:
    """
    Automated PWR startup sequence simulator.
    
    Runs through a realistic 9-phase startup procedure with smooth
    animations for educational purposes.
    
    Usage:
        simulator = AutoSimulator(
            state_manager=state_manager
        )
        
        # Start simulation (non-blocking)
        simulator.start()
        
        # Cancel if needed
        simulator.cancel()
        
        # Check status
        if simulator.is_running:
            print(f"Current phase: {simulator.current_phase}")
    """
    
    UPDATE_INTERVAL = 0.05  # 50ms for smooth animation
    
    def __init__(self, state_manager: 'StateManager'):
        """
        Initialize AutoSimulator.
        
        Args:
            state_manager: StateManager instance for state access
        """
        self._state_manager = state_manager
        self._current_phase = SimPhase.IDLE
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None
    
    @property
    def is_running(self) -> bool:
        """Check if simulation is currently running."""
        return self._running
    
    @property
    def current_phase(self) -> SimPhase:
        """Get current simulation phase."""
        return self._current_phase
    
    def start(self) -> threading.Thread:
        """
        Start the auto simulation.
        
        Returns:
            Thread object running the simulation
        """
        if self._running:
            logger.warning("Auto simulation already running!")
            return self._thread
        
        self._cancelled = False
        self._thread = threading.Thread(target=self._simulation_thread, daemon=True)
        self._thread.start()
        return self._thread
    
    def cancel(self) -> None:
        """Cancel the running simulation."""
        self._cancelled = True
        with self._state_manager as state:
            state.auto_sim_running = False
            state.simulation_mode = 'manual'
            state.auto_sim_phase = ""
        logger.warning("Auto simulation cancelled by user")
    
    def _check_cancelled(self) -> bool:
        """Check if simulation was cancelled."""
        if self._cancelled:
            return True
        with self._state_manager as state:
            return not state.auto_sim_running
    
    def _set_phase(self, phase: SimPhase, label: str) -> None:
        """Set current phase and update state."""
        self._current_phase = phase
        with self._state_manager as state:
            state.auto_sim_phase = label
    
    def _ramp_value(self, field: str, start: float, target: float, 
                    duration: float, is_int: bool = False) -> bool:
        """
        Smoothly ramp a state field from start to target.
        
        Args:
            field: State field name to update
            start: Starting value
            target: Target value
            duration: Duration in seconds
            is_int: If True, convert to int
            
        Returns:
            False if cancelled, True if completed
        """
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if self._check_cancelled():
                return False
            
            elapsed = time.time() - start_time
            progress = elapsed / duration
            current = start + (target - start) * progress
            
            if is_int:
                current = int(current)
            
            with self._state_manager as state:
                setattr(state, field, current)
            
            time.sleep(self.UPDATE_INTERVAL)
        
        # Ensure exact final value
        final_value = int(target) if is_int else target
        with self._state_manager as state:
            setattr(state, field, final_value)
        
        return True
    
    def _simulation_thread(self) -> None:
        """Main simulation execution thread."""
        try:
            self._running = True
            
            # Mark state as auto simulation running
            with self._state_manager as state:
                state.simulation_mode = 'auto'
                state.auto_sim_running = True
            
            logger.info("=" * 70)
            logger.info("AUTO SIMULATION MODE - Full PWR Startup Sequence")
            logger.info("   Simulasi berjalan otomatis dengan kecepatan lambat")
            logger.info("   untuk memudahkan pemahaman cara kerja PLTN")
            logger.info("")
            logger.info("Manual control tetap aktif - Anda bisa interrupt kapan saja")
            logger.info("=" * 70)
            
            # Execute all phases
            if not self._phase_1_init():
                return
            if not self._phase_2_pressure_45():
                return
            if not self._phase_3_pumps():
                return
            if not self._phase_4a_pressure_140():
                return
            if not self._phase_4b_safety_rod():
                return
            if not self._phase_4c_shim_rod_50():
                return
            if not self._phase_4d_reg_rod_50():
                return
            if not self._phase_4e_max_power():
                return
            if not self._phase_5_steam_gen():
                return
            if not self._phase_6_turbine():
                return
            if not self._phase_7_power_gen():
                return
            if not self._phase_8_cooling_tower():
                return
            
            self._phase_9_stable()
            
        except Exception as e:
            logger.error(f"Error in auto simulation: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._running = False
            self._current_phase = SimPhase.IDLE
            with self._state_manager as state:
                state.auto_sim_running = False
                state.simulation_mode = 'manual'
                state.auto_sim_phase = ""
            logger.info("Auto simulation thread stopped")
    
    def _phase_1_init(self) -> bool:
        """Phase 1: System Initialization."""
        self._set_phase(SimPhase.INIT, "Init")
        logger.info("\n Phase 1: System Initialization")
        logger.info("   ✓ Reactor system active (manual mode always on)")
        logger.info("   ✓ All controls ready")
        time.sleep(3)
        return not self._check_cancelled()
    
    def _phase_2_pressure_45(self) -> bool:
        """Phase 2: Raise pressure to 45 bar."""
        self._set_phase(SimPhase.PRESSURE_45, "Pressure 45")
        logger.info("\n Phase 2: Pressurizer Activation")
        logger.info("   Raising pressure to 45 bar (3 seconds)...")
        
        if not self._ramp_value('pressure', 0.0, 45.0, 3.0):
            return False
        
        logger.info("Pressure reached: 45.0 bar")
        logger.info("Interlock condition 1 satisfied (P ≥ 40 bar)")
        time.sleep(2)
        return True
    
    def _phase_3_pumps(self) -> bool:
        """Phase 3: Start pumps in sequence."""
        self._set_phase(SimPhase.PUMPS, "Pumps")
        logger.info("\n Phase 3: Coolant Pumps Startup Sequence")
        logger.info("   Following correct startup procedure...")
        
        # Tertiary pump
        logger.info("   Step 3.1: Starting Tertiary Pump (Cooling path)...")
        with self._state_manager as state:
            state.pump_tertiary_status = 1  # STARTING
        self._trigger_esp()
        time.sleep(3)
        if self._check_cancelled():
            return False
        logger.info("Tertiary Pump: ON")
        
        # Secondary pump
        logger.info("   Step 3.2: Starting Secondary Pump (Heat exchanger)...")
        with self._state_manager as state:
            state.pump_secondary_status = 1  # STARTING
        self._trigger_esp()
        time.sleep(3)
        if self._check_cancelled():
            return False
        logger.info("Secondary Pump: ON")
        
        # Primary pump
        logger.info("   Step 3.3: Starting Primary Pump (Main loop)...")
        with self._state_manager as state:
            state.pump_primary_status = 1  # STARTING
        self._trigger_esp()
        time.sleep(3)
        if self._check_cancelled():
            return False
        logger.info("Primary Pump: ON")
        logger.info("All pumps operational")
        logger.info("Interlock condition 2 satisfied (All pumps ON)")
        time.sleep(2)
        
        return True
    
    def _phase_4a_pressure_140(self) -> bool:
        """Phase 4A: Raise pressure to 140 bar."""
        self._set_phase(SimPhase.PRESSURE_140, "Pressure 140")
        logger.info("\n Phase 4A: Pressurizer to Operating Pressure")
        logger.info("   Raising pressure to 140 bar (7 seconds)...")
        logger.info("   (Operating pressure required before rod withdrawal)")
        
        with self._state_manager as state:
            start_pressure = state.pressure
        
        if not self._ramp_value('pressure', start_pressure, 140.0, 7.0):
            return False
        
        logger.info("Pressure at 140 bar (operating pressure)")
        time.sleep(2)
        return True
    
    def _phase_4b_safety_rod(self) -> bool:
        """Phase 4B: Withdraw safety rod."""
        self._set_phase(SimPhase.SAFETY_ROD, "Safety Rod")
        logger.info("\n Phase 4B: Safety Rod Withdrawal")
        logger.info("   Raising safety rod to 100% (3 seconds)...")
        logger.info("   (Safety rod must be fully withdrawn before power rods)")
        
        if not self._ramp_value('safety_rod', 0, 100, 3.0, is_int=True):
            return False
        
        logger.info("Safety rod at 100%")
        time.sleep(2)
        logger.info("Ready for power rod withdrawal")
        time.sleep(2)
        return True
    
    def _phase_4c_shim_rod_50(self) -> bool:
        """Phase 4C: Shim rod to 50%."""
        self._set_phase(SimPhase.SHIM_ROD_50, "Shim Rod 50%")
        logger.info("\n Phase 4C: Shim Rod Withdrawal (Coarse Control)")
        logger.info("   Raising shim rod to 50% (3 seconds)...")
        
        if not self._ramp_value('shim_rod', 0, 50, 3.0, is_int=True):
            return False
        
        logger.info("Shim rod at 50% (initial power level)")
        time.sleep(2)
        return True
    
    def _phase_4d_reg_rod_50(self) -> bool:
        """Phase 4D: Regulating rod to 50%."""
        self._set_phase(SimPhase.REG_ROD_50, "Reg Rod 50%")
        logger.info("\n Phase 4D: Regulating Rod Withdrawal (Fine Control)")
        logger.info("   Raising regulating rod to 50% (3 seconds)...")
        
        if not self._ramp_value('regulating_rod', 0, 50, 3.0, is_int=True):
            return False
        
        logger.info("Regulating rod at 50% (medium power)")
        time.sleep(2)
        return True
    
    def _phase_4e_max_power(self) -> bool:
        """Phase 4E: Ramp to maximum power."""
        self._set_phase(SimPhase.MAX_POWER, "Max Power")
        logger.info("\n Phase 4E: Power Ramp-up to Maximum")
        logger.info("   Raising shim rod to 100% (4 seconds)...")
        
        if not self._ramp_value('shim_rod', 50, 100, 4.0, is_int=True):
            return False
        
        logger.info("Shim rod at 100% (coarse max)")
        time.sleep(2)
        
        logger.info("   Raising regulating rod to 100% (4 seconds)...")
        
        if not self._ramp_value('regulating_rod', 50, 100, 4.0, is_int=True):
            return False
        
        logger.info("Regulating rod at 100% (fine max)")
        logger.info("Reactor at MAXIMUM POWER!")
        logger.info("Reactor criticality achieved")
        logger.info("Thermal power at maximum")
        time.sleep(3)
        return True
    
    def _phase_5_steam_gen(self) -> bool:
        """Phase 5: Steam generator operation."""
        self._set_phase(SimPhase.STEAM_GEN, "Steam Gen")
        logger.info("\n Phase 5: Steam Generator Operation")
        logger.info("   Steam generators automatically activate (Rods ≥ 40%)")
        logger.info("   Visual: Humidifiers SG1 & SG2 creating steam 💨")
        time.sleep(5)
        return not self._check_cancelled()
    
    def _phase_6_turbine(self) -> bool:
        """Phase 6: Turbine startup."""
        self._set_phase(SimPhase.TURBINE, "Turbine")
        logger.info("\n Phase 6: Turbine-Generator Startup")
        logger.info("   Turbine starting automatically...")
        logger.info("   Speed ramping up: 0% → 100%")
        time.sleep(8)
        if self._check_cancelled():
            return False
        logger.info("Turbine at full speed (100%)")
        logger.info("Generator synchronized to grid")
        time.sleep(3)
        return True
    
    def _phase_7_power_gen(self) -> bool:
        """Phase 7: Power generation."""
        self._set_phase(SimPhase.POWER_GEN, "Power Gen")
        logger.info("\n Phase 7: Electrical Power Generation")
        logger.info("   Reactor thermal: ~900 MWth")
        logger.info("   Turbine efficiency: ~33%")
        logger.info("   Electrical output: ~200-250 MWe")
        logger.info("   Visual: Power indicator LED brightness ↑ 💡")
        time.sleep(5)
        return not self._check_cancelled()
    
    def _phase_8_cooling_tower(self) -> bool:
        """Phase 8: Cooling tower activation."""
        self._set_phase(SimPhase.COOLING_TOWER, "Cooling")
        logger.info("\n Phase 8: Cooling Tower Humidifiers")
        logger.info("   Cooling towers activate automatically")
        logger.info("   CT1, CT2, CT3, CT4: Creating steam effect 💨")
        time.sleep(5)
        return not self._check_cancelled()
    
    def _phase_9_stable(self) -> None:
        """Phase 9: Stable operation achieved."""
        self._set_phase(SimPhase.STABLE, "Stable")
        logger.info("\n Phase 9: Normal Operation Achieved")
        logger.info("=" * 70)
        logger.info("REACTOR AT STABLE OPERATION")
        logger.info("")
        
        with self._state_manager as state:
            logger.info("Current Status:")
            logger.info(f"   • Pressure: {state.pressure:.2f} bar")
            logger.info(f"   • Control Rods: Shim={state.shim_rod}%, Reg={state.regulating_rod}%")
            logger.info(f"   • Safety Rod: {state.safety_rod}% (for SCRAM)")
            logger.info(f"   • Pumps: Primary={state.pump_primary_status}, "
                       f"Secondary={state.pump_secondary_status}, "
                       f"Tertiary={state.pump_tertiary_status}")
        
        logger.info("   • Turbine: Running at full speed")
        logger.info("   • Power Output: ~200-250 MWe")
        logger.info("")
        logger.info("🎓 EDUCATIONAL NOTES:")
        logger.info("   ✓ Startup sequence complete in ~70 seconds")
        logger.info("   ✓ Manual control TETAP AKTIF - Anda bisa adjust sesuai kebutuhan")
        logger.info("   ✓ Coba adjust control rods untuk fine tuning power")
        logger.info("   ✓ Pressure dapat disesuaikan (UP/DOWN buttons)")
        logger.info("   ✓ Emergency button siap untuk SCRAM kapan saja")
        logger.info("")
        logger.info("Silakan lanjutkan dengan kontrol manual")
        logger.info("=" * 70)
        
        self._current_phase = SimPhase.COMPLETE
        logger.info("\n Auto simulation complete")
        logger.info("   Mode: MANUAL (operator control active)")
