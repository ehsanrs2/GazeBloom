"""One-shot physical switch gate, also usable on CircuitPython.

No automatic keystroke, re-arm, or marker reset in a running process.
"""
RELEASE_S = 0.20
PRESS_S = 0.030


class Trigger:
    def __init__(self, marker_high, send_escape):
        self.marker_high = marker_high
        self.send_escape = send_escape
        self.state = "WAIT_RELEASE"
        self.since = None
        self.previous_time = None

    def update(self, pressed, now):
        if self.state in ("FIRED", "FAULT"):
            return self.state
        if (type(pressed) is not bool or not isinstance(now, (int, float))
                or isinstance(now, bool) or not 0 <= now < float("inf")
                or (self.previous_time is not None and now < self.previous_time)):
            self.state = "FAULT"
            raise ValueError("invalid input or clock")
        self.previous_time = now
        wanted = pressed if self.state == "READY" else not pressed
        if not wanted:
            self.since = None
            return self.state
        if self.since is None:
            self.since = now
        duration = PRESS_S if self.state == "READY" else RELEASE_S
        if now - self.since < duration:
            return self.state
        self.since = None
        if self.state == "WAIT_RELEASE":
            self.state = "READY"
        else:
            # Latch before I/O. On failure there is no second key or retry.
            self.state = "FIRED"
            try:
                self.marker_high()
                self.send_escape()
            except Exception:
                self.state = "FAULT"
                raise
        return self.state
