"""
ApexPrice Engine - Desktop Application Entrypoint
Target script for PyInstaller desktop standalone build.
"""

from gui.app import launch_gui

if __name__ == "__main__":
    launch_gui()
