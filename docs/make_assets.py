"""Builds the README visuals in docs/: banner.svg, screenshots of each tab (made-up data) and demo.gif.
Run: python docs/make_assets.py   (needs fonttools, Chrome and ffmpeg; fonts come from the RohanThakur Brand Kit)"""
import base64
import functools
import http.server
import io
import subprocess
import threading
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
FONTS = Path.home() / "RohanThakur-Brand-Kit" / "05-Fonts" / "install-ttf"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TABS = ["today", "digest", "chat", "notes"]


def font_face(chars):
    css = []
    for w in (500, 700):
        f = TTFont(FONTS / f"Satoshi-{w}.ttf")
        o = Options(); o.flavor = "woff2"; o.layout_features = ["kern"]
        s = Subsetter(o); s.populate(text=chars); s.subset(f)
        buf = io.BytesIO(); f.flavor = "woff2"; f.save(buf)
        css.append(f"@font-face{{font-family:S;font-weight:{w};src:url(data:font/woff2;base64,"
                   f"{base64.b64encode(buf.getvalue()).decode()}) format('woff2')}}")
    return "".join(css)


def banner():
    W, H = 1200, 440
    title, tag = "Convoy", "Your AI chief of staff, in a glass sidebar on your desktop."
    chips = ["Morning brief", "2 inboxes", "Voice notes", "Meeting prep", "Obsidian", "MCP"]
    eyebrow = "PERSONAL AI AGENT  ·  PYTHON  ·  GEMINI + CLAUDE"
    x, chip_svg = 72, []
    for i, c in enumerate(chips):
        cw = 34 + len(c) * 8.1
        chip_svg.append(f'<g class="up" style="animation-delay:{.55 + i * .08:.2f}s"><rect x="{x}" y="300" width="{cw:.0f}" height="36" '
                        f'rx="18" fill="#fff" fill-opacity=".06" stroke="url(#g)" stroke-opacity=".7"/>'
                        f'<text x="{x + cw / 2:.0f}" y="324" text-anchor="middle" font-size="15" font-weight="500" fill="#f4f1ee">{c}</text></g>')
        x += cw + 10
    # The app icon (three chevrons) and a mini sidebar mock on the right.
    chevrons = "".join(f'<path d="M{888 + i * 32} 128 l26 26 -26 26" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" '
                       f'stroke-linejoin="round" style="animation:pulse 2.4s {i * .25}s ease-in-out infinite"/>' for i in range(3))
    lines = "".join(f'<rect x="{878}" y="{236 + i * 26}" width="{w}" height="10" rx="5" fill="#fff" fill-opacity="{.5 - i * .07:.2f}"/>'
                    for i, w in enumerate((210, 170, 230, 140, 190)))
    body = f'''
<rect width="{W}" height="{H}" fill="url(#dots)"/>
<circle cx="980" cy="60" r="420" fill="url(#o)" style="animation:d1 13s ease-in-out infinite alternate"/>
<circle cx="1150" cy="460" r="360" fill="url(#r)" style="animation:d2 17s ease-in-out infinite alternate"/>
<circle cx="640" cy="520" r="300" fill="url(#v)" style="animation:d1 19s ease-in-out infinite alternate"/>
<g class="up" style="animation-delay:.05s"><circle cx="78" cy="78" r="5" fill="url(#g)" style="animation:pulse 2s ease-in-out infinite"/>
<text x="94" y="84" font-size="14" font-weight="500" letter-spacing="2.4" fill="#f4f1ee" fill-opacity=".7">{eyebrow}</text></g>
<text class="up" style="animation-delay:.15s" x="68" y="196" font-size="124" font-weight="700" letter-spacing="-5" fill="url(#g)">{title}</text>
<text class="up" style="animation-delay:.3s" x="72" y="256" font-size="27" font-weight="500" fill="#f4f1ee">{tag}</text>
{"".join(chip_svg)}
<g class="up" style="animation-delay:.4s">
  <rect x="850" y="90" width="282" height="300" rx="22" fill="#fff" fill-opacity=".07" stroke="#fff" stroke-opacity=".14"/>
  <rect x="866" y="108" width="140" height="92" rx="22" fill="url(#g)"/>{chevrons}
  {lines}
  <rect x="866" y="368" width="250" height="2" rx="1" fill="url(#shine)" style="animation:sweep 3.2s linear infinite"/>
</g>'''
    chars = title + tag + "".join(chips) + eyebrow
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>{font_face(chars)}
text{{font-family:S,'Segoe UI',Helvetica,Arial,sans-serif}}
.up{{animation:up 1s cubic-bezier(.2,.7,.2,1) both}}
@keyframes up{{from{{opacity:0;transform:translateY(16px)}}}}
@keyframes d1{{to{{transform:translate(-140px,70px) scale(1.15)}}}}
@keyframes d2{{to{{transform:translate(120px,-60px) scale(.9)}}}}
@keyframes pulse{{50%{{opacity:.3}}}}
@keyframes sweep{{0%{{transform:translateX(-120px);opacity:0}}50%{{opacity:1}}100%{{transform:translateX(120px);opacity:0}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#F16B0D"/><stop offset=".55" stop-color="#E61416"/><stop offset="1" stop-color="#C2187A"/></linearGradient>
<radialGradient id="o"><stop offset="0" stop-color="#F16B0D" stop-opacity=".55"/><stop offset="1" stop-color="#F16B0D" stop-opacity="0"/></radialGradient>
<radialGradient id="r"><stop offset="0" stop-color="#E61416" stop-opacity=".5"/><stop offset="1" stop-color="#E61416" stop-opacity="0"/></radialGradient>
<radialGradient id="v"><stop offset="0" stop-color="#7B2FF7" stop-opacity=".35"/><stop offset="1" stop-color="#7B2FF7" stop-opacity="0"/></radialGradient>
<linearGradient id="shine" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#fff" fill-opacity=".07"/></pattern>
<clipPath id="clip"><rect width="{W}" height="{H}" rx="20"/></clipPath>
</defs>
<g clip-path="url(#clip)"><rect width="{W}" height="{H}" fill="#070707"/>{body}</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="19.5" fill="none" stroke="#fff" stroke-opacity=".08"/>
</svg>'''
    (DOCS / "banner.svg").write_text(svg, encoding="utf-8")


def screenshots():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for tab in TABS:
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--window-size=1600,940", "--virtual-time-budget=6000",
                        f"--screenshot={DOCS / f'{tab}.png'}", f"http://127.0.0.1:{srv.server_port}/docs/showcase.html?tab={tab}"],
                       check=True, capture_output=True)
    srv.shutdown()


def gif():
    """Cross-fade through the four tabs, 2.4 s each."""
    ins = sum((["-loop", "1", "-t", "2.9", "-i", str(DOCS / f"{t}.png")] for t in TABS), [])
    fades = "".join(f"[v{i}][{i + 1}:v]xfade=transition=fade:duration=0.5:offset={2.4 * (i + 1):.1f}[v{i + 1}];" for i in range(len(TABS) - 1))
    graph = (f"[0:v]copy[v0];{fades}[v{len(TABS) - 1}]scale=1000:-1:flags=lanczos,fps=12,split[a][b];"
             "[a]palettegen=max_colors=200[p];[b][p]paletteuse=dither=sierra2_4a")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, str(DOCS / "demo.gif")], check=True)


if __name__ == "__main__":
    banner()
    screenshots()
    gif()
    print("Wrote", ", ".join(p.name for p in sorted(DOCS.glob("*.*")) if p.suffix in (".svg", ".png", ".gif")))
