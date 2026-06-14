import psutil
import time
import subprocess
import os
import sys
import threading

def run_measurement(duration=15):
    print("Starting Central Control for baseline measurement...")
    
    # Start the backend process
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath("raspi_central_control")
    
    proc = subprocess.Popen(
        [sys.executable, "raspi_central_control/raspi_main_panel.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print(f"Backend started with PID: {proc.pid}")
    
    try:
        p = psutil.Process(proc.pid)
        print(f"Measuring for {duration} seconds...")
        
        cpu_percents = []
        
        start_time = time.time()
        # Initial call to cpu_percent to set baseline
        p.cpu_percent()
        
        while time.time() - start_time < duration:
            time.sleep(1.0)
            # Get process CPU usage (can be > 100% on multicore)
            try:
                usage = p.cpu_percent()
                cpu_percents.append(usage)
                print(f"Process CPU usage: {usage:.1f}%")
            except psutil.NoSuchProcess:
                print("Process died early.")
                break
                
        if cpu_percents:
            avg_usage = sum(cpu_percents) / len(cpu_percents)
            print("\n--- BASELINE RESULTS ---")
            print(f"Average Backend CPU Usage: {avg_usage:.2f}%")
        else:
            print("No data collected.")
            
    finally:
        print("Terminating backend...")
        proc.terminate()
        proc.wait()
        print("Done.")

if __name__ == '__main__':
    run_measurement()
