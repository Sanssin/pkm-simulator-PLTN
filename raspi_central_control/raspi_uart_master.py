"""
UART Master Communication Module
Replaces I2C communication with UART for ESP32 slaves

Architecture:
- ESP-BC: /dev/ttyAMA0 (GPIO 14/15) - Control Rods + Turbine + Humidifier
- ESP-E:  /dev/ttyAMA1 (GPIO 4/5)   - LED Visualizer (UART3)

Protocol: Binary Protocol with ACK/NACK (115200 baud, 8N1)
- Format: STX | CMD | LEN | PAYLOAD | CRC | ETX
- Message size: 5-27 bytes (vs 42-187 bytes JSON)
- CRC8 checksum for error detection (CMD+LEN+PAYLOAD only)
- LEN field for payload validation
- Retry mechanism (3x with exponential backoff)
- Eliminates buffer garbage issues
"""

import serial
import json
import time
import logging
import struct
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import threading

logger = logging.getLogger(__name__)


# ============================================
# Binary Protocol Constants
# ============================================
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text
ACK = 0x06  # Acknowledge
NACK = 0x15  # Negative Acknowledge

# Command types
CMD_PING = 0x50  # 'P'
CMD_UPDATE = 0x55  # 'U'

# Protocol configuration
USE_BINARY_PROTOCOL = False  # Set to False to use legacy JSON protocol
MAX_RETRIES = 3
RETRY_DELAYS = [0.03, 0.05, 0.1]  # Optimized: 30ms, 50ms, 100ms (was 50ms, 100ms, 200ms)


# ============================================
# CRC8 Checksum (CRC-8/MAXIM)
# ============================================
def crc8_maxim(data: bytes) -> int:
    """
    Calculate CRC-8/MAXIM checksum
    
    Polynomial: 0x31
    Initial value: 0x00
    
    Args:
        data: Bytes to checksum
        
    Returns:
        CRC8 checksum (0-255)
    """
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x31
            else:
                crc = crc << 1
            crc &= 0xFF
    return crc


@dataclass
class ESP_BC_Data:
    """Data structure for ESP-BC (Control Rods + Turbine + Pumps + Motor Driver + Cooling Tower Relays)"""
    # To ESP-BC
    safety_target: int = 0
    shim_target: int = 0
    regulating_target: int = 0
    
    humid_ct1_cmd: int = 0
    humid_ct2_cmd: int = 0
    humid_ct3_cmd: int = 0
    humid_ct4_cmd: int = 0
    
    # From ESP-BC - Control Rods
    safety_actual: int = 0
    shim_actual: int = 0
    regulating_actual: int = 0
    
    # From ESP-BC - Turbine & Power
    kw_thermal: float = 0.0
    power_level: float = 0.0
    state: int = 0
    generator_status: int = 0
    turbine_status: int = 0
    turbine_speed: float = 0.0
    
    # From ESP-BC - Pump Speeds (automatic control by ESP)
    pump_primary_speed: float = 0.0
    pump_secondary_speed: float = 0.0
    pump_tertiary_speed: float = 0.0
    
    # From ESP-BC - Cooling Tower Humidifier Status (4 relays only)
    humid_ct1_status: int = 0
    humid_ct2_status: int = 0
    humid_ct3_status: int = 0
    humid_ct4_status: int = 0


@dataclass
class ESP_E_Data:
    """Data structure for ESP-E (Power Indicator + Water Flow Visualization)"""
    # To ESP-E
    thermal_power_kw: float = 0.0
    pump_primary_status: int = 0
    pump_secondary_status: int = 0
    pump_tertiary_status: int = 0
    
    # From ESP-E
    power_mwe: float = 0.0
    pwm: int = 0


# ============================================
# Binary Protocol Encoders
# ============================================

def encode_ping_command() -> bytes:
    """
    Encode ping command
    
    Format: [STX][CMD_PING][LEN=0][CRC8][ETX]
    Total: 5 bytes
    
    Returns:
        Binary message bytes
    """
    cmd = CMD_PING
    length = 0  # No payload
    crc_data = bytes([cmd, length])
    crc = crc8_maxim(crc_data)
    return bytes([STX, cmd, length, crc, ETX])


def encode_esp_bc_update(rods: list, pumps: list, humid: list) -> bytes:
    """
    Encode ESP-BC update command
    
    Format: [STX][CMD_UPDATE][LEN=10][rod1][rod2][rod3][pump1][pump2][pump3][h1][h2][h3][h4][CRC8][ETX]
    Total: 15 bytes
    
    Args:
        rods: [safety, shim, regulating] (0-100)
        pumps: [primary, secondary, tertiary] (0-3)
        humid: [ct1, ct2, ct3, ct4] (0-1)
        
    Returns:
        Binary message bytes
    """
    # Clamp values to valid ranges
    rod1 = max(0, min(100, int(rods[0])))
    rod2 = max(0, min(100, int(rods[1])))
    rod3 = max(0, min(100, int(rods[2])))
    
    pump1 = max(0, min(3, int(pumps[0])))
    pump2 = max(0, min(3, int(pumps[1])))
    pump3 = max(0, min(3, int(pumps[2])))
    
    h1 = 1 if int(humid[0]) != 0 else 0
    h2 = 1 if int(humid[1]) != 0 else 0
    h3 = 1 if int(humid[2]) != 0 else 0
    h4 = 1 if int(humid[3]) != 0 else 0
    
    cmd = CMD_UPDATE
    payload = bytes([rod1, rod2, rod3, pump1, pump2, pump3, h1, h2, h3, h4])
    length = len(payload)  # 10 bytes
    
    # CRC over CMD + LEN + PAYLOAD
    crc_data = bytes([cmd, length]) + payload
    crc = crc8_maxim(crc_data)
    
    return bytes([STX, cmd, length]) + payload + bytes([crc, ETX])


def encode_esp_e_update(thermal_kw: float, pump_primary: int, pump_secondary: int, pump_tertiary: int) -> bytes:
    """
    Encode ESP-E update command
    
    Format: [STX][CMD_UPDATE][LEN=7][thermal_kw (float32)][pump_prim][pump_sec][pump_ter][CRC8][ETX]
    Total: 12 bytes
    
    Args:
        thermal_kw: Thermal power in kW (float)
        pump_primary: Primary pump status (0-3)
        pump_secondary: Secondary pump status (0-3)
        pump_tertiary: Tertiary pump status (0-3)
        
    Returns:
        Binary message bytes
    """
    cmd = CMD_UPDATE
    
    # Pack thermal_kw (4 bytes) + 3 pump status bytes (1 byte each)
    payload = struct.pack('<f', thermal_kw)  # 4 bytes
    payload += bytes([
        max(0, min(3, int(pump_primary))),
        max(0, min(3, int(pump_secondary))),
        max(0, min(3, int(pump_tertiary)))
    ])  # 3 bytes
    
    length = len(payload)  # 7
    
    # CRC over CMD + LEN + PAYLOAD
    crc_data = bytes([cmd, length]) + payload
    crc = crc8_maxim(crc_data)
    
    return bytes([STX, cmd, length]) + payload + bytes([crc, ETX])


# ============================================
# Binary Protocol Decoders
# ============================================

def decode_binary_response(data: bytes) -> Tuple[Optional[int], Optional[int], Optional[bytes]]:
    """
    Decode binary response message
    
    Format: [STX][CMD][LEN][PAYLOAD...][CRC8][ETX]
    
    Args:
        data: Raw bytes from serial port
        
    Returns:
        Tuple of (length, msg_type, payload) or (None, None, None) if invalid
    """
    if len(data) < 5:  # Minimum: STX + CMD + LEN + CRC + ETX
        logger.error(f"Response too short: {len(data)} bytes")
        return None, None, None
    
    if data[0] != STX:
        logger.error(f"Invalid STX: 0x{data[0]:02X}")
        return None, None, None
    
    if data[-1] != ETX:
        logger.error(f"Invalid ETX: 0x{data[-1]:02X}")
        return None, None, None
    
    # Extract fields
    msg_type = data[1]  # CMD/ACK/NACK
    length = data[2]    # Payload length
    
    # Validate message length
    expected_total_len = 5 + length  # STX + CMD + LEN + PAYLOAD + CRC + ETX
    if len(data) != expected_total_len:
        logger.error(f"Length mismatch: got {len(data)} bytes, expected {expected_total_len} (LEN field={length})")
        return None, None, None
    
    payload = data[3:3+length]  # Extract payload based on LEN field
    received_crc = data[-2]
    
    # Validate CRC (over CMD + LEN + PAYLOAD)
    crc_data = data[1:3+length]  # CMD + LEN + payload
    calculated_crc = crc8_maxim(crc_data)
    
    if received_crc != calculated_crc:
        logger.error(f"CRC mismatch: received=0x{received_crc:02X}, calculated=0x{calculated_crc:02X}")
        return None, None, None
    
    return length, msg_type, payload


def decode_esp_bc_response(payload: bytes) -> Optional[Dict]:
    """
    Decode ESP-BC response payload
    
    Format: [rod1][rod2][rod3][thermal_kw (4)][power_lvl (2)][state][turb_spd (2)][pump1 (2)][pump2 (2)][pump3 (2)][h1][h2][h3][h4]
    Total payload: 23 bytes
    
    Args:
        payload: Response payload bytes
        
    Returns:
        Dictionary with decoded data or None if invalid
    """
    if len(payload) < 23:
        logger.error(f"ESP-BC payload too short: {len(payload)} bytes (expected 23)")
        return None
    
    try:
        # Unpack fixed-size fields
        rod1 = payload[0]
        rod2 = payload[1]
        rod3 = payload[2]
        thermal_kw = struct.unpack('<f', payload[3:7])[0]
        power_lvl = struct.unpack('<H', payload[7:9])[0] / 100.0  # uint16 → float (0.00-100.00)
        state = payload[9]
        turb_spd = struct.unpack('<H', payload[10:12])[0] / 100.0
        pump1 = struct.unpack('<H', payload[12:14])[0] / 100.0
        pump2 = struct.unpack('<H', payload[14:16])[0] / 100.0
        pump3 = struct.unpack('<H', payload[16:18])[0] / 100.0
        h1 = payload[18]
        h2 = payload[19]
        h3 = payload[20]
        h4 = payload[21]
        
        return {
            'rods': [rod1, rod2, rod3],
            'thermal_kw': thermal_kw,
            'power_level': power_lvl,
            'state': state,
            'turbine_speed': turb_spd,
            'pump_speeds': [pump1, pump2, pump3],
            'humid_status': [h1, h2, h3, h4]
        }
    except Exception as e:
        logger.error(f"Error decoding ESP-BC response: {e}")
        return None


def decode_esp_e_response(payload: bytes) -> Optional[Dict]:
    """
    Decode ESP-E response payload
    
    Format: [power_mwe (4)][pwm][pump_prim][pump_sec][pump_ter]
    Total payload: 8 bytes
    
    Args:
        payload: Response payload bytes
        
    Returns:
        Dictionary with decoded data or None if invalid
    """
    if len(payload) < 8:
        logger.error(f"ESP-E payload too short: {len(payload)} bytes (expected 8)")
        return None
    
    try:
        power_mwe = struct.unpack('<f', payload[0:4])[0]
        pwm = payload[4]
        pump_primary = payload[5]
        pump_secondary = payload[6]
        pump_tertiary = payload[7]
        
        return {
            'power_mwe': power_mwe,
            'pwm': pwm,
            'pump_primary': pump_primary,
            'pump_secondary': pump_secondary,
            'pump_tertiary': pump_tertiary
        }
    except Exception as e:
        logger.error(f"Error decoding ESP-E response: {e}")
        return None


class UARTDevice:
    """Base class for UART device communication"""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initialize UART device
        
        Args:
            port: Serial port path (e.g., '/dev/ttyAMA0')
            baudrate: Communication speed (default 115200)
            timeout: Read timeout in seconds (default 1.0)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self.lock = threading.Lock()
        self.error_count = 0
        self.last_comm_time = 0.0
        
    def connect(self) -> bool:
        """
        Open serial connection
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=1.0
            )
            
            # Flush buffers and wait for ESP32 to be ready
            time.sleep(0.5)  # Optimized: 500ms sufficient for ESP32 boot (was 2.0s)
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            logger.info(f"✅ UART connected: {self.port} at {self.baudrate} baud")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to open {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
                logger.info(f"UART disconnected: {self.port}")
        except Exception as e:
            logger.error(f"Error closing {self.port}: {e}")
    
    
    def send_json(self, data: dict) -> bool:
        """
        Send JSON message to device (fire-and-forget, no response expected)
        
        For request-response communication, use send_receive() instead.
        
        Args:
            data: Dictionary to send as JSON
            
        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            try:
                if not self.serial or not self.serial.is_open:
                    logger.error(f"Serial port {self.port} not open")
                    return False
                
                # Flush buffers before send (fire-and-forget mode)
                try:
                    self.serial.reset_input_buffer()
                    self.serial.reset_output_buffer()
                except Exception:
                    pass

                # Convert to JSON and add newline
                json_str = json.dumps(data) + '\n'
                
                # Send
                self.serial.write(json_str.encode('utf-8'))
                self.serial.flush()  # Ensure data is sent
                time.sleep(0.010)  # 10ms for ESP to process
                logger.info(f"TX {self.port}: {json_str.strip()}")
                return True
                
            except Exception as e:
                logger.error(f"Error sending to {self.port}: {e}")
                self.error_count += 1
                return False
    
    def receive_json(self, timeout: Optional[float] = None) -> Optional[dict]:
        """
        Receive JSON message from device
        
        Args:
            timeout: Optional timeout override
            
        Returns:
            Dictionary if successful, None otherwise
        """
        with self.lock:
            try:
                if not self.serial or not self.serial.is_open:
                    logger.error(f"Serial port {self.port} not open")
                    return None
                
                # Set timeout if provided
                old_timeout = self.serial.timeout
                if timeout is not None:
                    self.serial.timeout = timeout
                
                # Read line
                line = self.serial.readline()
                
                # Restore timeout
                if timeout is not None:
                    self.serial.timeout = old_timeout
                
                if not line:
                    logger.warning(f"No response from {self.port} (timeout)")
                    self.error_count += 1
                    return None
                
                # Decode and parse JSON
                json_str = line.decode('utf-8').strip()
                logger.info(f"RX {self.port}: {json_str}")
                
                data = json.loads(json_str)
                
                # Reset error count on success
                self.last_comm_time = time.time()
                if self.error_count > 0:
                    logger.info(f"Communication restored with {self.port}")
                    self.error_count = 0
                
                return data
                
            except json.JSONDecodeError as e:
                # Attempt to show raw bytes received for debugging
                try:
                    raw = line
                except Exception:
                    raw = b''
                logger.error(f"JSON decode error from {self.port}: {e}")
                logger.error(f"  --> Received raw bytes: {raw}")
                logger.error(f"  --> Decoded string attempted: '{json_str if 'json_str' in locals() else '<none>'}'")
                self.error_count += 1
                return None
                
            except Exception as e:
                logger.error(f"Error receiving from {self.port}: {e}")
                self.error_count += 1
                return None
    
    
    def send_receive(self, data: dict, timeout: float = 1.0) -> Optional[dict]:
        """
        Send command and wait for response
        
        Args:
            data: Dictionary to send
            timeout: Response timeout
            
        Returns:
            Response dictionary or None
        """
        with self.lock:
            try:
                if not self.serial or not self.serial.is_open:
                    logger.error(f"Serial port {self.port} not open")
                    return None
                
                # CRITICAL: Flush output buffer ONLY (not input!)
                # Input buffer should NOT be flushed here because previous response might still be there
                try:
                    self.serial.reset_output_buffer()  # Clear old TX data only
                except Exception:
                    pass

                # Convert to JSON and add newline
                json_str = json.dumps(data) + '\n'
                
                # Send
                self.serial.write(json_str.encode('utf-8'))
                self.serial.flush()  # Ensure data is sent
                logger.info(f"TX {self.port}: {json_str.strip()}")
                
                # Wait for ESP to process (don't flush input yet!)
                time.sleep(0.010)  # 10ms for ESP to start processing
                
                # Now receive response
                # Set timeout if provided
                old_timeout = self.serial.timeout
                if timeout is not None:
                    self.serial.timeout = timeout
                
                # Read line
                line = self.serial.readline()
                
                # Restore timeout
                if timeout is not None:
                    self.serial.timeout = old_timeout
                
                if not line:
                    logger.warning(f"No response from {self.port} (timeout)")
                    self.error_count += 1
                    # Flush input buffer NOW (after failed read)
                    try:
                        self.serial.reset_input_buffer()
                    except Exception:
                        pass
                    return None
                
                # Decode and parse JSON
                json_str_response = line.decode('utf-8').strip()
                logger.info(f"RX {self.port}: {json_str_response}")
                
                response_data = json.loads(json_str_response)
                
                # Reset error count on success
                self.last_comm_time = time.time()
                if self.error_count > 0:
                    logger.info(f"Communication restored with {self.port}")
                    self.error_count = 0
                
                # Flush input buffer NOW (after successful read)
                # This clears any garbage that might have accumulated
                try:
                    self.serial.reset_input_buffer()
                except Exception:
                    pass
                
                return response_data
                
            except json.JSONDecodeError as e:
                # Attempt to show raw bytes received for debugging
                try:
                    raw = line
                except Exception:
                    raw = b''
                logger.error(f"JSON decode error from {self.port}: {e}")
                logger.error(f"  --> Received raw bytes: {raw}")
                logger.error(f"  --> Decoded string attempted: '{json_str_response if 'json_str_response' in locals() else '<none>'}'")
                self.error_count += 1
                # Flush input buffer after error
                try:
                    self.serial.reset_input_buffer()
                except Exception:
                    pass
                return None
                
            except Exception as e:
                logger.error(f"Error in send_receive from {self.port}: {e}")
                self.error_count += 1
                # Flush input buffer after error
                try:
                    self.serial.reset_input_buffer()
                except Exception:
                    pass
                return None



    def send_receive_binary(self, command_bytes: bytes, expected_response_len: int, 
                           timeout: float = 1.0) -> Optional[Tuple[int, int, bytes]]:
        """
        Send binary command and wait for response with ACK/NACK and retry mechanism
        
        This method implements:
        - CRC8 checksum validation
        - ACK/NACK response handling
        - Automatic retry (up to 3 attempts) with exponential backoff
        - Buffer garbage prevention
        
        Args:
            command_bytes: Binary command to send (already encoded with STX/ETX/CRC)
            expected_response_len: Expected response length in bytes
            timeout: Response timeout in seconds
            
        Returns:
            Tuple of (length, msg_type, payload) or None if failed after all retries
        """
        with self.lock:
            
            for attempt in range(MAX_RETRIES):
                try:
                    if not self.serial or not self.serial.is_open:
                        logger.error(f"Serial port {self.port} not open")
                        return None
                    
                    # CRITICAL: Flush buffers BEFORE sending to prevent garbage
                    try:
                        self.serial.reset_input_buffer()
                        self.serial.reset_output_buffer()
                    except Exception:
                        pass
                    
                    # Send command all at once (not byte-by-byte)
                    # Byte-by-byte with 1ms delay was causing buffer issues on ESP
                    self.serial.write(command_bytes)
                    self.serial.flush()
                    
                    # Log TX (hex dump for binary data)
                    hex_str = ' '.join(f'{b:02X}' for b in command_bytes)
                    logger.info(f"TX {self.port} (attempt {attempt+1}/{MAX_RETRIES}): [{hex_str}] ({len(command_bytes)} bytes)")
                    
                    # Wait for ESP to process and start transmitting
                    time.sleep(0.030)  # 30ms for ESP processing
                    
                    # Read response with timeout
                    old_timeout = self.serial.timeout
                    self.serial.timeout = timeout
                    
                    # Read until ETX (0x03) - more robust than fixed length
                    # This ensures we get the complete message regardless of timing
                    response_data = b''
                    max_bytes = 50  # Safety limit (max expected is 28 bytes)
                    start_time = time.time()
                    
                    while len(response_data) < max_bytes:
                        # Check timeout
                        if time.time() - start_time > timeout:
                            logger.warning(f"Timeout waiting for ETX from {self.port}")
                            break
                        
                        # Read one byte at a time
                        byte = self.serial.read(1)
                        if byte:
                            response_data += byte
                            # Check if we got ETX (end of message)
                            if byte[0] == ETX:
                                break
                        else:
                            # No data available, wait a bit
                            time.sleep(0.005)  # 5ms
                    
                    # Restore timeout
                    self.serial.timeout = old_timeout
                    
                    # Validate we got a complete message
                    if not response_data or len(response_data) < 5:
                        logger.warning(f"No response or too short from {self.port} (got {len(response_data)} bytes)")
                    elif response_data[-1] != ETX:
                        logger.warning(f"Response from {self.port} does not end with ETX (got {len(response_data)} bytes)")
                        
                        # Flush and retry
                        try:
                            self.serial.reset_input_buffer()
                        except Exception:
                            pass
                        
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAYS[attempt])
                            continue
                        else:
                            self.error_count += 1
                            return None
                    
                    # Log RX (hex dump)
                    hex_str_rx = ' '.join(f'{b:02X}' for b in response_data)
                    logger.info(f"RX {self.port}: [{hex_str_rx}] ({len(response_data)} bytes)")
                    
                    # Decode response
                    length, msg_type, payload = decode_binary_response(response_data)
                    
                    if length is None or msg_type is None:
                        logger.error(f"Failed to decode response from {self.port}")
                        
                        # Flush and retry
                        try:
                            self.serial.reset_input_buffer()
                        except Exception:
                            pass
                        
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAYS[attempt])
                            continue
                        else:
                            self.error_count += 1
                            return None
                    
                    # Check message type
                    if msg_type == NACK:
                        logger.warning(f"Received NACK from {self.port}")
                        
                        # Flush and retry
                        try:
                            self.serial.reset_input_buffer()
                        except Exception:
                            pass
                        
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAYS[attempt])
                            continue
                        else:
                            self.error_count += 1
                            return None
                    
                    if msg_type != ACK:
                        logger.error(f"Unexpected message type: 0x{msg_type:02X} (expected ACK=0x06)")
                        self.error_count += 1
                        return None
                    
                    # Success! Reset error count
                    self.last_comm_time = time.time()
                    if self.error_count > 0:
                        logger.info(f"Communication restored with {self.port}")
                        self.error_count = 0
                    
                    # Flush input buffer after successful read (clear any garbage)
                    try:
                        self.serial.reset_input_buffer()
                    except Exception:
                        pass
                    
                    # CRITICAL: Wait before next command to prevent collision
                    # ESP needs time to finish transmitting response (28 bytes @ 115200 = ~2.4ms)
                    # Add safety margin for processing
                    time.sleep(0.030)  # 30ms inter-message delay
                    
                    logger.debug(f"✓ Binary communication successful with {self.port}")
                    return length, msg_type, payload
                    
                except Exception as e:
                    logger.error(f"Error in send_receive_binary from {self.port}: {e}")
                    
                    # Flush and retry
                    try:
                        self.serial.reset_input_buffer()
                    except Exception:
                        pass
                    
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAYS[attempt])
                        continue
                    else:
                        self.error_count += 1
                        return None
            
            # All retries exhausted
            logger.error(f"All {MAX_RETRIES} retry attempts failed for {self.port}")
            self.error_count += 1
            return None


class UARTMaster:
    """
    UART Master for ESP32 communication
    Manages 2 UART devices: ESP-BC and ESP-E
    """
    
    def __init__(self, esp_bc_port: str = '/dev/ttyAMA0', 
                 esp_e_port: str = '/dev/ttyAMA3',  # GPIO 4/5
                 baudrate: int = 115200):
        """
        Initialize UART Master
        
        Args:
            esp_bc_port: Serial port for ESP-BC (required)
            esp_e_port: Serial port for ESP-E (optional, None to disable)
            baudrate: Communication speed
        """
        logger.info("="*70)
        logger.info("UART Master Initialization")
        logger.info("="*70)
        
        # Create UART devices
        self.esp_bc = UARTDevice(esp_bc_port, baudrate)
        self.esp_e = None
        self.esp_e_enabled = esp_e_port is not None
        
        if self.esp_e_enabled:
            self.esp_e = UARTDevice(esp_e_port, baudrate)
        
        # Data storage
        self.esp_bc_data = ESP_BC_Data()
        self.esp_e_data = ESP_E_Data()
        
        # Connect devices
        self.esp_bc_connected = self.esp_bc.connect()
        self.esp_e_connected = False
        
        # Additional stabilization delay after connection (critical for reliability)
        if self.esp_bc_connected:
            logger.info("⏳ Waiting 1 second for ESP32 to stabilize...")
            time.sleep(1.0)
            # Handshake ping to ensure ESP firmware ready
            try:
                if USE_BINARY_PROTOCOL:
                    # Binary ping: [STX][CMD_PING][LEN=0][CRC][ETX] = 5 bytes
                    ping_cmd = encode_ping_command()
                    result = self.esp_bc.send_receive_binary(ping_cmd, expected_response_len=5, timeout=1.0)
                    if result:
                        length, msg_type, payload = result
                        if msg_type == ACK:
                            logger.info("✅ ESP-BC handshake successful (binary pong)")
                        else:
                            logger.warning("⚠️  ESP-BC sent unexpected response")
                            self.esp_bc_connected = False
                    else:
                        logger.warning("⚠️  ESP-BC did not respond to binary ping - marking as not connected")
                        self.esp_bc_connected = False
                else:
                    # JSON ping (fallback)
                    ping_resp = self.esp_bc.send_receive({"cmd":"ping"}, timeout=1.0)
                    if ping_resp and ping_resp.get("status") == "ok" and ping_resp.get("message") == "pong":
                        logger.info("✅ ESP-BC handshake successful (JSON pong)")
                    else:
                        logger.warning("⚠️  ESP-BC did not respond to JSON ping - marking as not connected")
                        self.esp_bc_connected = False
            except Exception as e:
                logger.warning(f"⚠️  ESP-BC handshake error: {e}")
                self.esp_bc_connected = False
        
        if self.esp_bc_connected:
            logger.info(f"✅ ESP-BC: {esp_bc_port} (Control Rods + Turbine + Motor + Humid)")
        else:
            logger.error(f"❌ ESP-BC: {esp_bc_port} - NOT CONNECTED!")
        
        if self.esp_e_enabled:
            self.esp_e_connected = self.esp_e.connect()
            if self.esp_e_connected:
                logger.info("⏳ Waiting 1 second for ESP32 to stabilize...")
                time.sleep(1.0)
                # Handshake ping to ensure ESP-E firmware ready
                try:
                    if USE_BINARY_PROTOCOL:
                        # Binary ping
                        ping_cmd = encode_ping_command()
                        result = self.esp_e.send_receive_binary(ping_cmd, expected_response_len=5, timeout=1.0)
                        if result:
                            length, msg_type, payload = result
                            if msg_type == ACK:
                                logger.info("✅ ESP-E handshake successful (binary pong)")
                            else:
                                logger.warning("⚠️  ESP-E sent unexpected response")
                                self.esp_e_connected = False
                        else:
                            logger.warning("⚠️  ESP-E did not respond to binary ping - marking as not connected")
                            self.esp_e_connected = False
                    else:
                        # JSON ping (fallback)
                        ping_resp_e = self.esp_e.send_receive({"cmd":"ping"}, timeout=1.0)
                        if ping_resp_e and ping_resp_e.get("status") == "ok" and ping_resp_e.get("message") == "pong":
                            logger.info("✅ ESP-E handshake successful (JSON pong)")
                        else:
                            logger.warning("⚠️  ESP-E did not respond to JSON ping - marking as not connected")
                            self.esp_e_connected = False
                except Exception as e:
                    logger.warning(f"⚠️  ESP-E handshake error: {e}")
                    self.esp_e_connected = False

                if self.esp_e_connected:
                    logger.info(f"✅ ESP-E: {esp_e_port} (LED Visualizer)")
                else:
                    logger.warning(f"⚠️  ESP-E: {esp_e_port} - NOT CONNECTED (non-critical)")
            else:
                logger.warning(f"⚠️  ESP-E: {esp_e_port} - NOT CONNECTED (non-critical)")
        else:
            logger.info("ℹ️  ESP-E: Disabled (not configured)")
        
        logger.info("="*70)
    
    def update_esp_bc(self, safety: int, shim: int, regulating: int,
                      pump_primary: int = 0, pump_secondary: int = 0, pump_tertiary: int = 0,
                      humid_ct1: int = 0, humid_ct2: int = 0,
                      humid_ct3: int = 0, humid_ct4: int = 0) -> bool:
        """
        Send update to ESP-BC using binary protocol
        
        Args:
            safety: Safety rod target (0-100%)
            shim: Shim rod target (0-100%)
            regulating: Regulating rod target (0-100%)
            pump_primary: Primary pump status (0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN)
            pump_secondary: Secondary pump status (0-3)
            pump_tertiary: Tertiary pump status (0-3)
            humid_ct1-4: Cooling Tower humidifiers (0/1)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.esp_bc_connected:
            return False
        
        # Update internal state
        self.esp_bc_data.safety_target = safety
        self.esp_bc_data.shim_target = shim
        self.esp_bc_data.regulating_target = regulating
        self.esp_bc_data.humid_ct1_cmd = humid_ct1
        self.esp_bc_data.humid_ct2_cmd = humid_ct2
        self.esp_bc_data.humid_ct3_cmd = humid_ct3
        self.esp_bc_data.humid_ct4_cmd = humid_ct4
        
        if USE_BINARY_PROTOCOL:
            # === BINARY PROTOCOL ===
            # Encode binary command
            command_bytes = encode_esp_bc_update(
                rods=[safety, shim, regulating],
                pumps=[pump_primary, pump_secondary, pump_tertiary],
                humid=[humid_ct1, humid_ct2, humid_ct3, humid_ct4]
            )
            
            # Expected response: [STX][ACK][LEN=23][23 bytes payload][CRC][ETX] = 28 bytes
            expected_len = 28
            
            # Send and receive with retry
            result = self.esp_bc.send_receive_binary(command_bytes, expected_len, timeout=1.5)
            
            if result is None:
                logger.warning("ESP-BC: Binary communication failed")
                return False
            
            length, msg_type, payload = result
            
            # Decode response
            response_data = decode_esp_bc_response(payload)
            
            if response_data is None:
                logger.error("ESP-BC: Failed to decode binary response")
                return False
            
            # Update internal state from response
            self.esp_bc_data.safety_actual = response_data['rods'][0]
            self.esp_bc_data.shim_actual = response_data['rods'][1]
            self.esp_bc_data.regulating_actual = response_data['rods'][2]
            
            self.esp_bc_data.kw_thermal = response_data['thermal_kw']
            self.esp_bc_data.power_level = response_data['power_level']
            self.esp_bc_data.state = response_data['state']
            self.esp_bc_data.turbine_speed = response_data['turbine_speed']
            
            self.esp_bc_data.pump_primary_speed = response_data['pump_speeds'][0]
            self.esp_bc_data.pump_secondary_speed = response_data['pump_speeds'][1]
            self.esp_bc_data.pump_tertiary_speed = response_data['pump_speeds'][2]
            
            self.esp_bc_data.humid_ct1_status = response_data['humid_status'][0]
            self.esp_bc_data.humid_ct2_status = response_data['humid_status'][1]
            self.esp_bc_data.humid_ct3_status = response_data['humid_status'][2]
            self.esp_bc_data.humid_ct4_status = response_data['humid_status'][3]
            
            logger.debug(f"ESP-BC: Rods={response_data['rods']}, "
                        f"Thermal={self.esp_bc_data.kw_thermal:.1f}kW, "
                        f"Pumps=[{self.esp_bc_data.pump_primary_speed:.1f}%, "
                        f"{self.esp_bc_data.pump_secondary_speed:.1f}%, "
                        f"{self.esp_bc_data.pump_tertiary_speed:.1f}%]")
            return True
        
        else:
            # === LEGACY JSON PROTOCOL (for fallback/debugging) ===
            command = {
                "cmd": "update",
                "rods": [int(safety), int(shim), int(regulating)],
                "pumps": [int(pump_primary), int(pump_secondary), int(pump_tertiary)],
                "humid_ct": [int(humid_ct1), int(humid_ct2), int(humid_ct3), int(humid_ct4)]
            }
            
            try:
                response = self.esp_bc.send_receive(command, timeout=2.5)
            except Exception as e:
                logger.error(f"Error sending to ESP-BC: {e}")
                return False
            
            if response and response.get("status") == "ok":
                self.esp_bc_data.safety_actual = response.get("rods", [0,0,0])[0]
                self.esp_bc_data.shim_actual = response.get("rods", [0,0,0])[1]
                self.esp_bc_data.regulating_actual = response.get("rods", [0,0,0])[2]
                
                self.esp_bc_data.kw_thermal = response.get("thermal_kw", 0.0)
                self.esp_bc_data.power_level = response.get("power_level", 0.0)
                self.esp_bc_data.state = response.get("state", 0)
                self.esp_bc_data.turbine_speed = response.get("turbine_speed", 0.0)
                
                pump_speeds = response.get("pump_speeds", [0.0, 0.0, 0.0])
                self.esp_bc_data.pump_primary_speed = pump_speeds[0]
                self.esp_bc_data.pump_secondary_speed = pump_speeds[1]
                self.esp_bc_data.pump_tertiary_speed = pump_speeds[2]
                
                humid_status = response.get("humid_status", [0, 0, 0, 0])
                self.esp_bc_data.humid_ct1_status = humid_status[0]
                self.esp_bc_data.humid_ct2_status = humid_status[1]
                self.esp_bc_data.humid_ct3_status = humid_status[2]
                self.esp_bc_data.humid_ct4_status = humid_status[3]
                
                return True
            else:
                logger.warning("ESP-BC: No valid JSON response")
                return False
    
    def update_esp_e(self, thermal_power_kw: float = 0.0, 
                     pump_primary_status: int = 0,
                     pump_secondary_status: int = 0,
                     pump_tertiary_status: int = 0) -> bool:
        """
        Send update to ESP-E using binary protocol (Power Indicator + Water Flow Visualization)
        
        Args:
            thermal_power_kw: Thermal power for LED indicator (0-300000 kW)
            pump_primary_status: Primary pump status (0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN)
            pump_secondary_status: Secondary pump status (0-3)
            pump_tertiary_status: Tertiary pump status (0-3)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.esp_e_enabled or not self.esp_e_connected:
            return False
        
        # Update internal state
        self.esp_e_data.thermal_power_kw = thermal_power_kw
        self.esp_e_data.pump_primary_status = pump_primary_status
        self.esp_e_data.pump_secondary_status = pump_secondary_status
        self.esp_e_data.pump_tertiary_status = pump_tertiary_status
        
        if USE_BINARY_PROTOCOL:
            # === BINARY PROTOCOL ===
            # Encode binary command with pump status
            command_bytes = encode_esp_e_update(
                thermal_kw=thermal_power_kw,
                pump_primary=pump_primary_status,
                pump_secondary=pump_secondary_status,
                pump_tertiary=pump_tertiary_status
            )
            
            # Expected response: [STX][ACK][LEN=8][8 bytes payload][CRC][ETX] = 13 bytes
            expected_len = 13
            
            # Send and receive with retry
            result = self.esp_e.send_receive_binary(command_bytes, expected_len, timeout=1.0)
            
            if result is None:
                logger.debug("ESP-E: Binary communication failed (non-critical)")
                return False
            
            length, msg_type, payload = result
            
            # Decode response
            response_data = decode_esp_e_response(payload)
            
            if response_data is None:
                logger.debug("ESP-E: Failed to decode binary response")
                return False
            
            # Update internal state from response (echo verification)
            self.esp_e_data.power_mwe = response_data['power_mwe']
            self.esp_e_data.pwm = response_data['pwm']
            
            logger.debug(f"ESP-E: Power={self.esp_e_data.power_mwe:.1f} MWe, "
                        f"PWM={self.esp_e_data.pwm}/255, "
                        f"Pumps: P={response_data['pump_primary']} S={response_data['pump_secondary']} T={response_data['pump_tertiary']}")
            return True
        
        else:
            # === LEGACY JSON PROTOCOL (for fallback/debugging) ===
            command = {
                "cmd": "update",
                "thermal_kw": float(thermal_power_kw)
            }
            
            try:
                response = self.esp_e.send_receive(command, timeout=1.0)
            except Exception as e:
                logger.debug(f"Error sending to ESP-E: {e}")
                return False
            
            if response and response.get("status") == "ok":
                self.esp_e_data.power_mwe = response.get("power_mwe", 0.0)
                self.esp_e_data.pwm = response.get("pwm", 0)
                
                logger.debug(f"ESP-E: Power={self.esp_e_data.power_mwe:.1f} MWe, "
                            f"PWM={self.esp_e_data.pwm}/255")
                return True
            
            return False
    
    def get_esp_bc_data(self) -> ESP_BC_Data:
        """Get latest data from ESP-BC"""
        return self.esp_bc_data
    
    def get_esp_e_data(self) -> ESP_E_Data:
        """Get latest data from ESP-E"""
        return self.esp_e_data
    
    def get_health_status(self) -> Dict:
        """
        Get health status of both ESP devices
        
        Returns:
            Dictionary with health information
        """
        return {
            'esp_bc': {
                'connected': self.esp_bc_connected,
                'port': self.esp_bc.port,
                'error_count': self.esp_bc.error_count,
                'last_comm': self.esp_bc.last_comm_time,
                'status': 'OK' if self.esp_bc.error_count < 5 else 'ERROR'
            },
            'esp_e': {
                'connected': self.esp_e_connected,
                'port': self.esp_e.port,
                'error_count': self.esp_e.error_count,
                'last_comm': self.esp_e.last_comm_time,
                'status': 'OK' if self.esp_e.error_count < 5 else 'WARNING'
            }
        }
    
    def close(self):
        """Close all UART connections"""
        logger.info("Closing UART connections...")
        
        # Send safe state before closing
        try:
            if self.esp_bc_connected:
                logger.info("Sending safe state to ESP-BC...")
                self.update_esp_bc(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        except:
            pass
        
        try:
            if self.esp_e_enabled and self.esp_e_connected:
                logger.info("Sending safe state to ESP-E...")
                self.update_esp_e(0.0)
        except:
            pass
        
        # Close connections
        self.esp_bc.disconnect()
        if self.esp_e_enabled:
            self.esp_e.disconnect()
        
        logger.info("✅ UART Master closed")


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("\n" + "="*70)
    print("Testing UART Master - ESP-BC Only")
    print("="*70)
    
    try:
        # Initialize (ESP-E disabled)
        master = UARTMaster(esp_bc_port='/dev/ttyAMA0', esp_e_port=None)
        
        # Wait for ESP to be fully ready
        print("\n⏳ Waiting 1 second for ESP32 to stabilize...")
        time.sleep(1.0)
        
        # Test ESP-BC
        print("\n[TEST] ESP-BC Communication...")
        success = master.update_esp_bc(
            safety=50, shim=60, regulating=70,
            pump_primary=2, pump_secondary=2, pump_tertiary=1,
            humid_ct1=1, humid_ct2=0, humid_ct3=1, humid_ct4=0
        )
        
        if success:
            data = master.get_esp_bc_data()
            print(f"  ✅ Rod positions: {data.safety_actual}, {data.shim_actual}, {data.regulating_actual}")
            print(f"  ✅ Thermal power: {data.kw_thermal} kW")
            print(f"  ✅ Turbine power: {data.power_level}%")
            print(f"  ✅ Turbine speed: {data.turbine_speed}%")
            print(f"  ✅ Pump speeds: Primary={data.pump_primary_speed}%, Secondary={data.pump_secondary_speed}%, Tertiary={data.pump_tertiary_speed}%")
            print(f"  ✅ Turbine state: {data.state} (0=IDLE, 1=STARTING, 2=RUNNING, 3=SHUTDOWN)")
        else:
            print("  ❌ Failed to communicate with ESP-BC")
        
        # Health check
        print("\n[TEST] Health Status:")
        health = master.get_health_status()
        for esp, info in health.items():
            print(f"  {esp.upper()}: {info['status']} (errors: {info['error_count']})")
        
        # Close
        master.close()
        
        print("\n" + "="*70)
        print("✅ Test complete")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
