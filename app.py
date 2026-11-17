import os
import subprocess
import tempfile
import shutil
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
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FONT_SOURCE  = os.path.join(BASE_DIR, "MinecraftEvenings-lgvPd.ttf")
TEMP_DIR     = tempfile.gettempdir()
TEMP_FONT    = os.path.join(TEMP_DIR, "minecraft_font.ttf")

# Copy font once to a safe ASCII path to prevent non-ASCII path encoding issues in OpenSCAD
if os.path.exists(FONT_SOURCE) and not os.path.exists(TEMP_FONT):
    try:
        shutil.copy2(FONT_SOURCE, TEMP_FONT)
    except Exception as e:
        print(f"Warning: could not copy font: {e}")

FONT_SCAD = TEMP_FONT.replace("\\", "/")

# ── OpenSCAD Template ──
# Reference dimensions for "STEVE": X≈47.66 mm, Y≈13.94 mm, Z≈12.80 mm
SCAD_TEMPLATE = """\
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
            // Base plate (printed in Green)
            color("LimeGreen")
            linear_extrude(height=Base_Thickness)
                offset(r=Plate_Offset) text_2d();
            // Raised text on top (printed in White)
            color("White")
            translate([0, 0, Base_Thickness])
                linear_extrude(height=Text_Thickness) text_2d();
        }}
        // Horizontal bore hole for pencil
        translate([0, 0, Base_Thickness / 2])
            rotate([0, 90, 0])
                cylinder(h=300, d=Pencil_Hole_Diameter, center=true);
    }}
}}

{mirror_line}topper();
"""


def run_openscad(args, timeout=120):
    """Run OpenSCAD command and return stderr output."""
    proc = subprocess.Popen(
        [OPENSCAD_EXE] + args,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(timeout=timeout)
    return stderr.decode("utf-8", errors="replace")


def generate(name_text, text_thickness, hole_diameter, mirror_text):
    name_text = name_text.strip() or "STEVE"
    safe = "".join(c for c in name_text if c.isalnum() or c in " -_").strip().replace(" ", "_") or "Topper"
    mirror_line = 'mirror([1,0,0]) ' if mirror_text else ''

    scad_code = SCAD_TEMPLATE.format(
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

    # Clean previous generated files
    for p in [png_path, stl_path]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    try:
        # ── STEP 1: Generate fast PNG preview via OpenCSG (1-2s) ──
        run_openscad([
            "-o", png_path,
            "--imgsize=1000,600",
            "--camera=0,0,6,55,0,25,80",
            "--colorscheme=Tomorrow",
            scad_path
        ], timeout=30)

        preview_img = png_path if os.path.exists(png_path) else None

        # Yield preview immediately to UI
        yield preview_img, None, "⏳ Preview ready! Generating STL for download..."

        # ── STEP 2: Generate production STL mesh via CGAL ──
        run_openscad(["-o", stl_path, scad_path], timeout=120)

        if not os.path.exists(stl_path) or os.path.getsize(stl_path) == 0:
            yield preview_img, None, "❌ STL generation failed."
            return

        yield preview_img, stl_path, f"✅ Done! File: {safe}.stl (Ready to download)"

    except FileNotFoundError:
        yield None, None, f"❌ OpenSCAD not found at: {OPENSCAD_EXE}\nPlease install OpenSCAD or set OPENSCAD_PATH."
    except subprocess.TimeoutExpired:
        yield None, None, "❌ OpenSCAD timed out"
    except Exception as e:
        yield None, None, f"❌ Error: {e}"


# ── Gradio Web Interface ──
with gr.Blocks(title="Minecraft Pencil Topper Generator") as app:
    gr.Markdown("# ✏️ Minecraft Pencil Topper Generator")
    gr.Markdown("Generate custom 3D-printable Minecraft-style pencil toppers with instant color preview and STL export.")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### ⚙️ Settings")
            name_in   = gr.Textbox(label="Name / Text", value="STEVE")
            thick_in  = gr.Slider(label="Text Thickness (mm)", minimum=1.0, maximum=5.0, value=2.0, step=0.1)
            hole_in   = gr.Slider(label="Pencil Hole Diameter (mm)", minimum=6.0, maximum=10.0, value=7.8, step=0.1,
                                  info="Standard wooden pencil ≈ 7.4–7.8 mm")
            mirror_in = gr.Checkbox(label="Mirror Text", value=False,
                                    info="Enable if your slicer or printer prints mirrored text")
            gen_btn   = gr.Button("🎮 Generate Model", variant="primary")
            status    = gr.Textbox(label="Status", interactive=False)

        with gr.Column(scale=2):
            gr.Markdown("### 🖥️ Model Preview")
            preview   = gr.Image(label="Live Render Preview", type="filepath")
            file_dl   = gr.File(label="⬇️ Download STL")

    gen_btn.click(fn=generate, inputs=[name_in, thick_in, hole_in, mirror_in],
                  outputs=[preview, file_dl, status])

if __name__ == "__main__":
    app.launch(inbrowser=True)
