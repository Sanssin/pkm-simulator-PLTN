import psutil
import time
import subprocess
import os
import sys

def run_stress_test(duration=30):
    print("=" * 60)
    print("Starting PLTN Simulator Stress Test")
    print("Launching all components: Backend + Touch UI + Video UI")
    print("=" * 60)
    
    env = os.environ.copy()
    if sys.platform != "win32" and "DISPLAY" not in env:
        env["DISPLAY"] = ":0"  # For Raspberry Pi GUI
    
    # Start Backend
    backend_env = env.copy()
    backend_env["PYTHONPATH"] = os.path.abspath("raspi_central_control")
    proc_backend = subprocess.Popen(
        [sys.executable, "raspi_central_control/raspi_main_panel.py"],
        env=backend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"-> Backend started (PID: {proc_backend.pid})")
    time.sleep(2)  # Give backend time to create /tmp/ files
    
    # Start Touch UI
    proc_touch = subprocess.Popen(
        [sys.executable, "touch_panel/touch_panel_app.py", "--launch", "--windowed"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"-> Touch UI started (PID: {proc_touch.pid})")
    time.sleep(1)
    
    # Start Video UI
    proc_video = subprocess.Popen(
        [sys.executable, "pltn_video_display/video_display_app.py"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"-> Video UI started (PID: {proc_video.pid})")
    
    try:
        p_backend = psutil.Process(proc_backend.pid)
        p_touch = psutil.Process(proc_touch.pid)
        p_video = psutil.Process(proc_video.pid)
        
        # Initial calls to clear baseline
        p_backend.cpu_percent()
        p_touch.cpu_percent()
        p_video.cpu_percent()
        
        print(f"\nMeasuring system CPU load for {duration} seconds...")
        
        metrics = {"backend": [], "touch": [], "video": [], "total_sys": []}
        
        start_time = time.time()
        while time.time() - start_time < duration:
            time.sleep(1.0)
            
            try:
                b_cpu = p_backend.cpu_percent()
                t_cpu = p_touch.cpu_percent()
                v_cpu = p_video.cpu_percent()
                
                # Measure overall system core loads
                sys_cores = psutil.cpu_percent(percpu=True)
                sys_avg = sum(sys_cores) / len(sys_cores)
                
                # Measure thermal if available (Raspberry Pi)
                temp_str = "N/A"
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if "cpu_thermal" in temps:
                        temp_str = f"{temps['cpu_thermal'][0].current:.1f}°C"
                
                metrics["backend"].append(b_cpu)
                metrics["touch"].append(t_cpu)
                metrics["video"].append(v_cpu)
                metrics["total_sys"].append(sys_avg)
                
                print(f"Backend: {b_cpu:4.1f}% | Touch: {t_cpu:4.1f}% | Video: {v_cpu:4.1f}% | Sys Avg: {sys_avg:4.1f}% | Temp: {temp_str}")
                
            except psutil.NoSuchProcess:
                print("\nOne of the processes died early!")
                break
                
        print("\n" + "=" * 60)
        print("--- STRESS TEST RESULTS ---")
        if metrics["backend"]:
            print(f"Average Backend CPU: {sum(metrics['backend'])/len(metrics['backend']):.2f}%")
            print(f"Average Touch UI CPU: {sum(metrics['touch'])/len(metrics['touch']):.2f}%")
            print(f"Average Video UI CPU: {sum(metrics['video'])/len(metrics['video']):.2f}%")
            print(f"Average SYSTEM CPU:   {sum(metrics['total_sys'])/len(metrics['total_sys']):.2f}%")
        else:
            print("No data collected.")
        print("=" * 60)
            
    finally:
        print("\nTerminating all processes...")
        proc_video.terminate()
        proc_touch.terminate()
        proc_backend.terminate()
        
        proc_video.wait()
        proc_touch.wait()
        proc_backend.wait()
        print("Done.")

if __name__ == '__main__':
    run_stress_test()
