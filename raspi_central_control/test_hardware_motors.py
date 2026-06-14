import time
import sys
import logging

# Setup basic logging to see output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from controllers.motor_controller import MotorController

def test_motor(motor_controller, motor_name):
    logger.info(f"\n--- Testing {motor_name} ---")
    logger.info("Ramping up speed from 0% to 100% in 5 seconds...")
    for i in range(0, 101, 5):
        motor_controller.set_speed(motor_name, i)
        time.sleep(0.25)
    
    logger.info(f"{motor_name} running at 100% for 3 seconds...")
    time.sleep(3)
    
    logger.info("Ramping down speed from 100% to 0% in 5 seconds...")
    for i in range(100, -1, -5):
        motor_controller.set_speed(motor_name, i)
        time.sleep(0.25)
    
    motor_controller.set_speed(motor_name, 0)
    logger.info(f"{motor_name} stopped.\n")

def main():
    logger.info("Initializing Motor Controller...")
    mc = MotorController()
    
    if mc.mock_mode:
        logger.warning("pigpio is not available or daemon is not running! Test will only run in MOCK mode.")
        logger.info("To test on real hardware, make sure you run 'sudo pigpiod' first.")
    
    try:
        test_motor(mc, 'pump_primary')
        time.sleep(1)
        test_motor(mc, 'pump_secondary')
        time.sleep(1)
        test_motor(mc, 'pump_tertiary')
        time.sleep(1)
        test_motor(mc, 'turbine')
        
        logger.info("Testing all motors simultaneously at 50% for 5 seconds...")
        mc.set_speed('pump_primary', 50)
        mc.set_speed('pump_secondary', 50)
        mc.set_speed('pump_tertiary', 50)
        mc.set_speed('turbine', 50)
        time.sleep(5)
        
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user.")
    finally:
        logger.info("Stopping all motors and cleaning up...")
        mc.cleanup()
        logger.info("Hardware Test Complete.")

if __name__ == "__main__":
    main()
