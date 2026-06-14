#!/usr/bin/env python3
import os
import sys
import time

try:
    import psutil
except ImportError:
    print("Please install psutil: pip install psutil")
    sys.exit(1)

def clear_screen():
    # ANSI escape code to clear screen and move cursor to top-left
    print("\033[H\033[J", end="")

def get_process_info(keyword):
    """Find a process by keyword and return its stats."""
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(p.info['cmdline'] or [])
            if keyword in cmd and "cpu_dashboard.py" not in cmd and "measure_baseline" not in cmd:
                # Found it
                cpu_usage = p.cpu_percent(interval=None)
                affinity = p.cpu_affinity() if hasattr(p, 'cpu_affinity') else "N/A"
                nice = p.nice() if hasattr(p, 'nice') else "N/A"
                return {
                    "pid": p.info['pid'],
                    "cpu": cpu_usage,
                    "affinity": affinity,
                    "nice": nice,
                    "status": p.status()
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return None

def main():
    # Initialize psutil cpu percent
    psutil.cpu_percent(percpu=True)
    
    # Initialize process cpu_percent to avoid 0.0 on first read
    for p in psutil.process_iter(['cmdline']):
        try:
            p.cpu_percent(interval=None)
        except:
            pass
            
    time.sleep(0.5)
    
    while True:
        try:
            clear_screen()
            print("="*60)
            print(" 🚀 PLTN SIMULATOR CPU DASHBOARD 🚀 ".center(60, "="))
            print("="*60)
            
            # Overall System Load
            sys_cpu = psutil.cpu_percent()
            print(f" System Total Load: {sys_cpu:.1f}%")
            
            # CPU Core Load
            cores = psutil.cpu_percent(percpu=True)
            print("\n[ HARDWARE CORES ]")
            for i, load in enumerate(cores):
                bar = "█" * int(load / 5)
                bar = bar.ljust(20, "░")
                print(f" Core {i}: |{bar}| {load:5.1f}%")
            
            # System Temperature (Raspberry Pi specific)
            print("\n[ THERMAL ]")
            try:
                temp = psutil.sensors_temperatures()
                if 'cpu_thermal' in temp:
                    t_val = temp['cpu_thermal'][0].current
                    print(f" CPU Temp: {t_val:.1f}°C")
                    if t_val > 80:
                        print(" ⚠️ WARNING: THERMAL THROTTLING IMMINENT!")
                else:
                    print(" CPU Temp: N/A (Hanya tersedia di Raspberry Pi Linux)")
            except:
                print(" CPU Temp: N/A")
                
            # Process Info
            print("\n[ SIMULATOR PROCESSES ]")
            targets = {
                "Backend": "raspi_main_panel.py",
                "Touch UI": "touch_panel_app.py",
                "Video UI": "video_display_app.py"
            }
            
            print(f" {'Component':<10} | {'PID':<6} | {'CPU%':<6} | {'Affinity':<12} | {'Priority'}")
            print("-" * 60)
            
            for name, keyword in targets.items():
                info = get_process_info(keyword)
                if info:
                    aff = str(info['affinity']).replace(" ", "")
                    # Tweak nice value formatting
                    if info['nice'] == 'N/A':
                        pri = 'N/A'
                    elif info['nice'] < 0 or info['nice'] == psutil.HIGH_PRIORITY_CLASS:
                        pri = f"{info['nice']} (HIGH)"
                    else:
                        pri = f"{info['nice']} (NORMAL)"
                        
                    print(f" {name:<10} | {info['pid']:<6} | {info['cpu']:>5.1f}% | {aff:<12} | {pri}")
                else:
                    print(f" {name:<10} | {'---':<6} | {'---':<6} | {'---':<12} | Not Running")
                    
            print("\n" + "="*60)
            print("Tekan Ctrl+C untuk keluar...")
            
            time.sleep(1.0)
        except KeyboardInterrupt:
            clear_screen()
            print("Keluar dari CPU Dashboard.")
            break

if __name__ == "__main__":
    main()
