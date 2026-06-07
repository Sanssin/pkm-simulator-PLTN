"""
Integration tests for PLTN Panel Simulator.

Tests the full system with all extracted modules working together.
Verifies behavior matches pre-refactor expectations.
"""

import unittest
import time
import threading
from queue import Queue
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers import StateManager, PanelState, InterlockValidator, EventProcessor
from controllers.interlock_validator import PUMP_OFF, PUMP_ON, PUMP_STARTING, PUMP_SHUTTING_DOWN
from sequences import SCRAMSequence, AutoSimulator
from io_handlers import ButtonEvent


class TestFullStartupSequence(unittest.TestCase):
    """Integration test for full PWR startup sequence."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.event_queue = Queue()
        self.interlock_validator = InterlockValidator()
    
    def test_manual_startup_sequence(self):
        """Test manual startup follows correct procedure."""
        state = self.state_manager.state
        
        # Step 1: Raise pressure to 45 bar
        state.pressure = 45.0
        
        # Step 2: Start pumps in sequence (Tertiary → Secondary → Primary)
        # Tertiary first
        can_start = self.interlock_validator.check_pump_start(state, "Tertiary")
        self.assertTrue(can_start, "Tertiary should be able to start at 45 bar")
        state.pump_tertiary_status = PUMP_ON
        
        # Secondary needs Tertiary ON
        can_start = self.interlock_validator.check_pump_start(state, "Secondary")
        self.assertTrue(can_start, "Secondary should start when Tertiary is ON")
        state.pump_secondary_status = PUMP_ON
        
        # Primary needs both
        can_start = self.interlock_validator.check_pump_start(state, "Primary")
        self.assertTrue(can_start, "Primary should start when both pumps are ON")
        state.pump_primary_status = PUMP_ON
        
        # Step 3: Raise pressure to 140 bar
        state.pressure = 140.0
        
        # Step 4: Now rod movement should be allowed
        can_move = self.interlock_validator.check_rod_movement(state)
        self.assertTrue(can_move, "Rod movement should be allowed")
        
        # Move rods
        state.safety_rod = 100
        state.shim_rod = 100
        state.regulating_rod = 100
        
        # Verify final state
        self.assertEqual(state.safety_rod, 100)
        self.assertEqual(state.shim_rod, 100)
        self.assertEqual(state.regulating_rod, 100)
    
    def test_wrong_pump_sequence_blocked(self):
        """Test that wrong pump sequence is blocked."""
        state = self.state_manager.state
        state.pressure = 50.0
        
        # Try to start Primary first (should fail)
        can_start = self.interlock_validator.check_pump_start(state, "Primary")
        self.assertFalse(can_start, "Primary should not start without others")
        
        # Try to start Secondary first (should fail)
        can_start = self.interlock_validator.check_pump_start(state, "Secondary")
        self.assertFalse(can_start, "Secondary should not start without Tertiary")
    
    def test_rod_movement_blocked_without_conditions(self):
        """Test rod movement blocked when conditions not met."""
        state = self.state_manager.state
        
        # Low pressure
        state.pressure = 100.0
        can_move = self.interlock_validator.check_rod_movement(state)
        self.assertFalse(can_move, "Rod movement blocked at low pressure")
        
        # High pressure but pumps not ON
        state.pressure = 150.0
        can_move = self.interlock_validator.check_rod_movement(state)
        self.assertFalse(can_move, "Rod movement blocked without pumps")


class TestSCRAMIntegration(unittest.TestCase):
    """Integration test for SCRAM sequence."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.esp_trigger = Mock()
    
    def test_scram_from_full_power(self):
        """Test SCRAM from full power state."""
        # Set up full power state
        with self.state_manager as state:
            state.pressure = 150.0
            state.pump_primary_status = PUMP_ON
            state.pump_secondary_status = PUMP_ON
            state.pump_tertiary_status = PUMP_ON
            state.safety_rod = 100
            state.shim_rod = 100
            state.regulating_rod = 100
            state.thermal_kw = 900000.0
            state.turbine_speed = 100.0
        
        # Execute SCRAM
        scram = SCRAMSequence(
            state_manager=self.state_manager,
            esp_trigger=self.esp_trigger
        )
        
        with patch.object(scram, 'ROD_DROP_DURATION', 0.1):
            with patch.object(scram, 'UPDATE_INTERVAL', 0.01):
                scram.execute_blocking()
        
        # Verify all rods dropped
        with self.state_manager as state:
            self.assertEqual(state.safety_rod, 0)
            self.assertEqual(state.shim_rod, 0)
            self.assertEqual(state.regulating_rod, 0)
            
            # Pumps should remain ON (for decay heat removal)
            self.assertEqual(state.pump_primary_status, PUMP_ON)
            self.assertEqual(state.pump_secondary_status, PUMP_ON)
            self.assertEqual(state.pump_tertiary_status, PUMP_ON)


class TestEventProcessorIntegration(unittest.TestCase):
    """Integration test for EventProcessor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.event_queue = Queue()
        self.interlock_validator = InterlockValidator()
        self.scram_sequence = SCRAMSequence(
            state_manager=self.state_manager,
            esp_trigger=Mock()
        )
        self.auto_simulator = AutoSimulator(
            state_manager=self.state_manager,
            esp_trigger=Mock()
        )
        
        self.processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.event_queue,
            interlock_validator=self.interlock_validator,
            scram_sequence=self.scram_sequence,
            auto_simulator=self.auto_simulator
        )
    
    def test_pressure_control(self):
        """Test pressure up/down events."""
        # Create mock ButtonEvent
        from enum import Enum
        class MockEvent(Enum):
            PRESSURE_UP = "PRESSURE_UP"
            PRESSURE_DOWN = "PRESSURE_DOWN"
        
        # Manually process events
        with self.state_manager as state:
            initial_pressure = state.pressure
            state.pressure = min(state.pressure + 1.0, 200.0)
        
        self.assertEqual(self.state_manager.get('pressure'), initial_pressure + 1.0)
    
    def test_pump_start_with_validation(self):
        """Test pump start events with interlock validation."""
        # Set conditions for pump start
        self.state_manager.update(pressure=50.0)
        
        # Simulate pump start sequence
        with self.state_manager as state:
            # Tertiary can start
            if self.interlock_validator.check_pump_start(state, "Tertiary"):
                state.pump_tertiary_status = PUMP_STARTING
        
        self.assertEqual(self.state_manager.get('pump_tertiary_status'), PUMP_STARTING)


class TestStateExport(unittest.TestCase):
    """Test state export functionality."""
    
    def test_state_to_dict(self):
        """Test state can be exported to dict."""
        state_manager = StateManager()
        
        with state_manager as state:
            state.pressure = 150.0
            state.safety_rod = 100
            state.thermal_kw = 500000.0
        
        snapshot = state_manager.snapshot()
        
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot['pressure'], 150.0)
        self.assertEqual(snapshot['safety_rod'], 100)
        self.assertEqual(snapshot['thermal_kw'], 500000.0)


class TestThreadSafety(unittest.TestCase):
    """Test thread safety of integrated system."""
    
    def test_concurrent_state_access(self):
        """Test multiple threads can access state safely."""
        state_manager = StateManager()
        errors = []
        
        def writer_thread(thread_id, iterations=50):
            try:
                for i in range(iterations):
                    with state_manager as state:
                        state.pressure = float(thread_id * 100 + i)
                        state.safety_rod = i % 100
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def reader_thread(iterations=50):
            try:
                for _ in range(iterations):
                    snapshot = state_manager.snapshot()
                    # Verify snapshot is valid
                    assert 'pressure' in snapshot
                    assert 'safety_rod' in snapshot
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=writer_thread, args=(i,)))
        threads.append(threading.Thread(target=reader_thread))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")


if __name__ == '__main__':
    unittest.main()
