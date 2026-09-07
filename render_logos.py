import subprocess
from pathlib import Path

from PIL import Image

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
LOGOS_DIR = Path("assets/logos").resolve()

def render_html_to_png(html_content: str, output_png: Path, width: int, height: int):
    temp_html = LOGOS_DIR / "_temp_render.html"
    temp_html.write_text(html_content, encoding="utf-8")
    
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--hide-scrollbars",
        "--default-background-color=00000000",
        f"--window-size={width},{height}",
        f"--screenshot={output_png}",
        temp_html.as_uri(),
    ]
    subprocess.run(cmd, check=True)
    if temp_html.exists():
        temp_html.unlink()

def main():
    # 1. Dark theme version of full logo (for dark theme app)
    html_dark_logo = """<!DOCTYPE html>
    <html>
    <head><style>
      body { margin: 0; padding: 0; background: transparent; overflow: hidden; display: flex; align-items: center; }
      svg { width: 560px; height: 160px; }
    </style></head>
    <body>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 160" width="560" height="160">
      <!-- Inverted V Apex in crisp white for dark mode -->
      <polyline points="26,118 78,42 130,118" fill="none" stroke="#FFFFFF" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- Radar waves in vibrant apex orange -->
      <path d="M 60 30 A 22 22 0 0 1 96 30" fill="none" stroke="#FF6A2B" stroke-width="3.5" stroke-linecap="round"/>
      <path d="M 50 18 A 34 34 0 0 1 106 18" fill="none" stroke="#FF6A2B" stroke-width="3.5" stroke-linecap="round" opacity="0.6"/>
      <circle cx="78" cy="42" r="7" fill="#FF6A2B"/>
      <!-- Wordmark -->
      <text x="168" y="80" font-family="'Segoe UI', -apple-system, Roboto, sans-serif" font-size="42" font-weight="700" fill="#FFFFFF">ApexPrice</text>
      <text x="168" y="112" font-family="'Segoe UI', -apple-system, Roboto, sans-serif" font-size="22" font-weight="600" letter-spacing="6" fill="#FF6A2B">RADAR</text>
    </svg>
    </body>
    </html>"""
    
    # 2. Light theme version of full logo
    html_light_logo = """<!DOCTYPE html>
    <html>
    <head><style>
      body { margin: 0; padding: 0; background: transparent; overflow: hidden; display: flex; align-items: center; }
      svg { width: 560px; height: 160px; }
    </style></head>
    <body>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 160" width="560" height="160">
      <polyline points="26,118 78,42 130,118" fill="none" stroke="#1B1D23" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M 60 30 A 22 22 0 0 1 96 30" fill="none" stroke="#FF6A2B" stroke-width="3.5" stroke-linecap="round"/>
      <path d="M 50 18 A 34 34 0 0 1 106 18" fill="none" stroke="#FF6A2B" stroke-width="3.5" stroke-linecap="round" opacity="0.6"/>
      <circle cx="78" cy="42" r="7" fill="#FF6A2B"/>
      <text x="168" y="80" font-family="'Segoe UI', -apple-system, Roboto, sans-serif" font-size="42" font-weight="700" fill="#1B1D23">ApexPrice</text>
      <text x="168" y="112" font-family="'Segoe UI', -apple-system, Roboto, sans-serif" font-size="22" font-weight="600" letter-spacing="6" fill="#FF6A2B">RADAR</text>
    </svg>
    </body>
    </html>"""

    # 3. Icon only (for window icon, taskbar, and favicon)
    html_icon = """<!DOCTYPE html>
    <html>
    <head><style>
      body { margin: 0; padding: 0; background: transparent; overflow: hidden; }
      svg { width: 160px; height: 160px; }
    </style></head>
    <body>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" width="160" height="160">
      <polyline points="26,118 78,42 130,118" fill="none" stroke="#FFFFFF" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M 60 30 A 22 22 0 0 1 96 30" fill="none" stroke="#FF6A2B" stroke-width="4" stroke-linecap="round"/>
      <path d="M 50 18 A 34 34 0 0 1 106 18" fill="none" stroke="#FF6A2B" stroke-width="4" stroke-linecap="round" opacity="0.7"/>
      <circle cx="78" cy="42" r="8" fill="#FF6A2B"/>
    </svg>
    </body>
    </html>"""

    logo_dark_png = LOGOS_DIR / "logo_dark.png"
    logo_light_png = LOGOS_DIR / "logo_light.png"
    icon_png = LOGOS_DIR / "app_icon.png"
    icon_ico = LOGOS_DIR / "app_icon.ico"

    print("A renderizar logo_dark.png...")
    render_html_to_png(html_dark_logo, logo_dark_png, 560, 160)
    print("A renderizar logo_light.png...")
    render_html_to_png(html_light_logo, logo_light_png, 560, 160)
    print("A renderizar app_icon.png...")
    render_html_to_png(html_icon, icon_png, 160, 160)

    # Gerar .ico a partir de app_icon.png com múltiplos tamanhos para Windows
    print("A gerar app_icon.ico...")
    img = Image.open(icon_png)
    img.save(icon_ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Renderização concluída com sucesso!")

if __name__ == "__main__":
    main()
