"""Third-party sign-in providers. Google today; the shape generalises to a second one.

Every provider here answers exactly one question -- *who is this person* -- and hands the
answer back. Issuing a session, creating an account and deciding what that account may do all
stay in Cardinal's own `AccountStore` (P12), so identity has one home rather than two.
"""

from __future__ import annotations

from src.adapters.oauth.google import GoogleAuthError, GoogleIdentity

__all__ = ["GoogleAuthError", "GoogleIdentity"]
