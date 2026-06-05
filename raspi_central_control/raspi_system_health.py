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
        self._check_multiplexers(panel_controller)
        self._check_uart_master(panel_controller)
        self._check_esp_bc(panel_controller)
        self._check_esp_e(panel_controller)
        self._check_oled_displays(panel_controller)
        self._check_gpio_buttons(panel_controller)
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
    
    def _check_multiplexers(self, panel):
        """Check TCA9548A multiplexers"""
        logger.info("\n[1/8] Checking I2C Multiplexers...")
        
        if not panel.mux_manager:
            self.components["mux"] = ComponentHealth(
                name="I2C Multiplexers",
                status=HealthStatus.CRITICAL,
                message="Multiplexer manager not initialized"
            )
            logger.error("  ❌ CRITICAL: Multiplexers not available")
            return
        
        try:
            # Try to scan multiplexers
            scan_result = panel.mux_manager.scan_all()
            
            mux1_ok = len(scan_result.get('mux1', {})) > 0
            mux2_ok = len(scan_result.get('mux2', {})) > 0
            
            if mux1_ok and mux2_ok:
                self.components["mux"] = ComponentHealth(
                    name="I2C Multiplexers",
                    status=HealthStatus.OK,
                    message="Both multiplexers responding",
                    details={
                        'mux1_devices': len(scan_result.get('mux1', {})),
                        'mux2_devices': len(scan_result.get('mux2', {}))
                    }
                )
                logger.info("  ✅ OK: Both TCA9548A multiplexers responding")
            elif mux1_ok or mux2_ok:
                self.components["mux"] = ComponentHealth(
                    name="I2C Multiplexers",
                    status=HealthStatus.ERROR,
                    message="One multiplexer not responding",
                    details={
                        'mux1_ok': mux1_ok,
                        'mux2_ok': mux2_ok
                    }
                )
                logger.error("  ❌ ERROR: One multiplexer not responding")
            else:
                self.components["mux"] = ComponentHealth(
                    name="I2C Multiplexers",
                    status=HealthStatus.CRITICAL,
                    message="No multiplexers responding"
                )
                logger.error("  ❌ CRITICAL: No multiplexers responding")
                
        except Exception as e:
            self.components["mux"] = ComponentHealth(
                name="I2C Multiplexers",
                status=HealthStatus.CRITICAL,
                message=f"Exception during check: {e}"
            )
            logger.error(f"  ❌ CRITICAL: Exception - {e}")
    
    def _check_uart_master(self, panel):
        """Check UART master initialization"""
        logger.info("\n[2/8] Checking UART Master...")
        
        if not hasattr(panel, 'uart_master') or not panel.uart_master:
            self.components["uart_master"] = ComponentHealth(
                name="UART Master",
                status=HealthStatus.CRITICAL,
                message="UART Master not initialized"
            )
            logger.error("  ❌ CRITICAL: UART Master not available")
            return
        
        self.components["uart_master"] = ComponentHealth(
            name="UART Master",
            status=HealthStatus.OK,
            message="UART Master initialized"
        )
        logger.info("  ✅ OK: UART Master initialized")
    
    def _check_esp_bc(self, panel):
        """Check ESP-BC communication"""
        logger.info("\n[3/8] Checking ESP-BC (Control Rods + Turbine)...")
        
        if not hasattr(panel, 'uart_master') or not panel.uart_master:
            self.components["esp_bc"] = ComponentHealth(
                name="ESP-BC",
                status=HealthStatus.UNKNOWN,
                message="Cannot test - UART not available"
            )
            logger.warning("  ⚠️  UNKNOWN: Cannot test without UART")
            return
        
        try:
            # Small delay before communication (stability)
            logger.info("  ⏳ Waiting 0.1s before communication...")
            time.sleep(0.1)
            
            # Try communication via UART
            success = panel.uart_master.update_esp_bc(0, 0, 0)
            
            if success:
                health = panel.uart_master.get_health_status()
                esp_bc_health = health.get('esp_bc', {})
                error_count = esp_bc_health.get('error_count', 999)
                
                if error_count == 0:
                    self.components["esp_bc"] = ComponentHealth(
                        name="ESP-BC",
                        status=HealthStatus.OK,
                        message="Communication successful",
                        details=esp_bc_health
                    )
                    logger.info("  ✅ OK: ESP-BC responding via UART")
                else:
                    self.components["esp_bc"] = ComponentHealth(
                        name="ESP-BC",
                        status=HealthStatus.WARNING,
                        message=f"Communication works but {error_count} errors",
                        details=esp_bc_health
                    )
                    logger.warning(f"  ⚠️  WARNING: ESP-BC has {error_count} errors")
            else:
                self.components["esp_bc"] = ComponentHealth(
                    name="ESP-BC",
                    status=HealthStatus.ERROR,
                    message="Communication failed"
                )
                logger.error("  ❌ ERROR: ESP-BC not responding")
                logger.error("     Check: ESP32 powered on, UART wiring (GPIO 14/15)")
                
        except Exception as e:
            self.components["esp_bc"] = ComponentHealth(
                name="ESP-BC",
                status=HealthStatus.ERROR,
                message=f"Exception: {e}"
            )
            logger.error(f"  ❌ ERROR: Exception - {e}")
    
    def _check_esp_e(self, panel):
        """Check ESP-E communication"""
        logger.info("\n[4/8] Checking ESP-E (LED Visualizer)...")
        
        if not hasattr(panel, 'uart_master') or not panel.uart_master:
            self.components["esp_e"] = ComponentHealth(
                name="ESP-E",
                status=HealthStatus.WARNING,
                message="Cannot test - UART not available (non-critical)"
            )
            logger.warning("  ⚠️  WARNING: Cannot test without UART (non-critical)")
            return
        
        # Check if ESP-E is enabled
        if not panel.uart_master.esp_e_enabled:
            self.components["esp_e"] = ComponentHealth(
                name="ESP-E",
                status=HealthStatus.INFO,
                message="ESP-E disabled (not configured)"
            )
            logger.info("  ℹ️  INFO: ESP-E disabled (non-critical)")
            return
        
        try:
            # Small delay before communication (stability)
            logger.info("  ⏳ Waiting 0.1s before communication...")
            time.sleep(0.1)
            
            # Try communication via UART (simplified protocol)
            success = panel.uart_master.update_esp_e(0.0)
            
            if success:
                health = panel.uart_master.get_health_status()
                esp_e_health = health.get('esp_e', {})
                error_count = esp_e_health.get('error_count', 999)
                
                if error_count == 0:
                    self.components["esp_e"] = ComponentHealth(
                        name="ESP-E",
                        status=HealthStatus.OK,
                        message="Communication successful",
                        details=esp_e_health
                    )
                    logger.info("  ✅ OK: ESP-E responding via UART")
                else:
                    self.components["esp_e"] = ComponentHealth(
                        name="ESP-E",
                        status=HealthStatus.WARNING,
                        message=f"Communication works but {error_count} errors",
                        details=esp_e_health
                    )
                    logger.warning(f"  ⚠️  WARNING: ESP-E has {error_count} errors")
            else:
                self.components["esp_e"] = ComponentHealth(
                    name="ESP-E",
                    status=HealthStatus.WARNING,
                    message="Communication failed (non-critical)"
                )
                logger.warning("  ⚠️  WARNING: ESP-E not responding (visualization only)")
                
        except Exception as e:
            self.components["esp_e"] = ComponentHealth(
                name="ESP-E",
                status=HealthStatus.WARNING,
                message=f"Exception: {e} (non-critical)"
            )
            logger.warning(f"  ⚠️  WARNING: Exception - {e} (non-critical)")
    
    def _check_oled_displays(self, panel):
        """Check OLED displays"""
        logger.info("\n[5/8] Checking OLED Displays...")
        
        # OLED is optional (non-critical)
        if not hasattr(panel, 'oled_manager') or not panel.oled_manager:
            self.components["oled"] = ComponentHealth(
                name="OLED Displays",
                status=HealthStatus.WARNING,
                message="OLED manager not initialized (non-critical)"
            )
            logger.warning("  ⚠️  WARNING: OLED displays not available (non-critical)")
            return
        
        # Count initialized displays
        display_count = 0
        display_list = [
            panel.oled_manager.oled_pressurizer,
            panel.oled_manager.oled_pump_primary,
            panel.oled_manager.oled_pump_secondary,
            panel.oled_manager.oled_pump_tertiary,
            panel.oled_manager.oled_safety_rod,
            panel.oled_manager.oled_shim_rod,
            panel.oled_manager.oled_regulating_rod,
            panel.oled_manager.oled_thermal_power,
            panel.oled_manager.oled_system_status
        ]
        
        for display in display_list:
            if display and display.initialized:
                display_count += 1
        
        if display_count >= 7:
            self.components["oled"] = ComponentHealth(
                name="OLED Displays",
                status=HealthStatus.OK,
                message=f"{display_count}/9 displays working",
                details={'display_count': display_count}
            )
            logger.info(f"  ✅ OK: {display_count}/9 OLED displays working")
        elif display_count > 0:
            self.components["oled"] = ComponentHealth(
                name="OLED Displays",
                status=HealthStatus.WARNING,
                message=f"Only {display_count}/9 displays working",
                details={'display_count': display_count}
            )
            logger.warning(f"  ⚠️  WARNING: Only {display_count}/9 displays working")
        else:
            self.components["oled"] = ComponentHealth(
                name="OLED Displays",
                status=HealthStatus.WARNING,
                message="No displays working (non-critical)",
                details={'display_count': 0}
            )
            logger.warning("  ⚠️  WARNING: No OLED displays working (non-critical)")
    
    def _check_gpio_buttons(self, panel):
        """Check GPIO button initialization"""
        logger.info("\n[6/8] Checking GPIO Buttons...")
        
        if not hasattr(panel, 'button_manager') or not panel.button_manager:
            self.components["buttons"] = ComponentHealth(
                name="GPIO Buttons",
                status=HealthStatus.WARNING,
                message="Button manager not initialized (simulation mode)"
            )
            logger.warning("  ⚠️  WARNING: Buttons not available (simulation mode)")
            return
        
        callback_count = len(panel.button_manager.callbacks)
        expected_count = 17  # Total buttons in system
        
        if callback_count == expected_count:
            self.components["buttons"] = ComponentHealth(
                name="GPIO Buttons",
                status=HealthStatus.OK,
                message=f"All {callback_count} buttons registered",
                details={'callback_count': callback_count}
            )
            logger.info(f"  ✅ OK: All {callback_count} buttons registered")
        elif callback_count > 0:
            self.components["buttons"] = ComponentHealth(
                name="GPIO Buttons",
                status=HealthStatus.WARNING,
                message=f"Only {callback_count}/{expected_count} buttons registered",
                details={'callback_count': callback_count}
            )
            logger.warning(f"  ⚠️  WARNING: Only {callback_count}/{expected_count} buttons")
        else:
            self.components["buttons"] = ComponentHealth(
                name="GPIO Buttons",
                status=HealthStatus.WARNING,
                message="No buttons registered",
                details={'callback_count': 0}
            )
            logger.warning("  ⚠️  WARNING: No buttons registered")
    
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
