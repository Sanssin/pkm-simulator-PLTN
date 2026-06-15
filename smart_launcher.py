import subprocess
import sys
import time
import argparse
import platform

def main():
    parser = argparse.ArgumentParser(description="Smart Watchdog Launcher for PLTN GUI Apps")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="The python script to run and auto-restart")
    parser.add_argument("--delay", type=int, default=3, help="Delay in seconds before restarting on crash")
    
    args = parser.parse_args()
    
    if not args.command:
        print("Error: No command specified.")
        print("Usage: python smart_launcher.py python touch_panel_app.py --launch")
        sys.exit(1)
        
    cmd = args.command
    
    # If the user passed something like: smart_launcher.py touch_panel_app.py
    # and forgot the 'python', let's auto prepend it if it's a .py file
    if cmd[0].endswith(".py"):
        python_exec = "python" if platform.system() == "Windows" else "python3"
        cmd = [python_exec] + cmd

    print(f"🔄 [Smart Launcher] Memulai pengawasan untuk perintah: {' '.join(cmd)}")
    print(f"🔄 [Smart Launcher] Jika program GUI tertutup (kabel HDMI dicabut/error), program akan otomatis restart.")
    
    retry_count = 0
    while True:
        try:
            print(f"▶️  [Smart Launcher] Menjalankan program...")
            process = subprocess.Popen(cmd)
            process.wait()
            
            # If the user explicitly stopped it or it exited cleanly with code 0 (and it's not a GUI crash)
            if process.returncode == 0:
                print(f"✅ [Smart Launcher] Program selesai dengan normal (Exit Code 0).")
                # Usually GUI apps run forever, if it exited 0, maybe user closed it intentionally.
                # However, for a kiosk display, we might even want to restart on 0. 
                # But let's restart anyway to be completely stubborn, unless interrupted.
            else:
                print(f"⚠️  [Smart Launcher] Program crash/tertutup dengan Exit Code {process.returncode}.")
                
        except KeyboardInterrupt:
            print(f"\n🛑 [Smart Launcher] Dihentikan oleh pengguna.")
            if 'process' in locals() and process.poll() is None:
                process.terminate()
            break
        except Exception as e:
            print(f"❌ [Smart Launcher] Terjadi kesalahan: {e}")
            
        retry_count += 1
        print(f"⏳ [Smart Launcher] Menunggu {args.delay} detik sebelum mencoba merestart program kembali (Percobaan #{retry_count})...")
        time.sleep(args.delay)

if __name__ == "__main__":
    main()
