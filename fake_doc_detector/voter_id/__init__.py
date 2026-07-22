"""Voter ID verification package"""

from .voter_id_detector import VoterIDDetector
from . import verify_voter_id

__all__ = [
    "VoterIDDetector",
    "verify_voter_id",
]

