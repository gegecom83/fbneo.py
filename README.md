# FinalBurn Neo [Libretro]

A Python/PyQt6 graphical frontend to launch ROMs via **RetroArch** and the **FinalBurn Neo (fbneo_libretro)** core.

---

## Requirements

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [RetroArch](https://www.retroarch.com/) installed
- The `fbneo_libretro` core (`.dll` / `.so` / `.dylib`)

Install Python dependencies:

```bash
pip install PyQt6
```

---

## Launch

```bash
python fbneo.py
```

---

## Supported Systems

| System |
|---|
| Arcade |
| Bally Astrocade Home Computer |
| CBS ColecoVision |
| Fairchild ChannelF |
| MSX 1 |
| Nec PC-Engine |
| Nec PC-Engine CD |
| Nec SuperGrafX |
| Nec TurboGrafx-16 |
| Nintendo Entertainment System |
| Nintendo Family Disk System |
| Nintendo Game Boy Advance |
| Super Nintendo Entertainment System |
| Sega GameGear |
| Sega Master System |
| Sega Megadrive |
| Sega SG-1000 |
| SNK Neo-Geo CD |
| SNK Neo-Geo Pocket |
| ZX Spectrum |

---

## File Structure

```
fbneo.py                   # Main script
config.json                # Configuration (auto-generated)
debug.log                  # Debug Mode (checkbox in the UI)
icon.ico / icon.png        # Icon

```

### XML/DAT Files

ROM metadata (title, year, manufacturer, clones) is read from FBNeo-compatible XML DAT files. Entries marked `isbios="yes"` are automatically excluded.

If no DAT file is provided for a system, the raw ROM filename is displayed.

---

## Configuration

On first launch, a `config.json` file is created automatically. It can then be edited via the **Settings** button in the interface.

Available settings:

- **RetroArch Executable** — path to the RetroArch binary
- **RetroArch Core** — path to `fbneo_libretro.dll` / `.so` / `.dylib`
- **ROMs Folder** — ROM directory for each system
- **XML/DAT File** — metadata file for each system
- **Title Image Folder** — folder containing title screenshots (PNG)
- **Preview Image Folder** — folder containing preview screenshots (PNG)
- **Display only the ROM list** — hide the image tabs

---

## Usage

### Main Window

- **System selector** — choose the system to browse
- **Search** — filter ROMs by name
- **Year / Manufacturer** — additional filters from the DAT file
- **Hide Clones** — hide clone ROMs
- **Debug Mode** — A dialog box displays the command before execution, with OK/Cancel options and a log file is generated
- **Double-click** or **Enter** — launch the selected ROM
- **Right-click** — add the ROM to favorites
- **Tooltip** — hovering over a game shows the ROM filename
- **F11** — toggle fullscreen
- **Tab** — open the About dialog

### Favorites

The **Favorites** button opens a list of favorite ROMs across all systems. Double-click or press Enter to launch directly. Right-click to remove from the list.

### Images

Title and preview images are looked up in the configured folders using the following naming convention:

```
<system_prefix><rom_name>.png
```

Example prefixes: `nes_`, `md_`, `snes_`, `pce_`, `gg_`...

---

## Supported ROM Formats

- `.zip`
- `.7z`
- `.cue` (Neo-Geo CD / PC-Engine CD — recursive folder search)
- `.chd` (Neo-Geo CD / PC-Engine CD — recursive folder search)

---
