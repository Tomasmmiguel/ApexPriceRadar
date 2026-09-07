import subprocess
import sys


def build():
    print("=== A iniciar a compilação do executável autónomo (.exe) ===")
    
    # Comando PyInstaller para gerar um ficheiro .exe único e autónomo
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name=ApexPriceRadar",
        "--icon=assets/logos/app_icon.ico",
        "--add-data=assets;assets",
        "--collect-all=customtkinter",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=PIL.PngImagePlugin",
        "--hidden-import=openpyxl",
        "--hidden-import=pandas",
        "--hidden-import=sqlalchemy",
        "--hidden-import=aiosqlite",
        "--hidden-import=tenacity",
        "--hidden-import=fake_useragent",
        "--hidden-import=bs4",
        "--hidden-import=httpx",
        "app_gui.py",
    ]
    
    print("A executar:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n=== COMPILAÇÃO CONCLUÍDA COM SUCESSO! ===")
        print("O ficheiro .exe autónomo está disponível em: dist/ApexPriceRadar.exe")
    else:
        print("\n=== Erro durante a compilação. Código:", result.returncode)

if __name__ == "__main__":
    build()
