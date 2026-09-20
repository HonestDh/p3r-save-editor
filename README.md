# Persona 3 Reload Save Editor

A GUI tool for decoding and editing **Persona 3 Reload** (Steam/PC) save files.

## Overview

P3R save files (`SaveDataNNN.sav`) are Unreal Engine 4.27 GVAS containers wrapped in simple obfuscation:
- XOR with 31-byte key `ae5zeitaix1joowooNgie3fahP5Ohph`
- Bit swap: positions 0-1 ↔ 4-5

This editor removes the wrapper, parses the GVAS tree, and exposes all game data through a Tkinter interface.

## Features

- **Gameplay**: Money, social stats (Academics/Charm/Courage), 22 social links, difficulty
- **Party**: Level, HP, SP, EXP for all 10 party members; party formation
- **Items**: 9 categories (Weapons/Armor/Footwear/Accessories/Items/Event Items/Materials/Skill Cards/Costumes) with search/filter
- **Personas**: 12-slot stock with 5 stats and 8 skill slots; place any persona from the database
- **Compendium**: Register/unregister all 194 personas
- **Raw area**: Direct access to all `SaveDataArea` words
- **Export**: Decoded GVAS and JSON dumps
- **Backup**: Auto-creates `./backup/` on save

## Requirements

- Python 3.10+ (standard library only, no external dependencies)

## Usage

```bash
python p3r_editor.pyw "path/to/SaveData007.sav"
```

Or launch the GUI and use **File → Open**.

## File Structure

| File | Purpose |
|------|---------|
| `p3r_codec.py` | XOR + bit-swap obfuscation (decode/encode) |
| `p3r_gvas.py` | GVAS container reader/writer (UE 4.27) |
| `p3r_fields.py` | Index tables for `SaveDataArea` |
| `p3r_data.py` | Inventory, persona stock, compendium, formation |
| `p3r_editor.pyw` | Tkinter GUI |
| `data/items.json` | 4352 item records |
| `data/personas.json` | 194 persona records |
| `data/skills.json` | Skill database |

## Format Notes

- `SaveDataArea` is a sparse `UInt32Property` array with numeric indices
- Version 1 uses indices as-is; Version 2 adds `+4` offset
- All gameplay values are stored in this single array

## Credits

Index tables and data files based on:
- [Luckyseer/p3r-save-editor](https://github.com/Luckyseer/p3r-save-editor)
- [illusionyy/P3R-Save-EnDecryptor](https://github.com/illusionyy/P3R-Save-EnDecryptor)
- [afkaf/Python-GVAS-JSON-Converter](https://github.com/afkaf/Python-GVAS-JSON-Converter)

Persona 3 Reload is a trademark of ATLUS/SEGA. This project is for educational purposes and not affiliated with the rights holders.

## Warning

Save editing may cause corruption or softlocks. Backups are created automatically, but use at your own risk.

## License

MIT
