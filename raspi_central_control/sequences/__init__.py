"""
Sequences module for PLTN Panel Simulator.

Contains:
- SCRAMSequence: Emergency shutdown sequence
- AutoSimulator: Automated startup simulation
"""

from .scram_sequence import SCRAMSequence
from .auto_simulation import AutoSimulator, SimPhase

__all__ = ['SCRAMSequence', 'AutoSimulator', 'SimPhase']
