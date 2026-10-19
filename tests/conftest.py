import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # sem tela: os testes rodam em qualquer lugar

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


@pytest.fixture(scope="session")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def calculadora(tmp_path):
    """Uma cópia do exemplo da calculadora, para cada teste mexer à vontade."""
    destino = tmp_path / "calculadora"
    shutil.copytree(EXEMPLOS / "calculadora", destino, ignore=shutil.ignore_patterns("telas", "__pycache__"))
    return destino


@pytest.fixture
def config(tmp_path, app):
    from PySide6.QtCore import QSettings
    return QSettings(str(tmp_path / "config.ini"), QSettings.Format.IniFormat)
