#!/usr/bin/env python3
"""
Standalone test script to verify servo wiring and pigpio on the Raspberry Pi.
"""
import time
import os
import sys

print("=== PLTN Servo Hardware Test ===")
print("Checking if pigpiod is running...")

# Check if pigpiod is running (only works on Linux/RPi)
if sys.platform == "linux" or sys.platform == "linux2":
    result = os.system("pgrep pigpiod > /dev/null")
    if result != 0:
        print("pigpiod is not running. Attempting to start it with 'sudo pigpiod'...")
        os.system("sudo pigpiod")
        time.sleep(1.5)
else:
    print("Warning: Not running on Linux. Hardware tests will fail if pigpio isn't mocked.")

try:
    import pigpio
except ImportError:
    print("Error: pigpio python library not installed.")
    print("Please run: pip install pigpio")
    sys.exit(1)

pi = pigpio.pi()
if not pi.connected:
    print("Error: Could not connect to pigpiod.")
    print("Ensure the daemon is running by typing: sudo pigpiod")
    sys.exit(1)

# Pins definition based on ActuatorManager
SAFETY_PIN = 23
SHIM_PIN = 24
REG_PIN = 25

PINS = {
    "Safety Rod": SAFETY_PIN,
    "Shim Rod": SHIM_PIN,
    "Regulating Rod": REG_PIN
}

# 500 = 0 degrees, 1500 = 90 degrees, 2500 = 180 degrees
MIN_PW = 500
MAX_PW = 2500
MID_PW = 1500

print(f"Safety: GPIO {SAFETY_PIN}, Shim: GPIO {SHIM_PIN}, Regulating: GPIO {REG_PIN}")
print("Please ensure the servos are connected to these GPIO pins.")

def smooth_move(pi, pin, start_pw, end_pw, duration=1.0, steps=50):
    pw_range = end_pw - start_pw
    delay = duration / steps
    for i in range(1, steps + 1):
        pw = start_pw + (pw_range * i / steps)
        pi.set_servo_pulsewidth(pin, int(pw))
        time.sleep(delay)

input("Press Enter to begin the test sequence...")

try:
    for name, pin in PINS.items():
        print(f"\n--- Testing {name} (GPIO {pin}) ---")
        
        print(f"  -> Moving to 0% (PW: {MIN_PW})")
        pi.set_servo_pulsewidth(pin, MIN_PW)
        time.sleep(1.0)
        
        print(f"  -> Ramping to 50% (PW: {MID_PW}) smoothly...")
        smooth_move(pi, pin, MIN_PW, MID_PW, duration=1.5, steps=75)
        time.sleep(0.5)
        
        print(f"  -> Ramping to 100% (PW: {MAX_PW}) smoothly...")
        smooth_move(pi, pin, MID_PW, MAX_PW, duration=1.5, steps=75)
        time.sleep(0.5)
        
        print("  -> Ramping back to 0% smoothly...")
        smooth_move(pi, pin, MAX_PW, MIN_PW, duration=2.0, steps=100)
        time.sleep(0.5)
        
        # Turn off PWM signal for this pin
        pi.set_servo_pulsewidth(pin, 0)

except KeyboardInterrupt:
    print("\nTest interrupted by user.")
finally:
    print("\nTurning off all servos and cleaning up...")
    for pin in PINS.values():
        pi.set_servo_pulsewidth(pin, 0)
    pi.stop()
    print("Test Complete!")
