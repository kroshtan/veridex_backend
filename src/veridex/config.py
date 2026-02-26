from pathlib import Path

from dynaconf import Dynaconf

current_dir = Path(__file__).parent

settings = Dynaconf(root_path=current_dir, environments=True, settings_files=["settings.toml", ".secrets.toml"])
