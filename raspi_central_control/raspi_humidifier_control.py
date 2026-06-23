#!/usr/bin/env python3
"""
Humidifier Control Logic for PLTN Simulator
Updated with optimized STAGED Cooling Tower Control mapping.
"""

import logging

logger = logging.getLogger(__name__)

class HumidifierController:
    """
    Controls 6 humidifiers (2 SG + 4 CT) based on system conditions.
    """
    
    def __init__(self, config=None):
        c = config or {}
        # Steam Generator Humidifier thresholds
        self.sg_thresh = (c.get('sg_shim_rod_threshold', 40.0), c.get('sg_reg_rod_threshold', 40.0))
        
        # Cooling Tower Humidifier thresholds (Staged)
        self.ct_thresh = [
            c.get('ct1_power_threshold', 60000.0),
            c.get('ct2_power_threshold', 120000.0),
            c.get('ct3_power_threshold', 180000.0),
            c.get('ct4_power_threshold', 240000.0)
        ]
        self.sg_hyst = c.get('sg_hysteresis', 5.0)
        self.ct_hyst = c.get('ct_hysteresis', 10000.0)
        
        # State tracking
        self.steam_gen_humidifier = False
        self.ct_states = [False] * 4
        
    def update(self, shim_rod, regulating_rod, power_kw):
        """Update states based on current readings."""
        # Update Steam Generator (SG) Humidifier
        sg_h = self.sg_hyst if self.steam_gen_humidifier else 0
        sg_new = shim_rod >= (self.sg_thresh[0] - sg_h) and regulating_rod >= (self.sg_thresh[1] - sg_h)
        if sg_new != self.steam_gen_humidifier:
            logger.info(f"{'🌊 Steam Gen Humidifier ON' if sg_new else '⭕ Steam Gen Humidifier OFF'}: Shim={shim_rod:.1f}% Reg={regulating_rod:.1f}%")
        self.steam_gen_humidifier = sg_new
        
        # Update Cooling Tower (CT) Humidifiers
        new_ct = []
        for i, (base_thresh, last_state) in enumerate(zip(self.ct_thresh, self.ct_states)):
            thresh = base_thresh - (self.ct_hyst if last_state else 0)
            state = power_kw >= thresh
            if state != last_state:
                logger.info(f"{'🌊 CT' + str(i+1) + ' ON' if state else '⭕ CT' + str(i+1) + ' OFF'}: Power={power_kw/1000.0:.1f} MWe")
            new_ct.append(state)
            
        self.ct_states = new_ct
        return (self.steam_gen_humidifier, *self.ct_states)

    def get_status(self):
        """Get current humidifier status."""
        return {
            'steam_gen_humidifier': self.steam_gen_humidifier,
            'ct1_active': self.ct_states[0],
            'ct2_active': self.ct_states[1],
            'ct3_active': self.ct_states[2],
            'ct4_active': self.ct_states[3],
            'ct_active_count': sum(self.ct_states)
        }
