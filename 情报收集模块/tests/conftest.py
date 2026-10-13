import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def attack_html():
    return (Path(__file__).parent / "fixtures" / "attack.html").read_text()
