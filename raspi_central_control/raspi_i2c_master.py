"""
⚠️ DEPRECATED - This module is no longer used as of v4.0
================================================================

This file contains the OLD I2C-based communication system.
As of v4.0, ESP communication uses UART instead of I2C.

**Current architecture:** See raspi_uart_master.py and AGENT.md Section 2

**Why deprecated:**
- Replaced by Binary UART Protocol (115200 baud, 8N1)
- Better reliability (CRC8 checksum, ACK/NACK)
- Lower latency (5-27 bytes vs 42-187 bytes JSON)
- Eliminates I2C buffer garbage issues

**Safe to delete** - File kept for reference only.

================================================================
I2C Master Communication Module - 2 ESP Architecture (LEGACY)
Handles communication with 2 ESP32 slaves (ESP-BC and ESP-E)
"""

import smbus2
import struct
import logging
import time
from typing import Optional, Tuple, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ESP_BC_Data:
    """Data structure for ESP-BC (Control Rods + Turbine + Humidifier + Pumps) - MERGED"""
    # To ESP-BC
    safety_target: int = 0
    shim_target: int = 0
    regulating_target: int = 0
    
    # Humidifier commands (6 individual relays)
    humid_sg1_cmd: int = 0  # Steam Generator #1
    humid_sg2_cmd: int = 0  # Steam Generator #2
    humid_ct1_cmd: int = 0  # Cooling Tower #1
    humid_ct2_cmd: int = 0  # Cooling Tower #2
    humid_ct3_cmd: int = 0  # Cooling Tower #3
    humid_ct4_cmd: int = 0  # Cooling Tower #4
    
    # From ESP-BC
    safety_actual: int = 0
    shim_actual: int = 0
    regulating_actual: int = 0
    kw_thermal: float = 0.0
    power_level: float = 0.0
    state: int = 0
    generator_status: int = 0
    turbine_status: int = 0
    
    # Humidifier status (6 individual relays)
    humid_sg1_status: int = 0
    humid_sg2_status: int = 0
    humid_ct1_status: int = 0
    humid_ct2_status: int = 0
    humid_ct3_status: int = 0
    humid_ct4_status: int = 0


@dataclass
class ESP_E_Data:
    """Data structure for ESP-E (3-Flow LED Visualizer + Power Indicator)"""
    # To ESP-E
    pressure_primary: float = 0.0
    pump_status_primary: int = 0
    pressure_secondary: float = 0.0
    pump_status_secondary: int = 0
    pressure_tertiary: float = 0.0
    pump_status_tertiary: int = 0
    thermal_power_kw: float = 0.0  # NEW: Thermal power for LED indicator
    
    # From ESP-E
    animation_speed: int = 0
    led_count: int = 0


class I2CMaster:
    """
    I2C Master for communicating with 2 ESP32 slaves
    - ESP-BC (0x08): Control rods + Turbine + Humidifier
    - ESP-E (0x0A): 48 LED visualizer
    """
    
    def __init__(self, bus_number: int, mux_select_callback=None):
        """
        Initialize I2C Master
        
        Args:
            bus_number: I2C bus number
            mux_select_callback: Function to select MUX #2 channel (for ESP-E only)
                                 ESP-BC uses MUX #1 channel 0 (handled separately)
        """
        self.bus_number = bus_number
        self.mux_select = mux_select_callback
        
        try:
            self.bus = smbus2.SMBus(bus_number)
            logger.info(f"I2C Master initialized on bus {bus_number} (2 ESP Architecture)")
            logger.info(f"  ESP-BC: 0x08 (MUX #1, Ch 0) - Control Rods + Turbine + Humidifier")
            logger.info(f"  ESP-E: 0x0A (MUX #2, Ch 0) - 3-Flow LED Visualizer")
        except Exception as e:
            logger.error(f"Failed to initialize I2C Master: {e}")
            raise
        
        # Data storage (Only 2 ESP)
        self.esp_bc_data = ESP_BC_Data()
        self.esp_e_data = ESP_E_Data()
        
        # Error tracking
        self.error_counts = {0x08: 0, 0x0A: 0}
        self.last_comm_time = {0x08: 0, 0x0A: 0}
    
    def write_read_with_retry(self, address: int, write_data: bytes, 
                               read_length: int, retry_count: int = 3) -> Optional[bytes]:
        """
        Write data to slave and read response with retry logic
        
        Args:
            address: I2C slave address
            write_data: Bytes to write
            read_length: Number of bytes to read
            retry_count: Number of retries on failure
            
        Returns:
            Bytes read from slave, or None on failure
        """
        for attempt in range(retry_count):
            try:
                # Write data
                self.bus.write_i2c_block_data(address, 0x00, list(write_data))
                time.sleep(0.01)  # Short delay for slave to process
                
                # Read response
                data = self.bus.read_i2c_block_data(address, 0x00, read_length)
                
                # Update last communication time
                self.last_comm_time[address] = time.time()
                
                # Reset error count on success
                if self.error_counts[address] > 0:
                    logger.info(f"Communication restored with ESP 0x{address:02X}")
                    self.error_counts[address] = 0
                
                return bytes(data)
                
            except OSError as e:
                if e.errno == 121:  # Remote I/O error
                    logger.warning(f"ESP 0x{address:02X} not responding (attempt {attempt+1})")
                elif e.errno == 110:  # Timeout
                    logger.warning(f"I2C timeout for ESP 0x{address:02X} (attempt {attempt+1})")
                else:
                    logger.error(f"I2C error {e.errno} for ESP 0x{address:02X}")
                
                self.error_counts[address] += 1
                
                if attempt < retry_count - 1:
                    time.sleep(0.05)  # Delay before retry
                    
            except Exception as e:
                logger.error(f"Unexpected error communicating with ESP 0x{address:02X}: {e}")
                self.error_counts[address] += 1
                
                if attempt < retry_count - 1:
                    time.sleep(0.05)
        
        return None
    
    # ============================================
    # ESP-BC Communication (Control Rods + Turbine + Humidifier)
    # ============================================
    
    def update_esp_bc(self, safety: int, shim: int, regulating: int,
                      humid_sg1: int = 0, humid_sg2: int = 0,
                      humid_ct1: int = 0, humid_ct2: int = 0,
                      humid_ct3: int = 0, humid_ct4: int = 0) -> bool:
        """
        Send rod positions and humidifier commands to ESP-BC
        
        Args:
            safety: Safety rod target (0-100%)
            shim: Shim rod target (0-100%)
            regulating: Regulating rod target (0-100%)
            humid_sg1: Steam Generator humidifier #1 (0/1)
            humid_sg2: Steam Generator humidifier #2 (0/1)
            humid_ct1: Cooling Tower humidifier #1 (0/1)
            humid_ct2: Cooling Tower humidifier #2 (0/1)
            humid_ct3: Cooling Tower humidifier #3 (0/1)
            humid_ct4: Cooling Tower humidifier #4 (0/1)
            
        Returns:
            True if successful, False otherwise
        """
        # NOTE: ESP-BC is on TCA9548A #1 (0x70), Channel 0
        # The mux_select callback is for MUX #2 only (ESP-E)
        # MUX #1 Channel 0 must be selected externally before calling this
        # OR we need a separate callback for MUX #1
        # For now, we assume MUX #1 Ch 0 is already selected or handled by main_panel
        
        try:
            # Update internal state
            self.esp_bc_data.safety_target = safety
            self.esp_bc_data.shim_target = shim
            self.esp_bc_data.regulating_target = regulating
            self.esp_bc_data.humid_sg1_cmd = humid_sg1
            self.esp_bc_data.humid_sg2_cmd = humid_sg2
            self.esp_bc_data.humid_ct1_cmd = humid_ct1
            self.esp_bc_data.humid_ct2_cmd = humid_ct2
            self.esp_bc_data.humid_ct3_cmd = humid_ct3
            self.esp_bc_data.humid_ct4_cmd = humid_ct4
            
            # Pack 6 humidifier commands into 1 byte (bit packing)
            humid_byte = (humid_sg1 & 0x01) | \
                        ((humid_sg2 & 0x01) << 1) | \
                        ((humid_ct1 & 0x01) << 2) | \
                        ((humid_ct2 & 0x01) << 3) | \
                        ((humid_ct3 & 0x01) << 4) | \
                        ((humid_ct4 & 0x01) << 5)
            
            # Pack data: 12 bytes
            write_data = struct.pack('<BBBBfBBBB',
                                    safety, shim, regulating, 0,
                                    0.0,  # Reserved float
                                    humid_byte, 0,  # Humidifier byte + reserved
                                    0, 0)  # Reserved bytes
            
            # Read response: 20 bytes
            response = self.write_read_with_retry(0x08, write_data, 20)
            
            if response:
                # Unpack response
                values = struct.unpack('<BBBBffIBBBB', response)
                self.esp_bc_data.safety_actual = values[0]
                self.esp_bc_data.shim_actual = values[1]
                self.esp_bc_data.regulating_actual = values[2]
                # values[3] reserved
                self.esp_bc_data.kw_thermal = values[4]
                self.esp_bc_data.power_level = values[5]
                self.esp_bc_data.state = values[6]
                self.esp_bc_data.generator_status = values[7]
                self.esp_bc_data.turbine_status = values[8]
                
                # Unpack humidifier status (bit-packed in 2 bytes)
                humid_status_byte1 = values[9]
                humid_status_byte2 = values[10]
                
                self.esp_bc_data.humid_sg1_status = humid_status_byte1 & 0x01
                self.esp_bc_data.humid_sg2_status = (humid_status_byte1 >> 1) & 0x01
                self.esp_bc_data.humid_ct1_status = (humid_status_byte1 >> 2) & 0x01
                self.esp_bc_data.humid_ct2_status = (humid_status_byte1 >> 3) & 0x01
                self.esp_bc_data.humid_ct3_status = humid_status_byte2 & 0x01
                self.esp_bc_data.humid_ct4_status = (humid_status_byte2 >> 1) & 0x01
                
                logger.debug(f"ESP-BC: Rods=[{values[0]},{values[1]},{values[2]}], "
                           f"Thermal={values[4]:.1f}kW, Power={values[5]:.1f}%, "
                           f"Humid_SG=[{self.esp_bc_data.humid_sg1_status},{self.esp_bc_data.humid_sg2_status}], "
                           f"Humid_CT=[{self.esp_bc_data.humid_ct1_status},{self.esp_bc_data.humid_ct2_status},"
                           f"{self.esp_bc_data.humid_ct3_status},{self.esp_bc_data.humid_ct4_status}]")
                return True
            
        except Exception as e:
            logger.error(f"Error updating ESP-BC: {e}")
        
        return False
    
    def get_esp_bc_data(self) -> ESP_BC_Data:
        """Get latest data from ESP-BC"""
        return self.esp_bc_data
    

    
    # ============================================
    # ESP-E Communication (3-Flow LED Visualizer)
    # ============================================
    
    def update_esp_e(self, 
                    pressure_primary: float, pump_status_primary: int,
                    pressure_secondary: float, pump_status_secondary: int,
                    pressure_tertiary: float, pump_status_tertiary: int,
                    thermal_power_kw: float = 0.0) -> bool:
        """
        Update ESP-E with all 3 flow visualizers + thermal power
        
        Args:
            pressure_primary: Primary flow pressure
            pump_status_primary: Primary pump status (0-3)
            pressure_secondary: Secondary flow pressure
            pump_status_secondary: Secondary pump status
            pressure_tertiary: Tertiary flow pressure
            pump_status_tertiary: Tertiary pump status
            thermal_power_kw: Thermal power in kW (for power indicator LEDs)
            
        Returns:
            True if successful, False otherwise
        """
        if self.mux_select:
            # Select ESP-E: TCA9548A #2 (0x71), Channel 0
            self.mux_select(0)
        
        try:
            # Update internal state
            self.esp_e_data.pressure_primary = pressure_primary
            self.esp_e_data.pump_status_primary = pump_status_primary
            self.esp_e_data.pressure_secondary = pressure_secondary
            self.esp_e_data.pump_status_secondary = pump_status_secondary
            self.esp_e_data.pressure_tertiary = pressure_tertiary
            self.esp_e_data.pump_status_tertiary = pump_status_tertiary
            self.esp_e_data.thermal_power_kw = thermal_power_kw
            
            # Pack data: 20 bytes (3 x (float + uint8) + thermal power float)
            write_data = struct.pack('<BfBfBfBf',
                                    0,  # Register address
                                    pressure_primary, pump_status_primary,
                                    pressure_secondary, pump_status_secondary,
                                    pressure_tertiary, pump_status_tertiary,
                                    thermal_power_kw)
            
            # Read response: 2 bytes
            response = self.write_read_with_retry(0x0A, write_data, 2)
            
            if response:
                values = struct.unpack('<BB', response)
                self.esp_e_data.animation_speed = values[0]
                self.esp_e_data.led_count = values[1]
                
                logger.debug(f"ESP-E: Speed={values[0]}, LEDs={values[1]}")
                return True
            
        except Exception as e:
            logger.error(f"Error updating ESP-E: {e}")
        
        return False
    
    def get_esp_e_data(self) -> ESP_E_Data:
        """Get latest data from ESP-E"""
        return self.esp_e_data
    
    # ============================================
    # Health Check
    # ============================================
    
    def get_health_status(self) -> Dict[int, dict]:
        """
        Get health status of all ESP slaves
        
        Returns:
            Dictionary mapping addresses to health info
        """
        current_time = time.time()
        health = {}
        
        for addr in [0x08, 0x0A]:  # Only 2 ESP (ESP-BC and ESP-E)
            last_comm = self.last_comm_time.get(addr, 0)
            time_since = current_time - last_comm if last_comm > 0 else -1
            
            health[addr] = {
                'error_count': self.error_counts.get(addr, 0),
                'last_comm': last_comm,
                'time_since': time_since,
                'status': 'OK' if self.error_counts.get(addr, 0) < 5 else 'ERROR'
            }
        
        return health
    
    def close(self):
        """Close I2C bus with proper cleanup"""
        try:
            # Disable all multiplexer channels first (if available)
            if hasattr(self, 'mux_select') and self.mux_select:
                try:
                    # Try to disable multiplexer channels
                    # This assumes we have access to multiplexer
                    pass
                except:
                    pass
            
            # Close bus
            if hasattr(self, 'bus'):
                self.bus.close()
            
            logger.info("I2C Master closed")
        except Exception as e:
            logger.error(f"Error closing I2C Master: {e}")


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing I2C Master (2 ESP Architecture)...")
    
    try:
        master = I2CMaster(bus_number=1)
        
        # Test ESP-BC communication
        print("\nTesting ESP-BC communication...")
        success = master.update_esp_bc(
            safety=50, shim=60, regulating=70,
            humid_sg1=1, humid_sg2=1,
            humid_ct1=1, humid_ct2=0, humid_ct3=1, humid_ct4=0
        )
        
        if success:
            data = master.get_esp_bc_data()
            print(f"  Rod positions: {data.safety_actual}, {data.shim_actual}, {data.regulating_actual}")
            print(f"  Thermal power: {data.kw_thermal} kW")
            print(f"  Turbine power: {data.power_level}%")
            print(f"  Humidifiers SG: [{data.humid_sg1_status}, {data.humid_sg2_status}]")
            print(f"  Humidifiers CT: [{data.humid_ct1_status}, {data.humid_ct2_status}, "
                  f"{data.humid_ct3_status}, {data.humid_ct4_status}]")
        else:
            print("  Failed to communicate with ESP-BC")
        
        # Test ESP-E communication
        print("\nTesting ESP-E communication...")
        success = master.update_esp_e(
            pressure_primary=155.0, pump_status_primary=2,
            pressure_secondary=50.0, pump_status_secondary=2,
            pressure_tertiary=15.0, pump_status_tertiary=2
        )
        
        if success:
            data = master.get_esp_e_data()
            print(f"  Animation speed: {data.animation_speed}")
            print(f"  LED count: {data.led_count}")
        else:
            print("  Failed to communicate with ESP-E")
        
        # Health check
        print("\nHealth Status:")
        health = master.get_health_status()
        for addr, info in health.items():
            print(f"  ESP 0x{addr:02X}: {info['status']} (errors: {info['error_count']})")
        
        master.close()
        
    except Exception as e:
        print(f"Error: {e}")
