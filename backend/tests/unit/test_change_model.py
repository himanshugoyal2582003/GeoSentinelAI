from __future__ import annotations

import torch

from app.change_model import ChangeCNN, load_model
from app.model_config import MODEL_INPUT_CHANNELS


def test_change_model_accepts_ten_channel_patches() -> None:
    model = ChangeCNN()

    assert model(torch.zeros(2, MODEL_INPUT_CHANNELS, 32, 32)).shape == (2,)


def test_load_model_preserves_six_channel_checkpoint(tmp_path) -> None:
    path = tmp_path / "legacy.pt"
    torch.save(ChangeCNN(input_channels=6).state_dict(), path)

    loaded = load_model(str(path))

    assert loaded is not None
    assert loaded.input_channels == 6
    assert not loaded.training
