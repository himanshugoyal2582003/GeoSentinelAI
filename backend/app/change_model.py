from __future__ import annotations

import torch
from torch import nn

from .model_config import MODEL_INPUT_CHANNELS


class ChangeCNN(nn.Module):
    """CPU-friendly binary change classifier for paired multispectral patches."""

    def __init__(self, input_channels: int = MODEL_INPUT_CHANNELS) -> None:
        super().__init__()
        if input_channels not in (6, MODEL_INPUT_CHANNELS):
            raise ValueError("ChangeCNN supports legacy RGB (6-channel) or multispectral (10-channel) inputs.")
        self.input_channels = input_channels
        self.features = nn.Sequential(
            nn.Conv2d(input_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(64, 1))

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(inputs)).squeeze(1)


def load_model(path: str) -> ChangeCNN | None:
    try:
        state_dict = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(state_dict, dict):
            return None
        first_layer = state_dict.get("features.0.weight")
        if not isinstance(first_layer, torch.Tensor) or first_layer.ndim != 4:
            return None
        model = ChangeCNN(input_channels=int(first_layer.shape[1]))
        model.load_state_dict(state_dict)
        model.eval()
        return model
    except (FileNotFoundError, RuntimeError, OSError, ValueError):
        return None

