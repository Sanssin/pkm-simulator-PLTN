"""
OLED Display Manager
Manages 4 OLED displays through TCA9548A multiplexer
With smooth value interpolation for better UX
"""

import logging
from PIL import Image, ImageDraw, ImageFont
import time

logger = logging.getLogger(__name__)

# Try to import Adafruit library
try:
    import board
    import adafruit_ssd1306
    ADAFRUIT_AVAILABLE = True
except ImportError:
    logger.warning("Adafruit libraries not available. Running in simulation mode.")
    ADAFRUIT_AVAILABLE = False


class DisplayValueInterpolator:
    """
    Smooth interpolation for display values without changing I2C timing.
    
    Provides gradual transition from current to target value, allowing users
    to see intermediate values (e.g., 10% -> 15% -> 20% instead of 10% -> 20%).
    
    Features:
    - Configurable interpolation speed
    - Selective updates (only when value changes)
    - No impact on I2C timing or communication flow
    """
    
    def __init__(self, speed=50.0, name="value", decimals=0):
        """
        Initialize interpolator
        
        Args:
            speed: Interpolation speed in units per second (default 50.0)
                   - For pressure: 50 bar/second
                   - For rods: 50%/second
            name: Name for debug logging
            decimals: Number of decimal places to round display value to (default 0)
        """
        self.current_value = 0.0
        self.target_value = 0.0
        self.last_displayed = -999  # Force first update
        self.last_update_time = time.time()
        self.speed = speed
        self.name = name
        self.decimals = decimals
        
    def set_target(self, new_target):
        """
        Set new target value for interpolation
        
        Args:
            new_target: Target value to interpolate towards
        """
        if self.target_value != new_target:
            self.target_value = float(new_target)
    
    def get_display_value(self):
        """
        Get smoothly interpolated value for display
        
        Returns:
            Rounded value (int or float) ready for display
        """
        current_time = time.time()
        elapsed = current_time - self.last_update_time
        
        # Calculate smooth transition
        threshold = 0.5 if self.decimals == 0 else (10 ** -self.decimals) / 2.0
        if abs(self.current_value - self.target_value) > threshold:
            # Calculate delta based on speed and elapsed time
            max_delta = self.speed * elapsed
            
            if self.current_value < self.target_value:
                self.current_value = min(self.current_value + max_delta, self.target_value)
            else:
                self.current_value = max(self.current_value - max_delta, self.target_value)
        else:
            # Close enough - snap to target
            self.current_value = self.target_value
        
        self.last_update_time = current_time
        if self.decimals == 0:
            return int(round(self.current_value))
        else:
            return round(self.current_value, self.decimals)
    
    def needs_update(self):
        """
        Check if display needs update (value changed since last display)
        
        This prevents unnecessary I2C calls when value hasn't changed.
        
        Returns:
            True if value changed and display needs update, False otherwise
        """
        if self.decimals == 0:
            current = int(round(self.current_value))
        else:
            current = round(self.current_value, self.decimals)
        if current != self.last_displayed:
            self.last_displayed = current
            return True
        return False
    
    def reset(self, value=0.0):
        """
        Reset interpolator to specific value (instant, no transition)
        
        Args:
            value: Value to reset to (default 0.0)
        """
        self.current_value = float(value)
        self.target_value = float(value)
        self.last_displayed = -999  # Force update on next call


class OLEDDisplay:
    """
    Single OLED display wrapper
    """
    
    def __init__(self, width: int = 128, height: int = 32):
        """
        Initialize OLED display
        
        Args:
            width: Display width in pixels
            height: Display height in pixels
        """
        self.width = width
        self.height = height
        self.device = None
        self.image = Image.new('1', (width, height))
        self.draw = ImageDraw.Draw(self.image)
        
        # Try to load a font - larger sizes for better readability
        try:
            self.font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 10)
            self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)
            self.font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)
            self.font_xlarge = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 16)
        except:
            self.font_small = ImageFont.load_default()
            self.font = ImageFont.load_default()
            self.font_large = ImageFont.load_default()
            self.font_xlarge = ImageFont.load_default()
        
        self.initialized = False
    
    def init_hardware(self, i2c, address: int = 0x3C, timeout: float = 1.0):
        """
        Initialize hardware OLED display with timeout
        
        Args:
            i2c: I2C bus object
            address: I2C address of OLED
            timeout: Timeout in seconds (default 1.0s)
        """
        if not ADAFRUIT_AVAILABLE:
            logger.warning("Hardware display not available")
            return False
        
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def try_init():
            try:
                self.device = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, i2c, addr=address)
                self.device.fill(0)
                self.device.show()
                self.initialized = True
                result_queue.put(True)
                logger.debug(f"OLED display initialized at 0x{address:02X}")
            except Exception as e:
                logger.debug(f"Failed to initialize OLED at 0x{address:02X}: {e}")
                result_queue.put(False)
        
        # Try init with timeout
        init_thread = threading.Thread(target=try_init, daemon=True)
        init_thread.start()
        init_thread.join(timeout=timeout)
        
        # Check result
        try:
            return result_queue.get_nowait()
        except:
            logger.debug(f"OLED at 0x{address:02X} timeout after {timeout}s")
            return False
    
    def clear(self):
        """Clear display"""
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
    
    def draw_text(self, text: str, x: int = 0, y: int = 0, font=None):
        """Draw text on display"""
        if font is None:
            font = self.font
        self.draw.text((x, y), text, font=font, fill=255)
    
    def draw_text_centered(self, text: str, y: int = 0, font=None):
        """Draw centered text"""
        if font is None:
            font = self.font
        bbox = self.draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        self.draw.text((x, y), text, font=font, fill=255)
    
    def draw_progress_bar(self, x: int, y: int, width: int, height: int, 
                         value: float, max_value: float = 100.0):
        """
        Draw a progress bar
        
        Args:
            x, y: Top-left corner
            width, height: Bar dimensions
            value: Current value
            max_value: Maximum value
        """
        # Draw outline
        self.draw.rectangle((x, y, x + width, y + height), outline=255, fill=0)
        
        # Draw filled portion
        if value > 0 and max_value > 0:
            fill_width = int((value / max_value) * (width - 2))
            if fill_width > 0:
                self.draw.rectangle((x + 1, y + 1, x + 1 + fill_width, y + height - 1), 
                                  outline=255, fill=255)
    
    def show(self):
        """Update display"""
        if self.initialized and self.device:
            try:
                self.device.image(self.image)
                self.device.show()
            except Exception as e:
                logger.error(f"Failed to update display: {e}")


class OLEDManager:
    """
    Manages 9 OLED displays (0.91 inch 128x64) through 2x TCA9548A multiplexers
    
    TCA9548A #1 (0x70):
      - Channel 1: OLED #1 (Pressurizer)
      - Channel 2: OLED #2 (Pump Primary)
      - Channel 3: OLED #3 (Pump Secondary)
      - Channel 4: OLED #4 (Pump Tertiary)
      - Channel 5: OLED #5 (Safety Rod)
      - Channel 6: OLED #6 (Shim Rod)
      - Channel 7: OLED #7 (Regulating Rod)
    
    TCA9548A #2 (0x71):
      - Channel 1: OLED #8 (Thermal Power)
      - Channel 2: OLED #9 (System Status)
    """
    
    def __init__(self, mux_manager, width: int = 128, height: int = 32):
        """
        Initialize OLED manager for 9 displays
        
        Args:
            mux_manager: TCA9548A multiplexer manager
            width: Display width (128 for 0.91 inch)
            height: Display height (32 for 0.91 inch)
        """
        self.mux = mux_manager
        self.width = width
        self.height = height
        
        # Create 9 display objects
        self.oled_pressurizer = OLEDDisplay(width, height)
        self.oled_pump_primary = OLEDDisplay(width, height)
        self.oled_pump_secondary = OLEDDisplay(width, height)
        self.oled_pump_tertiary = OLEDDisplay(width, height)
        self.oled_safety_rod = OLEDDisplay(width, height)
        self.oled_shim_rod = OLEDDisplay(width, height)
        self.oled_regulating_rod = OLEDDisplay(width, height)
        self.oled_thermal_power = OLEDDisplay(width, height)
        self.oled_system_status = OLEDDisplay(width, height)
        
        self.blink_state = False
        self.last_blink_time = time.time()
        
        # System status display state tracking
        self.status_mode_shown = False      # Track if mode already shown
        self.status_last_mode = None        # Last mode (manual/auto)
        self.status_blink_state = 0         # Blink cycle (0 or 1) for idle prompt / emergency
        self.status_blink_time = time.time() # Last blink toggle time
        self.emergency_blink_state = 0      # Emergency blink cycle (0 or 1)
        self.emergency_blink_time = time.time() # Last emergency blink time
        
        # Data tracking for optimization (only update if changed)
        self.last_data = {
            'pressurizer': None,
            'pump_primary': None,
            'pump_secondary': None,
            'pump_tertiary': None,
            'safety_rod': None,
            'shim_rod': None,
            'regulating_rod': None,
            'thermal_power': None,
            'system_status': None
        }
        
        # Interpolators for smooth display transitions (NO impact on I2C timing)
        # Speed: 50 units/second for smooth UX
        self.interp_pressure = DisplayValueInterpolator(speed=50.0, name="pressure", decimals=2)
        self.interp_safety_rod = DisplayValueInterpolator(speed=50.0, name="safety_rod")
        self.interp_shim_rod = DisplayValueInterpolator(speed=50.0, name="shim_rod")
        self.interp_regulating_rod = DisplayValueInterpolator(speed=50.0, name="regulating_rod")
        self.interp_thermal_power = DisplayValueInterpolator(speed=50000.0, name="thermal_kw")  # kW scale
        
        logger.info("OLED Manager initialized for 9 displays (128x32)")
        logger.info("Display interpolation enabled: 50 units/sec for smooth transitions")
    
    def init_all_displays(self):
        """Initialize all 9 OLED displays through 2x TCA9548A with graceful degradation"""
        # TCA9548A #1 (0x70) - 7 displays
        displays_mux1 = [
            (1, self.oled_pressurizer, "Pressurizer"),
            (2, self.oled_pump_primary, "Pompa Primer"),
            (3, self.oled_pump_secondary, "Pompa Sekunder"),
            (4, self.oled_pump_tertiary, "Pompa Tersier"),
            (5, self.oled_safety_rod, "Safety Rod"),
            (6, self.oled_shim_rod, "Shim Rod"),
            (7, self.oled_regulating_rod, "Reg Rod")
        ]
        
        # TCA9548A #2 (0x71) - 2 displays
        displays_mux2 = [
            (1, self.oled_thermal_power, "Daya"),
            (2, self.oled_system_status, "Status")
        ]
        
        if not ADAFRUIT_AVAILABLE:
            logger.warning("Running without hardware displays (simulation mode)")
            return
        
        success_count = 0
        
        try:
            i2c = board.I2C()
            
            # Initialize displays on TCA9548A #1 (0x70)
            logger.info("Initializing OLEDs on TCA9548A #1 (0x70)...")
            for channel, display, name in displays_mux1:
                try:
                    self.mux.select_display_channel(channel)
                    time.sleep(0.05)  # Minimal delay
                    
                    # Try to initialize with 0.5s timeout per display
                    if display.init_hardware(i2c, 0x3C, timeout=0.5):
                        # Show startup message (2 lines, larger font)
                        display.clear()
                        display.draw_text_centered(name, 4, display.font)
                        display.draw_text_centered("Siap", 18, display.font_large)
                        display.show()
                        logger.info(f"  ✓ OLED #{channel}: {name}")
                        success_count += 1
                    else:
                        logger.warning(f"  ✗ OLED #{channel}: {name} - skipped")
                    
                except Exception as e:
                    logger.warning(f"  ✗ OLED #{channel}: {name} - error: {e}")
                    continue  # Skip to next display
            
            # Initialize displays on TCA9548A #2 (0x71)
            logger.info("Initializing OLEDs on TCA9548A #2 (0x71)...")
            for channel, display, name in displays_mux2:
                try:
                    # Use esp_channel to access second multiplexer (0x71)
                    self.mux.select_esp_channel(channel)
                    time.sleep(0.05)  # Minimal delay
                    
                    # Try to initialize with 0.5s timeout per display
                    if display.init_hardware(i2c, 0x3C, timeout=0.5):
                        # Show startup message (2 lines, larger font)
                        display.clear()
                        display.draw_text_centered(name, 4, display.font)
                        display.draw_text_centered("Siap", 18, display.font_large)
                        display.show()
                        logger.info(f"  ✓ OLED #{channel + 7}: {name}")
                        success_count += 1
                    else:
                        logger.warning(f"  ✗ OLED #{channel + 7}: {name} - skipped")
                    
                except Exception as e:
                    logger.warning(f"  ✗ OLED #{channel + 7}: {name} - error: {e}")
                    continue  # Skip to next display
            
            logger.info(f"OLED initialization complete: {success_count}/9 displays ready")
            
        except Exception as e:
            logger.error(f"Failed to initialize displays: {e}")
            logger.warning("Continuing without OLED displays...")
    
    def update_blink_state(self, interval: float = 0.25):
        """Update blink state for warning indicators"""
        current_time = time.time()
        if current_time - self.last_blink_time > interval:
            self.blink_state = not self.blink_state
            self.last_blink_time = current_time
    
    def update_pressurizer_display(self, pressure: float, warning: bool = False, 
                                   critical: bool = False):
        """
        Update pressurizer display with smooth interpolation
        
        Args:
            pressure: Current pressure in bar (target value)
            warning: Warning flag (pressure high)
            critical: Critical flag (pressure critical)
        """
        # Set target value for interpolation
        self.interp_pressure.set_target(pressure)
        
        # Get smoothly interpolated value
        display_pressure = self.interp_pressure.get_display_value()
        
        # OPTIMIZATION: Only update I2C if value changed
        if not self.interp_pressure.needs_update():
            return  # Skip I2C call - no visual change
        
        # === I2C COMMUNICATION (timing preserved) ===
        self.mux.select_display_channel(1)  # Pressurizer on channel 1 (10ms delay inside)
        
        display = self.oled_pressurizer
        display.clear()
        
        # Show smoothly interpolated value with large font
        pressure_text = f"{display_pressure:.2f} bar"
        display.draw_text_centered(pressure_text, 8, display.font_xlarge)
        
        display.show()
        time.sleep(0.005)  # 5ms delay after show() - PRESERVED
    
    def update_pump_display(self, pump_name: str, channel: int, display_obj: OLEDDisplay,
                           status: int, pwm: int):
        """
        Update pump display
        
        Args:
            pump_name: Name of pump (e.g., "PRIMARY")
            channel: TCA9548A channel
            display_obj: OLED display object
            status: Pump status (0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN)
            pwm: PWM percentage (0-100)
        """
        # Check if status changed (optimization)
        cache_key = f"pump_{channel}"
        if cache_key in self.last_data and self.last_data[cache_key] == status:
            return  # No change, skip I2C call
        
        self.last_data[cache_key] = status
        
        # === I2C COMMUNICATION (timing preserved) ===
        self.mux.select_display_channel(channel)  # 10ms delay inside
        
        display_obj.clear()
        
        # Show only status in Indonesian with large font (panel already has label)
        status_text = ["MATI", "MULAI", "HIDUP", "BERHENTI"][status]
        display_obj.draw_text_centered(status_text, 8, display_obj.font_xlarge)
        
        display_obj.show()
        time.sleep(0.005)  # 5ms delay after show() - PRESERVED
    
    def update_pump_primary(self, status: int, pwm: int):
        """Update primary pump display"""
        self.update_pump_display("PRIMARY", 2, self.oled_pump_primary, status, pwm)  # Channel 2
    
    def update_pump_secondary(self, status: int, pwm: int):
        """Update secondary pump display"""
        self.update_pump_display("SECONDARY", 3, self.oled_pump_secondary, status, pwm)  # Channel 3
    
    def update_pump_tertiary(self, status: int, pwm: int):
        """Update tertiary pump display"""
        self.update_pump_display("TERTIARY", 4, self.oled_pump_tertiary, status, pwm)  # Channel 4
    
    def update_rod_display(self, rod_name: str, channel: int, display_obj: OLEDDisplay, 
                          position: int, interpolator: DisplayValueInterpolator):
        """
        Update control rod display with smooth interpolation
        
        Args:
            rod_name: Name of rod (e.g., "SAFETY", "SHIM", "REGULATING")
            channel: TCA9548A channel
            display_obj: OLED display object
            position: Rod position (0-100%) - target value
            interpolator: DisplayValueInterpolator instance for this rod
        """
        # Set target value for interpolation
        interpolator.set_target(position)
        
        # Get smoothly interpolated value
        display_position = interpolator.get_display_value()
        
        # OPTIMIZATION: Only update I2C if value changed
        if not interpolator.needs_update():
            return  # Skip I2C call - no visual change
        
        # === I2C COMMUNICATION (timing preserved) ===
        self.mux.select_display_channel(channel)  # 10ms delay inside
        
        display_obj.clear()
        
        # Show smoothly interpolated percentage value
        position_text = f"{display_position}%"
        display_obj.draw_text_centered(position_text, 8, display_obj.font_xlarge)
        
        display_obj.show()
        time.sleep(0.005)  # 5ms delay after show() - PRESERVED
    
    def update_safety_rod(self, position: int):
        """Update safety rod display with interpolation"""
        self.update_rod_display("SAFETY", 5, self.oled_safety_rod, position, self.interp_safety_rod)
    
    def update_shim_rod(self, position: int):
        """Update shim rod display with interpolation"""
        self.update_rod_display("SHIM", 6, self.oled_shim_rod, position, self.interp_shim_rod)
    
    def update_regulating_rod(self, position: int):
        """Update regulating rod display with interpolation"""
        self.update_rod_display("REGULATING", 7, self.oled_regulating_rod, position, self.interp_regulating_rod)
        # Extra delay: This is the LAST channel on MUX #1 (channel 7)
        # Give OLED time to fully process before switching to MUX #2
        time.sleep(0.010)  # 10ms post-update delay - PRESERVED
    
    def update_thermal_power(self, power_kw: float):
        """
        Update thermal power display with smooth interpolation
        
        Args:
            power_kw: Electrical power in kW (0-300,000 kW = 0-300 MWe) - target value
        """
        # Set target value for interpolation
        self.interp_thermal_power.set_target(power_kw)
        
        # Get smoothly interpolated value
        display_power_kw = self.interp_thermal_power.get_display_value()
        
        # OPTIMIZATION: Only update I2C if value changed significantly (> 100 kW change)
        # This prevents excessive updates for small thermal fluctuations
        if not self.interp_thermal_power.needs_update():
            return  # Skip I2C call - no visual change
        
        # === I2C COMMUNICATION (timing preserved) ===
        self.mux.select_esp_channel(1)  # Use ESP channel for TCA9548A #2, Channel 1 (10ms delay inside)
        
        display = self.oled_thermal_power
        display.clear()
        
        # Show smoothly interpolated power value
        power_mwe = display_power_kw / 1000.0
        power_text = f"{power_mwe:.2f} MWe"
        display.draw_text_centered(power_text, 8, display.font_xlarge)
        
        display.show()
        time.sleep(0.005)  # 5ms delay after show() - PRESERVED
    
    def _is_system_idle(self, pressure: float, pump_primary: int, pump_secondary: int,
                       pump_tertiary: int, safety_rod: int, shim_rod: int,
                       regulating_rod: int, thermal_kw: float) -> bool:
        """
        Determine if system is in steady/idle state (no user action needed)
        
        Idle conditions:
        1. Zero state (initial) - all off
        2. Full power achieved - rods at 100%, power ≥ 295 MW
        
        Args:
            pressure: Current pressure in bar
            pump_primary: Primary pump status
            pump_secondary: Secondary pump status
            pump_tertiary: Tertiary pump status
            safety_rod: Safety rod position (%)
            shim_rod: Shim rod position (%)
            regulating_rod: Regulating rod position (%)
            thermal_kw: Thermal power in kW
        
        Returns:
            True if system is idle (show blinking prompt), False otherwise
        """
        # Condition 1: Zero state (initial cold system)
        if (pressure < 1.0 and 
            pump_primary == 0 and pump_secondary == 0 and pump_tertiary == 0 and
            safety_rod == 0 and shim_rod == 0 and regulating_rod == 0):
            return True
        
        # Condition 2: Full power achieved (steady state operation)
        power_mwe = thermal_kw / 1000.0
        if (safety_rod == 100 and shim_rod == 100 and regulating_rod == 100 and
            power_mwe >= 299.0):  # Truly at 300 MW (not 295)
            return True
        
        # Not idle - user action or process ongoing
        return False
    
    def _get_manual_guidance(self, pressure: float, pump_primary: int, pump_secondary: int,
                            pump_tertiary: int, safety_rod: int, shim_rod: int,
                            regulating_rod: int, thermal_kw: float):
        """
        Determine what user should do in manual mode
        
        CRITICAL SEQUENCE FOR PWR STARTUP:
        1. Pressure to 140 bar (operating pressure)
        2. All pumps ON (coolant circulation)
        3. Safety rod to 100% (MUST BE FIRST! - for SCRAM capability)
        4. Shim rod to 100% (coarse power control - after safety ready)
        5. Regulating rod to 100% (fine power tuning - after safety ready)
        
        Args:
            pressure: Current pressure in bar
            pump_primary: Primary pump status (0=OFF, 1=STARTING, 2=ON)
            pump_secondary: Secondary pump status
            pump_tertiary: Tertiary pump status
            safety_rod: Safety rod position (%)
            shim_rod: Shim rod position (%)
            regulating_rod: Regulating rod position (%)
            thermal_kw: Thermal power in kW
        
        Returns:
            (line1_text, line2_text) tuple for OLED display
        """
        # ============================================
        # PRIORITY 1: Pressure Control (Initial)
        # ============================================
        if pressure < 45.0:
            current = int(pressure)
            return ("NAIK PRESSURE", f"{current}/45 BAR")
        
        # ============================================
        # PRIORITY 2: Pump Control (After 45 bar)
        # SEQUENCE: Tertiary → Secondary → Primary
        # ============================================
        # Check if pumps need to be started (after reaching 45 bar)
        if pressure >= 45.0 and pressure < 140.0:
            # Check pump status - start sequence: Tertiary first
            if pump_tertiary != 2:  # Tertiary not ON yet
                if pump_tertiary == 1:
                    return ("TUNGGU POMPA", "TERSIER...")
                else:
                    return ("NYALAKAN", "POMPA TERSIER")
            
            elif pump_secondary != 2:  # Secondary not ON yet (tertiary already ON)
                if pump_secondary == 1:
                    return ("TUNGGU POMPA", "SEKUNDER...")
                else:
                    return ("NYALAKAN", "POMPA SEKUNDER")
            
            elif pump_primary != 2:  # Primary not ON yet (tertiary & secondary already ON)
                if pump_primary == 1:
                    return ("TUNGGU POMPA", "PRIMER...")
                else:
                    return ("NYALAKAN", "POMPA PRIMER")
            
            # All pumps ON, now continue raising pressure to 140
            current = int(pressure)
            return ("NAIK PRESSURE", f"{current}/140 BAR")
        
        # ============================================
        # PRIORITY 3: Pressure Control (To operating level)
        # ============================================
        if pressure < 140.0:
            # This handles case where pressure drops below 140 after pumps are on
            current = int(pressure)
            return ("NAIK PRESSURE", f"{current}/140 BAR")
        
        # ============================================
        # PRIORITY 3: Control Rod Sequence
        # CRITICAL: Safety rod MUST reach 100% first!
        # ============================================
        
        # Step 3a: Safety rod not at 100% - THIS IS HIGHEST PRIORITY!
        if safety_rod < 100:
            if safety_rod == 0:
                # Safety rod at zero - clear instruction
                return ("NAIK SAFETY", "ROD KE 100%")
            else:
                # Safety rod in progress - show progress
                return ("NAIK SAFETY", f"{safety_rod}% → 100%")
        
        # Step 3b: Safety rod at 100%, now handle power rods
        # Shim rod should be raised next (coarse power control)
        if shim_rod < 100:
            if shim_rod == 0 and regulating_rod == 0:
                # Just starting power rods - guide to shim first
                return ("NAIK SHIM", "ROD KE 100%")
            else:
                # Shim in progress or both rods being adjusted
                return ("NAIK SHIM/REG", "KE 100%")
        
        # Step 3c: Shim at 100%, regulating rod remaining
        if regulating_rod < 100:
            return ("NAIK REG", "ROD KE 100%")
        
        # ============================================
        # PRIORITY 4: Operating State
        # All conditions met, show power level
        # ============================================
        power_mwe = thermal_kw / 1000.0
        
        # Show actual power value first, only show "DAYA PENUH" when truly at max
        if power_mwe >= 299.0:  # Truly at maximum (300 MW)
            return ("DAYA PENUH", "300 MW")
        elif power_mwe >= 10.0:  # Significant power (10 MW and above)
            return (f"DAYA: {power_mwe:.0f} MW", "")
        else:
            # Rods at 100% but power still building up (< 10 MW)
            return ("DAYA NAIK...", f"{power_mwe:.0f} MW")
    
    def _format_auto_phase(self, phase: str, pressure: float, safety_rod: int,
                          shim_rod: int, regulating_rod: int, thermal_kw: float,
                          pump_tertiary: int, pump_secondary: int, pump_primary: int):
        """
        Format auto simulation phase for display
        
        Args:
            phase: Current auto simulation phase name
            pressure: Current pressure in bar
            safety_rod: Safety rod position (%)
            shim_rod: Shim rod position (%)
            regulating_rod: Regulating rod position (%)
            thermal_kw: Thermal power in kW
            pump_tertiary: Tertiary pump status
            pump_secondary: Secondary pump status
            pump_primary: Primary pump status
        
        Returns:
            (line1_text, line2_text) tuple for OLED display
        """
        if phase == "Init":
            return ("INISIALISASI", "SISTEM")
        
        elif phase == "Pressure 45":
            current = int(pressure)
            return ("NAIK PRESSURE", f"{current}/45 BAR")
        
        elif phase == "Pumps":
            # Show which pump is being started (sequence: Tertiary → Secondary → Primary)
            if pump_tertiary != 2:  # Tertiary not ON yet
                return ("START POMPA", "TERSIER...")
            elif pump_secondary != 2:  # Secondary not ON yet
                return ("START POMPA", "SEKUNDER...")
            elif pump_primary != 2:  # Primary not ON yet
                return ("START POMPA", "PRIMER...")
            else:
                # All pumps ON
                return ("POMPA SIAP", "SEMUA HIDUP")
        
        elif phase == "Pressure 140":
            current = int(pressure)
            return ("NAIK PRESSURE", f"{current}/140 BAR")
        
        elif phase == "Safety Rod":
            return ("NAIK SAFETY", f"{safety_rod}%")
        
        elif phase == "Shim Rod 50%":
            return ("NAIK SHIM", f"{shim_rod}/50%")
        
        elif phase == "Reg Rod 50%":
            return ("NAIK REG", f"{regulating_rod}/50%")
        
        elif phase == "Max Power":
            power_mwe = int(thermal_kw / 1000.0)
            # Show actual power first, only say "PENUH" when truly at max
            if power_mwe >= 299:
                return ("DAYA PENUH", "300 MW")
            else:
                return ("DAYA NAIK", f"{power_mwe} MW")
        
        else:
            # Generic fallback for any other phase
            return ("BERJALAN...", "")
    
    def update_system_status(self, auto_sim_running: bool, auto_sim_phase: str,
                            pressure: float, pump_primary: int, pump_secondary: int, 
                            pump_tertiary: int, interlock: bool, thermal_kw: float, 
                            turbine_speed: float, emergency_active: bool = False):
        """
        Update system status display with enhanced user guidance
        
        Features:
        - Mode indicator shown once when mode changes
        - Manual mode: Step-by-step guidance with safety rod priority
        - Auto mode: Current process display with progress
        - Idle mode: Blinking prompt to start auto simulation
        - Emergency mode: Blinking "EMERGENCY / SISTEM SHUTDOWN"
        
        Args:
            auto_sim_running: Auto simulation running flag
            auto_sim_phase: Current auto simulation phase name
            pressure: Current pressure
            pump_primary: Primary pump status
            pump_secondary: Secondary pump status  
            pump_tertiary: Tertiary pump status
            interlock: Interlock satisfied flag
            thermal_kw: Thermal power in kW
            turbine_speed: Turbine speed percentage
            emergency_active: Emergency shutdown flag
        """
        # Select channel
        self.mux.select_esp_channel(2)  # Use ESP channel for TCA9548A #2, Channel 2
        
        display = self.oled_system_status
        display.clear()
        
        # ============================================
        # EMERGENCY MODE (HIGHEST PRIORITY!)
        # ============================================
        if emergency_active:
            # Update emergency blink state (0.5 second cycle - faster for urgency)
            current_time = time.time()
            if current_time - self.emergency_blink_time > 0.5:
                self.emergency_blink_state = 1 - self.emergency_blink_state
                self.emergency_blink_time = current_time
            
            if self.emergency_blink_state == 0:
                # Blink ON: Show emergency message
                display.draw_text_centered("EMERGENCY", 6, display.font_large)
                display.draw_text_centered("SISTEM SHUTDOWN", 22, display.font_small)
            # else: Blink OFF: Display remains blank (cleared above)
            
            display.show()
            time.sleep(0.005)
            time.sleep(0.010)
            return  # Skip normal display logic
        
        # ============================================
        # MODE CHANGE DETECTION
        # ============================================
        # Check if mode changed (show mode indicator once)
        current_mode = "AUTO" if auto_sim_running else "MANUAL"
        if self.status_last_mode != current_mode:
            # Mode just changed - reset mode shown flag
            self.status_mode_shown = False
            self.status_last_mode = current_mode
            logger.debug(f"System status: Mode changed to {current_mode}")
        
        # ============================================
        # SHOW MODE INDICATOR (ONCE ONLY)
        # ============================================
        if not self.status_mode_shown:
            # Show mode indicator only once when mode changes
            display.draw_text_centered(current_mode, 10, display.font_xlarge)
            display.show()
            time.sleep(0.005)
            
            # Mark as shown after first display
            self.status_mode_shown = True
            return
        
        # ============================================
        # GET INTERPOLATED ROD VALUES FOR DISPLAY
        # ============================================
        # Use interpolated values for smoother display
        display_safety = self.interp_safety_rod.get_display_value()
        display_shim = self.interp_shim_rod.get_display_value()
        display_reg = self.interp_regulating_rod.get_display_value()
        
        # ============================================
        # AUTO MODE: Show process and progress
        # ============================================
        if auto_sim_running:
            line1, line2 = self._format_auto_phase(
                auto_sim_phase, pressure, 
                display_safety, display_shim, display_reg,
                thermal_kw,
                pump_tertiary, pump_secondary, pump_primary
            )
            
            # Display line 1 (action)
            display.draw_text_centered(line1, 8, display.font)
            
            # Display line 2 (progress) if not empty
            if line2:
                display.draw_text_centered(line2, 20, display.font_small)
        
        # ============================================
        # MANUAL MODE: Active or Idle
        # ============================================
        else:
            # Check if system is idle (no action needed)
            is_idle = self._is_system_idle(
                pressure, pump_primary, pump_secondary, pump_tertiary,
                display_safety, display_shim, display_reg, thermal_kw
            )
            
            if is_idle:
                # ============================================
                # IDLE STATE: Blinking prompt
                # ============================================
                # Update blink state (1 second cycle)
                current_time = time.time()
                if current_time - self.status_blink_time > 1.0:
                    self.status_blink_state = 1 - self.status_blink_state  # Toggle 0/1
                    self.status_blink_time = current_time
                
                if self.status_blink_state == 0:
                    # Cycle 1: "TEKAN START / UNTUK AUTO"
                    display.draw_text_centered("TEKAN START", 8, display.font)
                    display.draw_text_centered("UNTUK AUTO", 20, display.font_small)
                else:
                    # Cycle 2: "SIMULASI / OTOMATIS"
                    display.draw_text_centered("SIMULASI", 8, display.font)
                    display.draw_text_centered("OTOMATIS", 20, display.font_small)
            
            else:
                # ============================================
                # ACTIVE STATE: User guidance
                # ============================================
                line1, line2 = self._get_manual_guidance(
                    pressure, pump_primary, pump_secondary, pump_tertiary,
                    display_safety, display_shim, display_reg, thermal_kw
                )
                
                # Display line 1 (primary instruction)
                display.draw_text_centered(line1, 8, display.font)
                
                # Display line 2 (detail/target) if not empty
                if line2:
                    display.draw_text_centered(line2, 20, display.font_small)
        
        display.show()
        time.sleep(0.005)  # 5ms delay after show() - PRESERVED
        
        # Post-update delay for MUX #2
        time.sleep(0.010)  # 10ms post-update delay
        
        # Extra delay: This is the LAST channel on MUX #2 (channel 2)
        # Give OLED time to fully process before next update cycle
        time.sleep(0.010)  # 10ms post-update delay
    
    def reset_all_interpolators(self):
        """
        Reset all interpolators to zero (instant, no transition).
        
        Useful for SCRAM, emergency stop, or system reset scenarios
        where values should immediately jump to zero without smooth transition.
        """
        self.interp_pressure.reset(0.0)
        self.interp_safety_rod.reset(0.0)
        self.interp_shim_rod.reset(0.0)
        self.interp_regulating_rod.reset(0.0)
        self.interp_thermal_power.reset(0.0)
        
        # Clear cache to force update
        self.last_data = {
            'pressurizer': None,
            'pump_primary': None,
            'pump_secondary': None,
            'pump_tertiary': None,
            'safety_rod': None,
            'shim_rod': None,
            'regulating_rod': None,
            'thermal_power': None,
            'system_status': None
        }
        
        logger.info("All display interpolators reset to zero")
    
    def sync_interpolators_to_state(self, state):
        """
        Synchronize interpolators to current state values (instant, no transition).
        
        Useful during initialization or when resuming from saved state.
        
        Args:
            state: PanelState object with current values
        """
        self.interp_pressure.reset(state.pressure)
        self.interp_safety_rod.reset(state.safety_rod)
        self.interp_shim_rod.reset(state.shim_rod)
        self.interp_regulating_rod.reset(state.regulating_rod)
        self.interp_thermal_power.reset(state.thermal_kw)
        
        # Clear cache to force first update
        self.last_data = {
            'pressurizer': None,
            'pump_primary': None,
            'pump_secondary': None,
            'pump_tertiary': None,
            'safety_rod': None,
            'shim_rod': None,
            'regulating_rod': None,
            'thermal_power': None,
            'system_status': None
        }
        
        logger.info(f"Interpolators synced to state: P={state.pressure:.2f}bar, "
                   f"Rods=[{state.safety_rod},{state.shim_rod},{state.regulating_rod}]%, "
                   f"Thermal={state.thermal_kw:.1f}kW")
        
        # Force immediate display update to clear startup screen
        logger.info("Forcing display update to clear startup screen...")
        self.update_all(state)
        logger.info("Startup screen cleared, displays now show actual values")
    
    def update_all(self, state):
        """
        Update all displays from panel state
        
        Args:
            state: PanelState object with all current values
        """
        self.update_blink_state()
        
        # ============================================
        # MUX #1 (0x70) - Channels 1-7
        # ============================================
        
        # Update all displays on MUX #1
        self.update_pressurizer_display(state.pressure, 
                                       warning=(state.pressure > 180),
                                       critical=(state.pressure > 195))
        
        self.update_pump_primary(state.pump_primary_status, 50)  # PWM placeholder
        self.update_pump_secondary(state.pump_secondary_status, 50)
        self.update_pump_tertiary(state.pump_tertiary_status, 50)
        
        self.update_safety_rod(state.safety_rod)
        self.update_shim_rod(state.shim_rod)
        self.update_regulating_rod(state.regulating_rod)
        
        # ============================================
        # MUX #2 (0x71) - Channels 1-2
        # ============================================
        # Auto-delay handled by TCA9548AManager when switching between MUX
        
        self.update_thermal_power(state.thermal_kw)
        
        self.update_system_status(
            auto_sim_running=state.auto_sim_running,
            auto_sim_phase=state.auto_sim_phase,
            pressure=state.pressure,
            pump_primary=state.pump_primary_status,
            pump_secondary=state.pump_secondary_status,
            pump_tertiary=state.pump_tertiary_status,
            interlock=state.interlock_satisfied,
            thermal_kw=state.thermal_kw,
            turbine_speed=state.turbine_speed,
            emergency_active=state.emergency_active
        )
    
    def show_startup_screen(self):
        """Show startup screen on all 9 displays (128x32 layout)"""
        screens_mux1 = [
            (1, self.oled_pressurizer, "Pressurizer"),
            (2, self.oled_pump_primary, "Pompa Primer"),
            (3, self.oled_pump_secondary, "Pompa Sekunder"),
            (4, self.oled_pump_tertiary, "Pompa Tersier"),
            (5, self.oled_safety_rod, "Safety Rod"),
            (6, self.oled_shim_rod, "Shim Rod"),
            (7, self.oled_regulating_rod, "Reg Rod")
        ]
        
        screens_mux2 = [
            (1, self.oled_thermal_power, "Daya"),
            (2, self.oled_system_status, "Status")
        ]
        
        # Show on TCA9548A #1
        for channel, display, name in screens_mux1:
            self.mux.select_display_channel(channel)
            display.clear()
            # Simple 2-line layout with larger font
            display.draw_text_centered(name, 4, display.font)
            display.draw_text_centered("Siap", 18, display.font_large)
            display.show()
        
        # Show on TCA9548A #2
        for channel, display, name in screens_mux2:
            self.mux.select_esp_channel(channel)
            display.clear()
            # Simple 2-line layout with larger font
            display.draw_text_centered(name, 4, display.font)
            display.draw_text_centered("Siap", 18, display.font_large)
            display.show()
        
        time.sleep(2)
    
    def show_error_screen(self, message: str):
        """Show error message on all 9 displays (128x32 layout)"""
        screens_mux1 = [
            (1, self.oled_pressurizer),
            (2, self.oled_pump_primary),
            (3, self.oled_pump_secondary),
            (4, self.oled_pump_tertiary),
            (5, self.oled_safety_rod),
            (6, self.oled_shim_rod),
            (7, self.oled_regulating_rod)
        ]
        
        screens_mux2 = [
            (1, self.oled_thermal_power),
            (2, self.oled_system_status)
        ]
        
        # Show on TCA9548A #1
        for channel, display in screens_mux1:
            self.mux.select_display_channel(channel)
            display.clear()
            # 2 lines layout with larger font
            display.draw_text_centered("ERROR", 4, display.font_large)
            display.draw_text_centered("Sistem", 18, display.font)
            display.show()
        
        # Show on TCA9548A #2
        for channel, display in screens_mux2:
            self.mux.select_esp_channel(channel)
            display.clear()
            # 2 lines layout with larger font
            display.draw_text_centered("ERROR", 4, display.font_large)
            display.draw_text_centered("Sistem", 18, display.font)
            display.show()


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("OLED Manager Test")
    print("Note: This is a simulation. Real display requires Raspberry Pi hardware.")
    
    # Create dummy display
    display = OLEDDisplay()
    
    # Test drawing (128x32 layout)
    display.clear()
    display.draw_text_centered("PRESSURIZER", 1, display.font_small)
    display.draw_text_centered("150.5 bar", 12, display.font)
    display.draw_text_centered("Normal", 22, display.font_small)
    
    print("Display test completed (image not shown in simulation)")
