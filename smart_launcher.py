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
    drm_files = glob.glob('/sys/class/drm/*HDMI*/status')
    if not drm_files:
        # Fallback jika nama port DRM bukan standard HDMI (misal DSI atau format lain)
        drm_files = glob.glob('/sys/class/drm/*/status')

    for status_file in drm_files:
        try:
            with open(status_file, 'r') as f:
                status = f.read().strip()
                if status == 'connected':
                    count += 1
        except Exception:
            pass
    return count

def setup_gui_environment():
    """Memastikan variabel display environment tersedia untuk Linux GUI."""
    env = os.environ.copy()
    if platform.system() != "Windows":
        if "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env:
            if os.path.exists("/tmp/.X11-unix/X0"):
                env["DISPLAY"] = ":0"
            elif os.path.exists(f"/run/user/{os.getuid() if hasattr(os, 'getuid') else 1000}/wayland-0"):
                env["WAYLAND_DISPLAY"] = "wayland-0"
            else:
                env["DISPLAY"] = ":0"

        if "XDG_RUNTIME_DIR" not in env:
            uid = os.getuid() if hasattr(os, "getuid") else 1000
            runtime_dir = f"/run/user/{uid}"
            if os.path.exists(runtime_dir):
                env["XDG_RUNTIME_DIR"] = runtime_dir

        if "XAUTHORITY" not in env:
            home = os.path.expanduser("~")
            xauth = os.path.join(home, ".Xauthority")
            if os.path.exists(xauth):
                env["XAUTHORITY"] = xauth
    return env

def main():
    parser = argparse.ArgumentParser(description="Smart Watchdog Launcher for PLTN GUI Apps")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="The python script to run and auto-restart")
    parser.add_argument("--delay", type=int, default=3, help="Delay in seconds before restarting on crash")
    parser.add_argument("--boot-wait", type=int, default=8, help="Max wait in seconds for HDMI on initial boot")
    
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
    
    # Pada saat booting baru selesai, tunggu hingga HDMI terdeteksi stabil
    if platform.system() != "Windows" and args.boot_wait > 0:
        print(f"⏳ [Smart Launcher] Menunggu inisialisasi monitor HDMI saat booting (maks {args.boot_wait}s)...")
        for _ in range(args.boot_wait):
            hdmi_now = get_connected_hdmi_count()
            if hdmi_now > 0:
                break
            time.sleep(1)

    retry_count = 0
    while True:
        try:
            # Cek status HDMI saat program baru mulai
            initial_hdmi_count = get_connected_hdmi_count()
            print(f"🖥️  [Smart Launcher] Monitor HDMI terdeteksi: {initial_hdmi_count}")
            
            env = setup_gui_environment()
            print(f"▶️  [Smart Launcher] Menjalankan program...")
            process = subprocess.Popen(cmd, env=env)
            
            # Polling loop untuk memantau koneksi HDMI dan status proses
            debounce_change_count = 0
            while process.poll() is None:
                current_hdmi_count = get_connected_hdmi_count()
                
                # Jika jumlah monitor HDMI berubah (dicabut atau dipasang baru)
                if current_hdmi_count != initial_hdmi_count:
                    debounce_change_count += 1
                    # Debounce 2 detik berturut-turut untuk menghindari noise transien kernel
                    if debounce_change_count >= 2:
                        print(f"\n🔌 [Smart Launcher] PERINGATAN: Perubahan monitor terdeteksi stabil! ({initial_hdmi_count} -> {current_hdmi_count})")
                        print(f"🛑 [Smart Launcher] Mematikan GUI agar dapat di-remap ulang ke layar yang benar...")
                        process.terminate()
                        
                        # Beri waktu sistem operasi untuk mengenali ulang display
                        time.sleep(2)
                        
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        break
                else:
                    debounce_change_count = 0
                    
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
