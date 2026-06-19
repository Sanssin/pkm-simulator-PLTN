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

    def play(self, filename: str = VIDEO_PATH, loop: bool = True, extra_mpv_args: list = None):
        """Play video non-blocking via mpv.
        
        Args:
            filename: Path to video file
            loop: If True, loop the video indefinitely
            extra_mpv_args: Additional mpv arguments to override defaults
                            (e.g. ['--vo=gpu', '--gpu-api=opengl', '--hwdec=no'] for HEVC 10-bit)
        """
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
            
            # Base command — kembalikan hwdec direct
            cmd = [
                "mpv",
                filename,
                "--fullscreen",
                "--no-border",
                "--window-maximized=yes",
                "--autofit=100%x100%",
                f"--fs-screen-name={TARGET_SCREEN_NAME}",
                "--ontop",
                "--vo=dmabuf-wayland",   # Penting untuk Wayland agar tidak blackscreen
                "--hwdec=v4l2m2m",       # Hardware decode murni (copy mode gagal di Wayland DMABUF)
                "--no-pause",
                "--video-sync=display-resample", # Sinkronisasi audio dengan refresh rate layar
                f"--log-file={log_path}"
            ]
            
            # Override flags jika disediakan (misal untuk HEVC 10-bit yang butuh software decode)
            if extra_mpv_args:
                # Hapus default vo/hwdec dari base command, ganti dengan yang disediakan
                cmd = [c for c in cmd if not c.startswith("--vo=") and not c.startswith("--hwdec=")]
                cmd.extend(extra_mpv_args)
            
            if loop:
                cmd.append("--loop-file=inf")
                cmd.append("--keep-open=yes")
                
            import os
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"
            env["WAYLAND_DISPLAY"] = "wayland-0" # changed from wayland-1 as it's more common
            env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
            
            # If running as root (e.g. systemd), drop privileges to user pkm for Wayland access
            if os.geteuid() == 0:
                cmd = ['sudo', '-u', 'pkm', 'env', 'WAYLAND_DISPLAY=wayland-0', 'XDG_RUNTIME_DIR=/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus'] + cmd
                
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
