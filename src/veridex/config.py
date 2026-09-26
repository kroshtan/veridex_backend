from pathlib import Path

from dynaconf import Dynaconf

current_dir = Path(__file__).parent

settings = Dynaconf(
    root_path=current_dir,
    envvar_prefix="VERIDEX",
    settings_files=["settings.toml", ".secrets.toml"],
    environments=True,
)
