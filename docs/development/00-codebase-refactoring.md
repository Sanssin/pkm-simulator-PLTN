# Pengembangan #0: Codebase Refactoring

**Status**: ✅ Completed  
**Priority**: ⭐ Paling Awal (sebelum Pengembangan #1 dan #2)  
**Estimasi**: 5 fase  
**Dampak**: Memudahkan maintenance dan pengembangan selanjutnya

---

## 📖 Latar Belakang

File `raspi_main_panel.py` saat ini memiliki **1992 baris** kode dengan banyak tanggung jawab yang tercampur dalam satu file:
- 17 button callbacks
- Event processing (240 baris dalam satu fungsi)
- Interlock logic
- SCRAM sequence
- Auto simulation (403 baris)
- 9 thread definitions
- ESP communication
- State management

Refactoring ini akan memecah file menjadi modul-modul kecil yang lebih mudah:
- **Di-test** secara unit
- **Di-debug** saat ada masalah
- **Di-modifikasi** saat pengembangan berikutnya (touchscreen, single controller)

---

## 📊 Analisis Current Codebase

### File Sizes (raspi_central_control/)

| File | Lines | Kondisi |
|------|-------|---------|
| raspi_main_panel.py | 1992 | ⚠️ Perlu dipecah |
| raspi_uart_master.py | 1215 | ⚠️ Besar tapi focused |
| raspi_oled_manager.py | 1125 | ✓ OK (akan dihapus di #1) |
| raspi_system_health.py | 500 | ✓ OK |
| raspi_humidifier_control.py | 389 | ✓ OK |
| raspi_buzzer_alarm.py | 337 | ✓ OK |
| raspi_tca9548a.py | 306 | ✓ OK (akan dihapus di #1) |
| raspi_gpio_buttons.py | 273 | ✓ OK (akan dihapus di #1) |
| raspi_config.py | 99 | ✓ OK |

### Fungsi Terpanjang di raspi_main_panel.py

| Fungsi | Lines | Masalah |
|--------|-------|---------|
| `auto_simulation_thread()` | 403 | 9 phase dalam 1 fungsi |
| `process_button_event()` | 240 | 17 event types, 1 fungsi |
| `_check_pump_start_safe()` | 88 | OK tapi tightly coupled |
| `control_logic_thread()` | 110 | Multiple concerns |

---

## 🎯 Target Refactoring

### Struktur Baru

```
raspi_central_control/
├── raspi_main_panel.py          # Orchestrator (reduced to ~500 lines)
├── raspi_config.py              # Config (existing)
│
├── controllers/                  # NEW: Control logic modules
│   ├── __init__.py
│   ├── interlock_validator.py   # Interlock & safety checks
│   ├── state_manager.py         # PanelState + transitions
│   ├── rod_controller.py        # Rod movement logic
│   ├── pump_controller.py       # Pump sequencing
│   └── event_processor.py       # Button event → state changes
│
├── sequences/                    # NEW: Operational sequences
│   ├── __init__.py
│   ├── scram_sequence.py        # Emergency SCRAM + turbine spindown
│   └── auto_simulation.py       # 9-phase startup sequence
│
├── communication/                # NEW: ESP communication
│   ├── __init__.py
│   └── esp_protocol.py          # UART protocol handler
│
├── io/                           # NEW: Input/Output handling
│   ├── __init__.py
│   ├── button_handler.py        # Button polling + hold detection
│   └── state_export.py          # JSON export for video display
│
└── existing files...            # raspi_buzzer_alarm.py, etc.
```

### Pengurangan Lines di raspi_main_panel.py

| Komponen yang Dipindah | Lines Saat Ini | Target File |
|------------------------|----------------|-------------|
| InterlockValidator | ~150 | controllers/interlock_validator.py |
| EventProcessor | ~240 | controllers/event_processor.py |
| RodController | ~100 | controllers/rod_controller.py |
| PumpController | ~80 | controllers/pump_controller.py |
| AutoSimulation | ~400 | sequences/auto_simulation.py |
| SCRAMSequence | ~120 | sequences/scram_sequence.py |
| ESPProtocol | ~100 | communication/esp_protocol.py |
| ButtonIO | ~80 | io/button_handler.py |
| StateExport | ~70 | io/state_export.py |
| **Total Dipindah** | **~1340** | - |
| **Sisa di Main** | **~650** | - |

---

## 📦 Modul yang Akan Dibuat

### Fase 1: Foundation (Safety-Critical)

#### 1.1 `controllers/interlock_validator.py`
```python
class InterlockValidator:
    """Validates safety conditions for reactor operations"""
    
    # Pressure thresholds
    MIN_PRESSURE_FOR_PUMPS = 40.0  # bar
    MIN_PRESSURE_FOR_RODS = 140.0  # bar
    
    def check_rod_movement(self, state) -> tuple[bool, str]:
        """Check if rod movement is allowed
        Returns: (allowed: bool, reason: str if not allowed)
        """
    
    def check_pump_start(self, pump_name: str, state) -> tuple[bool, str]:
        """Check if pump can be started
        Enforces sequence: Tertiary → Secondary → Primary
        """
    
    def get_interlock_status(self, state) -> dict:
        """Get full interlock status for display"""
```

#### 1.2 `controllers/state_manager.py`
```python
@dataclass
class PanelState:
    """Reactor control system state"""
    # (move dari raspi_main_panel.py)

class StateManager:
    """Thread-safe state management"""
    
    def __init__(self):
        self.state = PanelState()
        self.lock = threading.Lock()
    
    def get_snapshot(self) -> PanelState:
        """Get copy of current state (thread-safe)"""
    
    def apply_updates(self, updates: dict):
        """Apply multiple state updates atomically"""
    
    def reset(self):
        """Reset state to initial values"""
```

### Fase 2: Event Processing

#### 2.1 `controllers/event_processor.py`
```python
class ButtonEvent(Enum):
    """Button event types"""
    # (move dari raspi_main_panel.py)

class EventProcessor:
    """Process button events into state changes"""
    
    def __init__(self, interlock: InterlockValidator, buzzer=None):
        self.interlock = interlock
        self.buzzer = buzzer
    
    def process(self, event: ButtonEvent, state: PanelState) -> list[StateUpdate]:
        """Process event and return state updates to apply
        
        Returns list of (field_name, new_value) tuples
        Does NOT apply updates directly - caller handles locking
        """
    
    # Handler methods
    def _handle_pressure(self, event, state) -> list
    def _handle_pump(self, event, state) -> list
    def _handle_rod(self, event, state) -> list
    def _handle_emergency(self, event, state) -> list
    def _handle_reset(self, event, state) -> list
```

#### 2.2 `controllers/rod_controller.py`
```python
class RodController:
    """Rod movement logic with safety priority"""
    
    # Rod priority: Safety > Shim, Regulating
    
    def can_raise_rod(self, rod_name: str, state) -> tuple[bool, str]:
        """Check if rod can be raised"""
    
    def can_lower_rod(self, rod_name: str, state) -> tuple[bool, str]:
        """Check if rod can be lowered (safety guard)"""
    
    def get_new_position(self, rod_name: str, direction: str, current: int) -> int:
        """Calculate new position with bounds checking"""
```

#### 2.3 `controllers/pump_controller.py`
```python
class PumpController:
    """Pump state machine and sequencing"""
    
    # Status: 0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN
    STARTUP_DELAY = 2.0  # seconds
    SHUTDOWN_DELAY = 1.0  # seconds
    
    def update_transitions(self, state, current_time: float) -> list:
        """Update pump state machines, return state changes"""
    
    def can_start_pump(self, pump_name: str, state) -> tuple[bool, str]:
        """Check startup sequence (Tertiary → Secondary → Primary)"""
```

### Fase 3: Sequences

#### 3.1 `sequences/scram_sequence.py`
```python
class SCRAMSequence:
    """Emergency SCRAM sequence handler"""
    
    ROD_DROP_DURATION = 3.0  # seconds
    TURBINE_SPINDOWN_DURATION = 12.0  # seconds
    
    def __init__(self, state_manager, buzzer=None):
        self.state_manager = state_manager
        self.buzzer = buzzer
    
    def execute(self, callback_per_step=None):
        """Execute SCRAM sequence (non-blocking, runs in thread)"""
    
    def _drop_all_rods(self, initial_positions: dict):
        """Simultaneously drop all rods to 0% (smooth animation)"""
    
    def _spindown_turbine(self, initial_speed: float):
        """Gradually reduce turbine speed (realistic deceleration)"""
```

#### 3.2 `sequences/auto_simulation.py`
```python
@dataclass
class SimulationPhase:
    """A single phase in the startup sequence"""
    name: str
    duration: float  # seconds
    target_values: dict  # field_name: target_value
    description: str = ""

class AutoSimulationSequence:
    """9-phase PWR startup sequence"""
    
    PHASES = [
        SimulationPhase("Init", 3.0, {}, "System initialization"),
        SimulationPhase("Pressure 45", 3.0, {"pressure": 45.0}),
        SimulationPhase("Pumps", 9.0, {"pump_tertiary": 2, "pump_secondary": 2, "pump_primary": 2}),
        SimulationPhase("Pressure 140", 7.0, {"pressure": 140.0}),
        # ... etc
    ]
    
    def __init__(self, state_manager, esp_trigger=None):
        self.state_manager = state_manager
        self.running = False
        self.current_phase = ""
    
    def start(self):
        """Start auto simulation (non-blocking)"""
    
    def cancel(self):
        """Cancel running simulation"""
    
    def _execute_phase(self, phase: SimulationPhase):
        """Execute single phase with smooth animation"""
```

### Fase 4: Communication

#### 4.1 `communication/esp_protocol.py`
```python
class ESPProtocolHandler:
    """Handle ESP communication protocol"""
    
    def __init__(self, uart_master):
        self.uart = uart_master
        self.last_esp_e_time = 0
        self.ESP_E_THROTTLE = 0.2  # 200ms
    
    def send_control_state(self, state) -> bool:
        """Send control state to ESP-BC
        Returns success status
        """
    
    def send_power_output(self, thermal_kw: float) -> bool:
        """Send power output to ESP-E (throttled)"""
    
    def read_sensor_data(self) -> dict:
        """Read thermal_kw, turbine_speed from ESP-BC"""
    
    def prepare_esp_bc_packet(self, state) -> tuple:
        """Convert state to ESP-BC command parameters"""
```

### Fase 5: IO Handlers

#### 5.1 `io/button_handler.py`
```python
class ButtonIOHandler:
    """Handle button polling and hold detection"""
    
    POLL_INTERVAL = 0.005  # 5ms (200Hz)
    HOLD_INTERVAL = 0.05   # 50ms for continuous input
    
    HOLDABLE_BUTTONS = [
        "PRESSURE_UP", "PRESSURE_DOWN",
        "SAFETY_ROD_UP", "SAFETY_ROD_DOWN",
        "SHIM_ROD_UP", "SHIM_ROD_DOWN",
        "REGULATING_ROD_UP", "REGULATING_ROD_DOWN"
    ]
    
    def __init__(self, button_manager, event_queue):
        self.button_manager = button_manager
        self.event_queue = event_queue
    
    def run_polling_loop(self):
        """Main polling loop (for thread)"""
    
    def run_hold_detection_loop(self):
        """Hold detection loop (for thread)"""
```

#### 5.2 `io/state_export.py`
```python
class StateExporter:
    """Export state to JSON for video display integration"""
    
    EXPORT_PATH = Path("/tmp/pltn_state.json")
    EXPORT_RATE = 0.1  # 100ms (10Hz)
    
    def __init__(self, state_manager):
        self.state_manager = state_manager
    
    def run_export_loop(self):
        """Main export loop (for thread)"""
    
    def export_once(self) -> bool:
        """Export current state to file (atomic write)"""
```

---

## 🔄 Refactoring Strategy

### Pendekatan: Incremental dengan Backward Compatibility

1. **Buat modul baru** tanpa mengubah raspi_main_panel.py
2. **Test modul baru** secara independen
3. **Integrasikan satu-per-satu** ke main panel
4. **Hapus kode lama** setelah integrasi berhasil

### Dependency Order

```
                ┌─────────────────┐
                │  StateManager   │ ← Dibuat pertama
                └────────┬────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Interlock  │  │    Rod      │  │    Pump     │
│  Validator  │  │  Controller │  │  Controller │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
               ┌─────────────────┐
               │ EventProcessor  │
               └────────┬────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ SCRAM Seq.  │  │ Auto Sim.   │  │ ESP Protocol│
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## 📝 Task Breakdown

### Phase 1: Setup & Foundation
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| RF-001 | pkm-simulator-PLTN-bve | Create directory structure | Buat folder controllers/, sequences/, communication/, io/ |
| RF-002 | pkm-simulator-PLTN-vsp | StateManager module | Extract PanelState + thread-safe wrapper |
| RF-003 | pkm-simulator-PLTN-cnw | InterlockValidator module | Extract interlock logic, add unit tests |

### Phase 2: Controllers
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| RF-010 | pkm-simulator-PLTN-dfn | RodController module | Extract rod logic dengan priority rules |
| RF-011 | pkm-simulator-PLTN-n7f | PumpController module | Extract pump state machine |
| RF-012 | pkm-simulator-PLTN-h8d | EventProcessor module | Extract 240-line event handler |
| RF-013 | pkm-simulator-PLTN-86p | Unit tests | Test semua controller modules |

### Phase 3: Sequences
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| RF-020 | pkm-simulator-PLTN-22t | SCRAMSequence module | Extract emergency sequence |
| RF-021 | pkm-simulator-PLTN-7pm | AutoSimulation module | Extract 403-line auto simulation |
| RF-022 | pkm-simulator-PLTN-19y | Sequence unit tests | Test sequences dengan mocked state |

### Phase 4: Communication & IO
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| RF-030 | pkm-simulator-PLTN-g75 | ESPProtocol module | Extract UART communication |
| RF-031 | pkm-simulator-PLTN-1m5 | ButtonIOHandler module | Extract polling + hold detection |
| RF-032 | pkm-simulator-PLTN-yj1 | StateExporter module | Extract JSON export |

### Phase 5: Integration
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| RF-040 | pkm-simulator-PLTN-kaq | Integrate to main panel | Replace inline code dengan module calls |
| RF-041 | pkm-simulator-PLTN-ud9 | Integration tests | Test full system dengan modules |
| RF-042 | pkm-simulator-PLTN-s9l | Remove old code | Cleanup duplicate code |
| RF-043 | pkm-simulator-PLTN-f6a | Update documentation | Update AGENT.md dengan struktur baru |

---

## ⚠️ Pertimbangan

### Backward Compatibility
- Semua perubahan harus **backward compatible**
- Unit tests harus pass sebelum dan sesudah refactoring
- Tidak ada perubahan behavior, hanya struktur kode

### Testing Strategy
- **Unit tests** untuk setiap modul baru
- **Integration tests** untuk kombinasi modul
- **System tests** untuk full operation

### Risk Mitigation
- Refactor satu modul pada satu waktu
- Commit per modul (easy rollback)
- Jangan refactor safety-critical code tanpa thorough testing

---

## 📅 Dependency dengan Pengembangan Lain

- **Sebelum Pengembangan #1** (Touchscreen): Kode sudah terstruktur
- **Sebelum Pengembangan #2** (Single Controller): Modul controllers/ sudah ada
- **Mendukung semua pengembangan**: Easier testing, debugging, modification

---

## 🎯 Keuntungan Setelah Refactoring

| Aspek | Sebelum | Sesudah |
|-------|---------|---------|
| **File terbesar** | 1992 lines | ~500 lines |
| **Testability** | Sulit (tightly coupled) | Mudah (isolated modules) |
| **Debugging** | Cari di 2000 baris | Cari di modul spesifik |
| **Modification** | High risk | Low risk per module |
| **Code review** | Overwhelming | Focused per module |
| **New developer** | Confusing | Clear structure |

---

*Terakhir diupdate: 2026-05-19*
