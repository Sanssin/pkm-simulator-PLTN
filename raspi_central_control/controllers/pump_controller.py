import time
import logging
from .interlock_validator import PUMP_ON

logger = logging.getLogger(__name__)

class PumpController:
    """
    Manages pump state transitions (STARTING -> ON, SHUTTING_DOWN -> OFF) with timing.
    """
    
    def __init__(self, transition_time: float = 3.0):
        self.transition_time = transition_time

    def update(self, state):
        """
        Updates pump transition states. Should be called periodically.
        """
        current_time = time.time()
        
        for pump_name in ['primary', 'secondary', 'tertiary']:
            status_attr = f'pump_{pump_name}_status'
            transition_attr = f'pump_{pump_name}_transition_start'
            
            status = getattr(state, status_attr)
            transition_start = getattr(state, transition_attr)
            
            if status == 1:  # STARTING
                if transition_start == 0:
                    setattr(state, transition_attr, current_time)
                elif current_time - transition_start >= self.transition_time:
                    setattr(state, status_attr, PUMP_ON)
                    setattr(state, transition_attr, 0)
            elif status == 3:  # SHUTTING_DOWN
                if transition_start == 0:
                    setattr(state, transition_attr, current_time)
                elif current_time - transition_start >= self.transition_time:
                    setattr(state, status_attr, 0)  # OFF
                    setattr(state, transition_attr, 0)
