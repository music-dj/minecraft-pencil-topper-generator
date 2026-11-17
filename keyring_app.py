import os
import subprocess
import tempfile
import shutil
import urllib.request
import zipfile
import io
import gradio as gr

# ── Paths ──
def get_openscad_path():
    env_path = os.environ.get("OPENSCAD_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    candidates = [
        r"D:\program files\openscad-2021.01\openscad.exe",
        r"C:\Program Files\OpenSCAD\openscad.exe",
        r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
        shutil.which("openscad") or "",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "openscad"

OPENSCAD_EXE = get_openscad_path()
TEMP_DIR     = tempfile.gettempdir()
FONTS_DIR    = os.path.join(TEMP_DIR, "keyring_fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

# ── Font database: name → expected TTF filename after download ──
FONT_DB = {
    "Anton":           "Anton-Regular.ttf",
    "Archivo Black":   "ArchivoBlack-Regular.ttf",
    "Asap":            "Asap-Regular.ttf",
    "Bangers":         "Bangers-Regular.ttf",
    "Black Han Sans":  "BlackHanSans-Regular.ttf",
    "Bubblegum Sans":  "BubblegumSans-Regular.ttf",
    "Bungee":          "Bungee-Regular.ttf",
    "Changa One":      "ChangaOne-Regular.ttf",
    "Chewy":           "Chewy-Regular.ttf",
    "Concert One":     "ConcertOne-Regular.ttf",
    "Fruktur":         "Fruktur-Regular.ttf",
    "Gochi Hand":      "GochiHand-Regular.ttf",
    "Griffy":          "Griffy-Regular.ttf",
    "Inter":           "Inter_18pt-Regular.ttf",
    "Inter Tight":     "InterTight-Regular.ttf",
    "Itim":            "Itim-Regular.ttf",
    "Jockey One":      "JockeyOne-Regular.ttf",
    "Kanit":           "Kanit-Regular.ttf",
}

FONT_LIST  = list(FONT_DB.keys())
RING_CHARS = ["o", "O", "0"]


# ── Font downloader ──
def download_font(font_name):
    """Download a single font from Google Fonts. Returns True on success."""
    try:
        url = f"https://fonts.google.com/download?family={urllib.parse.quote(font_name)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read()

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for entry in zf.namelist():
                if entry.lower().endswith(".ttf"):
                    fname = os.path.basename(entry)
                    dest  = os.path.join(FONTS_DIR, fname)
                    if not os.path.exists(dest):
                        with zf.open(entry) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
        return True
    except Exception as e:
        print(f"  ✗ {font_name}: {e}")
        return False


def find_font_file(font_name):
    """Find the TTF file for a font. Returns path or None."""
    # Check expected name first
    expected = FONT_DB.get(font_name)
    if expected:
        path = os.path.join(FONTS_DIR, expected)
        if os.path.exists(path):
            return path.replace("\\", "/")

    # Fuzzy search: font name without spaces, case-insensitive
    key = font_name.lower().replace(" ", "")
    for f in os.listdir(FONTS_DIR):
        if f.lower().endswith(".ttf") and key in f.lower().replace("-", "").replace("_", ""):
            return os.path.join(FONTS_DIR, f).replace("\\", "/")
    return None


def download_all_fonts():
    """Download all fonts that aren't cached yet."""
    needed = []
    for name in FONT_LIST:
        if not find_font_file(name):
            needed.append(name)

    if not needed:
        print("✓ All fonts already cached.")
        return

    print(f"Downloading {len(needed)} fonts from Google Fonts...")
    for i, name in enumerate(needed, 1):
        print(f"  [{i}/{len(needed)}] {name}...", end=" ", flush=True)
        ok = download_font(name)
        print("✓" if ok else "✗")
    print("Font download complete!")


# ── OpenSCAD Template ──
SCAD_TEMPLATE = """\
{use_line}

Name_Text  = "{name_text}";
Font_Name  = "{font_name}";
Spacing    = {spacing};
Ring_Char  = "{ring_char}";
Ring_Size  = {ring_size};
Ring_X     = {ring_x};
Ring_Y     = {ring_y};
$fn        = 32;

function get_height(i) = (i % 2 == 0) ? 7 : 4;

module create_keychain() {{
    // Ring
    color("SteelBlue")
    linear_extrude(height=5) {{
        translate([-30 - Ring_X, Ring_Y, 0])
            rotate([0, 0, -90])
            text(size=Ring_Size, text=Ring_Char, font=Font_Name,
                 halign="center", valign="center");
    }}

    // Letters with alternating heights
    for (i = [0:min(len(Name_Text) - 1, 13)]) {{
        color(i % 2 == 0 ? "White" : "LightGray")
        linear_extrude(height=get_height(i)) {{
            translate([(Spacing * i) - 30, 0, 0])
                text(size=25, text=str(Name_Text[i]), font=Font_Name,
                     halign="center", valign="center");
        }}
    }}
}}

{mirror_line}create_keychain();
"""


def run_openscad(args, timeout=120):
    proc = subprocess.Popen(
        [OPENSCAD_EXE] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(timeout=timeout)
    return stderr.decode("utf-8", errors="replace")


def generate(name_text, font_name, spacing, ring_char, ring_size,
             ring_x, ring_y, mirror_text):
    name_text = (name_text.strip() or "Name")[:14]
    safe = "".join(c for c in name_text if c.isalnum() or c in " -_").strip().replace(" ", "_") or "Keyring"

    # Find or download font
    font_path = find_font_file(font_name)
    if not font_path:
        download_font(font_name)
        font_path = find_font_file(font_name)

    use_line = f'use <{font_path}>' if font_path else '// font not found'
    mirror_line = 'mirror([1,0,0]) ' if mirror_text else ''

    scad_code = SCAD_TEMPLATE.format(
        use_line    = use_line,
        name_text   = name_text.replace('"', '\\"'),
        font_name   = font_name,
        spacing     = spacing,
        ring_char   = ring_char,
        ring_size   = ring_size,
        ring_x      = ring_x,
        ring_y      = ring_y,
        mirror_line = mirror_line,
    )

    scad_path = os.path.join(TEMP_DIR, f"{safe}_keyring.scad")
    png_path  = os.path.join(TEMP_DIR, f"{safe}_keyring.png")
    stl_path  = os.path.join(TEMP_DIR, f"{safe}_keyring.stl")

    with open(scad_path, "w", encoding="utf-8") as f:
        f.write(scad_code)

    for p in [png_path, stl_path]:
        if os.path.exists(p):
            os.remove(p)

    try:
        # ── STEP 1: Fast PNG preview ──
        run_openscad([
            "-o", png_path,
            "--imgsize=1000,500",
            "--camera=30,0,4,55,0,25,120",
            "--colorscheme=Tomorrow",
            scad_path
        ], timeout=30)

        img = png_path if os.path.exists(png_path) else None
        yield img, None, "⏳ Preview ready! Generating STL..."

        # ── STEP 2: STL for download ──
        run_openscad(["-o", stl_path, scad_path], timeout=120)

        if not os.path.exists(stl_path) or os.path.getsize(stl_path) == 0:
            yield img, None, "❌ STL generation failed."
            return

        yield img, stl_path, f"✅ Done! File: {safe}_keyring.stl"

    except FileNotFoundError:
        yield None, None, "❌ OpenSCAD not found."
    except subprocess.TimeoutExpired:
        yield None, None, "❌ Timed out."
    except Exception as e:
        yield None, None, f"❌ {e}"


# ── Download fonts on startup ──
print("🔑 Custom Name Keyring Generator")
print("=" * 40)
download_all_fonts()

# ── Gradio UI ──
with gr.Blocks(title="Custom Name Keyring Generator") as app:
    gr.Markdown("# 🔑 Custom Name Keyring Generator")
    gr.Markdown("Generate a 3D-printable name keyring with custom fonts and ring style.")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### ✏️ Text & Font")
            name_in    = gr.Textbox(label="Name (max 14 chars)", value="Name")
            font_in    = gr.Dropdown(label="Font", choices=FONT_LIST, value="Chewy")
            spacing_in = gr.Slider(label="Letter Spacing", minimum=5.0, maximum=20.0, value=10.0, step=0.5)

            gr.Markdown("### ⭕ Ring")
            with gr.Row():
                ring_char_in = gr.Dropdown(label="Shape", choices=RING_CHARS, value="o")
                ring_size_in = gr.Slider(label="Size", minimum=15, maximum=30, value=20, step=1)
            with gr.Row():
                ring_x_in = gr.Slider(label="X Offset", minimum=-50.0, maximum=50.0, value=10.0, step=0.5)
                ring_y_in = gr.Slider(label="Y Offset", minimum=-20.0, maximum=20.0, value=0.0, step=0.5)

            mirror_in = gr.Checkbox(label="Mirror Text", value=False)
            gen_btn   = gr.Button("🔑 Generate Keyring", variant="primary")
            status    = gr.Textbox(label="Status", interactive=False)

        with gr.Column(scale=2):
            gr.Markdown("### 🖥️ Preview")
            preview  = gr.Image(label="Keyring Preview", type="filepath")
            file_dl  = gr.File(label="⬇️ Download STL")

    gen_btn.click(fn=generate,
                  inputs=[name_in, font_in, spacing_in, ring_char_in,
                          ring_size_in, ring_x_in, ring_y_in, mirror_in],
                  outputs=[preview, file_dl, status])

if __name__ == "__main__":
    app.launch(inbrowser=True)
