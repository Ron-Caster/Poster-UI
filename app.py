import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import json
import os
from io import BytesIO
import textwrap

# Paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BG = os.path.join(APP_DIR, "background.png")
DEFAULT_LOGO = os.path.join(APP_DIR, "logo.png")
POSITIONS_FILE = os.path.join(ROOT, "positions.json")

st.set_page_config(page_title="Poster Generator", layout="wide")

# -- Hide Streamlit default UI elements (header, menu, footer, toolbar) --
st.markdown(
    """
    <style>
    /* hide hamburger menu (top-right), header, footer and toolbar */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stHeader"] {visibility: hidden;}

    /* remove extra top padding that may be left behind */
    [data-testid="stAppViewContainer"] > .main {padding-top: 0rem;}

    /* optional: keep the sidebar intact (no changes) */
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Poster Generator — Streamlit UI")

# Load positions if available
positions = None
logo_size = (250, 250)
if os.path.exists(POSITIONS_FILE):
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            pj = json.load(f)
            positions = pj.get("positions", {})
            ls = pj.get("logo_size")
            if ls and isinstance(ls, (list, tuple)) and len(ls) >= 2:
                logo_size = (int(ls[0]), int(ls[1]))
    except Exception:
        positions = None

# Sidebar: assets
st.sidebar.header("Assets")
st.sidebar.markdown("**Background & logo** are loaded from `streamlit_app/` folder by default.")
uploaded_assets = st.sidebar.file_uploader(
    "Upload additional images (placed in center like assets folder)",
    type=["png", "jpg", "jpeg", "bmp", "gif"],
    accept_multiple_files=True
)

# Text inputs for positions 1,2,3
st.header("Poster text (these map to positions 1, 2, 3)")
col1, col2 = st.columns(2)
with col1:
    title_text = st.text_input("Position 1 — Title", "")
    subtitle_text = st.text_input("Position 2 — Subtitle", "")
with col2:
    body_text = st.text_area("Position 3 — Body (longer)", "", height=150)

# Options
st.sidebar.header("Options")

font_size_title = st.sidebar.slider("Title font size", 48, 300, 160, key="title_font_size")
font_size_sub = st.sidebar.slider("Subtitle font size", 28, 180, 100, key="subtitle_font_size")
font_size_body = st.sidebar.slider("Body font size", 18, 120, 80, key="body_font_size")
output_name = st.sidebar.text_input("Output filename", "generated_poster.jpg")

# Helper: load image from uploader or default path
def load_image_from_source(uploaded, default_path):
    if uploaded is not None:
        try:
            return Image.open(uploaded).convert("RGBA")
        except Exception:
            return None
    if os.path.exists(default_path):
        try:
            return Image.open(default_path).convert("RGBA")
        except Exception:
            return None
    return None

# Load images from local folder (always use defaults)
bg_img = load_image_from_source(None, DEFAULT_BG)
logo_img = load_image_from_source(None, DEFAULT_LOGO)

# Inform user about asset availability
if bg_img is None:
    st.warning("Background not found — copy background.png into the streamlit_app folder.")
if logo_img is None:
    st.info("Logo not found — copy logo.png into the streamlit_app folder. Logo is optional.")

# Load uploaded assets (center placement like assets folder)
asset_images = []
if uploaded_assets:
    for uploaded_file in uploaded_assets:
        try:
            img = Image.open(uploaded_file).convert("RGBA")
            asset_images.append(img)
        except Exception:
            continue

# Font loading logic (from poster_generator.py)
def try_load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return None

def load_font_with_bold(base_path, size, want_bold=False):
    """Try to load a font. If want_bold=True, try common bold variants and return (font, has_bold_flag).
    Falls back to the base font or PIL default if not found."""
    # Try exact path first
    f = try_load_font(base_path, size)
    base_dir = os.path.dirname(base_path)
    basename = os.path.basename(base_path)
    name_no_ext, ext = os.path.splitext(basename)
    if f is None:
        # try bare name (system font lookup)
        f = try_load_font(name_no_ext + ext, size)
    if not want_bold:
        if f is None:
            return ImageFont.load_default(), False
        return f, True

    # want bold: try common bold file name patterns
    bold_candidates = [
        name_no_ext + 'bd' + ext,
        name_no_ext + '-bd' + ext,
        name_no_ext + 'b' + ext,
        name_no_ext + 'bold' + ext,
        'arialbd' + ext,
        'DejaVuSans-Bold' + ext,
    ]
    for cand in bold_candidates:
        cand_path = os.path.join(base_dir, cand) if base_dir else cand
        bf = try_load_font(cand_path, size)
        if bf:
            return bf, True

    # No bold font found; return base or default and indicate bold is unavailable
    if f is None:
        return ImageFont.load_default(), False
    return f, False

def draw_bold_text(draw_obj, pos, text, font, fill, bold_available=True, stroke=2):
    """Draw text in bold. If a bold font is available, use it. Otherwise try stroke_width, then multi-draw fallback."""
    x, y = pos
    if bold_available:
        draw_obj.text((x, y), text, font=font, fill=fill)
        return
    # Try stroke_width API (Pillow >= 5-ish)
    try:
        draw_obj.text((x, y), text, font=font, fill=fill, stroke_width=stroke, stroke_fill=fill)
        return
    except TypeError:
        # Older Pillow may not support stroke_width
        pass
    # Fallback: draw the text multiple times with small offsets to emulate bold
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]
    for dx, dy in offsets:
        draw_obj.text((x + dx, y + dy), text, font=font, fill=fill)

# Asset placement function (from poster_generator.py)
def place_assets(bg_image, asset_imgs, max_width_ratio=0.4, max_height_ratio=0.4):
    """Place assets on the poster:
    - If 1 image: center it exactly at poster center.
    - If 2 images: place them centered vertically, left and right of center.
    - If >2: spread evenly across the horizontal center line.
    Images are resized to fit within max_width_ratio * bg.width per image and max_height_ratio * bg.height.
    """
    n = len(asset_imgs)
    if n == 0:
        return
    bw, bh = bg_image.size
    max_w = int(bw * max_width_ratio)
    max_h = int(bh * max_height_ratio)

    imgs = []
    for img in asset_imgs:
        try:
            im = img.copy()
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = getattr(Image, 'LANCZOS', Image.NEAREST)
            im.thumbnail((max_w, max_h), resample)
            imgs.append(im)
        except Exception:
            continue

    if not imgs:
        return

    center_x = bw // 2
    center_y = bh // 2

    if len(imgs) == 1:
        im = imgs[0]
        pos_x = center_x - im.width // 2
        pos_y = center_y - im.height // 2
        bg_image.paste(im, (pos_x, pos_y), im)
        return

    if len(imgs) == 2:
        left = imgs[0]
        right = imgs[1]
        spacing = int(bw * 0.05)
        pos_left_x = center_x - spacing//2 - left.width
        pos_right_x = center_x + spacing//2
        pos_y = center_y - max(left.height, right.height) // 2
        bg_image.paste(left, (pos_left_x, pos_y), left)
        bg_image.paste(right, (pos_right_x, pos_y), right)
        return

    # more than 2: distribute across center line
    total = len(imgs)
    total_imgs_w = sum(im.width for im in imgs)
    available_w = int(bw * 0.8)
    gap = max(10, (available_w - total_imgs_w) // (total - 1)) if total > 1 else 0
    start_x = center_x - (total_imgs_w + gap*(total-1)) // 2
    x = start_x
    for im in imgs:
        pos_y = center_y - im.height // 2
        bg_image.paste(im, (int(x), int(pos_y)), im)
        x += im.width + gap

# Core generation logic
def generate_poster(bg, logo, title, subtitle, body, assets, title_size, sub_size, body_size):
    if bg is None:
        return None, "No background image provided."
    canvas = bg.convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Load fonts with bold support (using same defaults as poster_generator.py)
    title_font, _ = load_font_with_bold("arialbd.ttf", title_size, want_bold=False)
    sub_font, subtitle_has_bold = load_font_with_bold("arial.ttf", sub_size, want_bold=True)
    body_font, body_has_bold = load_font_with_bold("arial.ttf", body_size, want_bold=True)

    def text_size(t, f):
        bbox = draw.textbbox((0,0), t, font=f)
        return bbox[2]-bbox[0], bbox[3]-bbox[1]

    # Title: position '1' else top center
    if positions and '1' in positions and title:
        tx, ty = positions['1']
        w, h = text_size(title, title_font)
        draw_bold_text(draw, (tx - w/2, ty - h/2), title, title_font, fill=(0,80,180), bold_available=True)
    elif title:
        w, h = text_size(title, title_font)
        draw_bold_text(draw, ((canvas.width - w)/2, 150), title, title_font, fill=(0,80,180), bold_available=True)

    # Subtitle
    if positions and '2' in positions and subtitle:
        sx, sy = positions['2']
        w, h = text_size(subtitle, sub_font)
        draw_bold_text(draw, (sx - w/2, sy - h/2), subtitle, sub_font, fill=(220,100,0), bold_available=subtitle_has_bold)
    elif subtitle:
        w, h = text_size(subtitle, sub_font)
        draw_bold_text(draw, ((canvas.width - w)/2, 250), subtitle, sub_font, fill=(220,100,0), bold_available=subtitle_has_bold)

    # Body (wrapped)
    if body:
        lines = textwrap.wrap(body, width=40)
        if positions and '3' in positions:
            bx, by = positions['3']
            offset_x = int(bx)
            offset_y = int(by)
            for ln in lines:
                draw_bold_text(draw, (offset_x, offset_y), ln, body_font, fill=(0,0,0), bold_available=body_has_bold)
                offset_y += int(body_font.size * 1.2)
        else:
            offset_x = 100
            offset_y = 400
            for ln in lines:
                draw_bold_text(draw, (offset_x, offset_y), ln, body_font, fill=(0,0,0), bold_available=body_has_bold)
                offset_y += int(body_font.size * 1.2)

    # Footer if present in positions
    if positions and '4' in positions:
        fx, fy = positions['4']
        # Use subtitle font for footer
        footer_text = ''
        # No explicit field in UI; left blank unless needed
        if footer_text:
            w, h = text_size(footer_text, sub_font)
            draw.text((fx - w/2, fy - h/2), footer_text, font=sub_font, fill=(80,80,80))

    # Paste logo
    if logo is not None:
        # Resize preserving aspect ratio
        max_w, max_h = logo_size
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = getattr(Image, 'LANCZOS', Image.NEAREST)
        logo_copy = logo.copy()
        logo_copy.thumbnail((max_w, max_h), resample)
        box = Image.new("RGBA", (max_w, max_h), (0,0,0,0))
        ox = (max_w - logo_copy.width)//2
        oy = (max_h - logo_copy.height)//2
        box.paste(logo_copy, (ox, oy), logo_copy)

        if positions and 'logo' in positions:
            cx, cy = positions['logo']
            pos_x = int(cx - max_w/2)
            pos_y = int(cy - max_h/2)
            canvas.paste(box, (pos_x, pos_y), box)
        else:
            gap = 50
            pos_x = canvas.width - gap - max_w
            pos_y = canvas.height - gap - max_h
            canvas.paste(box, (pos_x, pos_y), box)

    # Place uploaded assets in center
    if assets:
        place_assets(canvas, assets)

    return canvas.convert("RGB"), None

# Generate button
if st.button("Generate Poster"):
    poster, err = generate_poster(bg_img, logo_img, title_text, subtitle_text, body_text, asset_images, 
                                   font_size_title, font_size_sub, font_size_body)
    if err:
        st.error(err)
    elif poster is None:
        st.error("Poster generation failed — check inputs.")
    else:
        buf = BytesIO()
        poster.save(buf, format="JPEG")
        byte_im = buf.getvalue()
        st.image(poster, use_column_width=True)
        st.download_button("Download poster", data=byte_im, file_name=output_name, mime="image/jpeg")
        # Optionally save to disk in app dir
        save_to_disk = st.sidebar.checkbox("Also save a copy in streamlit_app/output/", value=False)
        if save_to_disk:
            outdir = os.path.join(APP_DIR, "output")
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, output_name)
            with open(outpath, "wb") as f:
                f.write(byte_im)
            st.success(f"Saved a copy to {outpath}")

st.markdown("---")
st.caption("Background and logo are loaded from `background.png` and `logo.png` in the `streamlit_app` folder. Upload additional images via the sidebar to place them in the center (like the assets folder in the original script).")
