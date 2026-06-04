"""
StateManager - Thread-safe state management for PLTN Panel Simulator.

This module provides:
- PanelState: Dataclass containing all simulator state
- StateManager: Thread-safe wrapper for state access

Thread Safety:
- All state modifications should go through StateManager
- Uses threading.RLock for reentrant locking
- Supports context manager pattern for explicit locking
"""

import threading
import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PanelState:
    """
    Panel control system state.
    
    Contains all runtime state for the PLTN simulator including:
    - Simulation mode and auto-sim progress
    - Pressure and pump status
    - Rod positions
    - Thermal power and turbine speed
    - Humidifier commands
    - Emergency and interlock flags
    
    Pump status codes:
        0 = OFF
        1 = STARTING
        2 = ON
        3 = SHUTTING_DOWN
    """
    # Simulation mode: 'manual' atau 'auto'
    simulation_mode: str = 'manual'
    auto_sim_running: bool = False
    auto_sim_step: int = 0
    auto_sim_phase: str = ""
    
    # Pressure control (bar)
    pressure: float = 0.0
    
    # Pump status (0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN)
    pump_primary_status: int = 0
    pump_secondary_status: int = 0
    pump_tertiary_status: int = 0
    
    # Pump transition timers (untuk tracking waktu startup/shutdown)
    pump_primary_transition_start: float = 0.0
    pump_secondary_transition_start: float = 0.0
    pump_tertiary_transition_start: float = 0.0
    
    # Rod positions (0-100%)
    safety_rod: int = 0
    shim_rod: int = 0
    regulating_rod: int = 0
    
    # Thermal power from ESP-BC (kW)
    thermal_kw: float = 0.0
    
    # Turbine speed from ESP-BC (%)
    turbine_speed: float = 0.0
    
    # Humidifier commands (Cooling Tower only - 4 relays)
    humid_ct1_cmd: int = 0
    humid_ct2_cmd: int = 0
    humid_ct3_cmd: int = 0
    humid_ct4_cmd: int = 0
    
    # Emergency state
    emergency_active: bool = False
    
    # Interlock satisfied flag
    interlock_satisfied: bool = False
    
    # System running flag
    running: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for JSON export."""
        return asdict(self)
    
    def reset(self) -> None:
        """Reset state to initial values (except running flag)."""
        self.simulation_mode = 'manual'
        self.auto_sim_running = False
        self.auto_sim_step = 0
        self.auto_sim_phase = ""
        self.pressure = 0.0
        self.pump_primary_status = 0
        self.pump_secondary_status = 0
        self.pump_tertiary_status = 0
        self.pump_primary_transition_start = 0.0
        self.pump_secondary_transition_start = 0.0
        self.pump_tertiary_transition_start = 0.0
        self.safety_rod = 0
        self.shim_rod = 0
        self.regulating_rod = 0
        self.thermal_kw = 0.0
        self.turbine_speed = 0.0
        self.humid_ct1_cmd = 0
        self.humid_ct2_cmd = 0
        self.humid_ct3_cmd = 0
        self.humid_ct4_cmd = 0
        self.emergency_active = False
        self.interlock_satisfied = False


class StateManager:
    """
    Thread-safe wrapper for PanelState.
    
    Provides:
    - Context manager for explicit locking
    - Atomic get/set methods for individual fields
    - Bulk update and snapshot methods
    
    Usage:
        # Context manager (recommended for multiple operations)
        with state_manager as state:
            state.pressure = 140.0
            state.pump_primary_status = 2
        
        # Single field access
        pressure = state_manager.get('pressure')
        state_manager.set('pressure', 150.0)
        
        # Atomic snapshot
        snapshot = state_manager.snapshot()
    """
    
    def __init__(self, state: Optional[PanelState] = None):
        """
        Initialize StateManager.
        
        Args:
            state: Optional existing PanelState. Creates new if None.
        """
        self._state = state if state is not None else PanelState()
        self._lock = threading.RLock()  # RLock allows reentrant locking
    
    @property
    def lock(self) -> threading.RLock:
        """Access to the underlying lock for advanced usage."""
        return self._lock
    
    @property
    def state(self) -> PanelState:
        """
        Direct access to state (use with lock).
        
        WARNING: For thread safety, always use with lock:
            with state_manager.lock:
                state_manager.state.pressure = 100.0
        
        Or use the context manager:
            with state_manager as state:
                state.pressure = 100.0
        """
        return self._state
    
    def __enter__(self) -> PanelState:
        """Enter context manager, acquiring lock."""
        self._lock.acquire()
        return self._state
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, releasing lock."""
        self._lock.release()
    
    def get(self, field: str) -> Any:
        """
        Thread-safe get for a single field.
        
        Args:
            field: Name of the field to get
            
        Returns:
            Value of the field
            
        Raises:
            AttributeError: If field doesn't exist
        """
        with self._lock:
            return getattr(self._state, field)
    
    def set(self, field: str, value: Any) -> None:
        """
        Thread-safe set for a single field.
        
        Args:
            field: Name of the field to set
            value: New value for the field
            
        Raises:
            AttributeError: If field doesn't exist
        """
        with self._lock:
            setattr(self._state, field, value)
    
    def update(self, **kwargs) -> None:
        """
        Thread-safe bulk update of multiple fields.
        
        Args:
            **kwargs: Field names and values to update
            
        Example:
            state_manager.update(pressure=140.0, pump_primary_status=2)
        """
        with self._lock:
            for field, value in kwargs.items():
                setattr(self._state, field, value)
    
    def snapshot(self) -> Dict[str, Any]:
        """
        Get atomic snapshot of entire state as dictionary.
        
        Returns:
            Dictionary copy of current state
        """
        with self._lock:
            return self._state.to_dict()
    
    def reset(self) -> None:
        """Thread-safe reset of state to initial values."""
        with self._lock:
            self._state.reset()
    
    @property
    def running(self) -> bool:
        """Thread-safe access to running flag."""
        with self._lock:
            return self._state.running
    
    @running.setter
    def running(self, value: bool) -> None:
        """Thread-safe set for running flag."""
        with self._lock:
            self._state.running = value
    
    @property
    def emergency_active(self) -> bool:
        """Thread-safe access to emergency flag."""
        with self._lock:
            return self._state.emergency_active
    
    @emergency_active.setter
    def emergency_active(self, value: bool) -> None:
        """Thread-safe set for emergency flag."""
        with self._lock:
            self._state.emergency_active = value
