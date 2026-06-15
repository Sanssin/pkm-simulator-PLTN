"""
InterlockValidator - Safety interlock validation for PLTN Panel Simulator.

This module provides safety checks for:
- Rod movement interlocks (pressure, pump status, emergency)
- Pump start sequence validation (correct startup order)

Thread Safety:
- All methods accept state as parameter (caller handles locking)
- Methods are stateless and can be called from any thread

Safety Note:
- These are safety-critical functions
- Changes require thorough testing
"""

import logging
from typing import Callable, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .state_manager import PanelState

logger = logging.getLogger(__name__)


# Pump status codes
PUMP_OFF = 0
PUMP_STARTING = 1
PUMP_ON = 2
PUMP_SHUTTING_DOWN = 3


class InterlockValidator:
    """
    Validates safety interlocks for PLTN simulator.
    
    Interlock Logic v3.4:
    - Rod movement requires: pressure >= 140 bar, all pumps ON, no emergency
    - Pump start requires: pressure >= 40 bar, correct sequence (Tertiary → Secondary → Primary)
    
    Usage:
        validator = InterlockValidator(on_violation=buzzer.sound_warning)
        
        # Check rod movement
        if validator.check_rod_movement(state):
            state.safety_rod += 1
        
        # Check pump start
        if validator.check_pump_start(state, "Primary"):
            state.pump_primary_status = PUMP_STARTING
    """
    
    # Interlock thresholds (in bar)
    MIN_PRESSURE_FOR_ROD_MOVEMENT = 140.0
    MIN_PRESSURE_FOR_PUMP_START = 40.0
    
    # LOFA safety thresholds (in Celsius)
    MAX_CORE_TEMPERATURE_LOFA = 300.0
    
    def __init__(self, 
                 on_interlock_violation: Optional[Callable[[str], None]] = None,
                 on_procedure_violation: Optional[Callable[[str], None]] = None):
        """
        Initialize InterlockValidator.
        
        Args:
            on_interlock_violation: Callback when rod movement interlock fails.
                                   Receives reason string.
            on_procedure_violation: Callback when pump sequence violation occurs.
                                   Receives reason string.
        """
        self._on_interlock_violation = on_interlock_violation
        self._on_procedure_violation = on_procedure_violation
    
    def check_rod_movement(self, state: 'PanelState', rod_type: str = "regulating") -> bool:
        """
        Check if rod movement is allowed.
        
        Safety rod has special rules - can always move down, but requires
        interlock for upward movement.
        
        Shim and regulating rods require full interlock satisfaction.
        
        Args:
            state: Current panel state
            rod_type: "safety", "shim", or "regulating"
        
        Returns:
            True if rod movement is allowed, False otherwise
        """
        # Safety rod down is always allowed (emergency insertion)
        # This check is handled by caller based on direction
        
        return self._check_interlock_conditions(state)
    
    def check_safety_rod_up(self, state: 'PanelState') -> bool:
        """
        Check if safety rod can be raised.
        
        Safety rod withdrawal requires same interlocks as other rods.
        
        Args:
            state: Current panel state
            
        Returns:
            True if safety rod can be raised
        """
        return self._check_interlock_conditions(state)
    
    def _check_interlock_conditions(self, state: 'PanelState') -> bool:
        """
        Internal check for all interlock conditions.
        
        INTERLOCK LOGIC v3.4:
        - Pressure >= 140 bar (operating pressure)
        - No emergency active
        - All three pumps in ON state (status == 2)
        
        Args:
            state: Current panel state (caller must hold lock)
            
        Returns:
            True if all conditions satisfied
        """
        # Check 1: Pressure >= 140 bar
        if state.pressure < self.MIN_PRESSURE_FOR_ROD_MOVEMENT:
            reason = f"Pressure too low ({state.pressure:.2f} bar < 140 bar)"
            logger.debug(f"Interlock: {reason}")
            if self._on_interlock_violation:
                self._on_interlock_violation(reason)
            return False
        
        # Check 2: No emergency active
        if state.emergency_active:
            reason = "Emergency shutdown active"
            logger.debug(f"Interlock: {reason}")
            if self._on_interlock_violation:
                self._on_interlock_violation(reason)
            return False
        
        # Check 3: All pumps must be ON (status == 2)
        if state.pump_primary_status != PUMP_ON:
            reason = f"Primary pump not ON (status={state.pump_primary_status})"
            logger.debug(f"Interlock: {reason}")
            if self._on_interlock_violation:
                self._on_interlock_violation(reason)
            return False
        
        if state.pump_secondary_status != PUMP_ON:
            reason = f"Secondary pump not ON (status={state.pump_secondary_status})"
            logger.debug(f"Interlock: {reason}")
            if self._on_interlock_violation:
                self._on_interlock_violation(reason)
            return False
        
        if state.pump_tertiary_status != PUMP_ON:
            reason = f"Tertiary pump not ON (status={state.pump_tertiary_status})"
            logger.debug(f"Interlock: {reason}")
            if self._on_interlock_violation:
                self._on_interlock_violation(reason)
            return False
        
        # All checks passed
        return True
    
    def check_pump_start(self, state: 'PanelState', pump_name: str) -> bool:
        """
        Check if pump can be started safely.
        
        Safety requirements:
        1. Pressure >= 40 bar (prevent cavitation)
        2. Correct startup sequence: Tertiary → Secondary → Primary
        
        Args:
            state: Current panel state (caller must hold lock)
            pump_name: "Primary", "Secondary", or "Tertiary"
            
        Returns:
            True if safe to start pump
        """
        # Check 1: Pressure must be >= 40 bar
        if state.pressure < self.MIN_PRESSURE_FOR_PUMP_START:
            reason = (f"Pressure too low for {pump_name} pump start! "
                      f"Current: {state.pressure:.2f} bar, Required: >= 40 bar")
            logger.warning(f"PUMP START BLOCKED: {pump_name} pump")
            logger.warning(f"   Reason: {reason}")
            logger.warning(f"   Action: Raise pressure to 40 bar before starting pumps")
            
            if self._on_procedure_violation:
                self._on_procedure_violation(reason)
            return False
        
        # Check 2: Enforce correct pump sequence
        if not self._check_pump_sequence(state, pump_name):
            return False
        
        # All checks passed
        logger.info(f"Pump start authorized: {pump_name}")
        return True
    
    def _check_pump_sequence(self, state: 'PanelState', pump_name: str) -> bool:
        """
        Check pump startup sequence.
        
        Correct sequence: Tertiary → Secondary → Primary
        
        Args:
            state: Current panel state
            pump_name: Pump being started
            
        Returns:
            True if sequence is valid
        """
        if pump_name == "Secondary":
            # Secondary can only start if Tertiary is ON
            if state.pump_tertiary_status != PUMP_ON:
                reason = (f"Cannot start Secondary pump - "
                         f"Tertiary pump must be ON first! "
                         f"(Tertiary status: {state.pump_tertiary_status})")
                logger.warning(f"PUMP SEQUENCE VIOLATION: {reason}")
                logger.warning("   Correct sequence: Tertiary → Secondary → Primary")
                
                if self._on_procedure_violation:
                    self._on_procedure_violation(reason)
                return False
        
        elif pump_name == "Primary":
            # Primary can only start if BOTH Tertiary AND Secondary are ON
            if state.pump_tertiary_status != PUMP_ON:
                reason = (f"Cannot start Primary pump - "
                         f"Tertiary pump must be ON first! "
                         f"(Tertiary status: {state.pump_tertiary_status})")
                logger.warning(f"PUMP SEQUENCE VIOLATION: {reason}")
                logger.warning("   Correct sequence: Tertiary → Secondary → Primary")
                
                if self._on_procedure_violation:
                    self._on_procedure_violation(reason)
                return False
            
            if state.pump_secondary_status != PUMP_ON:
                reason = (f"Cannot start Primary pump - "
                         f"Secondary pump must be ON first! "
                         f"(Secondary status: {state.pump_secondary_status})")
                logger.warning(f"PUMP SEQUENCE VIOLATION: {reason}")
                logger.warning("   Correct sequence: Tertiary → Secondary → Primary")
                
                if self._on_procedure_violation:
                    self._on_procedure_violation(reason)
                return False
        
        # Tertiary has no prerequisites
        return True
    
    def get_interlock_status(self, state: 'PanelState') -> Tuple[bool, str]:
        """
        Get detailed interlock status.
        
        Args:
            state: Current panel state
            
        Returns:
            Tuple of (is_satisfied, reason_if_not)
        """
        if state.pressure < self.MIN_PRESSURE_FOR_ROD_MOVEMENT:
            return False, f"Pressure {state.pressure:.2f} bar < 140 bar required"
        
        if state.emergency_active:
            return False, "Emergency shutdown active"
        
        if state.pump_primary_status != PUMP_ON:
            return False, f"Primary pump status={state.pump_primary_status} (need 2=ON)"
        
        if state.pump_secondary_status != PUMP_ON:
            return False, f"Secondary pump status={state.pump_secondary_status} (need 2=ON)"
        
        if state.pump_tertiary_status != PUMP_ON:
            return False, f"Tertiary pump status={state.pump_tertiary_status} (need 2=ON)"
        
        return True, "All conditions satisfied"
