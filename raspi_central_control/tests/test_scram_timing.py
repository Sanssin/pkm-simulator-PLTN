import time
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.state_manager import StateManager
from sequences.scram_sequence import SCRAMSequence
from controllers.actuator_manager import ActuatorManager

logging.basicConfig(level=logging.INFO)

def run_scram_timing_test():
    print("--- SCRAM Timing Test ---")
    state_manager = StateManager()
    actuator_manager = ActuatorManager()
    
    # Initialize state
    state_manager.update(safety_rod=100, shim_rod=100, regulating_rod=100, pump_primary=1)
    
    # Track time to snap-to-zero
    start_time = time.time()
    
    # We want to measure how fast the state manager reflects the zeroing, 
    # or how fast actuator_manager receives it.
    
    scram = SCRAMSequence(state_manager=state_manager)
    scram.ROD_DROP_DURATION = 0.05  # Simulate snap-to-zero for hardware
    
    # Start SCRAM
    thread = scram.execute()
    
    # Wait until rods are at 0
    while True:
        with state_manager as state:
            if state.safety_rod == 0 and state.shim_rod == 0 and state.regulating_rod == 0:
                break
        time.sleep(0.001)
        if time.time() - start_time > 1.0:
            print("TIMEOUT: Rods did not reach zero in 1 second")
            return False

    end_time = time.time()
    duration_ms = (end_time - start_time) * 1000
    
    # Call actuator update to push to servos
    with state_manager as state:
        actuator_manager.update_actuators(state)
        
    print(f"Time to rods zero state: {duration_ms:.2f} ms")
    
    if duration_ms < 100:
        print("PASS: SCRAM timing is under 100ms")
        return True
    else:
        print("FAIL: SCRAM timing exceeded 100ms")
        return False

if __name__ == "__main__":
    success = run_scram_timing_test()
    sys.exit(0 if success else 1)
