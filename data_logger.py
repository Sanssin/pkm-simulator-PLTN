import socket
import json
import csv
import time
import os
import signal
import sys
from datetime import datetime

# Konfigurasi Koneksi UDP
UDP_IP = "127.0.0.1"
UDP_PORT = 9997 # Port 9997 sudah tersedia dan tidak dipakai oleh touch_panel (9998)
CSV_FILENAME = "data_riset_lofa.csv"

def signal_handler(sig, frame):
    print("\n[INFO] Pengambilan data dihentikan. File CSV telah disimpan dengan aman.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main():
    print("=" * 60)
    print("☢️  PLTN Simulator - Data Logger KTI (Skenario LOFA) ☢️")
    print("=" * 60)
    
    # 1. Buka socket UDP untuk mendengarkan broadcast dari physics engine
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Tambahkan opsi SO_REUSEPORT dan SO_REUSEADDR agar bisa berbagi port dengan video_display_app
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        
    try:
        sock.bind((UDP_IP, UDP_PORT))
        print(f"[INFO] Mendengarkan data secara Real-Time pada UDP {UDP_IP}:{UDP_PORT} (Berbagi port dengan Video Display)...")
    except OSError as e:
        print(f"[ERROR] Gagal bind ke Port {UDP_PORT}: {e}")
        sys.exit(1)

    # 2. Persiapkan file CSV
    file_exists = os.path.isfile(CSV_FILENAME)
    
    with open(CSV_FILENAME, mode='a', newline='') as csv_file:
        fieldnames = [
            'waktu_lokal', 'waktu_sistem_detik', 
            'pompa_primer_status', 
            'suhu_core_celcius', 'suhu_pendingin_primer_celcius', 
            'daya_termal_kw', 'posisi_safety_rod', 
            'tekanan_pressurizer_bar',
            'status_scram'
        ]
        
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        
        # Tulis header jika file baru dibuat
        if not file_exists:
            writer.writeheader()
            print(f"[INFO] Membuat file baru: {CSV_FILENAME}")
        else:
            print(f"[INFO] Melanjutkan penulisan ke file: {CSV_FILENAME}")
            
        print("[INFO] Menunggu data dari Simulator... (Tekan CTRL+C untuk berhenti)\n")
        
        start_time = None
        data_count = 0
        
        try:
            while True:
                # Menerima data payload (max 4096 bytes)
                data, addr = sock.recvfrom(4096)
                
                try:
                    state = json.loads(data.decode('utf-8'))
                    
                    if start_time is None:
                        start_time = time.time()
                    
                    # Waktu berjalan relatif sejak script dijalankan
                    elapsed_time = round(time.time() - start_time, 1)
                    current_time_str = datetime.now().strftime('%H:%M:%S')
                    
                    # Ekstrak data yang di-broadcast oleh raspi_main_panel.py
                    # Catatan: Karena kita tidak mengubah program utama, kita hanya bisa
                    # mengambil data yang kebetulan memang sudah di-broadcast.
                    row = {
                        'waktu_lokal': current_time_str,
                        'waktu_sistem_detik': elapsed_time,
                        'pompa_primer_status': state.get('pump_primary', 0),
                        'suhu_core_celcius': round(state.get('temperature_core', 0.0), 2),
                        'suhu_pendingin_primer_celcius': round(state.get('temperature_coolant', 0.0), 2),
                        'daya_termal_kw': round(state.get('thermal_kw', 0.0), 2),
                        'posisi_safety_rod': round(state.get('safety_rod', 0.0), 2),
                        'tekanan_pressurizer_bar': round(state.get('pressure', 0.0), 2),
                        'status_scram': 1 if state.get('emergency', False) else 0
                    }
                    
                    # Simpan ke CSV
                    writer.writerow(row)
                    # Force write ke disk setiap detik (mencegah data hilang jika program crash)
                    csv_file.flush() 
                    
                    data_count += 1
                    
                    # Print ke terminal setiap ~1 detik (20hz log rate terlalu cepat untuk mata)
                    if data_count % 20 == 0:
                        scram_txt = "🚨 SCRAM!" if row['status_scram'] else "✅ Normal"
                        pump_txt = "🟢 ON" if row['pompa_primer_status'] else "🔴 OFF"
                        print(f"[{current_time_str}] t={elapsed_time}s | Pompa: {pump_txt} | Core: {row['suhu_core_celcius']}°C | Air Primer: {row['suhu_pendingin_primer_celcius']}°C | Tekanan: {row['tekanan_pressurizer_bar']} bar | SCRAM: {scram_txt}")
                        
                except json.JSONDecodeError:
                    pass # Abaikan jika ada paket rusak
                except KeyError as e:
                    pass # Abaikan jika format JSON tidak sesuai ekspektasi
                    
        except KeyboardInterrupt:
            # Ini akan ditangkap oleh signal_handler
            pass

if __name__ == "__main__":
    main()
