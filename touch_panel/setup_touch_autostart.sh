#!/bin/bash
# ==============================================================================
# Script Setup Autostart Touchscreen 10.01" PLTN Simulator
# Menjamin touchscreen otomatis muncul di layar 10.01 inch saat selesai booting
# ==============================================================================

set -e

CURRENT_USER=$(whoami)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=========================================================="
echo " Konfigurasi Autostart Layar Touchscreen 10.01 Inch PLTN"
echo " User: $CURRENT_USER | Direktori: $PROJECT_DIR"
echo "=========================================================="

# 1. Pastikan folder autostart desktop ada
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

# 2. Buat file autostart desktop entry
DESKTOP_FILE="$AUTOSTART_DIR/pltn-touch.desktop"
echo "Menulis desktop autostart ke: $DESKTOP_FILE"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=PLTN Touch Panel
Comment=HMI Touchscreen Panel for PLTN Simulator on 10.01 inch Display
Exec=/usr/bin/python3 $PROJECT_DIR/smart_launcher.py $PROJECT_DIR/touch_panel/touch_panel_app.py --launch
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

chmod +x "$DESKTOP_FILE"
echo "✅ Desktop autostart berhasil dipasang."

# 3. Opsi instalasi systemd service jika diinginkan
SERVICE_FILE="/etc/systemd/system/pltn-touch.service"
if [ "$1" == "--systemd" ]; then
    echo "Memasang systemd service ke $SERVICE_FILE..."
    sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=PLTN Touchscreen HMI Panel (10.01 inch Display)
After=graphical.target network.target pltn-controller.service
Wants=graphical.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$(id -gn $CURRENT_USER)
WorkingDirectory=$PROJECT_DIR
Environment=\"DISPLAY=:0\"
Environment=\"XAUTHORITY=$HOME/.Xauthority\"
Environment=\"WAYLAND_DISPLAY=wayland-0\"
Environment=\"XDG_RUNTIME_DIR=/run/user/$(id -u $CURRENT_USER)\"
ExecStart=/usr/bin/python3 $PROJECT_DIR/smart_launcher.py $PROJECT_DIR/touch_panel/touch_panel_app.py --launch
Restart=always
RestartSec=3
CPUAffinity=2,3

[Install]
WantedBy=graphical.target
EOF"

    sudo systemctl daemon-reload
    sudo systemctl enable pltn-touch.service
    echo "✅ Systemd service pltn-touch.service berhasil diaktifkan."
fi

echo ""
echo "🎉 Setup selesai! Touchscreen 10.01\" akan langsung muncul setelah sistem booting."
echo "Untuk menguji jalankan: python3 $PROJECT_DIR/touch_panel/touch_panel_app.py"
