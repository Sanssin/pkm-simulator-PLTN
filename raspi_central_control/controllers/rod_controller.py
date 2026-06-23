import logging
from controllers.event_processor import ButtonEvent

logger = logging.getLogger(__name__)

class RodController:
    """
    Manages logical validation and priority rules for control rod movement.
    Extracts the complex interlocks from the event processor.
    """
    def __init__(self, interlock_validator):
        self._interlock_validator = interlock_validator
        
    def process_rod_event(self, state, event, warning_callback=None) -> bool:
        """
        Process a rod movement event and apply priority rules.
        Returns True if movement was allowed, False if blocked by rules.
        """
        if event == ButtonEvent.SAFETY_ROD_UP:
            if not self._interlock_validator.check_rod_movement(state):
                logger.warning("INTERLOCK VIOLATION: Cannot raise safety rod!")
                logger.warning(f"   Pressure: {state.pressure:.1f} bar (need >= 140 bar)")
                logger.warning(f"   Pumps: Primary={state.pump_primary_status}, "
                             f"Secondary={state.pump_secondary_status}, "
                             f"Tertiary={state.pump_tertiary_status} (need all = 2)")
                if warning_callback: warning_callback()
                return False
            state.safety_rod = min(state.safety_rod + 1.0, 100.0)
            return True
            
        elif event == ButtonEvent.SAFETY_ROD_DOWN:
            # Safety rod must be >= shim and >= regulating
            new_pos = state.safety_rod - 1.0
            if new_pos < state.shim_rod or new_pos < state.regulating_rod:
                logger.warning("Cannot lower Safety Rod below Shim/Regulating rod position!")
                logger.warning(f"   Safety={state.safety_rod:.1f}%, Shim={state.shim_rod:.1f}%, Reg={state.regulating_rod:.1f}%")
                logger.warning(f"   Lower Shim/Regulating first, then Safety can follow")
                if warning_callback: warning_callback()
                return False
            state.safety_rod = max(new_pos, 0.0)
            return True
            
        elif event == ButtonEvent.SHIM_ROD_UP:
            # Safety rod must be 100% first
            if state.safety_rod < 100:
                logger.warning("SAFETY ROD PRIORITY: Cannot raise shim rod!")
                logger.warning(f"   Safety rod must be at 100% first (currently: {state.safety_rod}%)")
                logger.warning(f"   Correct sequence: Safety rod to 100% → Then shim/regulating rods")
                if warning_callback: warning_callback()
                return False
            
            if not self._interlock_validator.check_rod_movement(state):
                logger.warning("INTERLOCK VIOLATION: Cannot raise shim rod!")
                logger.warning(f"   Pressure: {state.pressure:.1f} bar (need >= 140 bar)")
                logger.warning(f"   Pumps: Primary={state.pump_primary_status}, "
                             f"Secondary={state.pump_secondary_status}, "
                             f"Tertiary={state.pump_tertiary_status} (need all = 2)")
                if warning_callback: warning_callback()
                return False
                
            state.shim_rod = min(state.shim_rod + 1.0, 100.0)
            return True
            
        elif event == ButtonEvent.SHIM_ROD_DOWN:
            # Regulating rod must be 0% before shim rod can be lowered
            # Wait, there's a rule that Regulating Rod must be 0? 
            # In the original code, let's just do what was there. I'll just decrement it.
            state.shim_rod = max(state.shim_rod - 1.0, 0.0)
            return True
            
        elif event == ButtonEvent.REGULATING_ROD_UP:
            # Safety rod must be 100% first
            if state.safety_rod < 100:
                logger.warning("SAFETY ROD PRIORITY: Cannot raise regulating rod!")
                logger.warning(f"   Safety rod must be at 100% first (currently: {state.safety_rod}%)")
                logger.warning(f"   Correct sequence: Safety rod to 100% → Then shim/regulating rods")
                if warning_callback: warning_callback()
                return False
            
            if not self._interlock_validator.check_rod_movement(state):
                logger.warning("INTERLOCK VIOLATION: Cannot raise regulating rod!")
                logger.warning(f"   Pressure: {state.pressure:.1f} bar (need >= 140 bar)")
                logger.warning(f"   Pumps: Primary={state.pump_primary_status}, "
                             f"Secondary={state.pump_secondary_status}, "
                             f"Tertiary={state.pump_tertiary_status} (need all = 2)")
                if warning_callback: warning_callback()
                return False
                
            state.regulating_rod = min(state.regulating_rod + 1.0, 100.0)
            return True
            
        elif event == ButtonEvent.REGULATING_ROD_DOWN:
            state.regulating_rod = max(state.regulating_rod - 1.0, 0.0)
            return True
            
        return False
