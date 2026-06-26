import json
import time
import threading
import logging
import os
import socket

logger = logging.getLogger(__name__)

class StateExporter:
    """
    Exports the current system state over UDP socket periodically.
    Used by the video display client and touch panel to show real-time metrics.
    """
    def __init__(self, state_manager, target_ip="127.0.0.1", ports=(9998, 9997)):
        self.state_manager = state_manager
        self.target_ip = target_ip
        self.ports = ports
        self._thread = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
    def start(self):
        """Start the background export thread."""
        self._thread = threading.Thread(target=self._export_loop, daemon=True, name="StateExportThread")
        self._thread.start()
        logger.info(f"StateExporter started. Broadcasting to {self.target_ip} on ports {self.ports}")
        
    def _export_loop(self):
        """Background loop to broadcast state via UDP."""
        # Config System IO affinity (Core 0)
        try:
            import psutil
            if hasattr(os, 'gettid'):
                p = psutil.Process(os.gettid())
                if hasattr(p, 'cpu_affinity'): p.cpu_affinity([0])
        except Exception:
            pass
            
        while self.state_manager.running:
            try:
                with self.state_manager as state:
                    state_dict = {
                        "timestamp": time.time(),
                        "mode": state.simulation_mode,
                        "auto_running": state.auto_sim_running,
                        "auto_phase": state.auto_sim_phase,
                        "pressure": float(state.pressure),
                        # Export as floats so that the UI can smoothly animate them without integer jumping
                        "safety_rod": float(state.safety_rod),
                        "shim_rod": float(state.shim_rod),
                        "regulating_rod": float(state.regulating_rod),
                        "pump_primary": int(state.pump_primary_status),
                        "pump_secondary": int(state.pump_secondary_status),
                        "pump_tertiary": int(state.pump_tertiary_status),
                        "thermal_kw": float(state.thermal_kw),
                        "temperature_core": float(state.temperature_core),
                        "temperature_coolant": float(state.temperature_coolant),
                        "turbine_speed": float(state.turbine_speed),
                        "emergency": bool(state.emergency_active),
                        "lofa_primary": bool(state.lofa_primary),
                        "lofa_secondary": bool(state.lofa_secondary),
                        "lofa_tertiary": bool(state.lofa_tertiary),
                        "relief_valve_open": getattr(state, 'relief_valve_open', False),
                        "spray_active": getattr(state, 'spray_active', False),
                        "user_interacted": bool(getattr(state, 'user_interacted', False)),
                        "show_credits": bool(getattr(state, 'show_credits', False)),
                    }
                
                payload = json.dumps(state_dict).encode('utf-8')
                for port in self.ports:
                    self.sock.sendto(payload, (self.target_ip, port))
                
            except Exception as e:
                logger.error(f"State export error: {e}")
            
            time.sleep(0.05)
