# @author 4Kumiho
# Copyright (c) 2026 4Kumiho. All rights reserved. See LICENSE.

"""OPTIONAL, developer-only: export a MobileNetV3-Small feature extractor to ONNX.

UIV Studio works without it (hand-crafted HOG + color descriptor). With the CNN
descriptor the visual score is more robust to theme/rendering changes.
The exported file (~6 MB) is picked up automatically when placed at
uiv_studio/resources/models/embedder.onnx and bundled by PyInstaller.

Requires (only on the dev machine):  pip install torch torchvision onnx
"""

from pathlib import Path

import torch
import torchvision

OUT = Path(__file__).resolve().parents[1] / "uiv_studio" / "resources" / "models" / "embedder.onnx"


class Features(torch.nn.Module):
    def __init__(self):
        super().__init__()
        m = torchvision.models.mobilenet_v3_small(weights=torchvision.models.MobileNet_V3_Small_Weights.DEFAULT)
        self.features = m.features
        self.pool = torch.nn.AdaptiveAvgPool2d(1)

    def forward(self, x):
        return torch.flatten(self.pool(self.features(x)), 1)   # 576-d


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    model = Features().eval()
    dummy = torch.zeros(1, 3, 128, 128)
    torch.onnx.export(model, dummy, str(OUT), input_names=["input"], output_names=["features"], opset_version=17)
    print(f"Exported {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
