import subprocess
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# === CONSTANTS ===
VIDEO_PATH = "/home/pkm/video_pltn/pwr_tutorial_ver.mp4"
TARGET_SCREEN_NAME = "HDMI-A-1" # As seen in wlr-randr for the 4K monitor
AUDIO_DEVICE = "alsa/plughw:1,0"    # Based on aplay -l (card 1: vc4hdmi0) or pulse/alsa_output.platform-fef00700.hdmi.hdmi-stereo

class VideoPlayer:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.current_video: Optional[str] = None
        self._lock = threading.Lock()

    def play(self, filename: str = VIDEO_PATH, loop: bool = True):
        """Play video non-blocking via mpv."""
        with self._lock:
            if self.is_playing() and self.current_video == filename:
                return
            
            if self.is_playing():
                # Stop existing video before starting a new one
                self._stop_internal()
                
            self.current_video = filename
            logger.info(f"[VideoPlayer] Starting video playback: {filename}")
            
            import os
            # Gunakan nama file video sebagai suffix log agar tidak bentrok
            log_suffix = os.path.basename(filename).replace('.', '_')
            log_path = f"/tmp/mpv_{log_suffix}.log"
            
            cmd = [
                "mpv",
                filename,
                "--fullscreen",
                "--no-border",
                "--window-maximized=yes",
                "--autofit=100%x100%",
                f"--fs-screen-name={TARGET_SCREEN_NAME}",
                "--ontop",
                # --vo=gpu bekerja dengan software dan hardware decoder
                "--vo=gpu",
                # --hwdec=no: force software decode agar HEVC 10-bit (yuv420p10le) tidak bluescreen
                # RPi4 v4l2m2m hanya support H.264 dan HEVC 8-bit via hardware
                "--hwdec=no",
                # Konversi 10-bit ke 8-bit sebelum output ke GPU agar warna benar
                "--vf=format=yuv420p",
                "--ao=alsa",
                f"--audio-device={AUDIO_DEVICE}",
                "--audio-fallback-to-null=yes",
                "--keep-open=yes",
                f"--log-file={log_path}"
            ]
            
            if loop:
                cmd.append("--loop-file=inf")
                
            import os
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"
            env["WAYLAND_DISPLAY"] = "wayland-0" # changed from wayland-1 as it's more common
            
            # If running as root (e.g. systemd), drop privileges to user pkm for Wayland access
            if os.geteuid() == 0:
                cmd = ['sudo', '-u', 'pkm', 'env', 'WAYLAND_DISPLAY=wayland-0', 'XDG_RUNTIME_DIR=/run/user/1000'] + cmd
                
            try:
                self.process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                logger.error(f"[VideoPlayer] Error starting mpv: {e}")

    def stop(self):
        """Stop video and cleanup process."""
        with self._lock:
            self._stop_internal()
            
    def _stop_internal(self):
        if self.process:
            logger.info("[VideoPlayer] Stopping video playback")
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.current_video = None

    def is_playing(self) -> bool:
        """Check if mpv process is still alive."""
        return self.process is not None and self.process.poll() is None
