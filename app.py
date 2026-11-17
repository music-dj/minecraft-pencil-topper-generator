import os
import sys
import subprocess
import tempfile
import shutil
import urllib.request
import zipfile
import io
import gradio as gr

# ── Dynamic OpenSCAD Path Resolution ──
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

# ── Base Directory (Supports PyInstaller frozen binary) ──
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_SOURCE = os.path.join(BASE_DIR, "MinecraftEvenings-lgvPd.ttf")
TEMP_DIR    = tempfile.gettempdir()
TEMP_FONT   = os.path.join(TEMP_DIR, "minecraft_font.ttf")

if os.path.exists(FONT_SOURCE) and not os.path.exists(TEMP_FONT):
    try:
        shutil.copy2(FONT_SOURCE, TEMP_FONT)
    except Exception as e:
        print(f"Warning: could not copy font: {e}")

FONT_SCAD = TEMP_FONT.replace("\\", "/")

# ── Fonts for Keyrings ──
KEYRING_FONTS_DIR = os.path.join(TEMP_DIR, "keyring_fonts")
os.makedirs(KEYRING_FONTS_DIR, exist_ok=True)

FONT_DB = {
    "Chewy":           "Chewy-Regular.ttf",
    "Bangers":         "Bangers-Regular.ttf",
    "Bungee":          "Bungee-Regular.ttf",
    "Anton":           "Anton-Regular.ttf",
    "Archivo Black":   "ArchivoBlack-Regular.ttf",
    "Asap":            "Asap-Regular.ttf",
    "Black Han Sans":  "BlackHanSans-Regular.ttf",
    "Bubblegum Sans":  "BubblegumSans-Regular.ttf",
    "Changa One":      "ChangaOne-Regular.ttf",
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


def download_keyring_font(font_name):
    try:
        url = f"https://fonts.google.com/download?family={urllib.parse.quote(font_name)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for entry in zf.namelist():
                if entry.lower().endswith(".ttf"):
                    fname = os.path.basename(entry)
                    dest  = os.path.join(KEYRING_FONTS_DIR, fname)
                    if not os.path.exists(dest):
                        with zf.open(entry) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
        return True
    except Exception:
        return False


def find_keyring_font(font_name):
    expected = FONT_DB.get(font_name)
    if expected:
        path = os.path.join(KEYRING_FONTS_DIR, expected)
        if os.path.exists(path):
            return path.replace("\\", "/")
    key = font_name.lower().replace(" ", "")
    for f in os.listdir(KEYRING_FONTS_DIR):
        if f.lower().endswith(".ttf") and key in f.lower().replace("-", "").replace("_", ""):
            return os.path.join(KEYRING_FONTS_DIR, f).replace("\\", "/")
    return None


# ── OpenSCAD Runner Helper ──
def run_openscad(args, timeout=120):
    proc = subprocess.Popen(
        [OPENSCAD_EXE] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(timeout=timeout)
    return stderr.decode("utf-8", errors="replace")


# ── 1. Pencil Topper Logic ──
TOPPER_SCAD_TEMPLATE = """\
use <""" + FONT_SCAD + """>

Name_Text                = "{name_text}";
Font_Name                = "Minecraft Evenings";
Text_Thickness           = {text_thickness};
Text_Scale               = 10.0;
Plate_Offset             = 2.0;
Pencil_Hole_Diameter     = {hole_diameter};
Cylinder_Outer_Thickness = 1.5;
Base_Thickness           = Pencil_Hole_Diameter + (Cylinder_Outer_Thickness * 2);
$fn                      = 32;

module text_2d() {{
    text(text=Name_Text, size=Text_Scale, font=Font_Name,
         halign="center", valign="center");
}}

module topper() {{
    difference() {{
        union() {{
            color("LimeGreen")
            linear_extrude(height=Base_Thickness)
                offset(r=Plate_Offset) text_2d();
            color("White")
            translate([0, 0, Base_Thickness])
                linear_extrude(height=Text_Thickness) text_2d();
        }}
        translate([0, 0, Base_Thickness / 2])
            rotate([0, 90, 0])
                cylinder(h=300, d=Pencil_Hole_Diameter, center=true);
    }}
}}

{mirror_line}topper();
"""

def generate_topper(name_text, text_thickness, hole_diameter, mirror_text):
    name_text = name_text.strip() or "STEVE"
    safe = "".join(c for c in name_text if c.isalnum() or c in " -_").strip().replace(" ", "_") or "Topper"
    mirror_line = 'mirror([1,0,0]) ' if mirror_text else ''

    scad_code = TOPPER_SCAD_TEMPLATE.format(
        name_text      = name_text.replace('"', '\\"'),
        text_thickness = text_thickness,
        hole_diameter  = hole_diameter,
        mirror_line    = mirror_line,
    )

    scad_path = os.path.join(TEMP_DIR, f"{safe}.scad")
    png_path  = os.path.join(TEMP_DIR, f"{safe}.png")
    stl_path  = os.path.join(TEMP_DIR, f"{safe}.stl")

    with open(scad_path, "w", encoding="utf-8") as f:
        f.write(scad_code)

    for p in [png_path, stl_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    try:
        run_openscad([
            "-o", png_path,
            "--imgsize=1000,600",
            "--camera=0,0,6,55,0,25,80",
            "--colorscheme=Tomorrow",
            scad_path
        ], timeout=30)

        preview_img = png_path if os.path.exists(png_path) else None
        yield preview_img, None, "⏳ Preview ready! Generating STL for download..."

        run_openscad(["-o", stl_path, scad_path], timeout=120)

        if not os.path.exists(stl_path) or os.path.getsize(stl_path) == 0:
            yield preview_img, None, "❌ STL generation failed."
            return

        yield preview_img, stl_path, f"✅ Done! File: {safe}.stl (Ready to download)"

    except FileNotFoundError:
        yield None, None, f"❌ OpenSCAD not found at: {OPENSCAD_EXE}"
    except subprocess.TimeoutExpired:
        yield None, None, "❌ OpenSCAD timed out"
    except Exception as e:
        yield None, None, f"❌ Error: {e}"


# ── 2. Keyring Logic ──
KEYRING_SCAD_TEMPLATE = """\
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
    color("SteelBlue")
    linear_extrude(height=5) {{
        translate([-30 - Ring_X, Ring_Y, 0])
            rotate([0, 0, -90])
            text(size=Ring_Size, text=Ring_Char, font=Font_Name,
                 halign="center", valign="center");
    }}

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

def generate_keyring(name_text, font_name, spacing, ring_char, ring_size, ring_x, ring_y, mirror_text):
    name_text = (name_text.strip() or "Name")[:14]
    safe = "".join(c for c in name_text if c.isalnum() or c in " -_").strip().replace(" ", "_") or "Keyring"

    font_path = find_keyring_font(font_name)
    if not font_path:
        download_keyring_font(font_name)
        font_path = find_keyring_font(font_name)

    use_line = f'use <{font_path}>' if font_path else '// default font'
    mirror_line = 'mirror([1,0,0]) ' if mirror_text else ''

    scad_code = KEYRING_SCAD_TEMPLATE.format(
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
            try:
                os.remove(p)
            except Exception:
                pass

    try:
        run_openscad([
            "-o", png_path,
            "--imgsize=1000,500",
            "--camera=30,0,4,55,0,25,120",
            "--colorscheme=Tomorrow",
            scad_path
        ], timeout=30)

        img = png_path if os.path.exists(png_path) else None
        yield img, None, "⏳ Preview ready! Generating STL..."

        run_openscad(["-o", stl_path, scad_path], timeout=120)

        if not os.path.exists(stl_path) or os.path.getsize(stl_path) == 0:
            yield img, None, "❌ STL generation failed."
            return

        yield img, stl_path, f"✅ Done! File: {safe}_keyring.stl"

    except FileNotFoundError:
        yield None, None, f"❌ OpenSCAD not found."
    except subprocess.TimeoutExpired:
        yield None, None, "❌ Timed out."
    except Exception as e:
        yield None, None, f"❌ {e}"


# ── Gradio Unified Web Interface ──
with gr.Blocks(title="Minecraft 3D Generator Suite") as app:
    gr.Markdown("# 🎮 Minecraft 3D Generator Suite")
    gr.Markdown("Parametric 3D printable designs: Minecraft Pencil Toppers & Custom Keyrings with instant color preview and STL download.")

    with gr.Tabs():
        # TAB 1: PENCIL TOPPER
        with gr.Tab("✏️ Minecraft Pencil Topper"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### ⚙️ Topper Settings")
                    top_name_in   = gr.Textbox(label="Name / Text", value="STEVE")
                    top_thick_in  = gr.Slider(label="Text Thickness (mm)", minimum=1.0, maximum=5.0, value=2.0, step=0.1)
                    top_hole_in   = gr.Slider(label="Pencil Hole Diameter (mm)", minimum=6.0, maximum=10.0, value=7.8, step=0.1,
                                             info="Standard pencil ≈ 7.4–7.8 mm")
                    top_mirror_in = gr.Checkbox(label="Mirror Text", value=False,
                                                info="Enable if needed for bottom-layer printing")
                    top_gen_btn   = gr.Button("🎮 Generate Topper", variant="primary")
                    top_status    = gr.Textbox(label="Status", interactive=False)

                with gr.Column(scale=2):
                    gr.Markdown("### 🖥️ Model Preview")
                    top_preview   = gr.Image(label="Live Render Preview", type="filepath")
                    top_file_dl   = gr.File(label="⬇️ Download STL")

            top_gen_btn.click(
                fn=generate_topper,
                inputs=[top_name_in, top_thick_in, top_hole_in, top_mirror_in],
                outputs=[top_preview, top_file_dl, top_status]
            )

        # TAB 2: CUSTOM KEYRING
        with gr.Tab("🔑 Custom Name Keyring"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### ✏️ Text & Font")
                    kr_name_in    = gr.Textbox(label="Name (max 14 chars)", value="Name")
                    kr_font_in    = gr.Dropdown(label="Font Choice", choices=FONT_LIST, value="Chewy")
                    kr_spacing_in = gr.Slider(label="Letter Spacing", minimum=5.0, maximum=20.0, value=10.0, step=0.5)

                    gr.Markdown("### ⭕ Ring Settings")
                    with gr.Row():
                        kr_char_in = gr.Dropdown(label="Ring Shape", choices=RING_CHARS, value="o")
                        kr_size_in = gr.Slider(label="Ring Size", minimum=15, maximum=30, value=20, step=1)
                    with gr.Row():
                        kr_x_in = gr.Slider(label="X Offset", minimum=-50.0, maximum=50.0, value=10.0, step=0.5)
                        kr_y_in = gr.Slider(label="Y Offset", minimum=-20.0, maximum=20.0, value=0.0, step=0.5)

                    kr_mirror_in = gr.Checkbox(label="Mirror Text", value=False)
                    kr_gen_btn   = gr.Button("🔑 Generate Keyring", variant="primary")
                    kr_status    = gr.Textbox(label="Status", interactive=False)

                with gr.Column(scale=2):
                    gr.Markdown("### 🖥️ Keyring Preview")
                    kr_preview   = gr.Image(label="Live Render Preview", type="filepath")
                    kr_file_dl   = gr.File(label="⬇️ Download STL")

            kr_gen_btn.click(
                fn=generate_keyring,
                inputs=[kr_name_in, kr_font_in, kr_spacing_in, kr_char_in,
                        kr_size_in, kr_x_in, kr_y_in, kr_mirror_in],
                outputs=[kr_preview, kr_file_dl, kr_status]
            )

if __name__ == "__main__":
    app.launch(inbrowser=True)
