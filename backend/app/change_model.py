from __future__ import annotations

import torch
from torch import nn


class ChangeCNN(nn.Module):
    """Small CPU-friendly classifier for paired historical/recent image patches."""

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(6, 16, kernel_size=3, padding=1),
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
        model = ChangeCNN()
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        model.eval()
        return model
    except (FileNotFoundError, RuntimeError, OSError):
        return None

