"""Rasterise the static mark at the sizes that need a PNG.

Rendered at 4x and downsampled with Lanczos: the fine tributaries alias badly
if the browser is asked to rasterise straight to 64 px.
"""
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

# The full network has more detail than 64 px can hold, so the small rasters
# come from the reduced mark instead of from a downsample of the dense one.
JOBS = [("logo.svg", (512, 256, 128)), ("logo-small.svg", (64, 32))]

def master_for(name):
    src = Path(name).resolve()
    page = src.parent / "_png.html"
    page.write_text(
        f'<html><body style="margin:0;background:transparent">'
        f'<img src="{src.name}" width="1024" height="1024"></body></html>')
    with sync_playwright() as pw:
        with pw.chromium.launch() as b:
            ctx = b.new_context(color_scheme="light", device_scale_factor=1)
            pg = ctx.new_page()
            pg.goto(page.as_uri())
            pg.wait_for_timeout(600)
            pg.locator("img").screenshot(path="/tmp/mark_1024.png", omit_background=True)
            ctx.close()
    page.unlink()
    return Image.open("/tmp/mark_1024.png").convert("RGBA")

done = []
for name, sizes in JOBS:
    master = master_for(name)
    for s in sizes:
        master.resize((s, s), Image.LANCZOS).save(f"logo-{s}.png")
        done.append(f"logo-{s}.png")
    if name == "logo-small.svg":
        master.resize((64, 64), Image.LANCZOS).save("icon.png")
print("png set:", ", ".join(done), "+ icon.png")
