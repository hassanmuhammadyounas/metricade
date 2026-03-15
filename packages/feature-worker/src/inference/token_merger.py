"""
Token merging: compress N adjacent raw event rows into one token via mean pooling.
Input:  cont tensor [num_raw_events, N_CONT]  (variable length, up to 2048)
Output: cont tensor [MAX_SEQ_LEN, N_CONT]     (always exactly 256, zero-padded if needed)

Why mean pooling:
- Session-level features (indices 25-39) are constant across all rows — mean = same value, no information loss
- Event type one-hots (indices 0-8) become soft frequency counts within the merged group
  (e.g. [0.5, 0, 0.5, ...] means half page_view, half scroll in that group) — MORE informative than a single one-hot
- Continuous behavioral features (indices 9-24) are averaged — smooths noise, preserves trend
"""
import torch
from ..constants import MAX_RAW_EVENTS, TOKEN_MERGE_FACTOR, MAX_SEQ_LEN, N_CONT


def merge_tokens(cont: torch.Tensor) -> torch.Tensor:
    """
    cont: [num_raw_events, N_CONT] float32 — variable length, up to MAX_RAW_EVENTS
    returns: [MAX_SEQ_LEN, N_CONT] float32 — always exactly 256 rows, zero-padded
    """
    num_events = cont.shape[0]

    if num_events == 0:
        return torch.zeros(MAX_SEQ_LEN, N_CONT, dtype=torch.float32)

    # Take only the most recent MAX_RAW_EVENTS events (keep latest, drop oldest if overflow)
    if num_events > MAX_RAW_EVENTS:
        cont = cont[-MAX_RAW_EVENTS:]
        num_events = MAX_RAW_EVENTS

    # Pad to the nearest multiple of TOKEN_MERGE_FACTOR with zeros
    # so we can reshape cleanly into groups of N
    remainder = num_events % TOKEN_MERGE_FACTOR
    if remainder != 0:
        pad_size = TOKEN_MERGE_FACTOR - remainder
        padding = torch.zeros(pad_size, N_CONT, dtype=torch.float32)
        cont = torch.cat([cont, padding], dim=0)

    # Reshape into groups of TOKEN_MERGE_FACTOR and mean pool each group
    # [num_padded_events, N_CONT] → [num_tokens, TOKEN_MERGE_FACTOR, N_CONT] → [num_tokens, N_CONT]
    num_tokens = cont.shape[0] // TOKEN_MERGE_FACTOR
    merged = cont.view(num_tokens, TOKEN_MERGE_FACTOR, N_CONT).mean(dim=1)
    # merged shape: [num_tokens, N_CONT] where num_tokens <= MAX_SEQ_LEN

    # Final zero-padding to exactly MAX_SEQ_LEN
    if num_tokens < MAX_SEQ_LEN:
        pad = torch.zeros(MAX_SEQ_LEN - num_tokens, N_CONT, dtype=torch.float32)
        merged = torch.cat([merged, pad], dim=0)

    return merged  # [256, N_CONT]
