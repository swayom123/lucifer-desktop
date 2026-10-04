from pathlib import Path

from scripts.install_desktop import desktop_entry
from ui.activation import instance_name, listen_for_activation, show_existing


def test_desktop_entry_launches_project_python_and_icon(tmp_path):
    entry = desktop_entry(tmp_path)
    assert f'Exec="{tmp_path}/.venv/bin/python" "{tmp_path}/main.py"' in entry
    assert f"Icon={tmp_path}/assets/lucifer.svg" in entry
    assert "Terminal=false" in entry
    assert "Categories=Utility;" in entry


def test_second_launch_activates_existing_window(qtbot, tmp_path):
    name = instance_name(Path(tmp_path))
    shown = []
    server = listen_for_activation(name, lambda: shown.append(True))
    try:
        assert show_existing(name)
        qtbot.waitUntil(lambda: shown == [True])
    finally:
        server.close()
