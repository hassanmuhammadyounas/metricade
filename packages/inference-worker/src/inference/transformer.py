"""
BehavioralTransformer model definition.
Input: 51-feature tensor. Output: 192-dimensional session vector (float32).
"""
import torch
import torch.nn as nn
from ..constants import VECTOR_DIMS


class BehavioralTransformer(nn.Module):
    INPUT_DIM = 51
    OUTPUT_DIM = VECTOR_DIMS  # 192

    def __init__(self, d_model: int = 128, nhead: int = 4, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input_proj = nn.Linear(self.INPUT_DIM, d_model)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dropout=dropout, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.output_proj = nn.Linear(d_model, self.OUTPUT_DIM)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [batch, seq_len, 51]
        x = self.input_proj(x)             # [batch, seq_len, d_model]
        x = self.transformer(x)            # [batch, seq_len, d_model]
        x = x.mean(dim=1)                  # mean pooling → [batch, d_model]
        x = self.output_proj(x)            # [batch, 192]
        x = nn.functional.normalize(x, dim=-1)  # L2 normalize for cosine similarity
        return x

    @torch.no_grad()
    def encode(self, features: torch.Tensor) -> list[float]:
        """Encode a single session feature matrix → 192-dim vector."""
        self.eval()
        vec = self(features.unsqueeze(0))   # add batch dim
        return vec.squeeze(0).tolist()
