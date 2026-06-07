# Pengembangan #4: CPU Optimization

**Status**: 📋 Planned  
**Priority**: Setelah Pengembangan #1, #2  
**Estimasi**: 3 fase  
**Dampak**: Distribusi beban kerja merata, responsivitas lebih baik

---

## 📖 Latar Belakang

Raspberry Pi 4 memiliki **4 CPU cores** (ARM Cortex-A72). Saat ini semua proses berjalan tanpa CPU affinity assignment, sehingga:
- Semua threads berkompetisi di semua cores
- Scheduler Linux memindahkan threads antar core (context switching overhead)
- Proses berat (video playback, animation) bisa mengganggu proses real-time (actuator control)

**Target**: Distribusi beban kerja ke 4 cores dengan affinity assignment.

---

## 📊 Analisis Current Architecture

### Proses Utama (Post-Pengembangan #1 dan #2)

| Proses | Deskripsi | CPU Intensity |
|--------|-----------|---------------|
| **raspi_main_panel.py** | Central controller, 9 threads | Medium-High |
| **touch_panel.py** (new) | PyQt5 touchscreen UI | Medium |
| **video_display_app.py** | Pygame video + animation | High |
| **System services** | Linux, pigpiod, etc. | Low |

### Thread Breakdown (raspi_main_panel.py)

| Thread | Fungsi | Frequency | CPU Impact |
|--------|--------|-----------|------------|
| ButtonThread | GPIO polling (setelah #1: USB HID) | 200 Hz | Low |
| ButtonHoldThread | Hold detection | 20 Hz | Very Low |
| EventThread | Event processing | Event-driven | Low |
| ControlThread | Control logic | 20 Hz | Medium |
| ESPCommThread | UART (setelah #2: ActuatorManager) | 20 Hz | Medium |
| OLEDThread | OLED update (dihapus di #1) | 10 Hz | Low |
| HealthThread | Health check | Passive | Very Low |
| AutoSimThread | Auto simulation | Event-driven | Low |
| StateExportThread | JSON export | 10 Hz | Low |

### Video Display (pygame)

| Component | Fungsi | CPU Impact |
|-----------|--------|------------|
| Video decoding | FFmpeg/pygame | **High** |
| Animation rendering | Pygame sprites | Medium |
| State polling | JSON read | Low |

---

## 🎯 CPU Core Assignment Strategy

### Raspberry Pi 4 - 4 Cores Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4 - 4 Core ARM                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│   │   Core 0    │  │   Core 1    │  │   Core 2    │  │   Core 3    ││
│   │             │  │             │  │             │  │             ││
│   │  SYSTEM +   │  │  CONTROL +  │  │    VIDEO    │  │ TOUCHSCREEN ││
│   │  IO/COMM    │  │  ACTUATOR   │  │   DISPLAY   │  │     UI      ││
│   │             │  │             │  │             │  │             ││
│   │ - Linux sys │  │ - Control   │  │ - Pygame    │  │ - PyQt5     ││
│   │ - pigpiod   │  │   logic     │  │ - Video     │  │ - Touch     ││
│   │ - State     │  │ - Actuator  │  │   decode    │  │   events    ││
│   │   export    │  │   manager   │  │ - Animation │  │ - UI render ││
│   │ - Health    │  │ - SCRAM     │  │             │  │             ││
│   │             │  │             │  │             │  │             ││
│   │   ~20%      │  │   ~30%      │  │   ~40%      │  │   ~30%      ││
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Detailed Assignment

#### Core 0: System & IO
**Affinity**: `taskset -c 0`

| Process/Thread | Justifikasi |
|----------------|-------------|
| Linux kernel threads | Default, tidak bisa dipindah |
| pigpiod daemon | Low frequency, shared dengan system |
| StateExportThread | IO-bound (file write) |
| HealthThread | Passive monitoring |
| JSON IPC reader/writer | Low CPU |

**Load Profile**: ~20% average, bursty saat boot

#### Core 1: Control & Actuator (REAL-TIME PRIORITY)
**Affinity**: `taskset -c 1` + `nice -n -10` (higher priority)

| Process/Thread | Justifikasi |
|----------------|-------------|
| ControlThread | Safety-critical, 20Hz |
| ActuatorManager | Direct GPIO control |
| SCRAMSequence | Emergency response |
| EventThread | Button event processing |
| AutoSimThread | Simulation choreography |

**Load Profile**: ~30% average, spikes during SCRAM

**Rationale**: Core 1 dedicated untuk control loop agar:
- Tidak terganggu video decoding
- Consistent latency untuk actuator response
- SCRAM sequence mendapat prioritas

#### Core 2: Video Display (ISOLATED)
**Affinity**: `taskset -c 2`

| Process/Thread | Justifikasi |
|----------------|-------------|
| video_display_app.py (main) | Heavy video decode |
| Pygame event loop | 60 FPS rendering |
| FFmpeg subprocess | Video decoding |

**Load Profile**: ~40% average, 80% saat video playback

**Rationale**: Video processing terisolasi agar:
- Tidak mengganggu control loop
- Frame drops tidak affect actuator timing
- Bisa turunkan FPS saat CPU throttling

#### Core 3: Touchscreen UI
**Affinity**: `taskset -c 3`

| Process/Thread | Justifikasi |
|----------------|-------------|
| touch_panel.py (main) | PyQt5 UI |
| Qt event loop | Touch input handling |
| UI rendering | Button animations |

**Load Profile**: ~30% average, spikes saat touch input

**Rationale**: UI terisolasi agar:
- Touch response tetap responsif
- Animasi tidak lag
- Independen dari video/control

---

## 🔧 Implementation Details

### Method 1: Python `os.sched_setaffinity()` (Recommended)

```python
import os
import psutil

def set_cpu_affinity(cores: list):
    """Set CPU affinity for current process
    
    Args:
        cores: List of core indices (0-3 for RPi4)
    """
    try:
        os.sched_setaffinity(0, cores)  # 0 = current process
        print(f"CPU affinity set to cores: {cores}")
    except Exception as e:
        print(f"Failed to set affinity: {e}")

def set_thread_affinity(thread, cores: list):
    """Set CPU affinity for specific thread
    
    Args:
        thread: threading.Thread object
        cores: List of core indices
    """
    try:
        # Get thread's native ID
        tid = thread.native_id
        os.sched_setaffinity(tid, cores)
        print(f"Thread {thread.name} affinity set to cores: {cores}")
    except Exception as e:
        print(f"Failed to set thread affinity: {e}")
```

### Method 2: psutil Library (Cross-Platform)

```python
import psutil

def set_process_affinity(pid: int, cores: list):
    """Set CPU affinity using psutil"""
    try:
        p = psutil.Process(pid)
        p.cpu_affinity(cores)
        print(f"Process {pid} affinity: {cores}")
    except Exception as e:
        print(f"Failed: {e}")

def set_process_priority(pid: int, priority: int):
    """Set process priority (nice value)
    
    Args:
        priority: -20 (highest) to 19 (lowest)
    """
    try:
        p = psutil.Process(pid)
        p.nice(priority)
        print(f"Process {pid} priority: {priority}")
    except Exception as e:
        print(f"Failed: {e}")
```

### Method 3: System-Level (systemd + taskset)

```bash
# /etc/systemd/system/pltn-controller.service
[Unit]
Description=PLTN Controller Service
After=pigpiod.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pltn-simulator/raspi_central_control
ExecStart=/usr/bin/taskset -c 1 /usr/bin/python3 raspi_main_panel.py
Nice=-10
CPUAffinity=1
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# /etc/systemd/system/pltn-video.service
[Unit]
Description=PLTN Video Display
After=pltn-controller.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pltn-simulator/pltn_video_display
ExecStart=/usr/bin/taskset -c 2 /usr/bin/python3 video_display_app.py
CPUAffinity=2
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 📐 Architecture After Optimization

### Process Model (3 Independent Processes)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PLTN Simulator System                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                      IPC Layer (JSON Files)                      ││
│  │  /tmp/pltn_state.json     /tmp/pltn_input.json                  ││
│  └───────────────────────────────────────────────────────────────────│
│                    ▲                    ▲                            │
│         writes     │          reads     │         writes             │
│                    │                    │                            │
│  ┌─────────────────┴────────┐  ┌────────┴─────────────────┐        │
│  │    Process 1: Controller │  │    Process 2: Touch UI   │        │
│  │    (Core 1 - RT Priority)│  │    (Core 3)              │        │
│  │                          │  │                          │        │
│  │  ┌──────────────────────┐│  │  ┌──────────────────────┐│        │
│  │  │ Control Threads      ││  │  │ PyQt5 Application    ││        │
│  │  │ - ControlThread      ││  │  │ - Touch events       ││        │
│  │  │ - EventThread        ││  │  │ - UI rendering       ││        │
│  │  │ - ActuatorManager    ││  │  │ - Button widgets     ││        │
│  │  │ - SCRAMSequence      ││  │  └──────────────────────┘│        │
│  │  │ - AutoSimThread      ││  │                          │        │
│  │  └──────────────────────┘│  │  CPU: ~30%              │        │
│  │                          │  │  Affinity: Core 3        │        │
│  │  CPU: ~30%              │  └──────────────────────────┘        │
│  │  Affinity: Core 1        │                                      │
│  │  Priority: -10           │                                      │
│  └──────────────────────────┘                                      │
│                                                                      │
│                    ▼ reads state                                    │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │                    Process 3: Video Display                      ││
│  │                    (Core 2)                                      ││
│  │                                                                  ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ││
│  │  │ Video Player    │  │ Animation       │  │ State Overlay   │  ││
│  │  │ (pygame/ffmpeg) │  │ (sprites/gauge) │  │ (text/meters)   │  ││
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  ││
│  │                                                                  ││
│  │  CPU: ~40%                                                       ││
│  │  Affinity: Core 2                                                ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Core 0: System (pigpiod, systemd, kernel threads)                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Thread-to-Core Mapping (Detailed)

| Thread/Process | Core | Priority | Frequency | Rationale |
|----------------|------|----------|-----------|-----------|
| **Core 0** | | | | |
| Linux kernel | 0 | System | - | Cannot move |
| pigpiod | 0 | Normal | 1kHz (DMA) | Shared IO |
| StateExportThread | 0 | Normal | 10 Hz | IO-bound |
| HealthThread | 0 | Low | Passive | Background |
| **Core 1 (RT)** | | | | |
| ControlThread | 1 | -10 | 20 Hz | Safety-critical |
| EventThread | 1 | -10 | Event | Fast response |
| ActuatorManager | 1 | -10 | On-demand | Real-time control |
| SCRAMSequence | 1 | -20 | Emergency | Highest priority |
| AutoSimThread | 1 | -5 | Choreographed | Smooth animation |
| **Core 2** | | | | |
| video_display_app | 2 | Normal | 60 FPS | Isolated |
| FFmpeg decode | 2 | Normal | 30 FPS | Heavy decode |
| Pygame render | 2 | Normal | 60 FPS | Display |
| **Core 3** | | | | |
| touch_panel.py | 3 | Normal | Event | UI responsive |
| Qt event loop | 3 | Normal | 60 FPS | Animations |
| Touch handler | 3 | -5 | On-touch | Fast feedback |

---

## ⚡ Performance Optimizations

### 1. Thread Pool untuk IO Operations

```python
from concurrent.futures import ThreadPoolExecutor

class IOThreadPool:
    """Dedicated thread pool for IO operations (Core 0)"""
    
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        # Set affinity for worker threads
        for worker in self.executor._threads:
            os.sched_setaffinity(worker.native_id, [0])
    
    def submit_io(self, func, *args):
        """Submit IO-bound task"""
        return self.executor.submit(func, *args)
```

### 2. Real-Time Scheduling untuk Control Loop

```python
import ctypes

SCHED_FIFO = 1
SCHED_RR = 2

class SchedParam(ctypes.Structure):
    _fields_ = [('sched_priority', ctypes.c_int)]

def set_realtime_priority(thread, priority=50):
    """Set real-time scheduling for control thread
    
    Note: Requires root or CAP_SYS_NICE capability
    """
    try:
        libc = ctypes.CDLL('libc.so.6', use_errno=True)
        param = SchedParam(priority)
        
        # Set SCHED_FIFO (first-in-first-out real-time)
        result = libc.sched_setscheduler(
            thread.native_id, 
            SCHED_FIFO, 
            ctypes.byref(param)
        )
        
        if result == 0:
            print(f"Thread {thread.name} set to RT priority {priority}")
        else:
            print(f"Failed to set RT priority")
    except Exception as e:
        print(f"RT scheduling not available: {e}")
```

### 3. CPU Governor untuk Consistent Performance

```bash
# Set performance governor (no frequency scaling)
echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Or add to /boot/config.txt:
force_turbo=1
arm_freq=1800
```

### 4. IRQ Affinity untuk Network/USB

```bash
# Move USB interrupts to Core 0 (away from control core)
echo 1 > /proc/irq/49/smp_affinity  # USB IRQ

# Move network to Core 0
echo 1 > /proc/irq/51/smp_affinity  # ETH IRQ
```

---

## 📊 Monitoring & Profiling

### CPU Usage per Core

```python
import psutil

def monitor_cpu_per_core():
    """Monitor CPU usage per core"""
    while True:
        usage = psutil.cpu_percent(interval=1, percpu=True)
        print(f"Core 0 (Sys): {usage[0]:5.1f}%  |  "
              f"Core 1 (Ctrl): {usage[1]:5.1f}%  |  "
              f"Core 2 (Video): {usage[2]:5.1f}%  |  "
              f"Core 3 (UI): {usage[3]:5.1f}%")
```

### Process Monitoring Dashboard

```python
def get_process_stats():
    """Get stats for all PLTN processes"""
    stats = {}
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'cpu_affinity']):
        if 'pltn' in proc.info['name'].lower() or 'python' in proc.info['name'].lower():
            stats[proc.info['pid']] = {
                'name': proc.info['name'],
                'cpu': proc.info['cpu_percent'],
                'affinity': proc.info['cpu_affinity']
            }
    return stats
```

---

## 📝 Task Breakdown

### Phase 1: Infrastructure
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| CPU-001 | pkm-simulator-PLTN-515 | Add psutil dependency | Install psutil untuk CPU management |
| CPU-002 | pkm-simulator-PLTN-dta | Create cpu_manager.py | Utility module untuk affinity/priority |
| CPU-003 | pkm-simulator-PLTN-cat | Add CPU monitoring | Dashboard untuk monitoring per-core usage |

### Phase 2: Process Affinity
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| CPU-010 | pkm-simulator-PLTN-ejt | Configure Controller affinity | Set Core 1 + RT priority untuk controller |
| CPU-011 | pkm-simulator-PLTN-su6 | Configure Video affinity | Set Core 2 untuk video_display_app |
| CPU-012 | pkm-simulator-PLTN-pym | Configure Touch affinity | Set Core 3 untuk touch_panel (setelah #1) |
| CPU-013 | pkm-simulator-PLTN-rl1 | Configure System affinity | Move IO threads ke Core 0 |

### Phase 3: Systemd Services
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| CPU-020 | pkm-simulator-PLTN-h14 | Create pltn-controller.service | Systemd unit dengan CPUAffinity |
| CPU-021 | pkm-simulator-PLTN-4nq | Create pltn-video.service | Systemd unit untuk video display |
| CPU-022 | pkm-simulator-PLTN-b5i | Create pltn-touch.service | Systemd unit untuk touchscreen |
| CPU-023 | pkm-simulator-PLTN-2yv | System startup optimization | CPU governor, IRQ affinity |

### Phase 4: Testing & Tuning
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| CPU-030 | pkm-simulator-PLTN-2gc | Baseline measurement | Measure CPU usage sebelum optimization |
| CPU-031 | pkm-simulator-PLTN-xhs | Stress test | Test semua proses berjalan |
| CPU-032 | pkm-simulator-PLTN-gd0 | Latency measurement | Measure actuator response time |
| CPU-033 | pkm-simulator-PLTN-ujr | Fine-tune priorities | Adjust nice values |

---

## ⚠️ Pertimbangan

### Thermal Management

Dengan CPU cores loaded lebih merata, thermal harus diperhatikan:

```python
def get_cpu_temp():
    """Get CPU temperature"""
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
        return int(f.read()) / 1000.0  # Convert to Celsius

# Throttle video FPS if temp > 70°C
if get_cpu_temp() > 70:
    pygame.time.set_timer(RENDER_EVENT, 33)  # 30 FPS instead of 60
```

### Python GIL Limitation

Python threading dibatasi oleh GIL, sehingga:
- True parallelism hanya dengan **multiprocessing**
- Current architecture sudah 3 processes (controller, video, touch)
- Threading dalam satu process tetap bergantian

### CAP_SYS_NICE Requirement

Untuk set real-time priority, perlu:
```bash
# Add capability to Python
sudo setcap cap_sys_nice=eip /usr/bin/python3
```

---

## 📅 Dependency dengan Pengembangan Lain

- **Setelah Pengembangan #1**: touch_panel.py sudah ada (Core 3)
- **Setelah Pengembangan #2**: ActuatorManager sudah ada (simplify Core 1)
- **Setelah Pengembangan #0**: Modular code easier to profile

---

## 🎯 Target Metrics

| Metric | Sebelum | Target |
|--------|---------|--------|
| Control loop latency | ~50ms (variable) | <20ms (consistent) |
| SCRAM response time | ~100ms | <50ms |
| Video frame drops | 10-20% | <5% |
| Touch response | ~80ms | <30ms |
| CPU temp under load | 75°C | <70°C |

---

*Terakhir diupdate: 2026-03-23*
