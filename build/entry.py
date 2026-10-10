"""PyInstaller entry point (absolute imports; hiveshot/__main__.py uses relative ones)."""
import multiprocessing

from hiveshot.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
