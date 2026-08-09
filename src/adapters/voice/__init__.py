"""Voice providers and the degradation cascade (PLAN-02 P16).

`src/domain/voice.py` owns the tier vocabulary and the pure selection logic; this package owns
everything that touches a network or an environment variable.
"""

from __future__ import annotations

from src.adapters.voice.cascade import VoiceCascade
from src.adapters.voice.protocol import QuotaExhausted, VoiceError

__all__ = ["QuotaExhausted", "VoiceCascade", "VoiceError"]
