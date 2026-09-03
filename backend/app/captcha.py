"""Stateless math CAPTCHA for the public research-order form.

A real CAPTCHA must be verified on the *server* — a browser-only check is bypassed
by any bot that POSTs the form directly. We keep it stateless (no DB row, no session
store, survives multiple workers and restarts) by signing the challenge with an HMAC:

    challenge():  pick a,b -> answer = a+b, exp = now + TTL
                  sig = HMAC_SHA256(SECRET, "answer|exp")
                  return {question, exp, sig}   # the answer itself is never sent out

    verify(answer, exp, sig):  recompute the HMAC over the *submitted* answer+exp and
                  constant-time compare. A wrong answer, a forged signature, or an
                  expired challenge all fail.

The answer travels back from the client in the clear (the user typed it), but the
signature binds it: a bot cannot fabricate a valid (answer, exp, sig) triple without
the server secret, and cannot reuse a guess against a different challenge.
"""

from __future__ import annotations

import hmac
import os
import random
import time
from hashlib import sha256

from fastapi import HTTPException

# Reuse the app's existing signing secret so no new env var is required to deploy.
# (auth.py defines JWT_SECRET the same way; CAPTCHA_SECRET lets ops rotate it apart.)
_SECRET = (os.environ.get("CAPTCHA_SECRET")
           or os.environ.get("JWT_SECRET", "dev-insecure-change-me")).encode()

TTL_SECONDS = 600  # a challenge is valid for 10 minutes


def _sign(answer: int, exp: int) -> str:
    msg = f"{answer}|{exp}".encode()
    return hmac.new(_SECRET, msg, sha256).hexdigest()


def make_challenge() -> dict:
    """A fresh signed addition challenge: ``{question, exp, sig}``."""
    a, b = random.randint(1, 9), random.randint(1, 9)
    exp = int(time.time()) + TTL_SECONDS
    return {"question": f"{a} + {b}", "exp": exp, "sig": _sign(a + b, exp)}


def verify(answer: int, exp: int, sig: str) -> None:
    """Raise ``HTTPException(400, 'captcha')`` unless the triple is valid and unexpired."""
    if int(time.time()) > exp:
        raise HTTPException(status_code=400, detail="captcha")
    if not hmac.compare_digest(_sign(answer, exp), sig):
        raise HTTPException(status_code=400, detail="captcha")
