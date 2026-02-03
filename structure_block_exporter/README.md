# Export Structures From Structure Blocks (Amulet Operation)

This repository contains an **Amulet Map Editor operation** that automatically exports Minecraft structures based on **Structure Blocks** placed in a world.

Instead of manually selecting regions, the script scans the current selection for structure blocks, reads their configured size and offset, and exports each structure to its own file.

The operation supports both **Bedrock `.mcstructure`** files and **Java structure template `.nbt`** files.

---

## What This Script Does

When you run the operation in Amulet:

1. It scans the **current selection** for all `structure_block` block entities.
2. For each structure block found:
   - Reads its **identifier** (e.g. `mystructure:house_01`)
   - Reads its **offset** and **size**
   - Computes the exact structure bounding box
3. Exports that region as a structure file:
   - One file per structure block
   - File is named after the identifier **without the namespace**
     - `mystructure:house_01` → `house_01.mcstructure`
4. Repeats this for every structure block in the selection.

This makes it easy to batch-export many structures in one pass.

---

## Supported Export Formats

### Bedrock `.mcstructure`
- Uses Amulet’s `MCStructureFormatWrapper`
- Correctly applies:
  - Block states
  - Block entities
  - Entities (optional)
- Uses the **exact Bedrock version you specify** (important for rotations and newer blocks)

### Java `.nbt` (Structure Template)
- Writes a Java structure-template NBT file
- Includes:
  - Palette
  - Blocks
  - Block entities
  - Entities (optional)
- Supports “entities-only” export by skipping blocks

---

## Operation Parameters

### Export Path Prefix
**Type:** `file_save`

Path used as the base for exported files.

Examples:
- `C:/exports/structures/house_`
- `D:/mc/exports/`

The script will:
- Use the folder part as the output directory
- Ignore the filename portion and replace it with the structure name

---

### Include Entities
**Type:** `bool`  
**Default:** `true`

Controls whether entities are included in the exported structure.

- `true` → mobs, item frames, etc. are exported
- `false` → only blocks (and block entities) are exported

Applies to **both** `.mcstructure` and `.nbt`.

---

### Remove Blocks
**Type:** `bool`  
**Default:** `false`

If enabled:
- Blocks are skipped
- Only entities are written

⚠️ This option **only applies to `.nbt` export**.  
Bedrock `.mcstructure` files always contain blocks.

---

### Format (mcstructure|nbt)
**Type:** `str`  
**Default:** `mcstructure`

Controls the output file type.

Accepted values:
- `mcstructure`
- `nbt`

Any other value falls back to `mcstructure`.

---

### Bedrock Version
**Type:** `str`  
**Default:** `1.21.132`

The Bedrock version used when writing `.mcstructure` files.

This is **critical** for correctness:
- Wrong versions can cause:
  - Missing blocks
  - Incorrect rotations (especially doors)
  - State mismatches

Use the exact version of the world you opened in Amulet.

---

### Debug
**Type:** `bool`  
**Default:** `false`

When enabled:
- Prints detailed information about:
  - Structure block NBT
  - Parsed identifiers / sizes
  - Export version being used
- Useful for troubleshooting translation or parsing issues

---

## Filename Behavior

Structure block identifiers are usually namespaced:

`mystructure:house_01`


For exported files, the **namespace is stripped**:

`house_01.mcstructure
house_01.nbt`


This avoids cluttered filenames while keeping identifiers intact internally.

---

## Requirements

- Amulet Map Editor `0.10.x`
- Bedrock or Java worlds supported by Amulet
- Python environment bundled with Amulet

---

## Known Limitations

- Custom or very new Bedrock blocks may not export correctly if Amulet’s translators do not yet support them.
- Door rotations and multi-block state correctness depend on accurate Bedrock version mapping.
- “Remove Blocks” is not supported for `.mcstructure`.

---

## License

MIT (or whatever license you choose)
