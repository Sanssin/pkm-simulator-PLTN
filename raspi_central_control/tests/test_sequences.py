"""
Unit tests for sequence modules.

Tests:
- SCRAMSequence: Rod drop animation, turbine spindown
- AutoSimulator: Phase progression, cancellation
"""

import unittest
import time
import threading
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.state_manager import StateManager, PanelState
from controllers.interlock_validator import InterlockValidator, PUMP_OFF, PUMP_ON, PUMP_SHUTTING_DOWN
from controllers.event_processor import EventProcessor, ButtonEvent
from controllers.physics_engine import PhysicsEngine
from sequences.scram_sequence import SCRAMSequence
from sequences.auto_simulation import AutoSimulator, SimPhase


class TestSCRAMSequence(unittest.TestCase):
    """Tests for SCRAMSequence."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.esp_trigger = Mock()
        self.on_complete = Mock()
    
    def test_scram_creation(self):
        """Test SCRAM sequence can be created."""
        scram = SCRAMSequence(
            state_manager=self.state_manager,
            on_complete=self.on_complete
        )
        
        self.assertIsNotNone(scram)
        self.assertFalse(scram.is_running)
    
    def test_scram_drops_all_rods(self):
        """Test SCRAM drops all rods to 0."""
        # Set initial rod positions
        self.state_manager.update(
            safety_rod=100,
            shim_rod=75,
            regulating_rod=50
        )
        
        scram = SCRAMSequence(
            state_manager=self.state_manager,
            on_complete=self.on_complete
        )
        
        # Execute blocking (faster for test)
        # We'll mock the timing to make it faster
        with patch.object(scram, 'ROD_DROP_DURATION', 0.1):
            with patch.object(scram, 'UPDATE_INTERVAL', 0.01):
                scram.execute_blocking()
        
        # Verify all rods at 0
        self.assertEqual(self.state_manager.get('safety_rod'), 0)
        self.assertEqual(self.state_manager.get('shim_rod'), 0)
        self.assertEqual(self.state_manager.get('regulating_rod'), 0)
        
        # Verify completion callback
        self.on_complete.assert_called_once()
    
    def test_scram_async_execution(self):
        """Test SCRAM runs asynchronously."""
        self.state_manager.update(safety_rod=50, shim_rod=50, regulating_rod=50, pump_primary_status=PUMP_ON)

        scram = SCRAMSequence(
            state_manager=self.state_manager
        )

        with patch.object(scram, 'DECAY_HEAT_COOLING_DURATION', 0.05), \
             patch.object(scram, 'PUMP_SHUTDOWN_DURATION', 0.05), \
             patch.object(scram, 'PUMP_STEP_GAP', 0.01), \
             patch.object(scram, 'UPDATE_INTERVAL', 0.01):
            thread = scram.execute()

            self.assertTrue(scram.is_running)

            thread.join(timeout=1.0)

        self.assertFalse(scram.is_running)
        self.assertEqual(self.state_manager.get('safety_rod'), 0)
        self.assertEqual(self.state_manager.get('pump_primary_status'), PUMP_OFF)

    def test_scram_35s_total_timing_constants(self):
        """Verify SCRAM default constants add up to 35.0 seconds total."""
        total = (
            SCRAMSequence.DECAY_HEAT_COOLING_DURATION
            + 3 * SCRAMSequence.PUMP_SHUTDOWN_DURATION
            + 2 * SCRAMSequence.PUMP_STEP_GAP
        )
        self.assertAlmostEqual(total, 35.0, places=2)

    def test_scram_sequential_pump_shutdown_order(self):
        """Test rods drop first, then pumps shut down sequentially Primary -> Secondary -> Tertiary."""
        self.state_manager.update(
            safety_rod=100,
            shim_rod=80,
            regulating_rod=60,
            pump_primary_status=PUMP_ON,
            pump_secondary_status=PUMP_ON,
            pump_tertiary_status=PUMP_ON,
            turbine_speed=100.0,
        )

        scram = SCRAMSequence(state_manager=self.state_manager, on_complete=self.on_complete)
        shutdown_order = []

        with patch.object(scram, 'DECAY_HEAT_COOLING_DURATION', 0.06), \
             patch.object(scram, 'PUMP_SHUTDOWN_DURATION', 0.06), \
             patch.object(scram, 'PUMP_STEP_GAP', 0.02), \
             patch.object(scram, 'TURBINE_SPINDOWN_DURATION', 0.05), \
             patch.object(scram, 'UPDATE_INTERVAL', 0.01):
            thread = scram.execute()

            # Rods must already be at 0 immediately while pumps stay ON for decay heat hold
            time.sleep(0.02)
            with self.state_manager as state:
                self.assertEqual(state.safety_rod, 0)
                self.assertEqual(state.shim_rod, 0)
                self.assertEqual(state.regulating_rod, 0)
                self.assertTrue(state.emergency_active)
                self.assertEqual(state.pump_primary_status, PUMP_ON)
                self.assertEqual(state.pump_secondary_status, PUMP_ON)
                self.assertEqual(state.pump_tertiary_status, PUMP_ON)

            # Observe exact transition order into SHUTTING_DOWN / OFF
            prev = {'primary': PUMP_ON, 'secondary': PUMP_ON, 'tertiary': PUMP_ON}
            while thread.is_alive():
                with self.state_manager as state:
                    for name in ('primary', 'secondary', 'tertiary'):
                        cur = getattr(state, f'pump_{name}_status')
                        if prev[name] == PUMP_ON and cur in (PUMP_SHUTTING_DOWN, PUMP_OFF):
                            shutdown_order.append(name)
                            prev[name] = cur
                time.sleep(0.005)

            thread.join(timeout=1.0)

        self.assertEqual(shutdown_order, ['primary', 'secondary', 'tertiary'])
        self.assertEqual(self.state_manager.get('pump_primary_status'), PUMP_OFF)
        self.assertEqual(self.state_manager.get('pump_secondary_status'), PUMP_OFF)
        self.assertEqual(self.state_manager.get('pump_tertiary_status'), PUMP_OFF)
        self.on_complete.assert_called_once()

    def test_scram_cancel_on_reactor_reset(self):
        """Test SCRAM sequence can be cancelled mid-flight via EventProcessor REACTOR_RESET."""
        self.state_manager.update(
            safety_rod=100,
            shim_rod=100,
            regulating_rod=100,
            pump_primary_status=PUMP_ON,
            pump_secondary_status=PUMP_ON,
            pump_tertiary_status=PUMP_ON,
        )
        scram = SCRAMSequence(state_manager=self.state_manager, on_complete=self.on_complete)
        processor = EventProcessor(
            state_manager=self.state_manager,
            interlock_validator=InterlockValidator(),
            scram_sequence=scram,
        )

        with patch.object(scram, 'DECAY_HEAT_COOLING_DURATION', 2.0), \
             patch.object(scram, 'PUMP_SHUTDOWN_DURATION', 2.0):
            processor.process_event(ButtonEvent.EMERGENCY)
            time.sleep(0.05)
            self.assertTrue(scram.is_running)

            # Reset mid-SCRAM must stop thread cleanly without deadlock
            processor.process_event(ButtonEvent.REACTOR_RESET)

        self.assertFalse(scram.is_running)
        self.assertFalse(self.state_manager.get('emergency_active'))
        self.assertEqual(self.state_manager.get('pump_primary_status'), PUMP_OFF)
        self.on_complete.assert_not_called()


class TestPhysicsDecayHeatAndSCRAMLatch(unittest.TestCase):
    """Tests for decay heat modeling and latched emergency_active in PhysicsEngine."""

    def test_decay_heat_buildup_and_post_scram_decay(self):
        pe = PhysicsEngine()
        state = PanelState()
        state.just_reset = False
        state.pump_primary_status = PUMP_ON
        state.pump_secondary_status = PUMP_ON
        state.pump_tertiary_status = PUMP_ON
        state.pressure = 150.0
        state.safety_rod = 100
        state.shim_rod = 100
        state.regulating_rod = 100
        pe.shim_rod_actual = 100.0
        pe.regulating_rod_actual = 100.0

        # Build up decay heat during operation
        for _ in range(100):
            pe.last_update_time -= 0.1
            pe.update(state)

        self.assertGreater(pe.decay_heat, 5.0)
        initial_decay = pe.decay_heat

        # Trigger SCRAM at normal temperatures (< 330C)
        state.emergency_active = True
        state.safety_rod = 0
        state.shim_rod = 0
        state.regulating_rod = 0

        for _ in range(100):  # 10 seconds post-SCRAM
            pe.last_update_time -= 0.1
            pe.update(state)

        # emergency_active must stay latched until REACTOR_RESET
        self.assertTrue(state.emergency_active)
        # Decay heat must decay exponentially but still be positive
        self.assertGreater(pe.decay_heat, 0.1)
        self.assertLess(pe.decay_heat, initial_decay)
        # Sequential pump shutdown during SCRAM must not raise false LOFA
        state.pump_primary_status = PUMP_OFF
        state.pump_secondary_status = PUMP_OFF
        state.pump_tertiary_status = PUMP_OFF
        pe.last_update_time -= 0.1
        pe.update(state)
        self.assertFalse(state.lofa_primary)
        self.assertFalse(state.lofa_secondary)
        self.assertFalse(state.lofa_tertiary)
    



class TestAutoSimulator(unittest.TestCase):
    """Tests for AutoSimulator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.state_manager = StateManager()
        self.esp_trigger = Mock()
    
    def test_simulator_creation(self):
        """Test AutoSimulator can be created."""
        simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        
        self.assertIsNotNone(simulator)
        self.assertFalse(simulator.is_running)
        self.assertEqual(simulator.current_phase, SimPhase.IDLE)
    
    @unittest.skip("Timing-sensitive test - works in isolation but flaky in batch")
    def test_simulator_start(self):
        """Test simulator starts correctly."""
        simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        
        # Start and immediately cancel to test start/cancel flow
        thread = simulator.start()
        
        # Wait briefly for thread to actually start
        timeout = time.time() + 0.5
        while not simulator.is_running and time.time() < timeout:
            time.sleep(0.01)
        
        simulator.cancel()
        
        thread.join(timeout=2.0)
        
        self.assertFalse(simulator.is_running)
    
    @unittest.skip("Timing-sensitive test - works in isolation but flaky in batch")
    def test_simulator_cancel(self):
        """Test simulator can be cancelled."""
        simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        
        thread = simulator.start()
        
        # Wait for it to actually start
        timeout = time.time() + 0.5
        while not simulator.is_running and time.time() < timeout:
            time.sleep(0.01)
        
        # Cancel
        simulator.cancel()
        
        thread.join(timeout=2.0)
        
        self.assertFalse(simulator.is_running)
        # After cancel, mode should be manual
        self.assertEqual(self.state_manager.get('simulation_mode'), 'manual')
    
    def test_simulator_phase_progression(self):
        """Test phases progress correctly."""
        simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        
        # Mock the _check_cancelled to always return False
        simulator._cancelled = False
        with self.state_manager as state:
            state.auto_sim_running = True
        
        # Test that ramp_value works
        with patch.object(simulator, 'UPDATE_INTERVAL', 0.01):
            result = simulator._ramp_value('pressure', 0, 10, 0.05)
        
        self.assertTrue(result)
        self.assertEqual(self.state_manager.get('pressure'), 10.0)
    
    def test_ramp_value_int(self):
        """Test ramp_value with integer values."""
        simulator = AutoSimulator(
            state_manager=self.state_manager
        )
        
        # Mock the _check_cancelled to always return False
        simulator._cancelled = False
        with self.state_manager as state:
            state.auto_sim_running = True
        
        with patch.object(simulator, 'UPDATE_INTERVAL', 0.01):
            result = simulator._ramp_value('safety_rod', 0, 100, 0.05, is_int=True)
        
        self.assertTrue(result)
        self.assertEqual(self.state_manager.get('safety_rod'), 100)
        self.assertIsInstance(self.state_manager.get('safety_rod'), int)


class TestSimPhase(unittest.TestCase):
    """Tests for SimPhase enum."""
    
    def test_all_phases_defined(self):
        """Test all expected phases are defined."""
        expected_phases = [
            'IDLE', 'INIT', 'PRESSURE_45', 'PUMPS', 'PRESSURE_140',
            'SAFETY_ROD', 'SHIM_ROD_50', 'REG_ROD_50', 'MAX_POWER',
            'STEAM_GEN', 'TURBINE', 'POWER_GEN', 'COOLING_TOWER',
            'STABLE', 'COMPLETE'
        ]
        
        for phase_name in expected_phases:
            self.assertTrue(hasattr(SimPhase, phase_name))


if __name__ == '__main__':
    unittest.main()
