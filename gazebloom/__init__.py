"""GazeBloom desktop reminder prototype.

Non-medical screen-break reminders; no eye tracking, optical measurement or
validated treatment is provided.
"""
from .engine import BreakTimer, Settings, State, TransitionError

__all__ = ["BreakTimer", "Settings", "State", "TransitionError"]
