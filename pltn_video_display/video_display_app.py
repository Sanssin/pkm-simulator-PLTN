"""
PLTN Video Display Application
Menampilkan video edukasi atau interactive guide
Fullscreen ke HDMI monitor

TESTING MODE: Run standalone tanpa simulasi backend
PRODUCTION MODE: Read state dari /tmp/pltn_state.json
"""

import pygame
import json
import time
import sys
import subprocess
from pathlib import Path
from enum import Enum
from typing import Optional, Dict
import argparse

# Fix Windows console encoding untuk emoji support
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Initialize Pygame
pygame.init()

class DisplayMode(Enum):
    AUTO_VIDEO = "auto_video"           # Play full video (auto sim)
    MANUAL_GUIDE = "manual_guide"       # Show step guide (manual)
    IDLE = "idle"                       # Standby/intro screen


# ============================================
# Keyboard Mapping untuk Simulasi Push Button
# ============================================

# Keyboard mapping untuk 17 tombol fisik
KEYBOARD_MAPPING = {
    # Pump controls (Numpad OR regular numbers)
    pygame.K_KP1: "PUMP_PRIMARY_ON",
    pygame.K_1: "PUMP_PRIMARY_ON",        # Alternative untuk laptop
    pygame.K_KP2: "PUMP_PRIMARY_OFF",
    pygame.K_2: "PUMP_PRIMARY_OFF",       # Alternative untuk laptop
    pygame.K_KP4: "PUMP_SECONDARY_ON",
    pygame.K_4: "PUMP_SECONDARY_ON",      # Alternative untuk laptop
    pygame.K_KP5: "PUMP_SECONDARY_OFF",
    pygame.K_5: "PUMP_SECONDARY_OFF",     # Alternative untuk laptop
    pygame.K_KP7: "PUMP_TERTIARY_ON",
    pygame.K_7: "PUMP_TERTIARY_ON",       # Alternative untuk laptop
    pygame.K_KP8: "PUMP_TERTIARY_OFF",
    pygame.K_8: "PUMP_TERTIARY_OFF",      # Alternative untuk laptop
    
    # Control rods (Q/W, E/R, T/Y)
    pygame.K_q: "SAFETY_ROD_UP",
    pygame.K_w: "SAFETY_ROD_DOWN",
    pygame.K_e: "SHIM_ROD_UP",
    pygame.K_r: "SHIM_ROD_DOWN",
    pygame.K_t: "REGULATING_ROD_UP",
    pygame.K_y: "REGULATING_ROD_DOWN",
    
    # Pressure (Arrow keys)
    pygame.K_UP: "PRESSURE_UP",
    pygame.K_DOWN: "PRESSURE_DOWN",
    
    # System controls (F-keys)
    pygame.K_F1: "START_AUTO_SIMULATION",
    pygame.K_F2: "REACTOR_RESET",
    pygame.K_F3: "EMERGENCY",
}

# Edge detection buttons (trigger once per press)
EDGE_BUTTONS = {
    "PUMP_PRIMARY_ON", "PUMP_PRIMARY_OFF",
    "PUMP_SECONDARY_ON", "PUMP_SECONDARY_OFF",
    "PUMP_TERTIARY_ON", "PUMP_TERTIARY_OFF",
    "START_AUTO_SIMULATION", "REACTOR_RESET", "EMERGENCY"
}

# Level detection buttons (trigger while held)
LEVEL_BUTTONS = {
    "SAFETY_ROD_UP", "SAFETY_ROD_DOWN",
    "SHIM_ROD_UP", "SHIM_ROD_DOWN",
    "REGULATING_ROD_UP", "REGULATING_ROD_DOWN",
    "PRESSURE_UP", "PRESSURE_DOWN"
}



class VideoDisplayApp:
    """
    Video Display Application for PLTN Simulator
    
    Supports 2 modes:
    1. TESTING MODE: Standalone dengan mock data
    2. PRODUCTION MODE: Read dari simulasi backend
    """
    
    def __init__(self, test_mode: bool = False, fullscreen: bool = True):
        """
        Initialize video display app
        
        Args:
            test_mode: If True, gunakan mock data tanpa simulasi
            fullscreen: If True, fullscreen window
        """
        self.test_mode = test_mode
        
        # Fullscreen window atau windowed (untuk testing)
        if fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((1280, 720))
        
        self.width, self.height = self.screen.get_size()
        pygame.display.set_caption("PLTN Simulator - Educational Display")
        
        # Calculate scale factor for 4K displays
        # Base design: 1920x1080, actual: could be 3840x2160
        self.scale_x = self.width / 1920.0
        self.scale_y = self.height / 1080.0
        self.scale = min(self.scale_x, self.scale_y)  # Use minimum to maintain aspect ratio
        
        print(f"🖥️  Display: {self.width}x{self.height}")
        print(f"📏 Scale factor: {self.scale:.2f}x")
        
        # State file path (cross-platform)
        if sys.platform == 'win32':
            # Windows: use temp folder
            self.state_file = Path("C:/temp/pltn_state.json")
            self.state_file.parent.mkdir(exist_ok=True)
        else:
            # Linux/RPi: use /tmp
            self.state_file = Path("/tmp/pltn_state.json")
        
        self.last_state = {}
        
        # Video player (mpv subprocess)
        self.video_process = None
        self.current_video = None
        
        # Display mode
        self.display_mode = DisplayMode.IDLE
        
        # Fonts - Enhanced for 4K display with better hierarchy
        # Scale fonts based on display resolution
        # For 3840x2160 (4K): scale = 2.0, so fonts are 2x larger
        base_scale = int(self.scale * 80)  # Increased from 56 to 80 for better visibility
        self.font_display = pygame.font.Font(None, base_scale)                    # Main title (80 → 160 for 4K)
        self.font_title = pygame.font.Font(None, int(base_scale * 0.90))          # Title (72)
        self.font_subtitle = pygame.font.Font(None, int(base_scale * 0.80))       # Subtitle (64)
        self.font_heading = pygame.font.Font(None, int(base_scale * 0.70))        # Institution (56)
        self.font_large = pygame.font.Font(None, int(base_scale * 0.63))          # Large text (50)
        self.font_medium = pygame.font.Font(None, int(base_scale * 0.56))         # Medium text (45)
        self.font_body = pygame.font.Font(None, int(base_scale * 0.50))           # Body text (40)
        self.font_small = pygame.font.Font(None, int(base_scale * 0.44))          # Small text (35)
        self.font_caption = pygame.font.Font(None, int(base_scale * 0.38))        # Caption/tiny (30)
        
        # Professional Nuclear Blue Color Palette
        # === BACKGROUNDS ===
        self.COLOR_BG = (10, 25, 41)              # #0A1929 - Deep Navy
        self.COLOR_BG_SECONDARY = (19, 47, 76)    # #132F4C - Medium Navy
        self.COLOR_BG_TERTIARY = (30, 73, 118)    # #1E4976 - Bright Navy
        self.COLOR_BG_PANEL = (26, 35, 46)        # #1A232E - Panel background
        
        # === BRAND COLORS ===
        self.COLOR_PRIMARY = (0, 180, 216)        # #00B4D8 - Cyan Blue
        self.COLOR_PRIMARY_BRIGHT = (0, 229, 255) # #00E5FF - Bright Cyan
        self.COLOR_PRIMARY_LIGHT = (72, 202, 228) # #48CAE4 - Sky Blue
        
        # === TEXT ===
        self.COLOR_TEXT = (255, 255, 255)         # #FFFFFF - Pure White
        self.COLOR_TEXT_SECONDARY = (224, 231, 255) # #E0E7FF - Light Blue Tint
        self.COLOR_TEXT_TERTIARY = (144, 202, 249)  # #90CAF9 - Pale Blue
        self.COLOR_TEXT_MUTED = (84, 110, 122)    # #546E7A - Blue Gray
        
        # === STATUS ===
        self.COLOR_SUCCESS = (76, 175, 80)        # #4CAF50 - Green
        self.COLOR_WARNING = (255, 167, 38)       # #FFA726 - Orange
        self.COLOR_ERROR = (239, 83, 80)          # #EF5350 - Red
        self.COLOR_INFO = (41, 182, 246)          # #29B6F6 - Light Blue
        
        # === ACCENTS ===
        self.COLOR_GOLD = (255, 179, 0)           # #FFB300 - Amber Gold
        self.COLOR_ENERGY = (0, 229, 255)         # #00E5FF - Energy Cyan
        self.COLOR_SAFETY = (118, 255, 3)         # #76FF03 - Safety Green
        
        # === UI ELEMENTS ===
        self.COLOR_BORDER = (72, 202, 228)        # #48CAE4 - Sky Blue
        self.COLOR_SEPARATOR = (30, 73, 118)      # #1E4976 - Bright Navy
        self.COLOR_HOVER = (19, 47, 76)           # #132F4C - Medium Navy
        
        # Legacy compatibility (deprecated, will be removed)
        self.COLOR_ACCENT = self.COLOR_PRIMARY_BRIGHT
        
        # Logo sizes - scaled for 4K (larger for better visibility)
        self.logo_size_large = (int(200 * self.scale), int(200 * self.scale))  # IDLE mode (increased from 120)
        self.logo_size_small = (int(100 * self.scale), int(100 * self.scale))   # MANUAL mode (increased from 60)
        self.load_logos()
        
        # IDLE screen animation
        self.idle_fade_alpha = 255
        self.idle_fade_direction = -1
        self.idle_fade_speed = 2
        
        # Mode transition tracking
        self.last_state_hash = None  # Track state changes
        self.auto_complete_time = None  # Track when auto simulation completes
        self.user_has_interacted = False  # Track if user pressed any button
        self.last_pressure = 0
        self.last_rods_sum = 0
        self.last_pumps_sum = 0
        
        # Manual guide - step tracker
        self.current_step = 0
        self.steps_completed = []
        
        # Test mode variables
        if self.test_mode:
            print("🧪 TESTING MODE ACTIVE")
            print("   Using mock simulation data")
            print("   Press keys to simulate push buttons:")
            print("")
            print("   === PUMP CONTROLS ===")
            print("   1/2: Primary ON/OFF | 4/5: Secondary ON/OFF | 7/8: Tertiary ON/OFF")
            print("")
            print("   === CONTROL RODS (Hold for continuous) ===")
            print("   Q/W: Safety UP/DOWN | E/R: Shim UP/DOWN | T/Y: Regulating UP/DOWN")
            print("")
            print("   === PRESSURE ===")
            print("   ↑/↓: Pressure UP/DOWN")
            print("")
            print("   === SYSTEM CONTROLS ===")
            print("   F1: Start Auto | F2: Reset | F3: Emergency")
            print("")
            print("   ESC: Exit")
            self.mock_state = self.create_mock_state()
            self.mock_mode = "idle"  # Start with IDLE mode
            
            # Keyboard state tracking (untuk level detection)
            self.last_key_trigger = {}  # Last trigger time for each button
            self.key_repeat_interval = 0.05  # 50ms repeat for held keys
            
            # Track user interaction untuk mode transition
            self.user_has_interacted = False  # Start False, switch to True on first input

        else:
            print("🚀 PRODUCTION MODE")
            print(f"   Reading state from: {self.state_file}")
        
        print(f"🎬 Video Display App initialized")
        print(f"   Screen: {self.width}x{self.height}")
        print(f"   Fullscreen: {fullscreen}")
        if self.logo_brin and self.logo_poltek:
            print(f"   ✅ Logos loaded successfully")
        else:
            print(f"   ⚠️  Logos not found (will skip)")
    
    def load_logos(self):
        """Load BRIN and Poltek logos from assets folder"""
        try:
            logo_path_brin = Path(__file__).parent / "assets" / "logo-brin.png"
            logo_path_poltek = Path(__file__).parent / "assets" / "logo-poltek.png"
            
            if logo_path_brin.exists():
                logo_img = pygame.image.load(str(logo_path_brin))
                # Scale for IDLE mode (large)
                self.logo_brin = pygame.transform.smoothscale(logo_img, self.logo_size_large)
                print(f"   ✅ Loaded BRIN logo")
            else:
                print(f"   ⚠️  BRIN logo not found: {logo_path_brin}")
            
            if logo_path_poltek.exists():
                logo_img = pygame.image.load(str(logo_path_poltek))
                # Scale for IDLE mode (large)
                self.logo_poltek = pygame.transform.smoothscale(logo_img, self.logo_size_large)
                print(f"   ✅ Loaded Poltek logo")
            else:
                print(f"   ⚠️  Poltek logo not found: {logo_path_poltek}")
        
        except Exception as e:
            print(f"   ❌ Error loading logos: {e}")
            self.logo_brin = None
            self.logo_poltek = None
    
    def create_mock_state(self) -> Dict:
        """Create mock state for testing"""
        return {
            "timestamp": time.time(),
            "mode": "manual",
            "auto_running": False,
            "auto_phase": "",
            "pressure": 0.0,
            "safety_rod": 0,
            "shim_rod": 0,
            "regulating_rod": 0,
            "pump_primary": 0,
            "pump_secondary": 0,
            "pump_tertiary": 0,
            "thermal_kw": 0.0,
            "turbine_speed": 0.0,
            "emergency": False
        }
    
    def read_simulation_state(self) -> Dict:
        """
        Read state from backend simulation
        In test mode: return mock state
        In production: read from JSON file
        """
        if self.test_mode:
            # Update mock state based on current mode
            if self.mock_mode == "idle":
                # Return empty state for IDLE mode
                return {}
            elif self.mock_mode == "auto":
                self.mock_state["mode"] = "auto"
                self.mock_state["auto_running"] = True
                self.mock_state["auto_phase"] = "Running"
            elif self.mock_mode == "manual":
                self.mock_state["mode"] = "manual"
                self.mock_state["auto_running"] = False
            
            return self.mock_state
        
        # Production mode: read from file
        try:
            if not self.state_file.exists():
                return {}
            
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Check if state has changed significantly (user interaction)
            if not self.user_has_interacted:
                current_pressure = state.get("pressure", 0)
                current_rods = (state.get("safety_rod", 0) + 
                              state.get("shim_rod", 0) + 
                              state.get("regulating_rod", 0))
                current_pumps = (state.get("pump_primary", 0) + 
                               state.get("pump_secondary", 0) + 
                               state.get("pump_tertiary", 0))
                
                # Detect user interaction (significant state change)
                if (abs(current_pressure - self.last_pressure) > 5 or
                    abs(current_rods - self.last_rods_sum) > 10 or
                    abs(current_pumps - self.last_pumps_sum) > 0):
                    
                    # Only consider as interaction if not during auto simulation
                    auto_running = state.get("auto_running", False)
                    if not auto_running:
                        self.user_has_interacted = True
                        print("👤 User interaction detected - enabling MANUAL mode")
                
                # Update last known values
                self.last_pressure = current_pressure
                self.last_rods_sum = current_rods
                self.last_pumps_sum = current_pumps
            
            return state
        except Exception as e:
            print(f"⚠️  Failed to read state: {e}")
            return {}
    
    def handle_test_mode_keys(self, event):
        """Handle keyboard input for test mode - 17 button simulation"""
        if not self.test_mode:
            return
        
        if event.type == pygame.KEYDOWN:
            # Check if key is mapped to a button
            if event.key in KEYBOARD_MAPPING:
                button_name = KEYBOARD_MAPPING[event.key]
                
                # Edge buttons: trigger once per press
                if button_name in EDGE_BUTTONS:
                    self.trigger_button_action(button_name)
                    print(f"🔘 Button pressed: {button_name}")
    
    def check_held_keys(self):
        """Check for held keys (level detection) - called in update loop"""
        if not self.test_mode:
            return
        
        current_time = time.time()
        keys = pygame.key.get_pressed()
        
        for key_code, button_name in KEYBOARD_MAPPING.items():
            if button_name in LEVEL_BUTTONS:
                if keys[key_code]:
                    # Check repeat interval
                    last_trigger = self.last_key_trigger.get(button_name, 0)
                    if current_time - last_trigger > self.key_repeat_interval:
                        self.trigger_button_action(button_name)
                        self.last_key_trigger[button_name] = current_time
    
    def trigger_button_action(self, button_name: str):
        """Execute action untuk button yang ditekan"""
        # Switch from IDLE to MANUAL on first input (except RESET and AUTO)
        if not self.user_has_interacted and button_name not in ["REACTOR_RESET", "START_AUTO_SIMULATION"]:
            self.user_has_interacted = True
            self.mock_mode = "manual"
            print(f"  → Switching to MANUAL mode (first input detected)")
        
        # Pump controls
        if button_name == "PUMP_PRIMARY_ON":
            self.mock_state["pump_primary"] = 2
            print(f"  ✓ Primary pump: ON")
        elif button_name == "PUMP_PRIMARY_OFF":
            self.mock_state["pump_primary"] = 0
            print(f"  ✓ Primary pump: OFF")
        elif button_name == "PUMP_SECONDARY_ON":
            self.mock_state["pump_secondary"] = 2
            print(f"  ✓ Secondary pump: ON")
        elif button_name == "PUMP_SECONDARY_OFF":
            self.mock_state["pump_secondary"] = 0
            print(f"  ✓ Secondary pump: OFF")
        elif button_name == "PUMP_TERTIARY_ON":
            self.mock_state["pump_tertiary"] = 2
            print(f"  ✓ Tertiary pump: ON")
        elif button_name == "PUMP_TERTIARY_OFF":
            self.mock_state["pump_tertiary"] = 0
            print(f"  ✓ Tertiary pump: OFF")
        
        # Control rods (increment/decrement by 2% per trigger)
        elif button_name == "SAFETY_ROD_UP":
            self.mock_state["safety_rod"] = min(100, self.mock_state["safety_rod"] + 2)
        elif button_name == "SAFETY_ROD_DOWN":
            self.mock_state["safety_rod"] = max(0, self.mock_state["safety_rod"] - 2)
        elif button_name == "SHIM_ROD_UP":
            self.mock_state["shim_rod"] = min(100, self.mock_state["shim_rod"] + 2)
        elif button_name == "SHIM_ROD_DOWN":
            self.mock_state["shim_rod"] = max(0, self.mock_state["shim_rod"] - 2)
        elif button_name == "REGULATING_ROD_UP":
            self.mock_state["regulating_rod"] = min(100, self.mock_state["regulating_rod"] + 2)
        elif button_name == "REGULATING_ROD_DOWN":
            self.mock_state["regulating_rod"] = max(0, self.mock_state["regulating_rod"] - 2)
        
        # Pressure (increment/decrement by 2 bar per trigger)
        elif button_name == "PRESSURE_UP":
            self.mock_state["pressure"] = min(200, self.mock_state["pressure"] + 2)
        elif button_name == "PRESSURE_DOWN":
            self.mock_state["pressure"] = max(0, self.mock_state["pressure"] - 2)
        
        # System controls
        elif button_name == "START_AUTO_SIMULATION":
            self.mock_mode = "auto"
            self.mock_state["mode"] = "auto"
            self.mock_state["auto_running"] = True
            self.user_has_interacted = True  # Mark as interacted
            print(f"  ✓ AUTO SIMULATION STARTED")
        elif button_name == "REACTOR_RESET":
            self.reset_simulation()
            print(f"  ✓ REACTOR RESET")
        elif button_name == "EMERGENCY":
            self.emergency_shutdown()
            print(f"  ✓ EMERGENCY SHUTDOWN!")
    
    def reset_simulation(self):
        """Reset semua parameter ke nilai awal dan kembali ke IDLE"""
        self.mock_state = self.create_mock_state()
        self.mock_mode = "idle"  # Kembali ke IDLE setelah reset
        self.current_step = 0
        self.user_has_interacted = False  # Reset interaction flag
        print("  → All parameters reset, returning to IDLE mode")
    
    def emergency_shutdown(self):
        """Emergency shutdown - set semua ke safe state"""
        self.mock_state["emergency"] = True
        self.mock_state["safety_rod"] = 0
        self.mock_state["shim_rod"] = 0
        self.mock_state["regulating_rod"] = 0
        self.mock_state["pump_primary"] = 0
        self.mock_state["pump_secondary"] = 0
        self.mock_state["pump_tertiary"] = 0
        self.mock_mode = "idle"  # Kembali ke IDLE setelah emergency
        self.user_has_interacted = False  # Reset interaction flag
        print("  → Emergency: All rods inserted, pumps stopped, returning to IDLE")

    
    def play_video(self, video_path: str, loop: bool = False):
        """
        Play video using mpv (Wayland compatible)
        
        Args:
            video_path: Path to video file
            loop: Loop video infinitely
        """
        # Stop any current video
        if self.video_process:
            self.stop_video()
        
        # Check if video file exists
        if not Path(video_path).exists():
            print(f"❌ Video not found: {video_path}")
            if self.test_mode:
                print("   💡 In test mode, this is expected")
                print("   💡 Create video file or use placeholder")
            return
        
        # Build mpv command for Wayland
        cmd = [
            'mpv',
            '--fs',                      # Fullscreen
            '--no-osd-bar',             # No on-screen display
            '--no-input-default-bindings',  # Disable keyboard
            '--really-quiet',           # Minimal output
            '--vo=gpu',                 # Video output: GPU (Wayland compatible)
            '--hwdec=auto',             # Hardware decode (4K support)
            '--gpu-context=wayland',    # Use Wayland context
            video_path
        ]
        
        if loop:
            cmd.insert(1, '--loop=inf')
        
        try:
            # Set Wayland environment for mpv
            env = {
                'DISPLAY': ':0',
                'WAYLAND_DISPLAY': 'wayland-0',
                'XDG_RUNTIME_DIR': '/run/user/1000'
            }
            
            self.video_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.current_video = video_path
            print(f"▶️  Playing: {Path(video_path).name}")
            print(f"   Using Wayland GPU context with hardware decode")
        except FileNotFoundError:
            print("❌ mpv not installed!")
            print("   Install: sudo apt install mpv")
            if self.test_mode:
                print("   💡 Test mode: Simulating video playback")
        except Exception as e:
            print(f"❌ Failed to play video: {e}")
    
    def stop_video(self):
        """Stop current video"""
        if self.video_process:
            self.video_process.terminate()
            try:
                self.video_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.video_process.kill()
            self.video_process = None
            self.current_video = None
            print("⏹️  Video stopped")
    
    def draw_idle_screen(self):
        """Display idle/intro screen - Optimized for 4K display"""
        self.screen.fill(self.COLOR_BG)
        
        # Update fade animation for instruction text
        self.idle_fade_alpha += self.idle_fade_direction * self.idle_fade_speed
        if self.idle_fade_alpha >= 255:
            self.idle_fade_alpha = 255
            self.idle_fade_direction = -1
        elif self.idle_fade_alpha <= 180:
            self.idle_fade_alpha = 180
            self.idle_fade_direction = 1
        
        # === TOP SECTION: LOGOS === (larger, more prominent)
        logo_y = int(80 * self.scale)  # Increased from 50
        logo_margin = int(100 * self.scale)  # Increased from 80
        
        # BRIN Logo (Top Left)
        if self.logo_brin:
            logo_x = logo_margin
            self.screen.blit(self.logo_brin, (logo_x, logo_y))
        
        # Poltek Logo (Top Right)
        if self.logo_poltek:
            logo_x = self.width - self.logo_size_large[0] - logo_margin
            self.screen.blit(self.logo_poltek, (logo_x, logo_y))
        
        # === CENTER SECTION: MAIN TITLE WITH DECORATIVE LINES ===
        center_y_start = self.height // 2 - int(180 * self.scale)  # Adjusted for larger content
        
        # Decorative line (top) - much longer to use more width
        line_width = int(1200 * self.scale)  # Increased from 600 - use more screen width
        line_x = (self.width - line_width) // 2
        line_thickness = max(int(4 * self.scale), 3)  # Thicker
        pygame.draw.line(self.screen, self.COLOR_BORDER, 
                        (line_x, center_y_start - int(30 * self.scale)), 
                        (line_x + line_width, center_y_start - int(30 * self.scale)), 
                        line_thickness)
        
        # Main Title Line 1 (Bright Cyan with shadow)
        title1_text = "ALAT PERAGA PLTN TIPE PWR"
        # Shadow (larger offset for 4K)
        title1_shadow = self.font_display.render(title1_text, True, (0, 0, 0))
        shadow_offset = int(4 * self.scale)  # Increased from 2
        title1_shadow_rect = title1_shadow.get_rect(center=(self.width//2 + shadow_offset, center_y_start + int(32 * self.scale)))
        self.screen.blit(title1_shadow, title1_shadow_rect)
        # Main text
        title1 = self.font_display.render(title1_text, True, self.COLOR_PRIMARY_BRIGHT)
        title1_rect = title1.get_rect(center=(self.width//2, center_y_start + int(30 * self.scale)))
        self.screen.blit(title1, title1_rect)
        
        # Main Title Line 2 (Pure White)
        title2_text = "BERBASIS MIKROKONTROLER"
        # Shadow
        title2_shadow = self.font_subtitle.render(title2_text, True, (0, 0, 0))
        title2_shadow_rect = title2_shadow.get_rect(center=(self.width//2 + shadow_offset, center_y_start + int(122 * self.scale)))
        self.screen.blit(title2_shadow, title2_shadow_rect)
        # Main text
        title2 = self.font_subtitle.render(title2_text, True, self.COLOR_TEXT)
        title2_rect = title2.get_rect(center=(self.width//2, center_y_start + int(120 * self.scale)))
        self.screen.blit(title2, title2_rect)
        
        # Decorative line (bottom)
        pygame.draw.line(self.screen, self.COLOR_BORDER, 
                        (line_x, center_y_start + int(190 * self.scale)), 
                        (line_x + line_width, center_y_start + int(190 * self.scale)), 
                        line_thickness)
        
        # Institution Name (Light Blue, larger)
        institution = self.font_heading.render("Politeknik Teknologi Nuklir Indonesia", 
                                               True, self.COLOR_TEXT_TERTIARY)
        inst_rect = institution.get_rect(center=(self.width//2, center_y_start + int(250 * self.scale)))
        self.screen.blit(institution, inst_rect)
        
        # === ADDITIONAL INFO SECTION === (NEW - fill empty space)
        info_y = center_y_start + int(330 * self.scale)
        
        # Description text
        desc_lines = [
            "Simulator Interaktif untuk Pembelajaran",
            "Pembangkit Listrik Tenaga Nuklir (PLTN)",
            "dengan Teknologi Pressurized Water Reactor (PWR)"
        ]
        
        for i, line in enumerate(desc_lines):
            desc_text = self.font_body.render(line, True, self.COLOR_TEXT_SECONDARY)
            desc_rect = desc_text.get_rect(center=(self.width//2, info_y + i * int(55 * self.scale)))
            self.screen.blit(desc_text, desc_rect)
        
        # === STATUS BADGE === (larger and more prominent)
        status_y = center_y_start + int(520 * self.scale)
        
        # Status badge background - much wider
        badge_width = int(800 * self.scale)  # Increased from 420 - use more width
        badge_height = int(60 * self.scale)  # Increased from 40
        badge_x = (self.width - badge_width) // 2
        badge_radius = int(30 * self.scale)  # Increased from 20
        badge_rect = pygame.Rect(badge_x, status_y - int(15 * self.scale), badge_width, badge_height)
        pygame.draw.rect(self.screen, self.COLOR_BG_TERTIARY, badge_rect, border_radius=badge_radius)
        pygame.draw.rect(self.screen, self.COLOR_GOLD, badge_rect, max(int(3 * self.scale), 2), border_radius=badge_radius)
        
        # Status text with icon (larger) - NO EMOJI
        status_text = ">>> SIMULATION READY <<<"  # Replaced emoji with ASCII
        status_surface = self.font_display.render(status_text, True, self.COLOR_GOLD)  # Use largest font
        status_rect = status_surface.get_rect(center=(self.width//2, status_y + int(15 * self.scale)))
        self.screen.blit(status_surface, status_rect)
        
        # === BOTTOM SECTION: INSTRUCTIONS ===
        instruction_y = self.height - int(120 * self.scale)  # Adjusted to avoid overlap
        
        # Instruction text with fade animation (Bright Cyan, larger)
        inst_text = ">> Tekan tombol untuk memulai simulasi <<"  # Removed emoji
        inst_surface = self.font_medium.render(inst_text, True, self.COLOR_ENERGY)  # Changed from font_body
        
        # Apply fade by adjusting alpha
        inst_surface.set_alpha(int(self.idle_fade_alpha))
        inst_rect = inst_surface.get_rect(center=(self.width//2, instruction_y))
        self.screen.blit(inst_surface, inst_rect)
        
        # === TEST MODE INDICATOR ===
        if self.test_mode:
            test_y = self.height - int(80 * self.scale)
            test_text = self.font_small.render("TEST MODE - Press I/M/A to change mode | ESC to exit", 
                                               True, self.COLOR_ERROR)
            test_rect = test_text.get_rect(center=(self.width//2, test_y))
            self.screen.blit(test_text, test_rect)
        
        pygame.display.flip()
    
    def draw_manual_guide(self, state: Dict):
        """Display interactive step-by-step guide - Optimized for 4K"""
        self.screen.fill(self.COLOR_BG)
        
        # Pressure warning will be drawn as floating overlay at the end (no layout shift)
        
        # === HEADER BAR === (larger and more prominent)
        header_height = int(120 * self.scale)  # Increased from 80
        left_margin = int(50 * self.scale)  # Increased from 30
        right_margin = int(50 * self.scale)
        
        # Draw header background (Medium Navy)
        pygame.draw.rect(self.screen, self.COLOR_BG_SECONDARY, 
                        (0, 0, self.width, header_height))
        line_thickness = max(int(4 * self.scale), 3)
        pygame.draw.line(self.screen, self.COLOR_BORDER, 
                        (0, header_height), 
                        (self.width, header_height), 
                        line_thickness)
        
        # Logo BRIN (left)
        if self.logo_brin:
            logo_small_brin = pygame.transform.smoothscale(self.logo_brin, self.logo_size_small)
            logo_y = (header_height - self.logo_size_small[1]) // 2
            self.screen.blit(logo_small_brin, (left_margin, logo_y))
        
        # Title text (center) - Larger font
        header_title = self.font_title.render("SIMULATOR PLTN TIPE PWR BERBASIS MIKROKONTROLER", 
                                                 True, self.COLOR_TEXT)
        header_title_rect = header_title.get_rect(center=(self.width//2, header_height//2))
        self.screen.blit(header_title, header_title_rect)
        
        # Logo Poltek (right)
        if self.logo_poltek:
            logo_small_poltek = pygame.transform.smoothscale(self.logo_poltek, self.logo_size_small)
            logo_y = (header_height - self.logo_size_small[1]) // 2
            logo_x = self.width - self.logo_size_small[0] - right_margin
            self.screen.blit(logo_small_poltek, (logo_x, logo_y))
        
        
        # === MAIN CONTENT AREA === (clean layout without step badge)
        content_y_start = header_height + int(80 * self.scale)  # Space from header
        
        # Current step instruction
        step_text = self.get_current_step_instruction(state)
        
        # Draw instruction directly (no badge, more space for text)
        # Start instructions higher up for better balance
        y_offset = content_y_start + int(40 * self.scale)  # Start closer to header
        line_spacing = int(80 * self.scale)  # More spacing between lines
        
        for line in step_text:
            if line:  # Skip empty lines for spacing
                text = self.font_large.render(line, True, self.COLOR_TEXT)
                text_rect = text.get_rect(center=(self.width//2, y_offset))
                self.screen.blit(text, text_rect)
            y_offset += line_spacing
        
        # === PARAMETERS SECTION === (larger, more visible)
        params_y_start = self.height - int(450 * self.scale)  # More space for parameters
        
        # Section title
        params_title = self.font_display.render("PARAMETER SISTEM", True, self.COLOR_PRIMARY_BRIGHT)  # Larger font
        params_title_rect = params_title.get_rect(center=(self.width//2, params_y_start - int(50 * self.scale)))
        self.screen.blit(params_title, params_title_rect)
        
        # Decorative line under title - wider
        line_width = int(1000 * self.scale)  # Increased from 400
        line_x = (self.width - line_width) // 2
        pygame.draw.line(self.screen, self.COLOR_BORDER,
                        (line_x, params_y_start - int(25 * self.scale)),
                        (line_x + line_width, params_y_start - int(25 * self.scale)),
                        max(int(3 * self.scale), 2))
        
        # Draw progress bars (larger)
        self.draw_progress_bar_enhanced(state, params_y_start)
        
        # === FLOATING PRESSURE WARNING OVERLAY === (drawn last, on top of everything)
        # This appears as a pop-up without shifting the layout
        current_pressure = state.get("pressure", 0)
        if current_pressure > 160:
            # 1. Semi-transparent dark overlay (full screen)
            overlay = pygame.Surface((self.width, self.height))
            overlay.set_alpha(180)  # 70% opacity
            overlay.fill((0, 0, 0))  # Black
            self.screen.blit(overlay, (0, 0))
            
            # 2. Warning box in center
            box_width = int(1200 * self.scale)
            box_height = int(400 * self.scale)
            box_x = (self.width - box_width) // 2
            box_y = (self.height - box_height) // 2
            
            # Determine color and text based on pressure level
            if current_pressure > 180:
                box_color = self.COLOR_ERROR  # Red - Danger!
                warning_title = "!!! BAHAYA !!!"
                warning_main = "TEKANAN PRESSURIZER TERLALU TINGGI"
            else:
                box_color = self.COLOR_WARNING  # Orange - Warning
                warning_title = "!!! PERINGATAN !!!"
                warning_main = "TEKANAN PRESSURIZER TINGGI"
            
            # Draw warning box with border
            box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
            border_radius = int(20 * self.scale)
            pygame.draw.rect(self.screen, box_color, box_rect, border_radius=border_radius)
            pygame.draw.rect(self.screen, self.COLOR_TEXT, box_rect, 
                           max(int(5 * self.scale), 3), border_radius=border_radius)
            
            # 3. Warning icon (circle with "!")
            icon_radius = int(80 * self.scale)
            icon_center_x = self.width // 2
            icon_center_y = box_y + int(100 * self.scale)
            pygame.draw.circle(self.screen, self.COLOR_TEXT, 
                             (icon_center_x, icon_center_y), icon_radius)
            pygame.draw.circle(self.screen, box_color, 
                             (icon_center_x, icon_center_y), icon_radius - int(8 * self.scale))
            
            # Warning icon text "!"
            icon_text = self.font_display.render("!", True, self.COLOR_TEXT)
            icon_text_rect = icon_text.get_rect(center=(icon_center_x, icon_center_y))
            self.screen.blit(icon_text, icon_text_rect)
            
            # 4. Warning title
            title_y = box_y + int(200 * self.scale)
            title_surface = self.font_title.render(warning_title, True, self.COLOR_TEXT)
            title_rect = title_surface.get_rect(center=(self.width // 2, title_y))
            self.screen.blit(title_surface, title_rect)
            
            # 5. Warning main text
            main_y = box_y + int(260 * self.scale)
            main_surface = self.font_large.render(warning_main, True, self.COLOR_TEXT)
            main_rect = main_surface.get_rect(center=(self.width // 2, main_y))
            self.screen.blit(main_surface, main_rect)
            
            # 6. Instruction text
            instruction_y = box_y + int(320 * self.scale)
            instruction_text = "Turunkan tekanan segera! (Tekan tombol TEKANAN TURUN)"
            instruction_surface = self.font_medium.render(instruction_text, True, self.COLOR_TEXT_SECONDARY)
            instruction_rect = instruction_surface.get_rect(center=(self.width // 2, instruction_y))
            self.screen.blit(instruction_surface, instruction_rect)
            
            # 7. Current pressure value
            value_y = box_y + int(370 * self.scale)
            value_text = f"Tekanan saat ini: {current_pressure:.1f} bar"
            value_surface = self.font_body.render(value_text, True, self.COLOR_TEXT_TERTIARY)
            value_rect = value_surface.get_rect(center=(self.width // 2, value_y))
            self.screen.blit(value_surface, value_rect)
        
        pygame.display.flip()
    
    def get_current_step_instruction(self, state: Dict) -> list:
        """Get instruction text for current step"""
        steps = [
            {
                "text": ["Naikkan Tekanan ke 45 bar", "Tekan tombol TEKANAN NAIK"],
                "check": lambda s: s.get("pressure", 0) >= 45
            },
            {
                "text": ["Hidupkan Pompa Tersier", "Tekan tombol POMPA TERSIER ON"],
                "check": lambda s: s.get("pump_tertiary", 0) >= 1
            },
            {
                "text": ["Hidupkan Pompa Sekunder", "Tekan tombol POMPA SEKUNDER ON"],
                "check": lambda s: s.get("pump_secondary", 0) >= 1
            },
            {
                "text": ["Hidupkan Pompa Primer", "Tekan tombol POMPA PRIMER ON"],
                "check": lambda s: s.get("pump_primary", 0) >= 1
            },
            {
                "text": ["Naikkan Tekanan ke 140 bar", "Terus tekan tombol TEKANAN NAIK"],
                "check": lambda s: s.get("pressure", 0) >= 140
            },
            {
                "text": ["Naikkan Safety Rod ke 100%", "Tekan tombol SAFETY ROD UP"],
                "check": lambda s: s.get("safety_rod", 0) >= 100
            },
            {
                "text": ["Naikkan Shim Rod ke 50%", "Tekan tombol SHIM ROD UP"],
                "check": lambda s: s.get("shim_rod", 0) >= 50
            },
            {
                "text": ["Naikkan Regulating Rod ke 50%", "Tekan tombol REGULATING ROD UP"],
                "check": lambda s: s.get("regulating_rod", 0) >= 50
            },
            {
                "text": ["Operasi Normal Tercapai!", "Sistem sedang menghasilkan daya"],
                "check": lambda s: True
            }
        ]
        
        # Check if current step completed
        if self.current_step < len(steps):
            step = steps[self.current_step]
            if step["check"](state):
                self.current_step += 1
                if self.test_mode:
                    print(f"✅ Step {self.current_step} completed!")
        
        if self.current_step < len(steps):
            return steps[self.current_step]["text"]
        else:
            # Final step: Manual control instructions
            return [
                "Gunakan kontrol batang kendali untuk mengatur daya PLTN",
                "Shim Rod & Regulating Rod untuk fine-tuning power output",
                "",
                "(Tekan tombol RESET untuk mengulang simulasi)"
            ]
    
    def draw_progress_bar_enhanced(self, state: Dict, y_start: int):
        """Draw enhanced parameter progress bars for 4K display"""
        bar_width = int(900 * self.scale)  # Much wider bars (from 500)
        bar_height = int(60 * self.scale)  # Taller bars (from 50)
        bar_spacing = int(85 * self.scale)  # More spacing
        
        # Get current pressure for color coding
        current_pressure = state.get("pressure", 0)
        
        # Determine pressure bar color based on value
        if current_pressure > 180:
            pressure_color = self.COLOR_ERROR  # Red - Danger!
        elif current_pressure > 160:
            pressure_color = self.COLOR_WARNING  # Yellow/Orange - Warning
        else:
            pressure_color = self.COLOR_PRIMARY  # Cyan - Normal
        
        params = [
            ("Pressure", current_pressure, 200, "bar", pressure_color),  # Max 200, not 155
            ("Safety Rod", state.get("safety_rod", 0), 100, "%", self.COLOR_SUCCESS),
            ("Shim Rod", state.get("shim_rod", 0), 100, "%", self.COLOR_PRIMARY),
            ("Regulating Rod", state.get("regulating_rod", 0), 100, "%", self.COLOR_INFO)
        ]
        
        # Calculate centered layout with more width
        total_width = int(1400 * self.scale)  # Increased from 800 - use more screen
        left_margin = (self.width - total_width) // 2
        
        for i, (label, value, max_val, unit, color) in enumerate(params):
            y = y_start + i * bar_spacing
            x_label = left_margin
            x_bar = left_margin + int(280 * self.scale)  # More space for label
            
            # Label (Larger font) - NO warning text on label, just normal label
            label_text = f"{label}:"
            label_color = self.COLOR_TEXT_TERTIARY
            
            text = self.font_large.render(label_text, True, label_color)  # Larger font
            self.screen.blit(text, (x_label, y + int(15 * self.scale)))
            
            # Bar background
            border_radius = int(12 * self.scale)  # Slightly larger radius
            bg_rect = pygame.Rect(x_bar, y, bar_width, bar_height)
            pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, bg_rect, border_radius=border_radius)
            
            # Bar fill
            fill_width = int((value / max_val) * bar_width) if max_val > 0 else 0
            if fill_width > 0:
                fill_rect = pygame.Rect(x_bar, y, fill_width, bar_height)
                pygame.draw.rect(self.screen, color, fill_rect, border_radius=border_radius)
            
            # Bar border (thicker for danger zone)
            if i == 0 and value > 160:
                border_thickness = max(int(5 * self.scale), 3)  # Thicker border for warning
            else:
                border_thickness = max(int(3 * self.scale), 2)
            pygame.draw.rect(self.screen, self.COLOR_BORDER, bg_rect, border_thickness, border_radius=border_radius)
            
            # Value text (inside bar, larger)
            value_text = self.font_large.render(f"{value:.0f}{unit}", True, self.COLOR_TEXT)  # Larger font
            value_rect = value_text.get_rect(center=(x_bar + bar_width//2, y + bar_height//2))
            self.screen.blit(value_text, value_rect)
    
    def draw_progress_bar(self, state: Dict):
        """Draw parameter progress bars with Nuclear Blue theme (4K scaled) - Legacy"""
        y_start = self.height - int(300 * self.scale)  # Moved up significantly - scaled
        bar_width = int(300 * self.scale)
        bar_height = int(30 * self.scale)
        bar_spacing = int(45 * self.scale)  # Reduced spacing - scaled
        
        params = [
            ("Pressure", state.get("pressure", 0), 200, "bar"),  # Updated max to 200
            ("Safety Rod", state.get("safety_rod", 0), 100, "%"),
            ("Shim Rod", state.get("shim_rod", 0), 100, "%"),
            ("Reg Rod", state.get("regulating_rod", 0), 100, "%")
        ]
        
        for i, (label, value, max_val, unit) in enumerate(params):
            y = y_start + i * bar_spacing
            x_label = int(200 * self.scale)
            x_bar = int(380 * self.scale)
            
            # Label (Light Blue)
            text = self.font_small.render(f"{label}:", True, self.COLOR_TEXT_TERTIARY)
            self.screen.blit(text, (x_label, y))
            
            # Value text (Pure White)
            value_text = self.font_small.render(f"{value:.0f}{unit}", True, self.COLOR_TEXT)
            self.screen.blit(value_text, (x_bar + bar_width + int(15 * self.scale), y))
            
            # Bar background (Panel BG)
            border_radius = int(5 * self.scale)
            bg_rect = pygame.Rect(x_bar, y + int(5 * self.scale), bar_width, bar_height)
            pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, bg_rect, border_radius=border_radius)
            
            # Bar fill (Color based on value)
            fill_width = int((value / max_val) * bar_width) if max_val > 0 else 0
            if fill_width > 0:
                fill_rect = pygame.Rect(x_bar, y + int(5 * self.scale), fill_width, bar_height)
                # Choose color based on value
                if value > max_val * 0.7:
                    color = self.COLOR_SUCCESS
                elif value > max_val * 0.3:
                    color = self.COLOR_PRIMARY
                else:
                    color = self.COLOR_INFO
                pygame.draw.rect(self.screen, color, fill_rect, border_radius=border_radius)
            
            # Bar border (Border color)
            border_thickness = max(int(2 * self.scale), 1)
            pygame.draw.rect(self.screen, self.COLOR_BORDER, bg_rect, border_thickness, border_radius=border_radius)
    
    def draw_video_playing_overlay(self):
        """Draw overlay when video is playing (for debug) with Nuclear Blue theme"""
        if self.test_mode and self.display_mode == DisplayMode.AUTO_VIDEO:
            self.screen.fill(self.COLOR_BG)
            
            # Title
            text = self.font_title.render("VIDEO PLAYING", True, self.COLOR_PRIMARY_BRIGHT)
            text_rect = text.get_rect(center=(self.width//2, self.height//2 - 30))
            self.screen.blit(text, text_rect)
            
            # Subtitle
            hint = self.font_body.render("(Simulated - no actual video)", True, self.COLOR_TEXT_TERTIARY)
            hint_rect = hint.get_rect(center=(self.width//2, self.height//2 + 20))
            self.screen.blit(hint, hint_rect)
            
            # Instructions
            inst = self.font_small.render("Press I to return to IDLE", True, self.COLOR_INFO)
            inst_rect = inst.get_rect(center=(self.width//2, self.height//2 + 60))
            self.screen.blit(inst, inst_rect)
            
            pygame.display.flip()
    
    def update(self):
        """Main update loop with improved mode transition logic"""
        state = self.read_simulation_state()
        
        # DEBUG: Print state info (less frequent)
        if state and hasattr(self, '_debug_counter'):
            self._debug_counter = (self._debug_counter + 1) % 30  # Print every 30 frames (~1 sec)
            if self._debug_counter == 0:
                mode = state.get("mode", "unknown")
                auto_running = state.get("auto_running", False)
                print(f"📊 mode={mode}, auto={auto_running}, display={self.display_mode.value}, user_interacted={self.user_has_interacted}")
        elif not hasattr(self, '_debug_counter'):
            self._debug_counter = 0
        
        # In test mode, check mock_mode first
        if self.test_mode:
            if self.mock_mode == "idle":
                # Force IDLE mode
                if self.display_mode != DisplayMode.IDLE:
                    self.stop_video()
                    self.display_mode = DisplayMode.IDLE
                self.draw_idle_screen()
                return
            elif self.mock_mode == "auto":
                # Force AUTO mode
                if self.display_mode != DisplayMode.AUTO_VIDEO:
                    print("🎬 Switching to AUTO VIDEO mode")
                    video_path = str(Path(__file__).parent / "assets" / "penjelasan.mp4")
                    self.play_video(video_path, loop=True)
                    self.display_mode = DisplayMode.AUTO_VIDEO
                
                # Show overlay in test mode
                self.draw_video_playing_overlay()
                return
            elif self.mock_mode == "manual":
                # Force MANUAL mode
                if self.display_mode != DisplayMode.MANUAL_GUIDE:
                    print("📋 Switching to MANUAL GUIDE mode")
                    self.stop_video()
                    self.display_mode = DisplayMode.MANUAL_GUIDE
                    self.current_step = 0
                
                self.draw_manual_guide(state)
                return
        
        # Production mode logic with improved transitions
        if not state:
            # No state yet - show idle
            if self._debug_counter == 0:
                print("⚠️  No state file - showing IDLE")
            if self.display_mode != DisplayMode.IDLE:
                self.stop_video()
                self.display_mode = DisplayMode.IDLE
                self.user_has_interacted = False  # Reset on no state
            self.draw_idle_screen()
            return
        
        mode = state.get("mode", "manual")
        auto_running = state.get("auto_running", False)
        emergency = state.get("emergency", False)
        
        # Check if simulation was RESET (pressure back to 0, all parameters reset)
        current_pressure = state.get("pressure", 0)
        current_rods = (state.get("safety_rod", 0) + 
                       state.get("shim_rod", 0) + 
                       state.get("regulating_rod", 0))
        current_pumps = (state.get("pump_primary", 0) + 
                        state.get("pump_secondary", 0) + 
                        state.get("pump_tertiary", 0))
        
        # Detect RESET: all values near zero
        if (current_pressure < 5 and current_rods < 10 and current_pumps == 0):
            if self.display_mode != DisplayMode.IDLE:
                print("🔄 RESET detected - returning to IDLE")
                self.stop_video()
                self.display_mode = DisplayMode.IDLE
                self.user_has_interacted = False
                self.auto_complete_time = None
            self.draw_idle_screen()
            return
        
        # Check if auto simulation just completed
        if not auto_running and self.display_mode == DisplayMode.AUTO_VIDEO:
            # Auto simulation just finished - go to MANUAL, not IDLE!
            print("🏁 Auto simulation completed - switching to MANUAL")
            self.stop_video()
            self.display_mode = DisplayMode.MANUAL_GUIDE
            self.user_has_interacted = True  # Enable manual mode immediately
            self.auto_complete_time = None
            self.current_step = 0
            # Don't return here, continue to draw manual guide
        
        # MODE 1: EMERGENCY - Always return to IDLE
        if emergency:
            if self.display_mode != DisplayMode.IDLE:
                print("🚨 Emergency detected - returning to IDLE")
                self.stop_video()
                self.display_mode = DisplayMode.IDLE
                self.user_has_interacted = False
                self.auto_complete_time = None
            self.draw_idle_screen()
            return
        
        # MODE 2: AUTO SIMULATION - Play video
        if mode == "auto" and auto_running:
            if self.display_mode != DisplayMode.AUTO_VIDEO:
                print(f"🎬 Switching to AUTO VIDEO mode")
                # Use video from assets folder (production ready)
                video_path = str(Path(__file__).parent / "assets" / "penjelasan.mp4")
                self.play_video(video_path, loop=True)
                self.display_mode = DisplayMode.AUTO_VIDEO
                self.auto_complete_time = None  # Reset completion timer
                self.user_has_interacted = False  # Reset interaction flag
            
            # Video is playing via mpv - don't draw anything
            # (mpv handles fullscreen itself)
            return
        
        # MODE 3: MANUAL - Show guide if user interacted or after auto complete
        if mode == "manual" and self.user_has_interacted:
            if self.display_mode != DisplayMode.MANUAL_GUIDE:
                print(f"📋 Switching to MANUAL GUIDE mode (user pressed button)")
                self.stop_video()
                self.display_mode = DisplayMode.MANUAL_GUIDE
                self.current_step = 0
            
            self.draw_manual_guide(state)
        
        # MODE 4: IDLE - Default (no user interaction yet, not in auto, not reset)
        else:
            if self.display_mode != DisplayMode.IDLE:
                self.stop_video()
                self.display_mode = DisplayMode.IDLE
            self.draw_idle_screen()
    
    def run(self):
        """Main application loop"""
        clock = pygame.time.Clock()
        running = True
        
        print("🚀 Video Display App running...")
        print("   Press ESC to exit")
        
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                
                # Test mode keyboard handling
                self.handle_test_mode_keys(event)
            
            # Check held keys (level detection for continuous actions)
            self.check_held_keys()
            
            # Update display
            self.update()
            
            # 30 FPS sufficient for UI updates
            clock.tick(30)
        
        # Cleanup
        self.stop_video()
        pygame.quit()
        print("👋 Video Display App stopped")



def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(description='PLTN Video Display Application')
    parser.add_argument('--test', action='store_true', 
                       help='Run in test mode (no simulation required)')
    parser.add_argument('--windowed', action='store_true',
                       help='Run in windowed mode (not fullscreen)')
    
    args = parser.parse_args()
    
    # Run application
    app = VideoDisplayApp(
        test_mode=args.test,
        fullscreen=not args.windowed
    )
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
