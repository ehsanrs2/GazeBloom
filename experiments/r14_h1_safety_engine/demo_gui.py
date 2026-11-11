#!/usr/bin/env python3
"""R14 manual H0 operator-only timer/STOP demo. NO experimental PNG rendering.

The GUI intentionally shows ONLY text placeholders, never actual stimulus
images, video, volunteer answers, session files or human-study authorization.
"""
from __future__ import annotations

import argparse
import time

from session import SimulatedSession
from simulate import fake_binding


def launch(*, operator_demo: bool) -> None:
    if not operator_demo:
        raise ValueError("operator-only simulation requires --operator-demo")
    # Import Tk only after explicit operator acknowledgement.
    import tkinter as tk

    engine=SimulatedSession(fake_binding())
    app=tk.Tk()
    app.title("R14 — H0 OPERATOR TIMER / STOP DEMO — NO PARTICIPANTS")
    app.geometry("780x390")
    app.configure(background="#242424")
    start_clock=time.monotonic()

    def now() -> float:
        return time.monotonic()-start_clock

    head=tk.Label(app,background="#242424",foreground="#f9d799",
                  font=("Sans",14,"bold"),
                  text="SIMULATION ONLY — DO NOT USE WITH PARTICIPANTS")
    head.pack(pady=12)
    placeholder=tk.Label(app,bg="#555555",fg="white",width=70,
                         height=5,font=("Sans",14,"bold"))
    placeholder.pack(padx=12,pady=5)
    description=tk.Label(app,bg="#242424",fg="white",font=("Sans",12),
                         justify="center")
    description.pack(pady=8)
    commands=tk.Frame(app,bg="#242424")
    commands.pack(pady=12)
    go=tk.Button(commands,text="Start virtual trial",width=20)
    go.pack(side="left",padx=5)
    response=tk.Button(commands,text="Record FAKE 7/10",width=20)
    response.pack(side="left",padx=5)
    stop=tk.Button(commands,text="STOP NOW (Esc)",width=20,
                   bg="#7a2020",fg="white")
    stop.pack(side="left",padx=5)

    def redraw() -> None:
        s=engine.snapshot(now())
        go.configure(state="normal" if s.state=="READY" else "disabled")
        response.configure(state="normal" if s.state=="RESPONSE" else "disabled")
        stop.configure(state="normal" if s.stop_available else "disabled")
        if s.state=="VIEWING":
            placeholder.configure(text="VIRTUAL VIEWING — NO IMAGE DISPLAYED",
                                  bg="#666666")
        elif s.state=="STOPPED":
            placeholder.configure(text="PERMANENT STOP — NO RESUME",
                                  bg="#7a2020")
        else:
            placeholder.configure(text="BLANK / NEUTRAL SIMULATION — NO STIMULUS",
                                  bg="#555555")
        description.configure(
            text=f"Virtual trial {s.trial_number}/8 | State: {s.state}"
                 f" | view left: {s.display_seconds_remaining:.1f}s"
                 f" | rest left: {s.rest_seconds_remaining:.1f}s\n"
                 "No photos, no camera, no consent, no human data, no automatic trial start.")
    def on_start() -> None:
        engine.start(now())
        redraw()
    def on_fake_response() -> None:
        engine.record_response(now(),clarity=7,comfort=7,reading_correct=True)
        redraw()
    def on_stop(_event=None) -> None:
        engine.stop(now())
        redraw()
    def on_close() -> None:
        engine.stop(now())
        app.destroy()
    def poll() -> None:
        if app.winfo_exists():
            redraw()
            app.after(100,poll)

    go.configure(command=on_start)
    response.configure(command=on_fake_response)
    stop.configure(command=on_stop)
    app.bind("<Escape>",on_stop)
    app.protocol("WM_DELETE_WINDOW",on_close)
    poll()
    app.mainloop()


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-demo",action="store_true")
    args=parser.parse_args()
    launch(operator_demo=args.operator_demo)


if __name__=="__main__":
    main()
