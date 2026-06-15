---
name: Path-Fixer
description: Cross-platform path validation (Windows backslash vs Linux). Detects .PNG/.JPG uppercase extensions and hardcoded Windows paths incompatible with Raspberry Pi.
---

# Skill: Cross-Platform Path Fixer

## 🎯 Kapan Digunakan

**Gunakan skill ini ketika:**
- Ada kode Python yang menggunakan hardcoded Windows paths dengan backslash (`\`)
- File gambar/aset menggunakan uppercase ekstensi (`.PNG`, `.JPG`, `.JPEG`)
- Code akan di-deploy dari Windows ke Linux/Raspberry Pi
- Testing di Windows tapi eksekusi final di Raspberry Pi
- Melakukan refactor untuk portabilitas cross-platform

**Contoh trigger kata kunci:**
- "ada error gambar di Raspberry Pi tapi lancar di Windows"
- "path tidak bisa dibaca di Linux"
- "aset tidak ditemukan saat eksekusi"
- "hardcoded path Windows"

---

## ❌ Anti-Pattern (Windows-Only, Tidak Portable)

### Masalah 1: Backslash Hardcoded

```python
# ❌ SALAH - Hanya work di Windows
image_path = "assets\reactor_schematic.png"
reactor_img = Image.open(image_path)

# ❌ SALAH - String mentah dengan backslash
config_file = "C:\Users\Admin\project\config.json"
```

**Hasil di Linux:** `FileNotFoundError`, karena `/` tidak di-escape, path tidak valid.

### Masalah 2: Uppercase Ekstensi

```python
# ❌ SALAH - Uppercase extension
logo = Image.open("assets/reactor_LOGO.PNG")
panel_bg = Image.open("images/control_PANEL.JPG")

# ❌ SALAH - Uppercase di variable path
IMG_EXT = ".PNG"
filepath = f"data/image{IMG_EXT}"
```

**Hasil di Linux:** File system case-sensitive, `.PNG` ≠ `.png`. Bahkan jika file ada dengan lowercase, pencarian uppercase fail.

---

## ✅ Pattern (Cross-Platform, Correct)

### Solusi 1: Gunakan `os.path.join()` atau `pathlib.Path`

```python
# ✅ BENAR - Portable dengan os.path.join
import os
image_path = os.path.join("assets", "reactor_schematic.png")
reactor_img = Image.open(image_path)

# ✅ BENAR - Modern approach dengan pathlib
from pathlib import Path
image_path = Path("assets") / "reactor_schematic.png"
reactor_img = Image.open(str(image_path))
```

### Solusi 2: Lowercase Semua Ekstensi

```python
# ✅ BENAR - Lowercase extension
logo = Image.open(os.path.join("assets", "reactor_logo.png"))
panel_bg = Image.open(os.path.join("images", "control_panel.jpg"))

# ✅ BENAR - Lowercase constant
IMG_EXT = ".png"
filepath = os.path.join("data", f"image{IMG_EXT}")
```

### Solusi 3: Prefix-based Path (Relative to Script)

```python
# ✅ BENAR - Relatif terhadap script location
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR / "assets"
IMAGE_FILE = ASSETS_DIR / "reactor_schematic.png"

# Load dengan pathlib
reactor_img = Image.open(str(IMAGE_FILE))
```

---

## 🔍 File-File Yang Perlu Diperhatikan

### Critical (Sering Path Issues)

- **`pltn_video_display/` directory** — Banyak PNG/JPG loading untuk UI
  - `video_display_app.py` — Background images, icons
  - `touch_panel*.py` — Touch panel UI assets
  
- **`raspi_config.py`** — Base path configuration (jika ada hardcoded paths)

- **`raspi_hmi_*.py`** — Display controller modules yang load gambar

### Secondary (Perlu dicek)

- Arduino sketches jika ada path string (serialization/SD card)
- Dokumentasi dengan contoh path (harus updated juga)

---

## 🛠️ Workflow untuk Agents

1. **Scan Phase**: Cari file Python dengan pattern:
   - `\\` (backslash) di dekat keyword: `png`, `jpg`, `aset`, `touch_panel`, `image`
   - Uppercase ekstensi: `.PNG`, `.JPG`, `.JPEG`

2. **Report Phase**: Kumpulkan semua findings dengan:
   - Nama file
   - Nomor baris
   - Snippet code yang problematic

3. **Fix Phase**: Gunakan filesystem tools untuk edit:
   - Ganti `path\to\file` → `os.path.join("path", "to", "file")`
   - Ganti `.PNG` → `.png` (lowercase semua)
   - Tambah `import os` jika perlu

4. **Verify Phase**: 
   - Test di Windows (dev environment)
   - Cross-check dengan Linux path semantics
   - Pastikan file actually exist di folder

---

## ⚠️ Edge Cases

| Case | Handling |
|------|----------|
| **Raw strings (`r"path\file"`)** | Konversi ke `os.path.join()`, jangan tinggal pakai raw string |
| **URL paths (http://)** | Skip — hanya handle file system paths |
| **Relative paths (../)** | OK, pakai `os.path.join()` atau pathlib |
| **Absolute paths (/home, C:\)** | Refactor ke relative atau env variables |
| **String concatenation** | Gunakan `os.path.join()` atau f-string dengan `/` (pathlib) |

---

## 📋 Auto-Detection Rules

Agents scanning untuk masalah harus detect:

```
✓ Backslash di line yang ada keyword: png, jpg, jpeg, aset, image, asset, file, path, image_path
✓ Uppercase: .PNG, .JPG, .JPEG, .GIF, .BMP di string literal
✓ Pattern: "C:\", "D:\", "\\", "\path" (Windows absolute/hardcoded)
✗ Skip: URL, comment, regex pattern, raw string literal tanpa perubahan
```