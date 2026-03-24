"""
BehavioralTransformer — session encoder.
Input:  cont=[MAX_SEQ_LEN, N_CONT=41], cat=[N_CAT=8]
Output: 192-dim L2-normalised session vector (float32)

Architecture:
  8 × nn.Embedding (74 total dims) → broadcast to seq_len
  concat with cont (41 dims) → input_proj(115 → d_model=128)
  CLS token + TransformerEncoder(nhead=4, layers=2)
  CLS output → output_proj(128 → 192) → L2 normalize
"""
import torch
import torch.nn as nn

from ..constants import VECTOR_DIMS, N_CONT

# Each entry: (vocab_size, embed_dim) — must match featurizer.py vocabularies exactly.
# Order matches cat tensor indices 0–7.
_EMB_CONFIGS: list[tuple[int, int]] = [
    (21,    10),   # 0: browser_family  (BROWSER_VOCAB  max=20  +1 UNK)
    (14,     8),   # 1: os_family       (OS_VOCAB       max=13  +1 UNK)
    (111,    8),   # 2: ip_country      (COUNTRY_VOCAB  max=110 +1 UNK)
    (14,     8),   # 3: click_id_type   (CLICK_ID_VOCAB max=13  +1 UNK)
    (16,     8),   # 4: session_source  (SESSION_SOURCE_VOCAB max=15 +1 UNK)
    (13,     8),   # 5: session_medium  (SESSION_MEDIUM_VOCAB max=12 +1 UNK)
    (18,     8),   # 6: device_vendor   (DEVICE_VENDOR_VOCAB  max=17 +1 UNK)
    (4097,  16),   # 7: page_path_hash  (hash % 4096) + 1; 0=UNK
]
_TOTAL_EMB_DIM = sum(d for _, d in _EMB_CONFIGS)   # 74
_INPUT_DIM     = N_CONT + _TOTAL_EMB_DIM            # 41 + 74 = 115


class BehavioralTransformer(nn.Module):
    OUTPUT_DIM = VECTOR_DIMS  # 192

    def __init__(self, d_model: int = 128, nhead: int = 4, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()

        self.embeddings = nn.ModuleList([
            nn.Embedding(vocab_size, dim) for vocab_size, dim in _EMB_CONFIGS
        ])

        self.input_proj = nn.Linear(_INPUT_DIM, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=dropout, batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # CLS token: learnable [1, 1, d_model] parameter, prepended to each sequence.
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))

        self.output_proj = nn.Linear(d_model, self.OUTPUT_DIM)

    def forward(self, cont: torch.Tensor, cat: torch.Tensor) -> torch.Tensor:
        """
        cont: [batch, seq_len, N_CONT]   float32
        cat:  [batch, N_CAT]             int64
        returns: [batch, 192]            float32, L2-normalised
        """
        batch_size, seq_len, _ = cont.shape

        # Embed each categorical field → concat → [batch, total_emb_dim]
        emb = torch.cat(
            [self.embeddings[i](cat[:, i]) for i in range(len(_EMB_CONFIGS))],
            dim=-1,
        )  # [batch, 74]

        # Broadcast session-level embeddings across every event row
        emb = emb.unsqueeze(1).expand(-1, seq_len, -1)  # [batch, seq_len, 74]

        x = torch.cat([cont, emb], dim=-1)   # [batch, seq_len, 114]
        x = self.input_proj(x)               # [batch, seq_len, d_model]

        # Prepend CLS token
        cls = self.cls_token.expand(batch_size, -1, -1)  # [batch, 1, d_model]
        x   = torch.cat([cls, x], dim=1)                 # [batch, seq_len+1, d_model]

        x = self.transformer(x)   # [batch, seq_len+1, d_model]
        x = x[:, 0, :]            # CLS output → [batch, d_model]

        x = self.output_proj(x)                       # [batch, 192]
        x = nn.functional.normalize(x, dim=-1)        # L2 normalise
        return x

    @torch.no_grad()
    def encode(self, cont: torch.Tensor, cat: torch.Tensor) -> list[float]:
        """Encode a single session → 192-dim vector. Adds/removes batch dim."""
        self.eval()
        vec = self(cont.unsqueeze(0), cat.unsqueeze(0))
        return vec.squeeze(0).tolist()
