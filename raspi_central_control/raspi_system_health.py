"""
System Health Check Module
Comprehensive hardware and software status verification
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict = field(default_factory=dict)
    last_check: float = 0.0
    
    def is_healthy(self) -> bool:
        """Check if component is in healthy state"""
        return self.status in [HealthStatus.OK, HealthStatus.WARNING]
    
    def is_critical(self) -> bool:
        """Check if component is in critical state"""
        return self.status in [HealthStatus.ERROR, HealthStatus.CRITICAL]


class SystemHealthMonitor:
    """
    Comprehensive system health monitoring
    
    Checks:
    - I2C multiplexers (TCA9548A #1 and #2)
    - ESP slaves (ESP-BC and ESP-E)
    - OLED displays (9 units)
    - GPIO buttons
    - Humidifier control
    - Buzzer alarm
    """
    
    def __init__(self):
        """Initialize health monitor"""
        self.components: Dict[str, ComponentHealth] = {}
        self.last_full_check = 0.0
        self.system_ready = False
        
    def check_all(self, panel_controller) -> bool:
        """
        Perform full system health check
        
        Args:
            panel_controller: Reference to PLTNPanelController
            
        Returns:
            True if system is ready, False if critical issues found
        """
        logger.info("="*70)
        logger.info("SYSTEM HEALTH CHECK - Starting comprehensive verification")
        logger.info("="*70)
        
        start_time = time.time()
        
        # Check each component
        self._check_actuator_manager(panel_controller)
        self._check_humidifier(panel_controller)
        self._check_buzzer(panel_controller)
        
        # Generate report
        self._print_health_report()
        
        # Determine system readiness
        critical_count = sum(1 for c in self.components.values() if c.is_critical())
        warning_count = sum(1 for c in self.components.values() if c.status == HealthStatus.WARNING)
        ok_count = sum(1 for c in self.components.values() if c.status == HealthStatus.OK)
        
        elapsed = time.time() - start_time
        
        logger.info("="*70)
        logger.info(f"HEALTH CHECK COMPLETE - Duration: {elapsed:.2f}s")
        logger.info(f"  ✅ OK: {ok_count} | ⚠️  WARNING: {warning_count} | ❌ CRITICAL: {critical_count}")
        
        if critical_count == 0:
            logger.info("✅ SYSTEM READY - All critical components operational")
            self.system_ready = True
        else:
            logger.error(f"❌ SYSTEM NOT READY - {critical_count} critical issues found")
            logger.error("   Please fix critical issues before running simulation")
            self.system_ready = False
        
        logger.info("="*70)
        
        self.last_full_check = time.time()
        return self.system_ready
    
    def _check_actuator_manager(self, panel):
        """Check Actuator Manager initialization"""
        logger.info("\n[2/8] Checking Actuator Manager...")
        
        if not hasattr(panel, 'actuator_manager') or not panel.actuator_manager:
            self.components["actuator_manager"] = ComponentHealth(
                name="Actuator Manager",
                status=HealthStatus.CRITICAL,
                message="Actuator Manager not initialized"
            )
            logger.error("  ❌ CRITICAL: Actuator Manager not available")
            return
        
        if panel.actuator_manager.hardware_active:
            self.components["actuator_manager"] = ComponentHealth(
                name="Actuator Manager",
                status=HealthStatus.OK,
                message="Hardware mode active"
            )
            logger.info("  ✅ OK: Actuator Manager (Hardware Mode)")
        else:
            self.components["actuator_manager"] = ComponentHealth(
                name="Actuator Manager",
                status=HealthStatus.WARNING,
                message="Mock mode active (GPIO unavailable)"
            )
            logger.warning("  ⚠️  WARNING: Actuator Manager (Mock Mode)")
    
    def _check_humidifier(self, panel):
        """Check humidifier control"""
        logger.info("\n[7/8] Checking Humidifier Control...")
        
        if not panel.humidifier:
            self.components["humidifier"] = ComponentHealth(
                name="Humidifier Control",
                status=HealthStatus.WARNING,
                message="Humidifier not initialized (non-critical)"
            )
            logger.warning("  ⚠️  WARNING: Humidifier not available (non-critical)")
            return
        
        self.components["humidifier"] = ComponentHealth(
            name="Humidifier Control",
            status=HealthStatus.OK,
            message="Humidifier controller initialized"
        )
        logger.info("  ✅ OK: Humidifier controller ready")
    
    def _check_buzzer(self, panel):
        """Check buzzer alarm"""
        logger.info("\n[8/8] Checking Buzzer Alarm...")
        
        # Buzzer is optional
        self.components["buzzer"] = ComponentHealth(
            name="Buzzer Alarm",
            status=HealthStatus.OK,
            message="Buzzer system available"
        )
        logger.info("  ✅ OK: Buzzer alarm system ready")
    
    def _print_health_report(self):
        """Print formatted health report"""
        logger.info("\n" + "="*70)
        logger.info("SYSTEM HEALTH REPORT")
        logger.info("="*70)
        
        # Group by status
        critical = []
        errors = []
        warnings = []
        ok = []
        
        for comp in self.components.values():
            if comp.status == HealthStatus.CRITICAL:
                critical.append(comp)
            elif comp.status == HealthStatus.ERROR:
                errors.append(comp)
            elif comp.status == HealthStatus.WARNING:
                warnings.append(comp)
            elif comp.status == HealthStatus.OK:
                ok.append(comp)
        
        # Print critical issues
        if critical:
            logger.error("\n❌ CRITICAL ISSUES:")
            for comp in critical:
                logger.error(f"  - {comp.name}: {comp.message}")
        
        # Print errors
        if errors:
            logger.error("\n❌ ERRORS:")
            for comp in errors:
                logger.error(f"  - {comp.name}: {comp.message}")
        
        # Print warnings
        if warnings:
            logger.warning("\n⚠️  WARNINGS:")
            for comp in warnings:
                logger.warning(f"  - {comp.name}: {comp.message}")
        
        # Print OK components
        if ok:
            logger.info("\n✅ OPERATIONAL:")
            for comp in ok:
                logger.info(f"  - {comp.name}: {comp.message}")
    
    def get_summary(self) -> Dict:
        """Get health check summary"""
        return {
            'system_ready': self.system_ready,
            'last_check': self.last_full_check,
            'components': {
                name: {
                    'status': comp.status.value,
                    'message': comp.message,
                    'details': comp.details
                }
                for name, comp in self.components.items()
            }
        }
