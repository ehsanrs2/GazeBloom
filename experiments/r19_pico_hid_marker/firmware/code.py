"""Copy to CIRCUITPY/code.py on a Pico RP2040 with matching adafruit_hid."""
import time
import board
import digitalio
import supervisor
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from trigger_core import Trigger

# Prevent filesystem writes from automatically restarting the one-shot gate.
supervisor.runtime.autoreload = False
marker = digitalio.DigitalInOut(board.GP15)
marker.switch_to_output(value=False)
switch = digitalio.DigitalInOut(board.GP14)
switch.switch_to_input(pull=digitalio.Pull.UP)
keyboard = Keyboard(usb_hid.devices)


def send_escape():
    # The marker has already been raised. No repeated presses.
    keyboard.send(Keycode.ESCAPE)


trigger = Trigger(lambda: setattr(marker, "value", True), send_escape)
print("R19: focus neutral bench before pressing; unplug/reset between captures")
previous = trigger.state
while True:
    try:
        state = trigger.update(not switch.value, time.monotonic())
    except Exception as exc:
        print("FAULT: do not use capture:", repr(exc))
        break
    if state != previous:
        print(state)
        previous = state
    if state in ("FIRED", "FAULT"):
        break
    time.sleep(0.005)

# Hold marker level and never send another key. Reset only with operator action.
while True:
    time.sleep(1)
