import subprocess
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# === CONSTANTS ===
VIDEO_PATH = "/home/pkm/video_pltn/pwr_tutorial_ver.mp4"
TARGET_SCREEN_NAME = "HDMI-A-1" # As seen in wlr-randr for the 4K monitor
AUDIO_DEVICE = "alsa/hw:1,0"    # Based on aplay -l (card 1: vc4hdmi0) or pulse/alsa_output.platform-fef00700.hdmi.hdmi-stereo

class VideoPlayer:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def play(self, filename: str = VIDEO_PATH, loop: bool = True):
        """Play video non-blocking via mpv."""
        with self._lock:
            if self.is_playing():
                return
            
            logger.info(f"[VideoPlayer] Starting video playback: {filename}")
            
            cmd = [
                "mpv",
                filename,
                "--fullscreen",
                "--screen=0",
                "--fs-screen=0",
                "--vo=gpu",
                "--hwdec=no",
                "--ao=alsa",
                f"--audio-device={AUDIO_DEVICE}",
                "--audio-fallback-to-null=yes",
                "--keep-open=yes",
                "--log-file=/tmp/mpv.log"
            ]
            
            if loop:
                cmd.append("--loop-file=inf")
                
            import os
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"
            env["WAYLAND_DISPLAY"] = "wayland-0" # changed from wayland-1 as it's more common
            
            # If running as root (e.g. systemd), drop privileges to user pkm for Wayland access
            if os.geteuid() == 0:
                cmd = ['sudo', '-u', 'pkm'] + cmd
                
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
            if self.process:
                logger.info("[VideoPlayer] Stopping video playback")
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None

    def is_playing(self) -> bool:
        """Check if mpv process is still alive."""
        return self.process is not None and self.process.poll() is None
