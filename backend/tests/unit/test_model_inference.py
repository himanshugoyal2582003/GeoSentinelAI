from __future__ import annotations

import numpy as np
import torch

from app.main import _analyse_pair
from app.spectral import SpectralChange


class CaptureModel(torch.nn.Module):
    input_channels = 10

    def __init__(self) -> None:
        super().__init__()
        self.received: torch.Tensor | None = None

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        self.received = inputs.detach().clone()
        return torch.zeros(inputs.shape[0])


def test_live_scene_passes_ten_channel_patch_to_model(monkeypatch) -> None:
    model = CaptureModel()
    monkeypatch.setattr("app.main.CHANGE_MODEL", model)
    monkeypatch.setattr("app.main._components", lambda _: [(10, 10, 20, 20, 400)])
    shape = (64, 64)
    spectral_change = SpectralChange(
        mask=np.ones(shape, dtype=bool),
        score=np.full(shape, 0.2, dtype=np.float32),
        ndvi_loss=np.full(shape, 0.1, dtype=np.float32),
        bsi_gain=np.zeros(shape, dtype=np.float32),
        cloud_mask=np.zeros(shape, dtype=bool),
        threshold=0.1,
    )
    model_input = np.stack([np.full(shape, channel / 10, dtype=np.float32) for channel in range(10)])

    result = _analyse_pair(
        np.full((64, 64, 3), 100, dtype=np.uint8),
        np.full((64, 64, 3), 100, dtype=np.uint8),
        18.5,
        73.8,
        10,
        "live-sentinel2",
        "2025-01-01",
        "2025-02-01",
        spectral_change=spectral_change,
        spectral_model_input=model_input,
        alignment_shift=(0, 0),
    )

    assert model.received is not None
    assert model.received.shape == (1, 10, 32, 32)
    torch.testing.assert_close(model.received[0, :, 16, 16], torch.arange(10) / 10)
    assert result["processing"]["modelAppliedToFindings"] == 1
    assert result["findings"][0]["modelScore"] == 0.5


def test_ten_channel_model_is_skipped_when_multispectral_input_is_missing(monkeypatch) -> None:
    model = CaptureModel()
    monkeypatch.setattr("app.main.CHANGE_MODEL", model)
    monkeypatch.setattr("app.main._components", lambda _: [(10, 10, 20, 20, 400)])
    image = np.full((64, 64, 3), 100, dtype=np.uint8)

    result = _analyse_pair(
        image,
        image.copy(),
        18.5,
        73.8,
        10,
        "upload-pair",
        "2025-01-01",
        "2025-02-01",
        alignment_shift=(0, 0),
    )

    assert model.received is None
    assert result["findings"][0]["modelScore"] is None
    assert result["processing"]["modelAppliedToFindings"] == 0
    assert result["processing"]["modelNote"] == "The 10-channel model is skipped for RGB-only image uploads."
