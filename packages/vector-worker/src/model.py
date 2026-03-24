"""
Hierarchical GRU (H-GRU) session encoder.

Two-level GRU:
  Level 1 — Event GRU  : processes events within a page → page embedding
  Level 2 — Session GRU: processes page embeddings      → session embedding

Session context (device, country, hour, etc.) is injected as the
initial hidden state of the Session GRU.

Final output: L2-normalised embed_dim-dimensional vector.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from .features import EVENT_DIM, PAGE_DIM, SESSION_DIM


class HierarchicalGRUEncoder(nn.Module):
    """
    Args:
        event_hidden  : Event GRU hidden size
        session_hidden: Session GRU hidden size
        embed_dim     : Final embedding dimension (stored in Upstash)
    """

    def __init__(
        self,
        event_hidden:   int = 64,
        session_hidden: int = 64,
        embed_dim:      int = 64,
    ):
        super().__init__()

        self.event_hidden   = event_hidden
        self.session_hidden = session_hidden
        self.embed_dim      = embed_dim

        # ── Level 1: Event GRU ──────────────────────────────────────────
        self.event_norm = nn.LayerNorm(EVENT_DIM)
        self.event_gru  = nn.GRU(
            input_size  = EVENT_DIM,
            hidden_size = event_hidden,
            batch_first = True,
            num_layers  = 1,
        )

        # ── Level 2: Session GRU ────────────────────────────────────────
        # Input = event_gru_output (event_hidden) + page_features (PAGE_DIM)
        page_input_dim = event_hidden + PAGE_DIM
        self.page_norm   = nn.LayerNorm(page_input_dim)
        self.session_gru = nn.GRU(
            input_size  = page_input_dim,
            hidden_size = session_hidden,
            batch_first = True,
            num_layers  = 1,
        )

        # Session context → initial hidden state for Session GRU
        self.session_h0 = nn.Sequential(
            nn.Linear(SESSION_DIM, session_hidden),
            nn.Tanh(),
        )

        # ── Projection head ─────────────────────────────────────────────
        # Maps session_hidden → embed_dim with residual-style MLP
        self.proj = nn.Sequential(
            nn.Linear(session_hidden, session_hidden),
            nn.LayerNorm(session_hidden),
            nn.GELU(),
            nn.Linear(session_hidden, embed_dim),
        )

    # ── Internal helpers ────────────────────────────────────────────────────

    def _encode_page(self, event_seq: torch.Tensor) -> torch.Tensor:
        """
        event_seq : (n_events, EVENT_DIM)
        Returns   : (event_hidden,)  — mean of all GRU hidden states
        """
        x = self.event_norm(event_seq)           # (n_events, EVENT_DIM)
        x = x.unsqueeze(0)                       # (1, n_events, EVENT_DIM)
        hidden_states, _ = self.event_gru(x)     # (1, n_events, event_hidden)
        # Mean-pool hidden states (better than last-state for long pages)
        page_emb = hidden_states.squeeze(0).mean(dim=0)  # (event_hidden,)
        return page_emb

    # ── Forward ─────────────────────────────────────────────────────────────

    def forward(
        self,
        pages_data:  list[tuple[torch.Tensor, torch.Tensor]],
        session_ctx: torch.Tensor,
    ) -> torch.Tensor:
        """
        pages_data  : list of (event_seq, page_feat) per page
                      event_seq  : (n_events, EVENT_DIM)
                      page_feat  : (PAGE_DIM,)
        session_ctx : (SESSION_DIM,)

        Returns     : (embed_dim,)  L2-normalised session embedding
        """
        # Initial hidden state from session context
        h0 = self.session_h0(session_ctx)        # (session_hidden,)
        h0 = h0.unsqueeze(0).unsqueeze(0)        # (1, 1, session_hidden)

        # Encode each page and build page sequence
        page_vecs = []
        for event_seq, page_feat in pages_data:
            page_emb = self._encode_page(event_seq)     # (event_hidden,)
            combined = torch.cat([page_emb, page_feat]) # (event_hidden + PAGE_DIM,)
            page_vecs.append(combined)

        # Stack → (1, n_pages, page_input_dim)
        page_seq = torch.stack(page_vecs).unsqueeze(0)  # (1, n_pages, page_input_dim)
        page_seq = self.page_norm(page_seq)

        # Session GRU over pages — mean pool all hidden states
        hidden_states, _ = self.session_gru(page_seq, h0)  # (1, n_pages, session_hidden)
        session_emb = hidden_states.squeeze(0).mean(dim=0)  # (session_hidden,)

        # Project and L2-normalise
        out = self.proj(session_emb)                        # (embed_dim,)
        return F.normalize(out, dim=-1)


# ── VICReg loss ─────────────────────────────────────────────────────────────

def vicreg_loss(
    z1: torch.Tensor,
    z2: torch.Tensor,
    sim_coef: float = 25.0,
    var_coef: float = 25.0,
    cov_coef: float =  1.0,
) -> torch.Tensor:
    """
    VICReg: Variance-Invariance-Covariance Regularization.
    z1, z2 : (batch, embed_dim) — two augmented views of the same sessions

    Three terms:
      Invariance : z1 ≈ z2  (same session, different augmentation)
      Variance   : each dimension has std > 1  (prevents collapse)
      Covariance : dimensions are decorrelated  (no redundancy)
    """
    N, D = z1.shape

    # Invariance — MSE between the two views
    inv_loss = F.mse_loss(z1, z2)

    # Variance — push std of each dim above 1
    std1 = torch.sqrt(z1.var(dim=0) + 1e-4)
    std2 = torch.sqrt(z2.var(dim=0) + 1e-4)
    var_loss = (F.relu(1.0 - std1).mean() + F.relu(1.0 - std2).mean()) / 2.0

    # Covariance — off-diagonal elements should be zero
    z1c = z1 - z1.mean(dim=0)
    z2c = z2 - z2.mean(dim=0)
    cov1 = (z1c.T @ z1c) / (N - 1)
    cov2 = (z2c.T @ z2c) / (N - 1)
    off1 = cov1.pow(2).sum() - cov1.pow(2).diagonal().sum()
    off2 = cov2.pow(2).sum() - cov2.pow(2).diagonal().sum()
    cov_loss = (off1 + off2) / D

    return sim_coef * inv_loss + var_coef * var_loss + cov_coef * cov_loss


# ── Augmentation ─────────────────────────────────────────────────────────────

def augment_events(events: list[dict], drop_rate: float = 0.15) -> list[dict]:
    """
    Create one augmented view of a session's event list:
      - Randomly drop ~15% of events (not page_view/route_change)
      - Jitter delta_ms by ±10%
    """
    import random
    result = []
    for e in events:
        et = (e.get('event_type') or '').lower()
        # Always keep page navigation events (preserve page structure)
        if et in ('page_view', 'route_change'):
            result.append(e)
            continue
        if random.random() < drop_rate:
            continue
        # Jitter delta_ms
        if e.get('delta_ms') is not None:
            e = dict(e)
            e['delta_ms'] = e['delta_ms'] * random.uniform(0.9, 1.1)
        result.append(e)
    return result if result else events  # guard: never return empty
