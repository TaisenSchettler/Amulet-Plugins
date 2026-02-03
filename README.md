# Amulet Operations Collection

This repository contains a collection of **custom operations for the Amulet Map Editor**, focused on automation, structure workflows, and advanced export utilities for Minecraft worlds.

---

## What Is Amulet?

[Amulet Map Editor](https://www.amuletmc.com/) is an open-source, multi-platform Minecraft world editor that supports both **Java Edition** and **Bedrock Edition**.

It provides:
- A universal block format
- Cross-edition conversion
- A Python-based plugin and operation system

This repository builds on top of that system.

---

## What You’ll Find Here

- Custom **Amulet operations** (drop-in `.py` files)
- Batch tools for structure export and processing
- Utilities that automate repetitive editor workflows
- Scripts designed for large-scale or technical projects

All operations are designed to be placed in: `AmuletMapEditor/plugins/operations/`


and accessed through Amulet’s **Operations** tab.

---

## Usage Notes

- Scripts are written for **Amulet 0.10.49**
- Some operations rely on:
  - Amulet Core
  - PyMCTranslate
  - Bedrock version-specific translators
- Always back up worlds before running custom operations

---

## AI-Assisted Development Notice

Some parts of the scripts in this repository were written or refined with the assistance of **AI tools**.

This includes:
- Boilerplate code
- NBT parsing helpers
- Export logic scaffolding
- Documentation drafts

All scripts were:
- Reviewed
- Tested
- Adapted to real Amulet behavior

---

## License

Unless stated otherwise, scripts in this repository are provided under the MIT License.

Feel free to adapt, modify, and reuse them in your own Amulet workflows.

---

## Credits

- Amulet Team — for Amulet Map Editor  
  https://www.amuletmc.com/
