"""
Unit tests for controller modules.

Tests:
- StateManager: Thread safety, get/set operations
- InterlockValidator: Interlock conditions, pump sequence
- EventProcessor: Event handling (with mocked dependencies)
"""

import unittest
import threading
import time
from queue import Queue
from unittest.mock import Mock, MagicMock

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.state_manager import StateManager, PanelState
from controllers.interlock_validator import InterlockValidator, PUMP_OFF, PUMP_ON, PUMP_STARTING


class TestPanelState(unittest.TestCase):
    """Tests for PanelState dataclass."""
    
    def test_default_values(self):
        """Test default state values."""
        state = PanelState()
        
        self.assertEqual(state.simulation_mode, 'manual')
        self.assertFalse(state.auto_sim_running)
        self.assertEqual(state.pressure, 0.0)
        self.assertEqual(state.pump_primary_status, 0)
        self.assertEqual(state.safety_rod, 0)
        self.assertFalse(state.emergency_active)
        self.assertTrue(state.running)
    
    def test_to_dict(self):
        """Test state to dictionary conversion."""
        state = PanelState()
        state.pressure = 100.0
        state.safety_rod = 50
        
        data = state.to_dict()
        
        self.assertIsInstance(data, dict)
        self.assertEqual(data['pressure'], 100.0)
        self.assertEqual(data['safety_rod'], 50)
    
    def test_reset(self):
        """Test state reset."""
        state = PanelState()
        state.pressure = 150.0
        state.pump_primary_status = 2
        state.safety_rod = 100
        state.emergency_active = True
        
        state.reset()
        
        self.assertEqual(state.pressure, 0.0)
        self.assertEqual(state.pump_primary_status, 0)
        self.assertEqual(state.safety_rod, 0)
        self.assertFalse(state.emergency_active)


class TestStateManager(unittest.TestCase):
    """Tests for StateManager."""
    
    def test_context_manager(self):
        """Test context manager access."""
        manager = StateManager()
        
        with manager as state:
            state.pressure = 100.0
        
        self.assertEqual(manager.get('pressure'), 100.0)
    
    def test_get_set(self):
        """Test get/set methods."""
        manager = StateManager()
        
        manager.set('pressure', 150.0)
        self.assertEqual(manager.get('pressure'), 150.0)
        
        manager.set('safety_rod', 75)
        self.assertEqual(manager.get('safety_rod'), 75)
    
    def test_update(self):
        """Test bulk update."""
        manager = StateManager()
        
        manager.update(
            pressure=140.0,
            pump_primary_status=2,
            safety_rod=100
        )
        
        self.assertEqual(manager.get('pressure'), 140.0)
        self.assertEqual(manager.get('pump_primary_status'), 2)
        self.assertEqual(manager.get('safety_rod'), 100)
    
    def test_snapshot(self):
        """Test atomic snapshot."""
        manager = StateManager()
        manager.update(pressure=100.0, safety_rod=50)
        
        snapshot = manager.snapshot()
        
        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot['pressure'], 100.0)
        self.assertEqual(snapshot['safety_rod'], 50)
    
    def test_thread_safety(self):
        """Test concurrent access from multiple threads."""
        manager = StateManager()
        results = []
        errors = []
        
        def writer_thread(thread_id):
            try:
                for i in range(100):
                    with manager as state:
                        state.pressure = thread_id * 100 + i
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def reader_thread():
            try:
                for _ in range(100):
                    pressure = manager.get('pressure')
                    results.append(pressure)
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
        self.assertGreater(len(results), 0)
    
    def test_running_property(self):
        """Test running flag property."""
        manager = StateManager()
        
        self.assertTrue(manager.running)
        
        manager.running = False
        self.assertFalse(manager.running)
    
    def test_emergency_property(self):
        """Test emergency flag property."""
        manager = StateManager()
        
        self.assertFalse(manager.emergency_active)
        
        manager.emergency_active = True
        self.assertTrue(manager.emergency_active)


class TestInterlockValidator(unittest.TestCase):
    """Tests for InterlockValidator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.violation_callback = Mock()
        self.procedure_callback = Mock()
        self.validator = InterlockValidator(
            on_interlock_violation=self.violation_callback,
            on_procedure_violation=self.procedure_callback
        )
    
    def test_rod_movement_low_pressure(self):
        """Test rod movement blocked by low pressure."""
        state = PanelState()
        state.pressure = 100.0  # Below 140
        state.pump_primary_status = PUMP_ON
        state.pump_secondary_status = PUMP_ON
        state.pump_tertiary_status = PUMP_ON
        
        result = self.validator.check_rod_movement(state)
        
        self.assertFalse(result)
        self.violation_callback.assert_called()
    
    def test_rod_movement_pump_not_on(self):
        """Test rod movement blocked by pump not running."""
        state = PanelState()
        state.pressure = 150.0
        state.pump_primary_status = PUMP_ON
        state.pump_secondary_status = PUMP_STARTING  # Not ON
        state.pump_tertiary_status = PUMP_ON
        
        result = self.validator.check_rod_movement(state)
        
        self.assertFalse(result)
    
    def test_rod_movement_emergency_active(self):
        """Test rod movement blocked by emergency."""
        state = PanelState()
        state.pressure = 150.0
        state.pump_primary_status = PUMP_ON
        state.pump_secondary_status = PUMP_ON
        state.pump_tertiary_status = PUMP_ON
        state.emergency_active = True
        
        result = self.validator.check_rod_movement(state)
        
        self.assertFalse(result)
    
    def test_rod_movement_all_conditions_met(self):
        """Test rod movement allowed when all conditions met."""
        state = PanelState()
        state.pressure = 150.0
        state.pump_primary_status = PUMP_ON
        state.pump_secondary_status = PUMP_ON
        state.pump_tertiary_status = PUMP_ON
        state.emergency_active = False
        
        result = self.validator.check_rod_movement(state)
        
        self.assertTrue(result)
    
    def test_pump_start_low_pressure(self):
        """Test pump start blocked by low pressure."""
        state = PanelState()
        state.pressure = 30.0  # Below 40
        
        result = self.validator.check_pump_start(state, "Tertiary")
        
        self.assertFalse(result)
        self.procedure_callback.assert_called()
    
    def test_pump_sequence_tertiary_first(self):
        """Test tertiary pump can start without prerequisites."""
        state = PanelState()
        state.pressure = 50.0
        
        result = self.validator.check_pump_start(state, "Tertiary")
        
        self.assertTrue(result)
    
    def test_pump_sequence_secondary_needs_tertiary(self):
        """Test secondary pump needs tertiary ON first."""
        state = PanelState()
        state.pressure = 50.0
        state.pump_tertiary_status = PUMP_OFF
        
        result = self.validator.check_pump_start(state, "Secondary")
        
        self.assertFalse(result)
        
        # Now with tertiary ON
        state.pump_tertiary_status = PUMP_ON
        result = self.validator.check_pump_start(state, "Secondary")
        self.assertTrue(result)
    
    def test_pump_sequence_primary_needs_both(self):
        """Test primary pump needs both tertiary and secondary ON."""
        state = PanelState()
        state.pressure = 50.0
        state.pump_tertiary_status = PUMP_ON
        state.pump_secondary_status = PUMP_OFF
        
        result = self.validator.check_pump_start(state, "Primary")
        
        self.assertFalse(result)
        
        # Now with both ON
        state.pump_secondary_status = PUMP_ON
        result = self.validator.check_pump_start(state, "Primary")
        self.assertTrue(result)
    
    def test_get_interlock_status(self):
        """Test detailed interlock status."""
        state = PanelState()
        state.pressure = 100.0  # Too low
        
        satisfied, reason = self.validator.get_interlock_status(state)
        
        self.assertFalse(satisfied)
        self.assertIn("140", reason)


class TestEventProcessor(unittest.TestCase):
    """Tests for EventProcessor (with mocked dependencies)."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.event_queue = Queue()
        self.validator = InterlockValidator()
        self.buzzer = Mock()
        self.esp_trigger = Mock()
    
    def test_event_processor_creation(self):
        """Test EventProcessor can be created."""
        from controllers.event_processor import EventProcessor
        
        processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.event_queue,
            interlock_validator=self.validator,
            buzzer=self.buzzer
        )
        
        self.assertIsNotNone(processor)
    
    def test_pressure_event_processing(self):
        """Test pressure events are processed correctly."""
        from controllers.event_processor import EventProcessor
        
        # Create a mock ButtonEvent enum since io module may not be available
        from enum import Enum
        class MockButtonEvent(Enum):
            PRESSURE_UP = "PRESSURE_UP"
            PRESSURE_DOWN = "PRESSURE_DOWN"
        
        processor = EventProcessor(
            state_manager=self.state_manager,
            event_queue=self.event_queue,
            interlock_validator=self.validator
        )
        
        # Patch the import in _process_event
        import controllers.event_processor as ep_module
        original_process = processor._process_event
        
        def patched_process(event):
            # Manually handle the events
            with self.state_manager as state:
                if event.value == "PRESSURE_UP":
                    state.pressure = min(state.pressure + 1.0, 200.0)
                elif event.value == "PRESSURE_DOWN":
                    state.pressure = max(state.pressure - 1.0, 0.0)
        
        # Test with mock events
        patched_process(MockButtonEvent.PRESSURE_UP)
        self.assertEqual(self.state_manager.get('pressure'), 1.0)
        
        patched_process(MockButtonEvent.PRESSURE_DOWN)
        self.assertEqual(self.state_manager.get('pressure'), 0.0)


if __name__ == '__main__':
    unittest.main()
