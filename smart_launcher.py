import subprocess
import sys
import time
import argparse
import platform
import os
import glob

def get_connected_hdmi_count():
    """Menghitung jumlah monitor HDMI yang berstatus 'connected'."""
    if platform.system() == "Windows":
         return 1 # Fallback untuk Windows
         
    count = 0
    # Mencari semua port HDMI di DRM
    for status_file in glob.glob('/sys/class/drm/*HDMI*/status'):
        try:
            with open(status_file, 'r') as f:
                status = f.read().strip()
                if status == 'connected':
                    count += 1
        except Exception:
            pass
    return count

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
    if cmd[0].endswith(".py"):
        python_exec = "python" if platform.system() == "Windows" else "python3"
        cmd = [python_exec] + cmd

    print(f"🔄 [Smart Launcher] Memulai pengawasan untuk perintah: {' '.join(cmd)}")
    print(f"🔄 [Smart Launcher] Pengawasan Kabel HDMI Aktif (akan restart jika dicabut/dipasang).")
    
    retry_count = 0
    while True:
        try:
            # Cek status HDMI saat program baru mulai
            initial_hdmi_count = get_connected_hdmi_count()
            print(f"🖥️  [Smart Launcher] Monitor HDMI terdeteksi: {initial_hdmi_count}")
            
            print(f"▶️  [Smart Launcher] Menjalankan program...")
            process = subprocess.Popen(cmd)
            
            # Polling loop untuk memantau koneksi HDMI dan status proses
            while process.poll() is None:
                current_hdmi_count = get_connected_hdmi_count()
                
                # Jika jumlah monitor HDMI berubah (dicabut atau dipasang baru)
                if current_hdmi_count != initial_hdmi_count:
                    print(f"\n🔌 [Smart Launcher] PERINGATAN: Perubahan monitor terdeteksi! ({initial_hdmi_count} -> {current_hdmi_count})")
                    print(f"🛑 [Smart Launcher] Mematikan GUI agar dapat di-remap ulang ke layar yang benar...")
                    process.terminate()
                    
                    # Beri waktu sistem operasi (Wayland/Sway) untuk mengenali ulang display
                    time.sleep(2)
                    
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill() # Force kill jika bandel
                    break # Keluar dari loop polling untuk merestart
                    
                time.sleep(1) # Cek setiap 1 detik
            
            if process.returncode == 0:
                print(f"✅ [Smart Launcher] Program selesai dengan normal (Exit Code 0).")
            elif process.returncode is not None:
                print(f"⚠️  [Smart Launcher] Program crash/tertutup dengan Exit Code {process.returncode}.")
                
        except KeyboardInterrupt:
            print(f"\n🛑 [Smart Launcher] Dihentikan oleh pengguna.")
            if 'process' in locals() and process.poll() is None:
                process.terminate()
            break
        except Exception as e:
            print(f"❌ [Smart Launcher] Terjadi kesalahan: {e}")
            
        retry_count += 1
        print(f"⏳ [Smart Launcher] Menunggu {args.delay} detik sebelum restart (Percobaan #{retry_count})...")
        time.sleep(args.delay)

if __name__ == "__main__":
    main()
