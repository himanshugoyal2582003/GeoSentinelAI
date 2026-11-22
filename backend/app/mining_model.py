from __future__ import annotations

import torch
from torch import nn


class MineFootprintCNN(nn.Module):
    """Small U-Net that segments mine footprints in Sentinel-2 RGB patches."""

    def __init__(self) -> None:
        super().__init__()
        self.enc1 = self._block(3, 16)
        self.enc2 = self._block(16, 32)
        self.bottleneck = self._block(32, 64)
        self.pool = nn.MaxPool2d(2)
        self.up2 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec2 = self._block(64, 32)
        self.up1 = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.dec1 = self._block(32, 16)
        self.output = nn.Conv2d(16, 1, kernel_size=1)

    @staticmethod
    def _block(in_channels: int, out_channels: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        enc1 = self.enc1(inputs)
        enc2 = self.enc2(self.pool(enc1))
        center = self.bottleneck(self.pool(enc2))
        dec2 = self.dec2(torch.cat([self.up2(center), enc2], dim=1))
        dec1 = self.dec1(torch.cat([self.up1(dec2), enc1], dim=1))
        return self.output(dec1).squeeze(1)


def load_mining_model(path: str) -> MineFootprintCNN | None:
    try:
        model = MineFootprintCNN()
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        model.eval()
        return model
    except (FileNotFoundError, RuntimeError, OSError):
        return None
