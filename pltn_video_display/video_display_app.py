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
import os
import subprocess
import math
import traceback
from pathlib import Path
from enum import Enum
from typing import Optional, Dict
import argparse

# Fix Windows console encoding untuk emoji support
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Force Wayland driver on Linux so app_id is correctly passed to Wayfire
if sys.platform.startswith('linux'):
    os.environ['SDL_VIDEODRIVER'] = 'wayland'
    os.environ['SDL_VIDEO_WAYLAND_WMCLASS'] = "pltn_video_display"

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
    
    def __init__(self, test_mode: bool = False, fullscreen: bool = True, display_idx: int = 0):
        """
        Initialize video display app
        """
        self.test_mode = test_mode
        self.fullscreen = fullscreen
        self.display_idx = display_idx
        
        # Set environment variables BEFORE init
        os.environ['SDL_VIDEO_DISPLAY_INDEX'] = str(display_idx)
        os.environ['SDL_VIDEO_WAYLAND_WMCLASS'] = "pltn_video_display"
            
        pygame.init()
        
        # Cek apakah display yang diminta tersedia
        num_displays = pygame.display.get_num_displays()
        print(f"🔍 Found {num_displays} displays. Target: {display_idx}")
        
        # Jika menggunakan Wayland, Wayland menyembunyikan topology monitor (selalu lapor 1 monitor)
        # Jadi fallback X11 (pygame.quit() dsb) jangan dipanggil jika kita menggunakan Wayland,
        # karena akan menghilangkan set_caption.
        is_wayland = os.environ.get('SDL_VIDEODRIVER') == 'wayland'
        
        if not is_wayland and display_idx >= num_displays and num_displays > 0:
            print(f"⚠️ Display {display_idx} tidak terdeteksi oleh SDL. Fallback ke windowed borderless offset.")
            pygame.quit()
            del os.environ['SDL_VIDEO_DISPLAY_INDEX']
            
            # Asumsi standar: offset 1920 untuk layar kedua (HDMI-A-2)
            offset_x = 1920 if display_idx == 1 else 0
            os.environ['SDL_VIDEO_WINDOW_POS'] = f"{offset_x},0"
            pygame.init()
            
            # SELALU set caption tepat sebelum membuat window agar Wayfire bisa membacanya
            pygame.display.set_caption("PLTN Simulator - Educational Display")
            
            if self.fullscreen:
                print(f"🚀 Membuka fallback di koordinat {offset_x},0 dengan mode NOFRAME.")
                self.screen = pygame.display.set_mode((1920, 1080), pygame.NOFRAME)
            else:
                self.screen = pygame.display.set_mode((1280, 720))
        else:
            # SELALU set caption tepat sebelum membuat window agar Wayfire bisa membacanya
            pygame.display.set_caption("PLTN Simulator - Educational Display")
            
            # Fullscreen window atau windowed (untuk testing)
            if self.fullscreen:
                try:
                    # Di Wayland, kita serahkan sepenuhnya pada Wayfire rule
                    # Jika menggunakan display_idx, terkadang SDL XWayland error "Invalid display index"
                    if is_wayland:
                        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_idx)
                except Exception as e:
                    print(f"⚠️ Error FULLSCREEN Pygame: {e}. Fallback ke NOFRAME.")
                    self.screen = pygame.display.set_mode((0, 0), pygame.NOFRAME)
            else:
                self.screen = pygame.display.set_mode((1280, 720))
        
        self.width, self.height = self.screen.get_size()
        
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
        
        self.manual_flag_file = Path("C:/temp/pltn_manual_started") if sys.platform == 'win32' else Path("/tmp/pltn_manual_started")
        self._clear_manual_flag()
        
    def _clear_manual_flag(self):
        try:
            if hasattr(self, 'manual_flag_file') and self.manual_flag_file.exists():
                self.manual_flag_file.unlink()
        except Exception:
            pass
        
        # Video player (mpv subprocess)
        self.video_process = None
        self.current_video = None
        
        # Display mode
        self.display_mode = DisplayMode.IDLE
        
        # Fonts - Enhanced for 4K display with better hierarchy
        # Scale fonts based on display resolution
        # For 3840x2160 (4K): scale = 2.0, so fonts are 2x larger
        font_name = "inter" # Use Inter font for modern, clean look (must be installed on system)
        base_scale = int(self.scale * 80)  # Increased from 56 to 80 for better visibility
        self.font_display = pygame.font.SysFont(font_name, base_scale)                    # Main title (80 → 160 for 4K)
        self.font_title = pygame.font.SysFont(font_name, int(base_scale * 0.90))          # Title (72)
        self.font_subtitle = pygame.font.SysFont(font_name, int(base_scale * 0.80))       # Subtitle (64)
        self.font_heading = pygame.font.SysFont(font_name, int(base_scale * 0.70))        # Institution (56)
        self.font_large = pygame.font.SysFont(font_name, int(base_scale * 0.63))          # Large text (50)
        self.font_medium = pygame.font.SysFont(font_name, int(base_scale * 0.56))         # Medium text (45)
        self.font_body = pygame.font.SysFont(font_name, int(base_scale * 0.50))           # Body text (40)
        self.font_small = pygame.font.SysFont(font_name, int(base_scale * 0.44))          # Small text (35)
        self.font_caption = pygame.font.SysFont(font_name, int(base_scale * 0.38))        # Caption/tiny (30)
        
       # === LIGHT THEME INDUSTRIAL HMI COLORS ===
        self.COLOR_BG = (245, 248, 250)                 # Abu-abu sangat terang (Latar luar)
        self.COLOR_BG_PANEL = (255, 255, 255)           # Putih bersih (Dalam kotak)
        self.COLOR_BG_TERTIARY = (200, 205, 210)        # Abu-abu (Batang kosong / mati)
        
        # === TEXT ===
        self.COLOR_TEXT = (44, 62, 80)                  # Biru Navy Gelap (Teks Utama)
        self.COLOR_TEXT_SECONDARY = (127, 140, 141)     # Abu-abu (Sub-teks)
        self.COLOR_TEXT_TERTIARY = (44, 62, 80)         # Teks Institusi
        
        # === STATUS & BARS ===
        self.COLOR_PRIMARY = (41, 142, 216)             # Biru (Isian Parameter Sistem)
        self.COLOR_SUCCESS = (60, 210, 30)              # Hijau (Isian Daya Output)
        self.COLOR_WARNING = (255, 180, 0)              # Oranye/Kuning Emas (Suhu)
        self.COLOR_ERROR = (255, 59, 48)                # Merah Terang (Pompa OFF)
        
        # === UI ELEMENTS ===
        self.COLOR_BORDER = (150, 150, 150)             # Abu-abu (Garis kotak panel)
        self.COLOR_GOLD = (44, 62, 80)                  # Judul Header sekarang gelap
        self.COLOR_INSTRUCTION = (104, 159, 170)        # Biru Tosca (Header Instruksi)
        
        # === MISSING COLOR DEFINITIONS (Fixed) ===
        self.COLOR_PRIMARY_BRIGHT = (41, 178, 240)      # Biru Cerah untuk highlight
        self.COLOR_DARK_NAVY = (20, 40, 60)             # Navy Gelap untuk contrast
        self.COLOR_PRIMARY_LIGHT = (70, 160, 210)       # Biru Muda untuk instruksi
        self.COLOR_INFO = (66, 165, 245)                # Biru Info
        
        # Legacy compatibility (deprecated, will be removed)
        self.COLOR_ACCENT = self.COLOR_PRIMARY
        
        # Logo sizes - scaled for 4K (larger for better visibility)
        self.logo_size_large = (int(150 * self.scale), int(150 * self.scale))  # IDLE mode (increased from 120)
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
            self.key_press_times = {}  # key_code -> press_time
            self.key_held_flags = {}   # key_code -> is_held
            
            # Track user interaction untuk mode transition
            self.user_has_interacted = False  # Start False, switch to True on first input

        else:
            print("🚀 PRODUCTION MODE")
            print(f"   Reading state from: {self.state_file}")
        
        print(f"🎬 Video Display App initialized")
        print(f"   Screen: {self.width}x{self.height}")
        print(f"   Fullscreen: {self.fullscreen}")
        if self.logo_brin and self.logo_poltek:
            print(f"   ✅ Logos loaded successfully")
        else:
            print(f"   ⚠️  Logos not found (will skip)")
    
    def load_logos(self):
        """Load BRIN and Poltek logos from assets folder"""
        # Initialize to None first
        self.logo_brin = None
        self.logo_poltek = None
        self.icon_pump_on = None
        self.icon_pump_off = None
        
        # Load Logos
        try:
            logo_path_brin = Path(__file__).parent / "assets" / "logo-brin.png"
            logo_path_poltek = Path(__file__).parent / "assets" / "logo-poltek.png"
            
            if logo_path_brin.exists():
                logo_img = pygame.image.load(str(logo_path_brin))
                self.logo_brin = pygame.transform.smoothscale(logo_img, self.logo_size_large)
                print(f"   ✅ Loaded BRIN logo")
            else:
                print(f"   ⚠️  BRIN logo not found: {logo_path_brin}")
            
            if logo_path_poltek.exists():
                logo_img = pygame.image.load(str(logo_path_poltek))
                self.logo_poltek = pygame.transform.smoothscale(logo_img, self.logo_size_large)
                print(f"   ✅ Loaded Poltek logo")
            else:
                print(f"   ⚠️  Poltek logo not found: {logo_path_poltek}")
        except Exception as e:
            print(f"   ❌ Error loading logos: {e}")
            self.logo_brin = None
            self.logo_poltek = None

        # Load Pump Icons
        try:
            self.pump_icon_size = (int(100 * self.scale), int(143.84 * self.scale))
            pump_on_path = Path(__file__).parent / "assets" / "pompa_on.png"
            pump_off_path = Path(__file__).parent / "assets" / "pompa_off.png"
            
            if pump_on_path.exists() and pump_off_path.exists():
                img_on = pygame.image.load(str(pump_on_path)).convert_alpha()
                img_off = pygame.image.load(str(pump_off_path)).convert_alpha()
                
                self.icon_pump_on = pygame.transform.smoothscale(img_on, self.pump_icon_size)
                self.icon_pump_off = pygame.transform.smoothscale(img_off, self.pump_icon_size)
                print(f"   ✅ Loaded Pump Icons from: {pump_on_path}")
            else:
                print(f"   ⚠️  Pump icons not found. Looked at: {pump_on_path}")
                self.icon_pump_on = None
                self.icon_pump_off = None
        except Exception as e:
            print(f"   ❌ Error loading pump icons: {e}")
            self.icon_pump_on = None
            self.icon_pump_off = None
    
    def create_mock_state(self) -> Dict:
        """Create mock state for testing - recalculates thermal_kw from current rod positions
        
        Uses ESP-BC formula (esp_utama_uart.ino lines 575-596):
        - ONLY shim_rod and regulating_rod contribute to power (NOT safety_rod!)
        - Complex quadratic formula with turbine efficiency
        """
        # Get current rod positions from existing mock_state (updated by keyboard input)
        current_safety = self.mock_state.get("safety_rod", 0) if hasattr(self, 'mock_state') else 0
        current_shim = self.mock_state.get("shim_rod", 0) if hasattr(self, 'mock_state') else 0
        current_reg = self.mock_state.get("regulating_rod", 0) if hasattr(self, 'mock_state') else 0
        
        # === ESP-BC THERMAL POWER CALCULATION ===
        # ONLY shim_rod and regulating_rod contribute to power!
        avg_rod_position = (current_shim + current_reg) / 2.0
        reactor_thermal_kw = 0.0
        
        if avg_rod_position > 10.0:
            # Quadratic formula for reactor thermal capacity
            reactor_thermal_kw = avg_rod_position * avg_rod_position * 90.0
            reactor_thermal_kw += current_shim * 150.0
            reactor_thermal_kw += current_reg * 200.0
        
        # Cap at 900 MW thermal
        if reactor_thermal_kw > 900000.0:
            reactor_thermal_kw = 900000.0
        
        # For test mode, assume turbine is running at 100% load
        # In production, this comes from ESP-BC turbine state
        turbine_load = 1.0  # 100% load for test mode
        TURBINE_EFFICIENCY = 0.34  # 34% efficiency
        
        thermal_kw = reactor_thermal_kw * TURBINE_EFFICIENCY * turbine_load
        
        # Cap at 300 MW electrical
        if thermal_kw < 0.0:
            thermal_kw = 0.0
        if thermal_kw > 300000.0:
            thermal_kw = 300000.0
        
        # DEBUG: Print thermal power calculation
        if hasattr(self, 'mock_state') and (current_shim > 0 or current_reg > 0):
            print(f"\n=== THERMAL POWER DEBUG ===")
            print(f"Shim Rod: {current_shim}%, Regulating Rod: {current_reg}%")
            print(f"Avg Rod Position: {avg_rod_position:.1f}%")
            print(f"Reactor Thermal: {reactor_thermal_kw:.1f} kW = {reactor_thermal_kw/1000:.1f} MW")
            print(f"Electrical Output: {thermal_kw:.1f} kW = {thermal_kw/1000:.1f} MW")
            print(f"==========================\n")
        
        return {
            "timestamp": time.time(),
            "mode": "manual",
            "auto_running": False,
            "auto_phase": "",
            "pressure": self.mock_state.get("pressure", 0.0) if hasattr(self, 'mock_state') else 0.0,
            "safety_rod": current_safety,
            "shim_rod": current_shim,
            "regulating_rod": current_reg,
            "pump_primary": self.mock_state.get("pump_primary", 0) if hasattr(self, 'mock_state') else 0,
            "pump_secondary": self.mock_state.get("pump_secondary", 0) if hasattr(self, 'mock_state') else 0,
            "pump_tertiary": self.mock_state.get("pump_tertiary", 0) if hasattr(self, 'mock_state') else 0,
            "thermal_kw": thermal_kw,  # ESP-BC formula: only shim + regulating contribute
            "turbine_speed": self.mock_state.get("turbine_speed", 0.0) if hasattr(self, 'mock_state') else 0.0,
            "emergency": self.mock_state.get("emergency", False) if hasattr(self, 'mock_state') else False
        }
    
    def read_simulation_state(self) -> Dict:
        """
        Read state from backend simulation
        In test mode: return mock state (recalculated)
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
            
            # CRITICAL FIX: Recalculate thermal_kw from current rod positions!
            # This ensures speedometer shows updated power values
            recalculated_state = self.create_mock_state()
            return recalculated_state
        
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
                if (abs(current_pressure - self.last_pressure) > 0.1 or
                    abs(current_rods - self.last_rods_sum) > 10):
                    
                    # Only consider as interaction if not during auto simulation
                    auto_running = state.get("auto_running", False)
                    if not auto_running:
                        self.user_has_interacted = True
                        print("👤 User interaction detected - enabling MANUAL mode")
                
            # Also check if HUD manual mode was started via file flag
            if not self.user_has_interacted and hasattr(self, 'manual_flag_file') and self.manual_flag_file.exists():
                self.user_has_interacted = True
                print("👤 Touch panel HUD started - enabling MANUAL mode")
                
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
        
        current_time = time.time()
        
        if event.type == pygame.KEYDOWN:
            # Check if key is mapped to a button
            if event.key in KEYBOARD_MAPPING:
                button_name = KEYBOARD_MAPPING[event.key]
                if button_name in ["PRESSURE_UP", "PRESSURE_DOWN"]:
                    self.key_press_times[event.key] = current_time
                    self.key_held_flags[event.key] = False
                elif button_name in EDGE_BUTTONS:
                    self.trigger_button_action(button_name)
            
            # Mode switching keys (Test mode only)
            elif event.key == pygame.K_i:  # I for IDLE
                self.reset_simulation()
                print(f"  → Mode: IDLE")
            elif event.key == pygame.K_m:  # M for MANUAL
                self.mock_mode = "manual"
                self.user_has_interacted = True
                print(f"  → Mode: MANUAL")
            elif event.key == pygame.K_a:  # A for AUTO
                self.mock_mode = "auto"
                self.mock_state["auto_running"] = True
                print(f"  → Mode: AUTO")
            elif event.key == pygame.K_ESCAPE:
                return False  # Exit signal
                
        elif event.type == pygame.KEYUP:
            if event.key in KEYBOARD_MAPPING:
                button_name = KEYBOARD_MAPPING[event.key]
                if button_name in ["PRESSURE_UP", "PRESSURE_DOWN"]:
                    if event.key in self.key_press_times:
                        is_held = self.key_held_flags.get(event.key, False)
                        if not is_held:
                            fast_action = "PRESSURE_UP_FAST" if button_name == "PRESSURE_UP" else "PRESSURE_DOWN_FAST"
                            self.trigger_button_action(fast_action)
                        self.key_press_times.pop(event.key, None)
                        self.key_held_flags.pop(event.key, None)
    
    def check_held_keys(self):
        """Check for held keys (level detection) - called in update loop"""
        if not self.test_mode:
            return
        
        current_time = time.time()
        keys = pygame.key.get_pressed()
        
        for key_code, button_name in KEYBOARD_MAPPING.items():
            if button_name in LEVEL_BUTTONS:
                if keys[key_code]:
                    if button_name in ["PRESSURE_UP", "PRESSURE_DOWN"]:
                        press_time = self.key_press_times.get(key_code)
                        if press_time is not None and (current_time - press_time > 0.30):
                            self.key_held_flags[key_code] = True
                            last_trigger = self.last_key_trigger.get(button_name, 0)
                            if current_time - last_trigger >= self.key_repeat_interval:
                                self.trigger_button_action(button_name)
                                self.last_key_trigger[button_name] = current_time
                    else:
                        # Check if enough time has passed for repeat trigger
                        last_trigger = self.last_key_trigger.get(button_name, 0)
                        if current_time - last_trigger >= self.key_repeat_interval:
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
        
        # Pressure (increment/decrement by 0.05 bar on hold/tap, 0.25 bar on fast)
        elif button_name == "PRESSURE_UP":
            self.mock_state["pressure"] = min(200.0, self.mock_state["pressure"] + 0.05)
        elif button_name == "PRESSURE_DOWN":
            self.mock_state["pressure"] = max(0.0, self.mock_state["pressure"] - 0.05)
        elif button_name == "PRESSURE_UP_FAST":
            self.mock_state["pressure"] = min(200.0, self.mock_state["pressure"] + 0.25)
        elif button_name == "PRESSURE_DOWN_FAST":
            self.mock_state["pressure"] = max(0.0, self.mock_state["pressure"] - 0.25)
        
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
        # Pumps are NOT stopped during emergency (decay heat removal)
        self.mock_mode = "manual"  # Tetap di MANUAL untuk melihat status
        self.user_has_interacted = True  # Keep interaction flag True to show status
        print("  → Emergency: All rods inserted, pumps running, switching to MANUAL")

    
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
        
        import pwd
        import os
        try:
            target_user = pwd.getpwuid(1000).pw_name
            target_home = pwd.getpwuid(1000).pw_dir
        except Exception:
            target_user = "pi"
            target_home = "/home/pi"

        # Check if video file exists
        if not Path(video_path).exists():
            print(f"❌ Video not found: {video_path}")
            if self.test_mode:
                print("   💡 In test mode, this is expected")
                print("   💡 Create video file or use placeholder")
            return
        
        # Build mpv command optimized for Wayland/Raspberry Pi 4
        cmd = [
            "mpv",
            "--fullscreen",
            "--no-border",
            "--window-maximized=yes",
            "--autofit=100%x100%",
            "--fs-screen-name=HDMI-A-1", # As seen in wlr-randr for the 4K monitor
            "--ontop",
            "--vo=dmabuf-wayland",
            "--hwdec=v4l2m2m",
            "--keep-open=yes",
            "--no-osd-bar",             
            "--no-input-default-bindings",  
            "--really-quiet",
            "--ao=alsa",
            "--audio-device=alsa/plughw:1,0",
            "--audio-fallback-to-null=yes",
            "--audio-channels=stereo",
            "--volume=100",
            video_path
        ]
        
        if loop:
            cmd.insert(1, '--loop=inf')
            
        # If running as root (e.g. systemd service), run mpv as the normal user
        # to avoid XDG_RUNTIME_DIR ownership errors
        if os.geteuid() == 0:
            print(f"   Running as root. Dropping privileges to user: {target_user} for mpv")
            cmd = ['sudo', '-u', target_user, 'env', 'WAYLAND_DISPLAY=wayland-0', 'XDG_RUNTIME_DIR=/run/user/1000', 'AUDIODEV=hw:1,0'] + cmd
        
        try:
            # Set environment for mpv
            env = {
                'DISPLAY': ':0',
                'WAYLAND_DISPLAY': 'wayland-0', # Re-enabled for native Wayland performance
                'XDG_RUNTIME_DIR': '/run/user/1000',
                'AUDIODEV': 'hw:1,0'    # Force HDMI audio device
            }
            
            # Combine current os.environ with our custom env variables
            process_env = os.environ.copy()
            process_env.update(env)
            
            self.video_process = subprocess.Popen(
                cmd,
                env=process_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.current_video = video_path
            print(f"▶️  Playing: {Path(video_path).name}")
            print(f"   Using Wayland GPU context with hardware decode")
            print(f"   Audio output: PipeWire → HDMI (Built-in Audio Digital Stereo)")
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
        """Display idle/intro screen - Redesigned to match new UI Mockup"""
        self.screen.fill(self.COLOR_BG)
        
        # Efek kedip (fade) untuk teks instruksi
        self.idle_fade_alpha += self.idle_fade_direction * self.idle_fade_speed
        if self.idle_fade_alpha >= 255:
            self.idle_fade_alpha = 255
            self.idle_fade_direction = -1
        elif self.idle_fade_alpha <= 100:
            self.idle_fade_alpha = 100
            self.idle_fade_direction = 1
        
        # === 1. BAGIAN HEADER (Logo dan Garis) ===
        header_y = int(40 * self.scale)
        margin_x = int(60 * self.scale)
        
        # Logo BRIN (Kiri Atas)
        if self.logo_brin:
            self.screen.blit(self.logo_brin, (margin_x, header_y))
        
        # Logo Poltek (Kanan Atas)
        if self.logo_poltek:
            logo_x = self.width - self.logo_size_large[0] - margin_x
            self.screen.blit(self.logo_poltek, (logo_x, header_y))
            
        # Garis Pemisah Horizontal (Sesuai mockup)
        line_y = header_y + int(180 * self.scale)
        pygame.draw.line(self.screen, self.COLOR_TEXT_TERTIARY, (margin_x, line_y), (self.width - margin_x, line_y), max(int(3* self.scale), 1))
        
        # === 2. BAGIAN TENGAH (Judul Utama) ===
        center_y_start = self.height // 2 - int(180 * self.scale)
        
        # Baris 1: ALAT PERAGA PLTN TIPE PWR (Warna Emas/Orange)
        title1_text = "ALAT PERAGA PLTN TIPE PWR"
        title1 = self.font_display.render(title1_text, True, self.COLOR_PRIMARY_BRIGHT)
        title1_rect = title1.get_rect(center=(self.width//2, center_y_start))
        self.screen.blit(title1, title1_rect)
        
        # Baris 2: BERBASIS MIKROKONTROLLER (Warna Putih)
        title2_text = "BERBASIS MIKROKONTROLLER"
        title2 = self.font_title.render(title2_text, True, self.COLOR_TEXT)
        title2_rect = title2.get_rect(center=(self.width//2, center_y_start + int(80 * self.scale)))
        self.screen.blit(title2, title2_rect)
        
        # Baris 3: Nama Institusi (Warna Biru Muda)
        title3_text = "POLITEKNIK TEKNOLOGI NUKLIR INDONESIA"
        title3 = self.font_subtitle.render(title3_text, True, self.COLOR_TEXT_TERTIARY)
        title3_rect = title3.get_rect(center=(self.width//2, center_y_start + int(150 * self.scale)))
        self.screen.blit(title3, title3_rect)
        
        # === 3. BAGIAN TOMBOL / BADGE "SIMULASI SIAP" ===
        badge_y = center_y_start + int(310 * self.scale)
        badge_width = int(450 * self.scale)
        badge_height = int(90 * self.scale)
        badge_rect = pygame.Rect(0, 0, badge_width, badge_height)
        badge_rect.center = (self.width//2, badge_y)
        
        # Latar belakang tombol (Warna Emas/Orange dengan sudut melengkung)
        pygame.draw.rect(self.screen, self.COLOR_WARNING, badge_rect, border_radius=int(10 * self.scale))
        
        # Teks dalam tombol (Warna Gelap/Background agar kontras)
        badge_text = self.font_subtitle.render("SIMULASI SIAP", True, self.COLOR_DARK_NAVY)
        badge_text_rect = badge_text.get_rect(center=badge_rect.center)
        self.screen.blit(badge_text, badge_text_rect)
        
        # === 4. INSTRUKSI & MODE TEST ===
        inst_y = badge_y + int(80 * self.scale)
        
        # Teks instruksi berkedip (Biru Muda)
        inst_text = self.font_body.render("Tekan Tombol Untuk Memulai Simulasi", True, self.COLOR_PRIMARY_LIGHT)
        inst_text.set_alpha(int(self.idle_fade_alpha))  # Efek berkedip
        inst_rect = inst_text.get_rect(center=(self.width//2, inst_y))
        self.screen.blit(inst_text, inst_rect)
        
        # Indikator Mode Test (Warna Merah)
        if self.test_mode:
            test_y = inst_y + int(50 * self.scale)
            test_text = self.font_small.render("Test Mode: Tekan I/M/A Untuk Mengganti Mode | ESC Untuk Keluar", 
                                               True, self.COLOR_ERROR)
            test_rect = test_text.get_rect(center=(self.width//2, test_y))
            self.screen.blit(test_text, test_rect)
        
        # === 5. DESKRIPSI BAWAH ===
        desc_y_start = self.height - int(150 * self.scale)
        desc_lines = [
            "Simulasi Interaktif Untuk Pembelajaran",
            "Pembangkit Listrik Tenaga Nuklir (PLTN)",
            "Dengan Teknologi Pressurized Water Reactor (PWR)"
        ]
        for i, line in enumerate(desc_lines):
            # Menggunakan warna biru muda sesuai mockup
            desc_text = self.font_small.render(line, True, self.COLOR_PRIMARY)
            desc_rect = desc_text.get_rect(center=(self.width//2, desc_y_start + i * int(40 * self.scale)))
            self.screen.blit(desc_text, desc_rect)
        
        pygame.display.flip()
    
    def draw_reactor_diagnostic_displays(self, state: Dict, start_x: int, start_y: int, width: int, height: int):
        """Draw Reactor Diagnostic Displays in a hierarchical layout"""
        
        # 1. Gauges Row (Side-by-Side: Power and Pressure)
        gauge_y = start_y + int(140 * self.scale)
        
        # Left Gauge: Thermal Power
        thermal_mw = state.get("thermal_kw", 0.0) / 1000.0
        power_cx = start_x + width // 4
        self.draw_gauge(power_cx, gauge_y, thermal_mw, 300.0, "Listrik Dihasilkan", "{:.2f} MW")
        
        # Right Gauge: Pressurizer
        press_val = state.get("pressure", 0)
        press_cx = start_x + (3 * width) // 4
        self.draw_gauge(press_cx, gauge_y, press_val, 200.0, "Tekanan Pressurizer", "{:.2f} bar", warn_val=160.0, crit_val=180.0)
            
        # 2. Bottom Row: Pump Status (Full Width)
        bottom_y = gauge_y + int(240 * self.scale)
        bottom_h = height - (bottom_y - start_y)
        
        box_x = start_x + int(10 * self.scale)
        box_w = width - int(20 * self.scale)
        box_rect = pygame.Rect(box_x, bottom_y, box_w, bottom_h)
        pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, box_rect, border_radius=int(8 * self.scale))
        pygame.draw.rect(self.screen, self.COLOR_BORDER, box_rect, max(int(1 * self.scale), 1), border_radius=int(8 * self.scale))
        
        pump_title = self.font_medium.render("STATUS POMPA PENDINGIN", True, self.COLOR_TEXT)
        self.screen.blit(pump_title, pump_title.get_rect(center=(box_x + box_w // 2, bottom_y + int(35 * self.scale))))
        
        pumps = [
            ("Primer", state.get("pump_primary", 0) > 0),
            ("Sekunder", state.get("pump_secondary", 0) > 0),
            ("Tersier", state.get("pump_tertiary", 0) > 0)
        ]
        
        segment_w = box_w // 3
        # Center the pump vertically in the remaining space below the title
        item_y = bottom_y + int(35 * self.scale) + (bottom_h - int(35 * self.scale)) // 2
        
        for idx, (name, is_on) in enumerate(pumps):
            center_x = box_x + idx * segment_w + segment_w // 2
            
            # Check LOFA status for this pump
            is_lofa = False
            if name == "Primer" and state.get("lofa_primary", False): is_lofa = True
            if name == "Sekunder" and state.get("lofa_secondary", False): is_lofa = True
            if name == "Tersier" and state.get("lofa_tertiary", False): is_lofa = True
            
            import time
            if is_lofa and int(time.time() * 2) % 2 == 0:
                # Blink effect behind the pump
                pygame.draw.circle(self.screen, self.COLOR_ERROR, (center_x, item_y), int(55 * self.scale))
                
            # Draw the actual pump icon/image
            self.draw_centrifugal_pump(center_x, item_y, is_on)
            
            # Draw label below the pump
            status_str = "AKTIF" if is_on else "MATI (GAGAL)" if is_lofa else "MATI"
            lbl_color = self.COLOR_ERROR if is_lofa else self.COLOR_TEXT
            lbl_pump = self.font_body.render(f"Pompa {name}: {status_str}", True, lbl_color)
            self.screen.blit(lbl_pump, lbl_pump.get_rect(center=(center_x, item_y + int(95 * self.scale))))

    def draw_manual_guide(self, state: Dict):
        """Display SCADA/HMI Light Theme Layout"""
        self.screen.fill(self.COLOR_BG)
        
        # === HEADER BAR (Sama seperti sebelumnya) ===
        header_y = int(30 * self.scale)
        margin_x = int(40 * self.scale)
        
        if self.logo_brin:
            logo_small_brin = pygame.transform.smoothscale(self.logo_brin, self.logo_size_small)
            self.screen.blit(logo_small_brin, (margin_x, header_y))
        if self.logo_poltek:
            logo_small_poltek = pygame.transform.smoothscale(self.logo_poltek, self.logo_size_small)
            self.screen.blit(logo_small_poltek, (self.width - self.logo_size_small[0] - margin_x, header_y))
        
        header_title = self.font_title.render("ALAT PERAGA PLTN TIPE PWR", True, self.COLOR_TEXT)
        self.screen.blit(header_title, header_title.get_rect(center=(self.width//2, header_y + int(40 * self.scale))))
        
        line_y = header_y + int(120 * self.scale)
        pygame.draw.line(self.screen, self.COLOR_BORDER, (margin_x, line_y), (self.width - margin_x, line_y), max(int(2 * self.scale), 1))
        
        # === STATUS BANNER (Sistem Normal / Peringatan / Bahaya) ===
        banner_y = line_y + int(15 * self.scale)
        banner_h = int(60 * self.scale)
        content_y = banner_y + banner_h + int(20 * self.scale)
        
        current_pressure = state.get("pressure", 0)
        default_temp = state.get("temperature", (current_pressure / 160.0) * 300.0)
        core_temp = state.get("temperature_core", default_temp)
        
        import time
        blink_on = int(time.time() * 2) % 2 == 0
        
        status_text = "SISTEM PLTN NORMAL"
        status_color = self.COLOR_SUCCESS
        status_text_color = (255, 255, 255)
        
        press_crit = current_pressure > 180
        temp_crit = core_temp > 500
        press_warn = current_pressure > 160
        temp_warn = core_temp > 400
        
        if press_crit and temp_crit:
            status_color = self.COLOR_ERROR
            status_text = "BAHAYA: SUHU & TEKANAN KRITIS"
            if blink_on: status_color = (200, 0, 0)
        elif press_crit:
            status_color = self.COLOR_ERROR
            status_text = "BAHAYA: TEKANAN KRITIS"
            if blink_on: status_color = (200, 0, 0)
        elif temp_crit:
            status_color = self.COLOR_ERROR
            status_text = "BAHAYA: SUHU KRITIS"
            if blink_on: status_color = (200, 0, 0)
        elif press_warn and temp_warn:
            status_color = self.COLOR_WARNING
            status_text = "PERINGATAN: SUHU & TEKANAN TINGGI"
            status_text_color = (0, 0, 0)
        elif press_warn:
            status_color = self.COLOR_WARNING
            status_text = "PERINGATAN: TEKANAN TINGGI"
            status_text_color = (0, 0, 0)
        elif temp_warn:
            status_color = self.COLOR_WARNING
            status_text = "PERINGATAN: SUHU TINGGI"
            status_text_color = (0, 0, 0)
            
        relief_open = state.get("relief_valve_open", False)
        mitigasi_text = f"Relief Valve: {'TERBUKA' if relief_open else 'MENUTUP'}"
        mitigasi_color = self.COLOR_ERROR if relief_open else self.COLOR_BG_PANEL
        if relief_open and blink_on:
            mitigasi_color = (200, 0, 0)
        mitigasi_text_color = (255, 255, 255) if relief_open else self.COLOR_TEXT
        
        lofa_active = state.get("lofa_primary", False) or state.get("lofa_secondary", False) or state.get("lofa_tertiary", False)
        lofa_text = "PERINGATAN: LOFA AKTIF" if lofa_active else "LOFA: TIDAK AKTIF"
        lofa_color = self.COLOR_ERROR if lofa_active else self.COLOR_BG_PANEL
        if lofa_active and blink_on:
            lofa_color = (200, 0, 0)
        lofa_text_color = (255, 255, 255) if lofa_active else self.COLOR_TEXT
        
        box_gap = int(15 * self.scale)
        box_w = (self.width - 2 * margin_x - 2 * box_gap) // 3
        
        boxes = [
            (margin_x, status_color, status_text, status_text_color),
            (margin_x + box_w + box_gap, mitigasi_color, mitigasi_text, mitigasi_text_color),
            (margin_x + 2 * (box_w + box_gap), lofa_color, lofa_text, lofa_text_color)
        ]
        
        for bx, bcolor, btext, btcolor in boxes:
            brect = pygame.Rect(bx, banner_y, box_w, banner_h)
            pygame.draw.rect(self.screen, bcolor, brect, border_radius=int(8 * self.scale))
            pygame.draw.rect(self.screen, self.COLOR_BORDER, brect, max(int(2 * self.scale), 1), border_radius=int(8 * self.scale))
            bsurf = self.font_medium.render(btext, True, btcolor)
            self.screen.blit(bsurf, bsurf.get_rect(center=(bx + box_w//2, banner_y + banner_h//2)))
        
        # === MENGHITUNG GRID LAYOUT (Improved proportions) ===
        panel_gap = int(20 * self.scale)  # Gap antar panel (vertikal dan horizontal sama)
        
        # Better column split dengan gap yang sama
        col_gap = panel_gap  # Gap horizontal = gap vertikal
        left_col_w = int((self.width - 2 * margin_x - col_gap) * 0.63)
        right_col_w = int((self.width - 2 * margin_x - col_gap) * 0.37)
        right_col_x = margin_x + left_col_w + col_gap
        
        # === KIRI: REACTOR DIAGNOSTIC DISPLAYS ===
        diag_h = self.height - content_y - int(40 * self.scale)
        self.draw_boxed_panel(margin_x, content_y, left_col_w, diag_h, "REACTOR DIAGNOSTIC DISPLAYS")
        
        # Content area setelah judul (80px reserved untuk judul + garis)
        diag_content_y = content_y + int(80 * self.scale)
        diag_content_h = diag_h - int(100 * self.scale)
        self.draw_reactor_diagnostic_displays(state, margin_x, diag_content_y, left_col_w, diag_content_h)

        # === KANAN 1: MONITOR SUHU (LOFA) ===
        temp_y = content_y
        temp_h = int(260 * self.scale)
        self.draw_boxed_panel(right_col_x, temp_y, right_col_w, temp_h, "MONITOR SUHU (LOFA)")
        
        # Read temperatures from state (fallback to calculated if not available)
        ambient_temp = 28.0  # Suhu ruangan normal
        # Jika belum beroperasi, suhu minimal adalah suhu ruangan
        default_temp = state.get("temperature", max(ambient_temp, (state.get("pressure", 0) / 160.0) * 300.0))
        
        core_temp = max(ambient_temp, state.get("temperature_core", default_temp))
        clad_temp = max(ambient_temp, state.get("temperature_fuel_cladding", ambient_temp + (core_temp - ambient_temp) * 0.95))
        prim_temp = max(ambient_temp, state.get("temperature_coolant_primary", ambient_temp + (clad_temp - ambient_temp) * 0.85))
        sec_temp = max(ambient_temp, state.get("temperature_coolant_secondary", ambient_temp + (prim_temp - ambient_temp) * 0.70))
        
        temps = [
            ("Bahan Bakar", core_temp, 350.0),
            ("Cladding", clad_temp, 350.0),
            ("Aliran Primer", prim_temp, 300.0),
            ("Aliran Sekunder", sec_temp, 250.0)
        ]
        
        temp_content_y = temp_y + int(80*self.scale)
        temp_content_h = temp_h - int(155*self.scale)
        bar_w = int(40 * self.scale)
        spacing = int((right_col_w - (4 * bar_w)) / 5)
        
        for i, (name, val, max_val) in enumerate(temps):
            bar_x = right_col_x + spacing + i * (bar_w + spacing)
            self.draw_vertical_temperature_bar(bar_x, temp_content_y, bar_w, temp_content_h, val, max_val)
            
            # Label (Bisa dua baris jika ada spasi)
            if " " in name:
                words = name.split(" ")
                lbl1 = self.font_caption.render(words[0], True, self.COLOR_TEXT_SECONDARY)
                lbl2 = self.font_caption.render(words[1], True, self.COLOR_TEXT_SECONDARY)
                self.screen.blit(lbl1, lbl1.get_rect(center=(bar_x + bar_w//2, temp_content_y + temp_content_h + int(15*self.scale))))
                self.screen.blit(lbl2, lbl2.get_rect(center=(bar_x + bar_w//2, temp_content_y + temp_content_h + int(30*self.scale))))
                val_y = temp_content_y + temp_content_h + int(52*self.scale)
            else:
                lbl = self.font_caption.render(name, True, self.COLOR_TEXT_SECONDARY)
                self.screen.blit(lbl, lbl.get_rect(center=(bar_x + bar_w//2, temp_content_y + temp_content_h + int(22*self.scale))))
                val_y = temp_content_y + temp_content_h + int(52*self.scale)
            
            # Value
            val_txt = self.font_small.render(f"{val:.0f}°C", True, self.COLOR_TEXT)
            self.screen.blit(val_txt, val_txt.get_rect(center=(bar_x + bar_w//2, val_y)))

        # === KANAN 2: POSISI BATANG KENDALI ===
        rods_y = temp_y + temp_h + panel_gap
        rods_h = int(240 * self.scale)
        self.draw_boxed_panel(right_col_x, rods_y, right_col_w, rods_h, "POSISI BATANG KENDALI")
        
        rods = [
            ("Safety", state.get("safety_rod", 0)),
            ("Shim", state.get("shim_rod", 0)),
            ("Regulating", state.get("regulating_rod", 0))
        ]
        
        rod_content_y = rods_y + int(80*self.scale)
        rod_content_h = rods_h - int(130*self.scale)
        rod_bar_w = int(40 * self.scale)
        rod_spacing = int((right_col_w - (3 * rod_bar_w)) / 4)
        
        for i, (name, val) in enumerate(rods):
            bar_x = right_col_x + rod_spacing + i * (rod_bar_w + rod_spacing)
            
            # Background Bar
            bg_rect = pygame.Rect(bar_x, rod_content_y, rod_bar_w, rod_content_h)
            pygame.draw.rect(self.screen, self.COLOR_BG_TERTIARY, bg_rect, border_radius=int(6 * self.scale))
            pygame.draw.rect(self.screen, self.COLOR_BORDER, bg_rect, max(int(1 * self.scale), 1), border_radius=int(6 * self.scale))
            
            # Fill Bar (from bottom up)
            f_ratio = min(max(val / 100.0, 0.0), 1.0)
            f_h = int((rod_content_h - 4) * f_ratio)
            if f_h > 0:
                f_y = bg_rect.bottom - 2 - f_h
                f_rect = pygame.Rect(bar_x + 2, f_y, rod_bar_w - 4, f_h)
                fill_color = self.COLOR_WARNING if name == "Safety" else self.COLOR_SUCCESS
                pygame.draw.rect(self.screen, fill_color, f_rect, border_radius=int(4 * self.scale))
            
            # Label
            lbl = self.font_caption.render(name, True, self.COLOR_TEXT_SECONDARY)
            self.screen.blit(lbl, lbl.get_rect(center=(bar_x + rod_bar_w//2, rod_content_y + rod_content_h + int(15*self.scale))))
            
            # Value
            val_txt = self.font_small.render(f"{val:.0f}%", True, self.COLOR_TEXT)
            self.screen.blit(val_txt, val_txt.get_rect(center=(bar_x + rod_bar_w//2, rod_content_y + rod_content_h + int(35*self.scale))))

        # === KANAN 3: PANDUAN OPERASI ===
        inst_y = rods_y + rods_h + panel_gap
        inst_h = self.height - inst_y - int(40 * self.scale)
        inst_rect = pygame.Rect(right_col_x, inst_y, right_col_w, inst_h)
        
        pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, inst_rect, border_radius=int(8*self.scale))
        pygame.draw.rect(self.screen, self.COLOR_BORDER, inst_rect, max(int(3 * self.scale), 1), border_radius=int(8*self.scale))
        
        header_h = int(60*self.scale)
        header_rect = pygame.Rect(right_col_x, inst_y, right_col_w, header_h)
        pygame.draw.rect(self.screen, self.COLOR_PRIMARY, header_rect, border_top_left_radius=int(8*self.scale), border_top_right_radius=int(8*self.scale))
        
        inst_title = self.font_heading.render("PANDUAN OPERASI", True, (255,255,255))
        self.screen.blit(inst_title, inst_title.get_rect(center=(right_col_x + right_col_w//2, inst_y + header_h//2)))
        
        step_text = self.get_current_step_instruction(state)
        y_offset = inst_y + header_h + int(15 * self.scale)
        x_margin = right_col_x + int(25*self.scale)
        max_text_width = right_col_w - int(50*self.scale)  # Margin kiri & kanan
        
        for i, line in enumerate(step_text):
            if line:
                # Pilih font berdasarkan baris pertama atau baris lainnya
                if i == 0:
                    font_to_use = self.font_medium
                    color_to_use = self.COLOR_TEXT
                else:
                    font_to_use = self.font_body
                    color_to_use = self.COLOR_TEXT_SECONDARY
                
                # Bungkus text agar sesuai dengan lebar panel
                wrapped_lines = self.wrap_text(line, font_to_use, max_text_width)
                
                # Gambar setiap baris wrapped text
                for wrapped_line in wrapped_lines:
                    text = font_to_use.render(wrapped_line, True, color_to_use)
                    self.screen.blit(text, (x_margin, y_offset))
                    y_offset += int(40 * self.scale)  # Jarak antar baris wrapped text
            else:
                y_offset += int(20 * self.scale)  # Spasi untuk baris kosong

        # The old floating pressure warning overlay has been replaced by the Status Banner at the top.
        
        pygame.display.flip()
            
        
        pygame.display.flip()
    
    def get_current_step_instruction(self, state: Dict) -> list:
        """Get instruction text for current step"""
        steps = [
            {
                "text": ["Tahap 1: Nyalakan Pompa Tersier", "Silakan tekan tombol 'POMPA TERSIER ON' di panel kontrol untuk memulai sirkulasi air pendingin luar."],
                "check": lambda s: s.get("pump_tertiary", 0) >= 1
            },
            {
                "text": ["Tahap 2: Nyalakan Pompa Sekunder", "Bagus! Selanjutnya, tekan tombol 'POMPA SEKUNDER ON' untuk mendinginkan uap dari turbin."],
                "check": lambda s: s.get("pump_secondary", 0) >= 1
            },
            {
                "text": ["Tahap 3: Naikkan Tekanan Awal", "Tekan dan tahan tombol 'TEKANAN NAIK' hingga pressurizer mencapai tekanan aman minimal 40 bar."],
                "check": lambda s: s.get("pressure", 0) >= 40
            },
            {
                "text": ["Tahap 4: Nyalakan Pompa Primer", "Tekanan sudah aman! Sekarang tekan tombol 'POMPA PRIMER ON' agar air pendingin reaktor mulai bersirkulasi."],
                "check": lambda s: s.get("pump_primary", 0) >= 1
            },
            {
                "text": ["Tahap 5: Capai Tekanan Operasi", "Kembali tekan dan tahan tombol 'TEKANAN NAIK' sampai mencapai target operasi normal di 140 bar."],
                "check": lambda s: s.get("pressure", 0) >= 140
            },
            {
                "text": ["Tahap 6: Angkat Safety Rod", "Tekanan optimal! Tarik penuh tuas 'SAFETY ROD UP' sampai 100% untuk menyiapkan kondisi kritis."],
                "check": lambda s: s.get("safety_rod", 0) >= 100
            },
            {
                "text": ["Tahap 7: Posisikan Shim Rod", "Tarik batang kendali utama dengan tuas 'SHIM ROD UP' perlahan hingga mencapai posisi 50%."],
                "check": lambda s: s.get("shim_rod", 0) >= 50
            },
            {
                "text": ["Tahap 8: Naikkan Daya Reaktor", "Terakhir, tarik tuas pengatur 'REGULATING ROD UP' hingga 50% untuk mulai memanaskan air reaktor."],
                "check": lambda s: s.get("regulating_rod", 0) >= 50
            },
            {
                "text": ["Selamat! Reaktor Beroperasi Normal", "PLTN kini siap menghasilkan listrik. Jaga agar suhu dan tekanan tetap stabil dalam batas aman."],
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
                "Pertahankan Performa Optimal!", "Gunakan tuas batang kendali untuk mengatur daya sesuai kebutuhan.", "",
                "Jika ingin memulai dari awal, tekan tombol RESET kapan saja."
            ]
    
    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list:
        """
        Membungkus text agar sesuai dengan max_width
        Returns: list of strings (tiap string adalah satu baris)
        """
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            text_width = font.size(test_line)[0]
            
            if text_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]
    
    def draw_boxed_panel(self, x: int, y: int, w: int, h: int, title: str = ""):
        """Menggambar kotak panel putih bergaris abu-abu"""
        panel_rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, panel_rect)
        pygame.draw.rect(self.screen, self.COLOR_BORDER, panel_rect, max(int(2 * self.scale), 1))
        
        if title:
            title_surf = self.font_large.render(title, True, self.COLOR_TEXT)
            # Centered title
            title_rect = title_surf.get_rect(center=(x + w//2, y + int(30 * self.scale)))
            self.screen.blit(title_surf, title_rect)
            
            line_y = y + int(60 * self.scale)
            pygame.draw.line(self.screen, self.COLOR_BORDER, (x, line_y), (x + w, line_y), max(int(2 * self.scale), 1))
        return panel_rect

    def draw_segmented_bars(self, state: Dict, start_x: int, start_y: int, width: int, height: int):
        """Menggambar parameter sistem dengan segment block - fill berjalan continue untuk detail"""
        params = [
            ("TEKANAN", state.get("pressure", 0), 200, "bar", self.COLOR_PRIMARY),
            ("SAFETY ROD", state.get("safety_rod", 0), 100, "%", self.COLOR_PRIMARY),
            ("SHIM ROD", state.get("shim_rod", 0), 100, "%", self.COLOR_PRIMARY),
            ("REGULATING", state.get("regulating_rod", 0), 100, "%", self.COLOR_PRIMARY)
        ]
        
        num_bars = len(params)
        bar_width = int(55 * self.scale)
        segments = 12
        segment_gap = int(5 * self.scale)
        
        # Reserve space untuk label (DALAM content area)
        label_space_top = int(35 * self.scale)
        label_space_bottom = int(55 * self.scale)
        segment_area_h = height - label_space_top - label_space_bottom
        segment_h = (segment_area_h - (segments * segment_gap)) // segments
        
        # Center all bars horizontally
        total_bars_width = num_bars * bar_width
        gap = (width - total_bars_width) // (num_bars + 1)
        
        for i, (label, value, max_val, unit, color) in enumerate(params):
            x_center = start_x + gap * (i + 1) + bar_width * i + (bar_width // 2)
            
            # Label Atas (dalam content area)
            title_surf = self.font_body.render(label, True, self.COLOR_TEXT)
            title_rect = title_surf.get_rect(center=(x_center, start_y + label_space_top // 2))
            self.screen.blit(title_surf, title_rect)
            
            # Calculate percentage (dengan precision float)
            percentage = min(max(value / max_val, 0.0), 1.0)
            
            # Hitung berapa segment yang terisi (dengan decimal)
            filled_segments_float = percentage * segments
            fully_filled = int(filled_segments_float)  # Segment yang penuh terisi
            partial_fill = filled_segments_float - fully_filled  # Sisa decimal (0.0 - 1.0)
            
            # Segments start setelah label atas
            segments_start_y = start_y + label_space_top
            
            # Draw segments dari bawah ke atas
            for seg in range(segments):
                seg_y = segments_start_y + segment_area_h - ((seg + 1) * (segment_h + segment_gap))
                seg_rect = pygame.Rect(x_center - bar_width//2, seg_y, bar_width, segment_h)
                
                # Tentukan warna segment
                if seg < fully_filled:
                    # Segment penuh terisi
                    fill_color = color
                    pygame.draw.rect(self.screen, fill_color, seg_rect, border_radius=int(3*self.scale))
                elif seg == fully_filled and partial_fill > 0.01:
                    # Segment partial (terakhir yang terisi sebagian)
                    # Isi sebagian dari bawah ke atas
                    partial_h = int(segment_h * partial_fill)
                    partial_y = seg_y + segment_h - partial_h
                    partial_rect = pygame.Rect(x_center - bar_width//2, partial_y, bar_width, partial_h)
                    pygame.draw.rect(self.screen, color, partial_rect, border_radius=int(3*self.scale))
                    # Background untuk bagian kosong
                    pygame.draw.rect(self.screen, self.COLOR_BG_TERTIARY, seg_rect, border_radius=int(3*self.scale))
                else:
                    # Segment kosong
                    pygame.draw.rect(self.screen, self.COLOR_BG_TERTIARY, seg_rect, border_radius=int(3*self.scale))
                
                # Border
                pygame.draw.rect(self.screen, self.COLOR_BORDER, seg_rect, max(int(1*self.scale), 1), border_radius=int(3*self.scale))
            
            # Label Bawah (dalam content area)
            val_unit_text = f"{int(value)} {unit}"
            val_surf = self.font_heading.render(val_unit_text, True, self.COLOR_TEXT)
            val_y = start_y + height - label_space_bottom // 2
            val_rect = val_surf.get_rect(center=(x_center, val_y))
            self.screen.blit(val_surf, val_rect)

    def draw_centrifugal_pump(self, x: int, y: int, is_on: bool):
        """Menampilkan ikon Pompa dari file PNG, dengan fallback ke gambar manual jika file tidak ada"""
        
        # Cek apakah file gambar berhasil diload sebelumnya
        if hasattr(self, 'icon_pump_on') and self.icon_pump_on is not None:
            # Jika ada file PNG, gunakan gambarnya
            icon = self.icon_pump_on if is_on else self.icon_pump_off
            
            # Posisikan gambar persis di titik tengah (x, y)
            icon_rect = icon.get_rect(center=(x, y))
            self.screen.blit(icon, icon_rect)
            
        else:
            # === FALLBACK (Jaga-jaga kalau kamu belum punya file PNG-nya) ===
            # Kode lama menggambar manual tetap disimpan di sini sebagai cadangan
            color = self.COLOR_SUCCESS if is_on else self.COLOR_ERROR
            radius = int(35 * self.scale)
            pipe_w = int(25 * self.scale)
            pipe_h = int(40 * self.scale)
            border_w = max(int(2 * self.scale), 1)
            
            pipe_rect = pygame.Rect(x - radius, y - radius - pipe_h + int(10*self.scale), pipe_w, pipe_h)
            pygame.draw.rect(self.screen, color, pipe_rect)
            pygame.draw.rect(self.screen, self.COLOR_TEXT, pipe_rect, border_w)
            
            pygame.draw.circle(self.screen, color, (x, y), radius)
            pygame.draw.circle(self.screen, self.COLOR_TEXT, (x, y), radius, border_w)
            
            pygame.draw.circle(self.screen, self.COLOR_BG_TERTIARY, (x, y), int(radius * 0.4))
            pygame.draw.circle(self.screen, self.COLOR_TEXT, (x, y), int(radius * 0.4), border_w)

    def draw_vertical_temperature_bar(self, x: int, y: int, w: int, h: int, temp: float, max_temp: float):
        """Draw vertical temperature bar with color coding and scale marks"""
        # Lebar background dan fill bisa diatur terpisah
        bar_bg_w = int(w * 0.7)      # Lebar background
        bar_fill_w = int(w * 0.7)   # Lebar fill (bisa berbeda dari background)
        bar_x = x
        
        # Background bar
        bar_rect = pygame.Rect(bar_x, y, bar_bg_w, h)
        pygame.draw.rect(self.screen, self.COLOR_BG_TERTIARY, bar_rect, border_radius=int(8*self.scale))
        pygame.draw.rect(self.screen, self.COLOR_BORDER, bar_rect, max(int(3*self.scale), 1), border_radius=int(8*self.scale))
        
        # Fill - lebar bisa berbeda dari background, di-center di tengahnya
        percentage = min(max(temp / max_temp, 0.0), 1.0)
        fill_h = int(percentage * h)
        
        if temp < 75:
            fill_color = self.COLOR_PRIMARY
        elif temp < 150:
            fill_color = self.COLOR_SUCCESS
        elif temp < 225:
            fill_color = self.COLOR_WARNING
        else:
            fill_color = self.COLOR_ERROR
        
        if fill_h > 0:
            fill_y = y + h - fill_h
            # Center fill di tengah background
            fill_x = bar_x + (bar_bg_w - bar_fill_w) // 2
            fill_rect = pygame.Rect(fill_x, fill_y, bar_fill_w, fill_h)
            pygame.draw.rect(self.screen, fill_color, fill_rect, border_radius=int(8*self.scale))
            pygame.draw.rect(self.screen, self.COLOR_BORDER, fill_rect, max(int(2.7*self.scale), 1), border_radius=int(8*self.scale))
    
    def draw_gauge(self, center_x: int, center_y: int, value: float, max_val: float, subtitle: str, format_str: str, warn_val: float = None, crit_val: float = None):
        """Gauge Full Circle (360 derajat) dengan isian dari bawah dan Jarum Tepi"""
        import math
        
        # Ring dimensions
        outer_radius = int(130 * self.scale)
        ring_thickness = int(26 * self.scale)
        inner_radius = outer_radius - ring_thickness
        ratio = min(max(value / max_val, 0.0), 1.0)
        
        
        # Start dari kiri bawah (135 derajat) dan memutar 270 derajat
        start_angle_deg = 135  
        end_angle_deg = 135 + (270 * ratio)  
        
        # 1. Menggambar Latar Belakang Abu-abu (Background Ring)
        for angle_deg in range(135, 405, 2):
            angle_rad = math.radians(angle_deg)
            next_angle_rad = math.radians(angle_deg + 2)
            
            # Outer & Inner arcs
            x1_outer = center_x + int(outer_radius * math.cos(angle_rad))
            y1_outer = center_y + int(outer_radius * math.sin(angle_rad))
            x2_outer = center_x + int(outer_radius * math.cos(next_angle_rad))
            y2_outer = center_y + int(outer_radius * math.sin(next_angle_rad))
            
            x1_inner = center_x + int(inner_radius * math.cos(angle_rad))
            y1_inner = center_y + int(inner_radius * math.sin(angle_rad))
            x2_inner = center_x + int(inner_radius * math.cos(next_angle_rad))
            y2_inner = center_y + int(inner_radius * math.sin(next_angle_rad))
            
            points = [(x1_outer, y1_outer), (x2_outer, y2_outer), (x2_inner, y2_inner), (x1_inner, y1_inner)]
            pygame.draw.polygon(self.screen, self.COLOR_BG_TERTIARY, points)
        
        # 2. Menggambar Isian Warna (Aktif)
        if ratio > 0.01:
            # Perubahan warna otomatis
            fill_color = self.COLOR_SUCCESS
            if crit_val is not None and value >= crit_val:
                fill_color = self.COLOR_ERROR
            elif warn_val is not None and value >= warn_val:
                fill_color = self.COLOR_WARNING
            
            for angle_deg in range(135, int(end_angle_deg), 2):
                angle_rad = math.radians(angle_deg)
                # Mencegah ujungnya melebihi batas end_angle
                next_angle_rad = math.radians(min(angle_deg + 2, end_angle_deg))
                
                x1_outer = center_x + int(outer_radius * math.cos(angle_rad))
                y1_outer = center_y + int(outer_radius * math.sin(angle_rad))
                x2_outer = center_x + int(outer_radius * math.cos(next_angle_rad))
                y2_outer = center_y + int(outer_radius * math.sin(next_angle_rad))
                
                x1_inner = center_x + int(inner_radius * math.cos(angle_rad))
                y1_inner = center_y + int(inner_radius * math.sin(angle_rad))
                x2_inner = center_x + int(inner_radius * math.cos(next_angle_rad))
                y2_inner = center_y + int(inner_radius * math.sin(next_angle_rad))
                
                points = [(x1_outer, y1_outer), (x2_outer, y2_outer), (x2_inner, y2_inner), (x1_inner, y1_inner)]
                pygame.draw.polygon(self.screen, fill_color, points)

        #2. OUTLINE RING (Border)
        outline_color = self.COLOR_BORDER
        outline_thick = max(int(3 * self.scale), 1)

        outer_points = []
        inner_points = []

        # Mengumpulkan semua titik dari 135 sampai 405 derajat
        for angle_deg in range(135, 406): 
            rad = math.radians(angle_deg)
            outer_points.append((center_x + int(outer_radius * math.cos(rad)), center_y + int(outer_radius * math.sin(rad))))
            inner_points.append((center_x + int(inner_radius * math.cos(rad)), center_y + int(inner_radius * math.sin(rad))))
            
        # Menggambar garis lengkung luar dan dalam
        pygame.draw.lines(self.screen, outline_color, False, outer_points, outline_thick)
        pygame.draw.lines(self.screen, outline_color, False, inner_points, outline_thick)
        
        # Menggambar garis penutup (caps) di ujung kiri bawah dan kanan bawah
        pygame.draw.line(self.screen, outline_color, outer_points[0], inner_points[0], outline_thick)
        pygame.draw.line(self.screen, outline_color, outer_points[-1], inner_points[-1], outline_thick)

        
        # 3. JARUM TEPI (Di atas arc, bukan dari tengah)
        current_angle_rad = math.radians(end_angle_deg)
        
        # Jarum memotong sedikit ke dalam (inner) dan menonjol sedikit ke luar (outer)
        needle_in = inner_radius - int(10 * self.scale)
        needle_out = outer_radius + int(10 * self.scale)
        
        nx_in = center_x + int(needle_in * math.cos(current_angle_rad))
        ny_in = center_y + int(needle_in * math.sin(current_angle_rad))
        nx_out = center_x + int(needle_out * math.cos(current_angle_rad))
        ny_out = center_y + int(needle_out * math.sin(current_angle_rad))
        
        # Menggambar jarum tebal berwarna merah
        pygame.draw.line(self.screen, self.COLOR_ERROR, (nx_in, ny_in), (nx_out, ny_out), max(int(3 * self.scale), 3))

        # 4. LABEL ANGKA YANG RAPI (0, 100, 200, 300)
        val_0 = 0
        val_1 = int(max_val / 3)
        val_2 = int(max_val * 2 / 3)
        val_3 = int(max_val)

        label_positions = [
            (val_0, 135),   
            (val_1, 225),   
            (val_2, 315),   
            (val_3, 405)    
        ]
        
        # Jarak angka seragam agar membentuk radius memutar yang rapi
        label_radius = outer_radius + int(30 * self.scale)
        
        for val, angle_deg in label_positions:
            angle_rad = math.radians(angle_deg)
            label_text = self.font_small.render(str(val), True, self.COLOR_TEXT_SECONDARY)
            
            lx = center_x + int(label_radius * math.cos(angle_rad))
            ly = center_y + int(label_radius * math.sin(angle_rad))
            self.screen.blit(label_text, label_text.get_rect(center=(lx, ly)))

        # 5. TEKS UTAMA DI TENGAH
        val_text = format_str.format(value)
        # Teks nilai berada pas di tengah
        val_surface = self.font_heading.render(val_text, True, self.COLOR_TEXT)
        self.screen.blit(val_surface, val_surface.get_rect(center=(center_x, center_y)))
        
        # Subtitle (Teks Label) diletakkan di BAWAH spedometer
        lbl_text = self.font_body.render(subtitle, True, self.COLOR_TEXT)
        self.screen.blit(lbl_text, lbl_text.get_rect(center=(center_x, center_y + outer_radius + int(30 * self.scale))))

    def draw_pump_status(self, state: Dict, center_x: int, start_y: int):
        """Menggambar indikator pompa tanpa judul (judul diurus oleh parent)"""
        pumps = [
            ("Pompa 1", state.get("pump_primary", 0), state.get("lofa_primary", False)),
            ("Pompa 2", state.get("pump_secondary", 0), state.get("lofa_secondary", False)),
            ("Pompa 3", state.get("pump_tertiary", 0), state.get("lofa_tertiary", False))
        ]
        
        spacing = int(160 * self.scale)
        start_x = center_x - spacing
        
        import time
        blink = int(time.time() * 2) % 2 == 0
        
        for i, (name, p_state, lofa) in enumerate(pumps):
            px = start_x + (i * spacing)
            
            lbl_top = self.font_medium.render(name, True, self.COLOR_TEXT)
            self.screen.blit(lbl_top, lbl_top.get_rect(center=(px, start_y)))
            
            if lofa:
                color = self.COLOR_ERROR if blink else self.COLOR_WARNING
                status_text = "FAILED"
            elif p_state == 2:
                color = self.COLOR_SUCCESS
                status_text = "ON"
            elif p_state == 1:
                color = (150, 200, 50) if blink else self.COLOR_SUCCESS
                status_text = "STARTING"
            elif p_state == 3:
                color = self.COLOR_WARNING
                status_text = "STOPPING"
            else:
                color = self.COLOR_ERROR
                status_text = "OFF"
                
            pygame.draw.circle(self.screen, color, (px, start_y + int(50 * self.scale)), int(20 * self.scale))
            
            lbl_bot = self.font_medium.render(status_text, True, self.COLOR_TEXT)
            self.screen.blit(lbl_bot, lbl_bot.get_rect(center=(px, start_y + int(100 * self.scale))))

    def draw_vertical_bars(self, state: Dict, start_y: int, col_start: int, col_width: int):
        # 4 Parameter sesuai desain
        params = [
            ("Pressure", state.get("pressure", 0), 200, "bar"),
            ("Safety Rod", state.get("safety_rod", 0), 100, "%"),
            ("Shim Rod", state.get("shim_rod", 0), 100, "%"),
            ("Regulating", state.get("regulating_rod", 0), 100, "%")
        ]
        
        num_bars = len(params)
        bar_width = int(50 * self.scale)
        bar_height = int(200 * self.scale)
        
        # Hitung jarak (gap) antar batang agar seimbang di kolom kanan
        total_bars_width = num_bars * bar_width
        gap = (col_width - total_bars_width) // (num_bars + 1)
        
        for i, (label, value, max_val, unit) in enumerate(params):
            # Hitung posisi tengah untuk masing-masing bar
            x_center = col_start + gap * (i + 1) + bar_width * i + (bar_width // 2)
            
            # Teks Judul Atas (Pressure, Safety Rod, dll)
            title_surf = self.font_medium.render(label, True, self.COLOR_TEXT)
            title_rect = title_surf.get_rect(center=(x_center, start_y - int(30 * self.scale)))
            self.screen.blit(title_surf, title_rect)
            
            # Background Kapsul (Warna Biru Gelap)
            bg_rect = pygame.Rect(x_center - (bar_width//2), start_y, bar_width, bar_height)
            border_radius = bar_width // 2 # Membuat ujungnya membulat penuh seperti kapsul
            pygame.draw.rect(self.screen, self.COLOR_BG_PANEL, bg_rect, border_radius=border_radius)
            
            # Foreground / Isi Kapsul (Warna Biru Terang)
            percentage = min(max(value / max_val, 0.0), 1.0)
            fill_height = int(percentage * bar_height)
            
            if fill_height > 0:
                fill_rect = pygame.Rect(x_center - (bar_width//2), start_y + bar_height - fill_height, bar_width, fill_height)

                # Permukaan atas akan datar, KECUALI jika sudah mau penuh (menyentuh lengkungan atas kapsul)
                top_radius = border_radius if fill_height >= bar_height - border_radius else 0

                #Gambar isiannya (Ganti warna RGB di bawah ini sesuai selera)
                pygame.draw.rect(self.screen, (0, 255, 255), fill_rect, 
                                 border_bottom_left_radius=border_radius,
                                 border_bottom_right_radius=border_radius,
                                 border_top_left_radius=top_radius,
                                 border_top_right_radius=top_radius)
                
            # Teks Nilai Bawah (0 bar, 0 %, dll)
            val_surf = self.font_large.render(f"{int(value)} {unit}", True, self.COLOR_TEXT)
            val_rect = val_surf.get_rect(center=(x_center, start_y + bar_height + int(40 * self.scale)))
            self.screen.blit(val_surf, val_rect) 
    
    
    
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
                    import pwd
                    try:
                        target_home = pwd.getpwuid(1000).pw_dir
                    except Exception:
                        target_home = "/home/pi"
                    video_path = str(Path(target_home) / "video_pltn" / "pwr_tutorial_ver.mp4")
                    # Video is now handled by raspi_main_panel.py subprocess!
                    # self.play_video(video_path, loop=True)
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
        is_zero = (current_pressure < 5 and current_rods < 10 and current_pumps == 0)
        
        # Clear the just_woke_up flag if we've started doing something
        if not is_zero and getattr(self, 'just_woke_up', False):
            self.just_woke_up = False

        is_manual_started = hasattr(self, 'manual_flag_file') and self.manual_flag_file.exists()

        if is_zero and not getattr(self, 'just_woke_up', False) and not is_manual_started:
            if self.display_mode != DisplayMode.IDLE:
                print("🔄 RESET detected - returning to IDLE")
                self.stop_video()
                self.display_mode = DisplayMode.IDLE
                self.user_has_interacted = False
                self.auto_complete_time = None
                self._clear_manual_flag()
            self.draw_idle_screen()
            return
        
        # Check if auto simulation just completed
        if not auto_running and mode != "cinematic_lofa" and self.display_mode == DisplayMode.AUTO_VIDEO:
            # Auto simulation just finished - go to MANUAL, not IDLE!
            print("🏁 Auto simulation completed - switching to MANUAL")
            self.stop_video()
            self.display_mode = DisplayMode.MANUAL_GUIDE
            self.user_has_interacted = True  # Enable manual mode immediately
            self.auto_complete_time = None
            self.current_step = 0
            # Don't return here, continue to draw manual guide
        
        # MODE 1: EMERGENCY - Switch to MANUAL to show real-time physics updates
        if emergency:
            if self.display_mode != DisplayMode.MANUAL_GUIDE:
                print("🚨 Emergency detected - switching to MANUAL to show status")
                self.stop_video()
                self.display_mode = DisplayMode.MANUAL_GUIDE
                self.user_has_interacted = True
            
            # Draw the manual guide to show status, then add a SCRAM overlay if needed
            self.draw_manual_guide(state)
            return
        
        # MODE 2: AUTO SIMULATION - Play video
        if mode == "auto" and auto_running:
            if self.display_mode != DisplayMode.AUTO_VIDEO:
                print(f"🎬 Switching to AUTO VIDEO mode")
                import pwd
                try:
                    target_home = pwd.getpwuid(1000).pw_dir
                except Exception:
                    target_home = "/home/pi"
                video_path = str(Path(target_home) / "video_pltn" / "pwr_tutorial_ver.mp4")
                self.play_video(video_path, loop=True)
                self.display_mode = DisplayMode.AUTO_VIDEO
                self.auto_complete_time = None  # Reset completion timer
                self.user_has_interacted = False  # Reset interaction flag
            
            # Video is playing via mpv - don't draw anything
            # (mpv handles fullscreen itself)
            return

        # MODE 2.5: CINEMATIC LOFA - Play video
        if mode == "cinematic_lofa":
            if self.display_mode != DisplayMode.AUTO_VIDEO:
                print(f"🎬 Switching to CINEMATIC LOFA VIDEO mode")
                import pwd
                try:
                    target_home = pwd.getpwuid(1000).pw_dir
                except Exception:
                    target_home = "/home/pi"
                video_path = str(Path(target_home) / "video_pltn" / "simulasi_lofa.mp4")
                self.play_video(video_path, loop=False)
                self.display_mode = DisplayMode.AUTO_VIDEO
                self.auto_complete_time = None
                self.user_has_interacted = False
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
        
        import subprocess
        check_monitor_timer = 0
        
        while running:
            # Pastikan secara absolut HDMI-A-1 masih terhubung. Jika tidak, matikan diri.
            check_monitor_timer += 1
            if check_monitor_timer >= 60:  # Cek setiap ~2 detik (30 fps x 2)
                check_monitor_timer = 0
                try:
                    res = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=1)
                    if "HDMI-A-1" not in res.stdout:
                        print("🚨 Kritis: Monitor HDMI-A-1 tidak ditemukan! Mematikan program agar tidak nyangkut di Touchscreen...")
                        running = False
                except Exception:
                    pass
            
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                elif event.type == getattr(pygame, 'WINDOWEVENT', None):
                    if event.event in (getattr(pygame, 'WINDOWEVENT_MINIMIZED', None), 
                                     getattr(pygame, 'WINDOWEVENT_HIDDEN', None),
                                     getattr(pygame, 'WINDOWEVENT_DISPLAY_CHANGED', None)):
                        print("⚠️ Window bermigrasi atau tersembunyi (kabel HDMI mungkin dicabut). Mematikan program agar Watchdog me-restart...")
                        running = False
                
                # Handle touch/mouse click to switch from IDLE to MANUAL
                elif event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.FINGERDOWN:
                    if not self.user_has_interacted:
                        print("👉 Layar disentuh - beralih ke mode MANUAL")
                        self.user_has_interacted = True
                        self.just_woke_up = True
                        if self.test_mode:
                            self.mock_mode = "manual"
                
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
    parser = argparse.ArgumentParser(description='Video Display App untuk Simulator PLTN')
    parser.add_argument('--display', type=int, default=0,
                       help='Indeks monitor display (0, 1, dst. default=0)')
    parser.add_argument('--test', action='store_true', 
                       help='Run in test mode (no simulation required)')
    parser.add_argument('--windowed', action='store_true',
                       help='Run in windowed mode (not fullscreen)')
    
    args = parser.parse_args()
    
    # [CPU-033] Fine-tune priorities: Pin UI to Core 2 & 3
    try:
        import psutil
        import platform
        p = psutil.Process()
        if hasattr(p, 'cpu_affinity'): p.cpu_affinity([2, 3])
        if hasattr(p, 'nice'):
            p.nice(getattr(psutil, 'NORMAL_PRIORITY_CLASS', 32) if platform.system() == 'Windows' else 0)
    except Exception:
        pass
        
    # Run application
    app = VideoDisplayApp(
        test_mode=args.test,
        fullscreen=not args.windowed,
        display_idx=args.display
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
