#!/usr/bin/env python3
"""Generate the per-layer keymap diagrams in images/ from keymap.c.

Pipeline:
  keymap.c
    -> qmk c2json                      (needs QMK firmware checkout)
    -> keymap parse                    (keymap-drawer)
    -> inject combos parsed from keymap.c
    -> keymap draw -s LN               (one SVG per layer)
    -> svg2png.swift                   (rasterise via WebKit; macOS only)

Usage:
  tools/gen_layer_images.py            # regenerate images/layer_*.{svg,png}
  tools/gen_layer_images.py --check    # exit 1 if outputs would differ

Required tools (install via: pipx install keymap-drawer):
  - qmk        (must be runnable from a qmk_firmware checkout)
  - keymap     (keymap-drawer)
  - swift      (macOS only; for the SVG->PNG step. PNGs are skipped
               on non-macOS hosts.)
"""
from __future__ import annotations

import argparse
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEYMAP_C = REPO_ROOT / "layouts/ergodox/stoneman/keymap.c"
CONFIG_YAML = REPO_ROOT / "tools/keymap_drawer_config.yaml"
IMAGES_DIR = REPO_ROOT / "images"
SVG2PNG = REPO_ROOT / "tools/svg2png.swift"

# Logical (CSS px) size of the rendered SVG. Matches the keymap layout the
# drawer emits for ergodox_ez/glow with our config; see
# `<svg width=... height=...>` in any images/layer_*.svg. PNGs are rendered
# at 2x this size for crisp display on retina screens.
PNG_SIZE = (1012, 560)
PNG_SCALE = 2

KEYBOARD = "ergodox_ez/glow"
KEYMAP_NAME = "stoneman"
LAYER_NAMES = ["Main", "Func", "Emoji", "Num", "Nav", "Dota"]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def need(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        die(f"required command not found on PATH: {cmd}")
    return path


def ensure_yaml() -> None:
    """Make `import yaml` work by borrowing PyYAML from keymap-drawer's venv.

    The system python3 won't usually have PyYAML installed, but keymap-drawer
    (a hard dependency of this script) ships it. Locate that venv via the
    `keymap` shim and prepend its site-packages to sys.path.
    """
    try:
        import yaml  # noqa: F401
        return
    except ImportError:
        pass
    keymap = shutil.which("keymap")
    if not keymap:
        die("PyYAML missing and `keymap` not on PATH; install keymap-drawer "
            "(`pipx install keymap-drawer`) or `pip install pyyaml`")
    # Resolve symlinks: pipx puts the real script under .../venvs/<pkg>/bin/.
    real = Path(keymap).resolve()
    venv_root = real.parent.parent  # .../venvs/<pkg>
    candidates = list(venv_root.glob("lib/python*/site-packages"))
    for sp in candidates:
        if (sp / "yaml").is_dir():
            sys.path.insert(0, str(sp))
            return
    die("could not find PyYAML in keymap-drawer's venv; "
        "try `pip install pyyaml` (or `pipx inject keymap-drawer pyyaml --force`)")


def find_qmk_firmware() -> Path:
    """Locate the qmk_firmware checkout (qmk c2json must be run from inside it)."""
    env = os.environ.get("QMK_HOME")
    if env:
        p = Path(env).expanduser()
        if (p / "lib/python/qmk").is_dir():
            return p
        die(f"QMK_HOME='{env}' does not look like a qmk_firmware checkout")
    # Fall back to `qmk config user.qmk_home`.
    try:
        out = subprocess.check_output(
            ["qmk", "config", "-ro", "user.qmk_home"], text=True
        ).strip()
    except Exception as e:
        die(f"could not query qmk config: {e}")
    val = out.split("=", 1)[-1].strip()
    if val and val != "None":
        p = Path(val).expanduser()
        if (p / "lib/python/qmk").is_dir():
            return p
    die(
        "cannot find qmk_firmware. Set QMK_HOME env var or run "
        "`qmk config user.qmk_home=/path/to/qmk_firmware`."
    )


def run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        die(f"command failed ({proc.returncode}): {' '.join(cmd)}")


# ─────────────────────────────────────────────────────────────────────────────
# Combos
# ─────────────────────────────────────────────────────────────────────────────
# keymap-drawer's QMK parser doesn't read the C `combo_t key_combos[]` array,
# so we extract combo definitions directly from keymap.c and inject them into
# the parsed YAML. Each combo lists key positions in the flattened layer
# array (0-based, matching the order in keymap.json's "layers": [[...]]).

# Cache of (keycode -> position) computed from layer 0 of keymap.json. Combos
# fire on the base layer in this layout, so layer 0 indices are sufficient.
def load_binding_labels() -> dict[str, object]:
    """Read parse_config.raw_binding_map from our keymap-drawer config."""
    import yaml

    cfg = yaml.safe_load(CONFIG_YAML.read_text()) or {}
    return ((cfg.get("parse_config") or {}).get("raw_binding_map") or {})


def label_for(keycode: str, label_map: dict[str, object]) -> str:
    """Best-effort friendly label for a combo result keycode."""
    if keycode in label_map:
        v = label_map[keycode]
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return str(v.get("t", keycode))
    return keycode.removeprefix("KC_")


def extract_combos(
    keymap_c: str,
    layer0_keycodes: list[str],
    label_map: dict[str, object],
) -> list[dict]:
    """Extract COMBO(name, keycode) entries plus their `name_combo[]` defs."""
    # Map each base-layer keycode (e.g. "KC_F") to its index. Skip duplicates;
    # combos in this keymap involve unique letter keys.
    pos: dict[str, int] = {}
    for i, kc in enumerate(layer0_keycodes):
        pos.setdefault(kc, i)

    combos: list[dict] = []

    # Parse `const uint16_t PROGMEM <name>_combo[] = {KC_X, KC_Y, COMBO_END};`
    combo_arrays: dict[str, list[str]] = {}
    for m in re.finditer(
        r"const\s+uint16_t\s+PROGMEM\s+(\w+)_combo\[\]\s*=\s*\{([^}]+)\}",
        keymap_c,
    ):
        name = m.group(1)
        keys = [k.strip() for k in m.group(2).split(",")]
        keys = [k for k in keys if k and k != "COMBO_END"]
        combo_arrays[name] = keys

    # Parse `COMBO(<name>_combo, <result_keycode>)` entries.
    for m in re.finditer(r"COMBO\(\s*(\w+)_combo\s*,\s*([^)]+)\)", keymap_c):
        name, result = m.group(1), m.group(2).strip()
        keys = combo_arrays.get(name)
        if not keys:
            print(f"warning: combo '{name}' has no _combo[] array", file=sys.stderr)
            continue
        try:
            indices = [pos[k] for k in keys]
        except KeyError as e:
            print(
                f"warning: combo '{name}' references {e} which is not on layer 0; "
                "skipping.",
                file=sys.stderr,
            )
            continue
        # Show on the layer that contains the trigger keys (Main).
        combos.append(
            {"p": indices, "k": label_for(result, label_map), "l": [LAYER_NAMES[0]]}
        )

    return combos


def inject_combos(yaml_path: Path, combos: list[dict]) -> None:
    """Append a `combos:` section to the keymap-drawer YAML."""
    if not combos:
        return
    import yaml  # PyYAML ships with keymap-drawer's venv but not necessarily here.

    data = yaml.safe_load(yaml_path.read_text())
    data["combos"] = combos
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def resolve_transparent_keys(yaml_path: Path) -> None:
    """Replace transparent keys in non-base layers with the base-layer binding.

    keymap-drawer renders KC_TRANSPARENT as a small "▽" glyph, which makes it
    hard to see what the active key actually is on a higher layer. This walks
    each non-base layer and, for every position whose tap legend matches the
    `trans_legend` (default "▽"), substitutes the layer 0 binding for that
    position. The substituted key keeps `type: trans` so it can be styled
    differently in CSS (e.g. faded) to indicate it's inherited.

    Note: this is an approximation. QMK's real `KC_TRANSPARENT` resolves to
    the next active layer below, not necessarily layer 0. For this keymap
    layer 0 is always active so the approximation is exact.
    """
    import yaml

    data = yaml.safe_load(yaml_path.read_text())
    layers = data.get("layers") or {}
    if not layers:
        return
    base_name = LAYER_NAMES[0]
    base = layers.get(base_name)
    if base is None:
        return

    def is_trans(key) -> bool:
        if isinstance(key, str):
            return key == "▽"
        if isinstance(key, dict):
            return key.get("t") == "▽" or key.get("type") == "trans"
        return False

    def with_trans_type(key):
        # Normalise to a dict and add type=trans (preserved for CSS hooks).
        if isinstance(key, str):
            key = {"t": key}
        else:
            key = dict(key)
        key["type"] = "trans"
        return key

    for name, keys in layers.items():
        if name == base_name:
            continue
        for i, key in enumerate(keys):
            if is_trans(key) and i < len(base):
                keys[i] = with_trans_type(base[i])

    yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def generate(out_dir: Path) -> None:
    need("qmk")
    need("keymap")
    ensure_yaml()

    qmk_firmware = find_qmk_firmware()
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        keymap_json = tmp / "keymap.json"
        keymap_yaml = tmp / "keymap.yaml"

        # 1. C -> JSON. Must run from inside qmk_firmware.
        run(
            [
                "qmk", "c2json",
                "--no-cpp",
                "-kb", KEYBOARD,
                "-km", KEYMAP_NAME,
                "-o", str(keymap_json),
                str(KEYMAP_C),
            ],
            cwd=qmk_firmware,
        )

        # 2. JSON -> keymap-drawer YAML, with friendly layer names and our config.
        run(
            [
                "keymap", "-c", str(CONFIG_YAML),
                "parse",
                "-q", str(keymap_json),
                "-l", *LAYER_NAMES,
                "-o", str(keymap_yaml),
            ]
        )

        # 3. Inject combos parsed from keymap.c.
        import json
        layer0 = json.loads(keymap_json.read_text())["layers"][0]
        combos = extract_combos(KEYMAP_C.read_text(), layer0, load_binding_labels())
        inject_combos(keymap_yaml, combos)

        # 3b. Resolve transparent keys to the base-layer binding so that higher
        #     layers show what each position actually does instead of "▽".
        resolve_transparent_keys(keymap_yaml)

        # 4. Render one SVG per layer.
        for i, name in enumerate(LAYER_NAMES):
            svg = out_dir / f"layer_{i}.svg"
            run(
                [
                    "keymap", "-c", str(CONFIG_YAML),
                    "draw",
                    "-k", KEYBOARD,
                    "-s", name,
                    "-o", str(svg),
                    str(keymap_yaml),
                ]
            )

        # 5. Rasterise each SVG to PNG via WebKit (colour-emoji capable).
        rasterize_to_png(out_dir)


def rasterize_to_png(out_dir: Path) -> None:
    """Render layer_*.svg in out_dir to layer_*.png using svg2png.swift.

    We use WebKit (via a small Swift shim) because it's the only SVG
    renderer readily available on macOS that draws Apple Color Emoji in
    colour. rsvg-convert and CoreSVG fall back to monochrome glyphs.

    On non-macOS hosts this step is skipped; SVGs are still emitted.
    """
    if sys.platform != "darwin":
        print("note: skipping PNG rasterisation (not macOS)", file=sys.stderr)
        return
    if not shutil.which("swift"):
        die("swift not on PATH; install Xcode command-line tools")
    width, height = PNG_SIZE
    for i in range(len(LAYER_NAMES)):
        svg = out_dir / f"layer_{i}.svg"
        png = out_dir / f"layer_{i}.png"
        run(
            [
                "swift", str(SVG2PNG),
                str(svg), str(png),
                str(width), str(height), str(PNG_SCALE),
            ]
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def cmd_generate() -> int:
    generate(IMAGES_DIR)
    print(f"wrote {len(LAYER_NAMES)} files to {IMAGES_DIR.relative_to(REPO_ROOT)}/")
    return 0


def cmd_check() -> int:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        generate(tmp)
        diffs: list[str] = []
        # PNGs are non-deterministic across machines (font rasterisation,
        # antialiasing) so only the SVG sources are part of the freshness
        # check. Regenerate PNGs locally with `make images`.
        for i in range(len(LAYER_NAMES)):
            rel = f"layer_{i}.svg"
            fresh = tmp / rel
            committed = IMAGES_DIR / rel
            if not committed.exists():
                diffs.append(f"  {rel}: missing in images/")
            elif not filecmp.cmp(fresh, committed, shallow=False):
                diffs.append(f"  {rel}: out of date")
        if diffs:
            print("Layer images are out of date:", file=sys.stderr)
            for d in diffs:
                print(d, file=sys.stderr)
            print(
                "\nRun `make images` and commit the result, "
                "or push with `--no-verify` to skip this check.",
                file=sys.stderr,
            )
            return 1
    print("Layer images are up to date.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if images/ would change. Does not modify any files.",
    )
    args = ap.parse_args()
    return cmd_check() if args.check else cmd_generate()


if __name__ == "__main__":
    sys.exit(main())
