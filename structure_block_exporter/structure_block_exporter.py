from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple, Optional, Any

from amulet.api.selection import SelectionGroup, SelectionBox
from amulet.api.level import BaseLevel
from amulet.api.data_types import Dimension
from amulet.api.errors import ChunkLoadError

from amulet.level.formats.mcstructure import MCStructureFormatWrapper

import amulet_nbt as nbt


# ============================================================
# Helpers: filenames / paths
# ============================================================

def _safe_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "unnamed"
    name = name.replace("\\", "_").replace("/", "_").replace(":", "_")
    name = re.sub(r"[^\w\-. ]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:150]

def _strip_namespace(identifier: str) -> str:
    """
    Convert 'namespace:name' -> 'name'
    If no namespace is present, return as-is.
    """
    if not identifier:
        return identifier
    if ":" in identifier:
        return identifier.split(":", 1)[1]
    return identifier



def _unique_path(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(filename)
    i = 1
    while True:
        candidate = os.path.join(directory, f"{root}_{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _split_export_prefix(prefix: str) -> Tuple[str, str]:
    """
    'file_save' options typically return a file path.
    We treat it as:
      out_dir  = dirname(prefix) (or cwd)
      base_pre = basename(prefix) (or "structure")
    """
    prefix = (prefix or "").strip().replace("\\", "/")
    if not prefix:
        return os.getcwd(), "structure"

    if prefix.endswith("/"):
        return prefix.rstrip("/"), "structure"

    directory = os.path.dirname(prefix) or os.getcwd()
    base = os.path.basename(prefix) or "structure"
    return directory, base


def _parse_bedrock_version(s: str) -> Optional[Tuple[int, int, int]]:
    """
    Accepts:
      "1.21.132"
      "1,21,132"
      "1 21 132"
    Returns (major, minor, patch) or None.
    """
    if not s:
        return None
    s = str(s).strip().replace(",", ".")
    # turn any non-digit into dots, then split
    cleaned = "".join(ch if ch.isdigit() else "." for ch in s)
    parts = [p for p in cleaned.split(".") if p.isdigit()]
    if len(parts) >= 3:
        return int(parts[0]), int(parts[1]), int(parts[2])
    return None


# ============================================================
# Helpers: NBT traversal / fuzzy lookup (for Structure Block BE)
# ============================================================

def _nbt_value(v: Any):
    return getattr(v, "value", v)


def _iter_nbt_tree(tag: Any, prefix: str = ""):
    """
    Yield (path, key, value) for all nested tags in an NBT compound/list tree.
    Compatible with amulet_nbt.
    """
    # CompoundTag-like
    try:
        keys = list(tag.keys())
        for k in keys:
            v = tag[k]
            path = f"{prefix}/{k}" if prefix else str(k)
            yield (path, k, v)
            if hasattr(v, "keys"):
                yield from _iter_nbt_tree(v, path)
            else:
                try:
                    if getattr(v, "tag_id", None) == nbt.TAG_List or isinstance(v, (list, tuple)):
                        yield from _iter_nbt_tree(v, path)
                except Exception:
                    pass
        return
    except Exception:
        pass

    # ListTag / list-like
    try:
        for i, v in enumerate(tag):
            path = f"{prefix}[{i}]"
            yield (path, str(i), v)
            if hasattr(v, "keys"):
                yield from _iter_nbt_tree(v, path)
            else:
                try:
                    if getattr(v, "tag_id", None) == nbt.TAG_List or isinstance(v, (list, tuple)):
                        yield from _iter_nbt_tree(v, path)
                except Exception:
                    pass
    except Exception:
        return


def _find_first_str(tag: Any, key_substrings: Tuple[str, ...]) -> Optional[str]:
    for _path, k, v in _iter_nbt_tree(tag):
        lk = str(k).lower()
        if any(s in lk for s in key_substrings):
            val = _nbt_value(v)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _find_first_int(tag: Any, key_substrings: Tuple[str, ...]) -> Optional[int]:
    for _path, k, v in _iter_nbt_tree(tag):
        lk = str(k).lower()
        if any(s in lk for s in key_substrings):
            try:
                return int(_nbt_value(v))
            except Exception:
                continue
    return None


def _parse_structure_block(tag: Any) -> Optional[Dict]:
    """
    Try to find identifier/name + offset + size anywhere in the tag tree.
    This is needed because your build showed only a few top-level keys.
    """
    name = _find_first_str(tag, ("structurename", "structure_name", "name", "identifier"))
    if not name:
        return None

    ox = _find_first_int(tag, ("xstructureoffset", "structureoffsetx", "offsetx", "posx"))
    oy = _find_first_int(tag, ("ystructureoffset", "structureoffsety", "offsety", "posy"))
    oz = _find_first_int(tag, ("zstructureoffset", "structureoffsetz", "offsetz", "posz"))

    sx = _find_first_int(tag, ("xstructuresize", "structuresizex", "sizex", "size_x"))
    sy = _find_first_int(tag, ("ystructuresize", "structuresizey", "sizey", "size_y"))
    sz = _find_first_int(tag, ("zstructuresize", "structuresizez", "sizez", "size_z"))

    if None in (ox, oy, oz, sx, sy, sz):
        return None
    if sx <= 0 or sy <= 0 or sz <= 0:
        return None

    return {"name": name, "offset": (ox, oy, oz), "size": (sx, sy, sz)}


def _debug_print_structure_block(tag: Any):
    try:
        print("NBTag top keys:", list(tag.keys()))
    except Exception:
        print("NBTag:", tag)

    hits = 0
    for path, k, v in _iter_nbt_tree(tag):
        lk = str(k).lower()
        if any(s in lk for s in ("name", "size", "offset", "pos")):
            print(f"  {path} = {_nbt_value(v)}")
            hits += 1
            if hits > 120:
                print("  ... (truncated)")
                break


# ============================================================
# World scanning
# ============================================================

def _is_structure_block(world: BaseLevel, dimension: Dimension, x: int, y: int, z: int) -> bool:
    try:
        blk = world.get_block(x, y, z, dimension)
        return getattr(blk, "base_name", None) == "structure_block"
    except Exception:
        return False


def _iter_structure_blocks(
    world: BaseLevel, dimension: Dimension, selection: SelectionGroup, debug: bool
) -> List[Tuple[Tuple[int, int, int], Any, Optional[Dict]]]:
    boxes = list(selection)

    def in_any_box(x: int, y: int, z: int) -> bool:
        for b in boxes:
            if b.min_x <= x < b.max_x and b.min_y <= y < b.max_y and b.min_z <= z < b.max_z:
                return True
        return False

    out: List[Tuple[Tuple[int, int, int], Any, Optional[Dict]]] = []

    for cx, cz in selection.chunk_locations():
        try:
            chunk = world.get_chunk(cx, cz, dimension)
        except ChunkLoadError:
            continue

        bes = getattr(chunk, "block_entities", None) or {}
        for (x, y, z), be in bes.items():
            if not in_any_box(x, y, z):
                continue
            if not _is_structure_block(world, dimension, x, y, z):
                continue

            tag = getattr(be, "nbt", None)
            if tag is None:
                if debug:
                    print("---- DEBUG: Structure block has no NBT at", (x, y, z))
                continue

            parsed = _parse_structure_block(tag)

            if debug:
                print("---- DEBUG: Found structure block at", (x, y, z))
                print("BlockEntity type:", getattr(be, "namespace", None), getattr(be, "base_name", None))
                if parsed is None:
                    print("Parse FAILED. NBT paths containing name/size/offset/pos:")
                    _debug_print_structure_block(tag)
                else:
                    print("Parse OK:", parsed)

            out.append(((x, y, z), tag, parsed))

    return out


# ============================================================
# Export: .mcstructure (Bedrock)
# ============================================================

def _export_mcstructure(
    world: BaseLevel,
    dimension: Dimension,
    region: SelectionGroup,
    out_path: str,
    include_entities: bool,
    bedrock_version_str: str,
    debug: bool,
):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    wrapper = MCStructureFormatWrapper(out_path)

    version = _parse_bedrock_version(bedrock_version_str) or (1, 21, 132)
    if debug:
        print("MCSTRUCTURE export version:", version)

    wrapper.create_and_open("bedrock", version, region, include_entities)
    wrapper.translation_manager = world.translation_manager
    wrapper_dimension = wrapper.dimensions[0]

    for (cx, cz) in region.chunk_locations():
        try:
            chunk = world.get_chunk(cx, cz, dimension)
        except ChunkLoadError:
            continue
        wrapper.commit_chunk(chunk, wrapper_dimension)

    wrapper.save()
    wrapper.close()


# ============================================================
# Export: Java structure-template .nbt
# ============================================================

def _state_key(block) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    namespace = getattr(block, "namespace", "minecraft")
    base_name = getattr(block, "base_name", "air")
    props = getattr(block, "properties", {}) or {}
    props_items = tuple(sorted((str(k), str(v)) for k, v in props.items()))
    return (f"{namespace}:{base_name}", props_items)


def _universal_block_to_java_state(block) -> nbt.CompoundTag:
    namespace = getattr(block, "namespace", "minecraft")
    base_name = getattr(block, "base_name", "air")
    name = f"{namespace}:{base_name}"
    props = getattr(block, "properties", {}) or {}
    if props:
        props_tag = nbt.CompoundTag({str(k): nbt.StringTag(str(v)) for k, v in props.items()})
        return nbt.CompoundTag({"Name": nbt.StringTag(name), "Properties": props_tag})
    return nbt.CompoundTag({"Name": nbt.StringTag(name)})


def _collect_block_entities_in_box(world: BaseLevel, dimension: Dimension, box: SelectionBox) -> Dict[Tuple[int, int, int], Any]:
    out: Dict[Tuple[int, int, int], Any] = {}
    for cx, cz in SelectionGroup(box).chunk_locations():
        try:
            chunk = world.get_chunk(cx, cz, dimension)
        except ChunkLoadError:
            continue
        bes = getattr(chunk, "block_entities", None) or {}
        for (x, y, z), be in bes.items():
            if box.min_x <= x < box.max_x and box.min_y <= y < box.max_y and box.min_z <= z < box.max_z:
                out[(x, y, z)] = be
    return out


def _export_java_structure_nbt(
    world: BaseLevel,
    dimension: Dimension,
    box: SelectionBox,
    out_path: str,
    include_entities: bool,
    remove_blocks: bool,
):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    origin_x, origin_y, origin_z = box.min_x, box.min_y, box.min_z
    sx = box.max_x - box.min_x
    sy = box.max_y - box.min_y
    sz = box.max_z - box.min_z

    palette: List[nbt.CompoundTag] = []
    palette_index: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}

    def get_state_index(block) -> int:
        key = _state_key(block)
        if key in palette_index:
            return palette_index[key]
        idx = len(palette)
        palette_index[key] = idx
        palette.append(_universal_block_to_java_state(block))
        return idx

    be_map = _collect_block_entities_in_box(world, dimension, box)
    blocks_list: List[nbt.CompoundTag] = []

    # NOTE: remove_blocks only applies to .nbt export.
    for y in range(box.min_y, box.max_y):
        for z in range(box.min_z, box.max_z):
            for x in range(box.min_x, box.max_x):
                if remove_blocks:
                    continue

                blk = world.get_block(x, y, z, dimension)
                if getattr(blk, "base_name", "air") == "air":
                    continue

                state_idx = get_state_index(blk)

                rel_x = x - origin_x
                rel_y = y - origin_y
                rel_z = z - origin_z

                entry = {
                    "pos": nbt.IntArrayTag([rel_x, rel_y, rel_z]),
                    "state": nbt.IntTag(state_idx),
                }

                be = be_map.get((x, y, z))
                if be is not None and getattr(be, "nbt", None) is not None:
                    tag = be.nbt
                    try:
                        tag = tag.copy()
                        for k in ("x", "y", "z"):
                            if k in tag:
                                del tag[k]
                    except Exception:
                        pass
                    entry["nbt"] = tag

                blocks_list.append(nbt.CompoundTag(entry))

    entities_list: List[nbt.CompoundTag] = []
    if include_entities:
        for cx, cz in SelectionGroup(box).chunk_locations():
            try:
                chunk = world.get_chunk(cx, cz, dimension)
            except ChunkLoadError:
                continue

            ents = getattr(chunk, "entities", None)
            if not ents:
                continue

            for ent in ents:
                ent_nbt = getattr(ent, "nbt", None)
                if ent_nbt is None:
                    continue

                try:
                    pos_tag = ent_nbt.get("Pos", None)
                    if pos_tag is None or len(pos_tag) != 3:
                        continue
                    ex = float(pos_tag[0].value)
                    ey = float(pos_tag[1].value)
                    ez = float(pos_tag[2].value)
                except Exception:
                    continue

                if not (box.min_x <= ex < box.max_x and box.min_y <= ey < box.max_y and box.min_z <= ez < box.max_z):
                    continue

                rx, ry, rz = ex - origin_x, ey - origin_y, ez - origin_z
                bx, by, bz = int(ex) - origin_x, int(ey) - origin_y, int(ez) - origin_z

                entities_list.append(
                    nbt.CompoundTag(
                        {
                            "pos": nbt.DoubleArrayTag([rx, ry, rz]),
                            "blockPos": nbt.IntArrayTag([bx, by, bz]),
                            "nbt": ent_nbt,
                        }
                    )
                )

    root = nbt.CompoundTag(
        {
            "size": nbt.IntArrayTag([sx, sy, sz]),
            "palette": nbt.ListTag(palette, list_data_type=nbt.TAG_Compound),
            "blocks": nbt.ListTag(blocks_list, list_data_type=nbt.TAG_Compound),
            "entities": nbt.ListTag(entities_list, list_data_type=nbt.TAG_Compound),
        }
    )

    nbt.save_to(out_path, root, compressed=True)


# ============================================================
# Operation entry point
# ============================================================

def export_structures_from_structure_blocks(
    world: BaseLevel, dimension: Dimension, selection: SelectionGroup, options: dict
):
    export_prefix = options.get("Export Path Prefix", "")
    out_dir, _base_prefix = _split_export_prefix(export_prefix)

    debug = bool(options.get("Debug", False))
    include_entities = bool(options.get("Include Entities", True))
    remove_blocks = bool(options.get("Remove Blocks", False))

    bedrock_version_str = str(options.get("Bedrock Version", "1.21.132")).strip()

    fmt_raw = str(options.get("Format (mcstructure|nbt)", "mcstructure")).strip().lower()
    if fmt_raw not in ("mcstructure", "nbt"):
        fmt_raw = "mcstructure"

    os.makedirs(out_dir, exist_ok=True)

    # 1) Find structure blocks in selection
    found = _iter_structure_blocks(world, dimension, selection, debug=debug)
    parsed = [((x, y, z), data) for ((x, y, z), _tag, data) in found if data is not None]

    if not parsed:
        print("No structure blocks with valid name/size found inside selection.")
        print("Tip: enable Debug to see what NBT Amulet exposes for your Structure Blocks.")
        return

    total = len(parsed)
    print(f"Exporting {total} structure(s) to {out_dir} as {fmt_raw}...")

    # 2) Export each structure
    for i, ((bx, by, bz), data) in enumerate(parsed, start=1):
        name = data["name"]
        ox, oy, oz = data["offset"]
        sx, sy, sz = data["size"]

        min_x = bx + ox
        min_y = by + oy
        min_z = bz + oz
        max_x = min_x + sx
        max_y = min_y + sy
        max_z = min_z + sz

        box = SelectionBox((min_x, min_y, min_z), (max_x, max_y, max_z))
        region = SelectionGroup(box)
        safe = _safe_filename(_strip_namespace(name))

        try:
            if fmt_raw == "mcstructure":
                out_path = _unique_path(out_dir, f"{safe}.mcstructure")
                _export_mcstructure(
                    world,
                    dimension,
                    region,
                    out_path,
                    include_entities=include_entities,
                    bedrock_version_str=bedrock_version_str,
                    debug=debug,
                )
                print(f"[{i}/{total}] Exported mcstructure: {out_path}")
            else:
                out_path = _unique_path(out_dir, f"{safe}.nbt")
                _export_java_structure_nbt(
                    world,
                    dimension,
                    box,
                    out_path,
                    include_entities=include_entities,
                    remove_blocks=remove_blocks,
                )
                print(f"[{i}/{total}] Exported nbt: {out_path}")

        except Exception as e:
            print(f"[{i}/{total}] Failed to export '{name}' at ({bx},{by},{bz}): {e}")

        yield i / total


# ============================================================
# Amulet operation registration
# ============================================================

operation_options = {
    # Uses Amulet's file picker; we interpret it as "directory + prefix"
    "Export Path Prefix": ["file_save", "C:/temp/structures/structure_"],

    # Your requested toggles
    "Include Entities": ["bool", True],
    "Remove Blocks": ["bool", False],

    # No "choice" type in your build, so use a string field.
    # Enter exactly: mcstructure OR nbt
    "Format (mcstructure|nbt)": ["str", "mcstructure"],

    # IMPORTANT for Bedrock correctness (doors, some block states, etc.)
    "Bedrock Version": ["str", "1.21.132"],

    # Debug output for structure block NBT parsing + selected export version
    "Debug": ["bool", False],
}

export = {
    "name": "Structure Block Exporter",
    "operation": export_structures_from_structure_blocks,
    "options": operation_options,
}
