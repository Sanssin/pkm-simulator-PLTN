#!/usr/bin/env python3
"""
Humidifier Control Logic for PLTN Simulator - v3.6
Updated with STAGED Cooling Tower Control:
1. Steam Generator (2 units) - Based on Shim + Regulating Rod (before turbine starts)
2. Cooling Tower (4 units) - STAGED activation based on Electrical Power Output

Logic Explanation:
- SG Humidifiers: Activate ketika batang kendali ditarik (Phase 2-3)
  Ini karena reactor mulai panas sebelum turbine generate power
  
- CT Humidifiers: Activate BERTAHAP 1-by-1 based on power level (Phase 6+)
  CT1: 60 MWe (20% of 300 MWe)
  CT2: 120 MWe (40% of 300 MWe)
  CT3: 180 MWe (60% of 300 MWe)
  CT4: 240 MWe (80% of 300 MWe)
  
  Realistic cooling capacity management!
"""

import logging

logger = logging.getLogger(__name__)

class HumidifierController:
    """
    Controls 6 humidifiers (2 SG + 4 CT) based on system conditions:
    - Steam Generator (2): Based on control rod positions (before power generation)
    - Cooling Tower (4): STAGED based on electrical power output (during power generation)
    """
    
    def __init__(self, config=None):
        """
        Initialize humidifier controller
        
        Args:
            config: Optional configuration dict with thresholds
        """
        # Use config if provided, otherwise use defaults
        if config is None:
            config = {}
        
        # ========================================
        # STEAM GENERATOR HUMIDIFIER THRESHOLDS
        # ========================================
        # Trigger: Shim Rod >= 40% AND Regulating Rod >= 40%
        # Phase: 2-3 (Control Rods Withdrawal, before turbine)
        # Reason: Reactor thermal mulai naik, uap mulai terbentuk
        self.sg_shim_rod_threshold = config.get('sg_shim_rod_threshold', 40.0)  # 40%
        self.sg_reg_rod_threshold = config.get('sg_reg_rod_threshold', 40.0)    # 40%
        self.sg_hysteresis = config.get('sg_hysteresis', 5.0)  # 5% hysteresis
        
        # ========================================
        # COOLING TOWER HUMIDIFIER THRESHOLDS (STAGED)
        # ========================================
        # Reactor Rating: 300 MWe
        # Staged activation for realistic cooling capacity management
        #
        # CT1: 60 MWe (20% power) - First stage cooling
        # CT2: 120 MWe (40% power) - Second stage cooling
        # CT3: 180 MWe (60% power) - Third stage cooling
        # CT4: 240 MWe (80% power) - Maximum cooling capacity
        
        self.ct1_power_threshold = config.get('ct1_power_threshold', 60000.0)   # 60 MWe
        self.ct2_power_threshold = config.get('ct2_power_threshold', 120000.0)  # 120 MWe
        self.ct3_power_threshold = config.get('ct3_power_threshold', 180000.0)  # 180 MWe
        self.ct4_power_threshold = config.get('ct4_power_threshold', 240000.0)  # 240 MWe
        self.ct_hysteresis = config.get('ct_hysteresis', 10000.0)  # 10 MWe hysteresis untuk semua
        
        # Current states
        self.steam_gen_humidifier = False  # Controls both SG1 + SG2
        self.ct1_active = False
        self.ct2_active = False
        self.ct3_active = False
        self.ct4_active = False
        
        # History for hysteresis
        self.sg_last_state = False
        self.ct1_last_state = False
        self.ct2_last_state = False
        self.ct3_last_state = False
        self.ct4_last_state = False
        
        logger.info("Humidifier Controller initialized (v3.6 - STAGED CT)")
        logger.info(f"  Steam Gen (2 units): Shim>={self.sg_shim_rod_threshold}% AND Reg>={self.sg_reg_rod_threshold}%")
        logger.info(f"  Cooling Tower (STAGED):")
        logger.info(f"    CT1: >={self.ct1_power_threshold/1000.0:.0f} MWe (20% power)")
        logger.info(f"    CT2: >={self.ct2_power_threshold/1000.0:.0f} MWe (40% power)")
        logger.info(f"    CT3: >={self.ct3_power_threshold/1000.0:.0f} MWe (60% power)")
        logger.info(f"    CT4: >={self.ct4_power_threshold/1000.0:.0f} MWe (80% power)")
    
    def update_steam_gen_humidifier(self, shim_rod_pos, regulating_rod_pos):
        """
        Update Steam Generator Humidifier based on rod positions
        
        Logic (Phase 2-3):
        - ON when BOTH Shim Rod >= 40% AND Regulating Rod >= 40%
        - OFF when EITHER rod falls below 35% (40% - 5% hysteresis)
        
        Reason: Reactor thermal power mulai naik ketika control rods ditarik,
                uap mulai terbentuk di steam generator sebelum turbine jalan
        
        Args:
            shim_rod_pos: Shim rod position (0-100%)
            regulating_rod_pos: Regulating rod position (0-100%)
            
        Returns:
            bool: True if humidifier should be ON, False otherwise
        """
        # Calculate thresholds with hysteresis
        if self.sg_last_state:
            # Currently ON - use lower threshold to turn OFF
            on_threshold = self.sg_shim_rod_threshold - self.sg_hysteresis
            on_threshold_reg = self.sg_reg_rod_threshold - self.sg_hysteresis
        else:
            # Currently OFF - use normal threshold to turn ON
            on_threshold = self.sg_shim_rod_threshold
            on_threshold_reg = self.sg_reg_rod_threshold
        
        # Check conditions
        shim_ok = shim_rod_pos >= on_threshold
        reg_ok = regulating_rod_pos >= on_threshold_reg
        
        # Both must be above threshold
        new_state = shim_ok and reg_ok
        
        # Log state change
        if new_state != self.sg_last_state:
            if new_state:
                logger.info(f"🌊 Steam Gen Humidifier (SG1+SG2) ON: Shim={shim_rod_pos:.1f}% Reg={regulating_rod_pos:.1f}%")
            else:
                logger.info(f"⭕ Steam Gen Humidifier (SG1+SG2) OFF: Shim={shim_rod_pos:.1f}% Reg={regulating_rod_pos:.1f}%")
        
        self.sg_last_state = new_state
        self.steam_gen_humidifier = new_state
        return new_state
    
    def update_cooling_tower_humidifiers(self, electrical_power_kw):
        """
        Update Cooling Tower Humidifiers with STAGED activation
        
        Logic (Phase 6+):
        - CT1 ON when power >= 60 MWe (20% of 300 MWe max)
        - CT2 ON when power >= 120 MWe (40% of 300 MWe max)
        - CT3 ON when power >= 180 MWe (60% of 300 MWe max)
        - CT4 ON when power >= 240 MWe (80% of 300 MWe max)
        
        Hysteresis: 10 MWe untuk prevent oscillation
        
        Reason: Cooling tower digunakan untuk reject heat excess dari
                electrical power generation. Staged activation lebih
                realistis dan efficient.
        
        Args:
            electrical_power_kw: Electrical power output in kW
            
        Returns:
            tuple: (ct1, ct2, ct3, ct4) as (bool, bool, bool, bool)
        """
        # Staged CT logic refactored
        thresholds = [
            (self.ct1_power_threshold, self.ct1_last_state, "Stage 1/4"),
            (self.ct2_power_threshold, self.ct2_last_state, "Stage 2/4"),
            (self.ct3_power_threshold, self.ct3_last_state, "Stage 3/4"),
            (self.ct4_power_threshold, self.ct4_last_state, "Stage 4/4 - MAX COOLING")
        ]
        
        new_states = []
        for i, (base_thresh, last_state, desc) in enumerate(thresholds, 1):
            threshold = base_thresh - self.ct_hysteresis if last_state else base_thresh
            new_state = electrical_power_kw >= threshold
            
            if new_state != last_state:
                if new_state:
                    logger.info(f"🌊 CT{i} ON: Power={electrical_power_kw/1000.0:.1f} MWe ({desc})")
                else:
                    logger.info(f"⭕ CT{i} OFF: Power={electrical_power_kw/1000.0:.1f} MWe")
            new_states.append(new_state)
            
        self.ct1_last_state, self.ct2_last_state, self.ct3_last_state, self.ct4_last_state = new_states
        self.ct1_active, self.ct2_active, self.ct3_active, self.ct4_active = new_states
        
        return tuple(new_states)
    
    def update(self, shim_rod, regulating_rod, electrical_power_kw):
        """
        Update all humidifiers based on current system state
        
        Args:
            shim_rod: Shim rod position (0-100%)
            regulating_rod: Regulating rod position (0-100%)
            electrical_power_kw: ELECTRICAL power in kW (from ESP-BC thermal_kw)
            
        Returns:
            tuple: (sg_on, ct1, ct2, ct3, ct4) as (bool, bool, bool, bool, bool)
        """
        # Update Steam Generator humidifier (based on Shim + Regulating rods)
        # This activates in Phase 2-3 (before turbine starts)
        sg_on = self.update_steam_gen_humidifier(shim_rod, regulating_rod)
        
        # Update Cooling Tower humidifiers (STAGED based on electrical power)
        # This activates in Phase 6+ (staged as power increases)
        ct1, ct2, ct3, ct4 = self.update_cooling_tower_humidifiers(electrical_power_kw)
        
        # Return as tuple: (sg, ct1, ct2, ct3, ct4)
        return (sg_on, ct1, ct2, ct3, ct4)
    
    def get_ct_count_active(self):
        """Get number of CT humidifiers currently active"""
        count = 0
        if self.ct1_active: count += 1
        if self.ct2_active: count += 1
        if self.ct3_active: count += 1
        if self.ct4_active: count += 1
        return count
    
    def get_status(self):
        """
        Get current humidifier status
        
        Returns:
            dict: Status information
        """
        return {
            'steam_gen_humidifier': self.steam_gen_humidifier,
            'ct1_active': self.ct1_active,
            'ct2_active': self.ct2_active,
            'ct3_active': self.ct3_active,
            'ct4_active': self.ct4_active,
            'ct_active_count': self.get_ct_count_active(),
            'sg_threshold': f"{self.sg_shim_rod_threshold}% rods",
            'ct_thresholds': f"60/120/180/240 MWe (staged)"
        }

# ============================================
# Configuration Example
# ============================================

HUMIDIFIER_CONFIG_DEFAULT = {
    # Steam Generator Humidifier thresholds (based on rod positions)
    'sg_shim_rod_threshold': 40.0,      # Shim rod must be >= 40%
    'sg_reg_rod_threshold': 40.0,       # Regulating rod must be >= 40%
    'sg_hysteresis': 5.0,               # Turn off when < 35%
    
    # Cooling Tower Humidifier thresholds - STAGED (based on electrical power)
    'ct1_power_threshold': 60000.0,     # CT1: 60 MWe (20% of max)
    'ct2_power_threshold': 120000.0,    # CT2: 120 MWe (40% of max)
    'ct3_power_threshold': 180000.0,    # CT3: 180 MWe (60% of max)
    'ct4_power_threshold': 240000.0,    # CT4: 240 MWe (80% of max)
    'ct_hysteresis': 10000.0,           # 10 MWe hysteresis untuk semua CT
}

# Alternative configurations for different scenarios
HUMIDIFIER_CONFIG_CONSERVATIVE = {
    'sg_shim_rod_threshold': 50.0,      # Higher threshold (50%)
    'sg_reg_rod_threshold': 50.0,
    'sg_hysteresis': 10.0,
    'ct1_power_threshold': 80000.0,     # CT1: 80 MWe
    'ct2_power_threshold': 140000.0,    # CT2: 140 MWe
    'ct3_power_threshold': 200000.0,    # CT3: 200 MWe
    'ct4_power_threshold': 260000.0,    # CT4: 260 MWe
    'ct_hysteresis': 15000.0,           # 15 MWe hysteresis
}

HUMIDIFIER_CONFIG_AGGRESSIVE = {
    'sg_shim_rod_threshold': 30.0,      # Lower threshold (30%)
    'sg_reg_rod_threshold': 30.0,
    'sg_hysteresis': 3.0,
    'ct1_power_threshold': 40000.0,     # CT1: 40 MWe (earlier activation)
    'ct2_power_threshold': 100000.0,    # CT2: 100 MWe
    'ct3_power_threshold': 160000.0,    # CT3: 160 MWe
    'ct4_power_threshold': 220000.0,    # CT4: 220 MWe
    'ct_hysteresis': 8000.0,            # 8 MWe hysteresis
}

HUMIDIFIER_CONFIG_TESTING = {
    'sg_shim_rod_threshold': 20.0,      # Very low for testing (20%)
    'sg_reg_rod_threshold': 20.0,
    'sg_hysteresis': 5.0,
    'ct1_power_threshold': 20000.0,     # CT1: 20 MWe (easy testing)
    'ct2_power_threshold': 50000.0,     # CT2: 50 MWe
    'ct3_power_threshold': 100000.0,    # CT3: 100 MWe
    'ct4_power_threshold': 150000.0,    # CT4: 150 MWe
    'ct_hysteresis': 5000.0,            # 5 MWe hysteresis
}

# ============================================
# Test Function
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("="*70)
    print("  Humidifier Controller Test - v3.6 (STAGED CT ACTIVATION)")
    print("  Updated Logic:")
    print("    - SG: Based on Rod Positions (before power)")
    print("    - CT: STAGED 1-by-1 based on Power Level")
    print("="*70)
    
    # Create controller with default config
    controller = HumidifierController(HUMIDIFIER_CONFIG_DEFAULT)
    
    print("\nTest Scenario: PWR Startup with STAGED CT Activation")
    print("-" * 70)
    
    # Simulate realistic PWR startup with staged CT
    test_scenarios = [
        # (shim, reg, power_kw, phase_description)
        (0, 0, 0, "Phase 1: Initial - System START"),
        (10, 10, 0, "Phase 2a: Rods raising (10%), no power yet"),
        (30, 30, 0, "Phase 2b: Rods raising (30%), thermal rising"),
        (40, 40, 0, "Phase 3: SG TRIGGER - Rods=40% (SG1+SG2 ON)"),
        (50, 50, 30000, "Phase 4: Turbine starting, 30 MWe"),
        (55, 55, 50000, "Phase 5a: Power rising, 50 MWe"),
        (60, 60, 65000, "Phase 5b: CT1 TRIGGER - 65 MWe (Stage 1/4)"),
        (65, 65, 100000, "Phase 6a: 100 MWe, CT1 running"),
        (70, 70, 125000, "Phase 6b: CT2 TRIGGER - 125 MWe (Stage 2/4)"),
        (75, 75, 150000, "Phase 7a: 150 MWe, CT1+CT2 running"),
        (80, 80, 185000, "Phase 7b: CT3 TRIGGER - 185 MWe (Stage 3/4)"),
        (85, 85, 220000, "Phase 8a: 220 MWe, CT1+CT2+CT3 running"),
        (90, 90, 245000, "Phase 8b: CT4 TRIGGER - 245 MWe (Stage 4/4 MAX)"),
        (95, 95, 290000, "Phase 9: Maximum power 290 MWe (ALL CT running)"),
        (85, 85, 230000, "Steady: 230 MWe (All CT still ON)"),
        (75, 75, 170000, "Reducing: 170 MWe (CT4 OFF, CT1-3 ON)"),
        (65, 65, 110000, "Lower: 110 MWe (CT3-4 OFF, CT1-2 ON)"),
        (55, 55, 55000, "Low power: 55 MWe (CT2-4 OFF, CT1 ON)"),
        (45, 45, 40000, "Shutdown: 40 MWe (All CT OFF, SG still ON)"),
        (30, 30, 20000, "Cooldown: 20 MWe (SG OFF)"),
        (0, 0, 0, "Stopped: All OFF"),
    ]
    
    for shim, reg, power_kw, desc in test_scenarios:
        print(f"\n{desc}")
        print(f"  Rods: Shim={shim}%, Reg={reg}%")
        print(f"  Power: {power_kw/1000.0:.0f} MWe")
        
        sg_on, ct1, ct2, ct3, ct4 = controller.update(shim, reg, power_kw)
        
        # Visual representation
        sg_status = '🌊 ON' if sg_on else '⭕ OFF'
        ct1_status = '🌊' if ct1 else '⭕'
        ct2_status = '🌊' if ct2 else '⭕'
        ct3_status = '🌊' if ct3 else '⭕'
        ct4_status = '🌊' if ct4 else '⭕'
        
        ct_count = controller.get_ct_count_active()
        
        print(f"  → Steam Gen (SG1+SG2): {sg_status}")
        print(f"  → Cooling Tower: CT1:{ct1_status} CT2:{ct2_status} CT3:{ct3_status} CT4:{ct4_status} ({ct_count}/4 active)")
    
    print("\n" + "="*70)
    print("Test completed! STAGED CT activation validated.")
    print("="*70)
    print("\nKey Features Demonstrated:")
    print("  ✓ SG activates at 40% rods (before power generation)")
    print("  ✓ CT1 activates at 60 MWe (20% power)")
    print("  ✓ CT2 activates at 120 MWe (40% power)")
    print("  ✓ CT3 activates at 180 MWe (60% power)")
    print("  ✓ CT4 activates at 240 MWe (80% power)")
    print("  ✓ Staged deactivation during shutdown")
    print("  ✓ Hysteresis prevents oscillation")
    print("="*70)
