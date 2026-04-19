"""
A32NX Throttle Overlay
Tested with FlyByWire A320neo (FBW) on MSFS 2020/2024
Reads throttle position via SimConnect — no SimConnect, no launch.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import sys
from pathlib import Path

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.joystick.init()

try:
    from SimConnect import SimConnect, AircraftRequests
    SIMCONNECT_AVAILABLE = True
except ImportError:
    SIMCONNECT_AVAILABLE = False

# ── Config ───────────────────────────────────────────────────────────────────
POLL_HZ    = 15   # joystick poll rate
SC_POLL_HZ = 20   # SimConnect poll rate
SC_TIMEOUT = 10   # seconds to wait for SimConnect before giving up

CAL_FILE   = Path(__file__).parent / "throttle_range_cal.json"
BG_COLOR   = "#0a0d0f"
ALPHA      = 0.88

# SimConnect lever ranges — A32NX FBW specific
SC_NRM_THRESHOLD =  0.5    # above this = normal thrust
SC_REV_THRESHOLD = -1.0    # below this = reverse thrust
DEBOUNCE_N       = 5       # reads before mode commits (~0.25s)

COLORS = {
    "TOGA":     "#d43a2a",
    "FLX":      "#e6a817",
    "CLB":      "#1a7a4a",
    "IDLE":     "#4a5560",
    "REV_IDLE": "#6a3acd",
    "REV_FULL": "#4a1a9e",
    "---":      "#333a42",
}

AXIS_ENG    = 2
CANVAS_W    = 90
CANVAS_H    = 240
BAR_L, BAR_R = 26, 50
TICK_R      = BAR_R + 2
LABEL_X     = BAR_R + 12
TOP_Y       = 30
BOT_Y       = 198
FWD_DETENTS = ["TOGA", "FLX", "CLB", "IDLE"]
REV_DETENTS = ["REV_FULL", "REV_IDLE"]


# ── Helpers ──────────────────────────────────────────────────────────────────
def cal_centre(cal, label):
    v = cal.get(label)
    if isinstance(v, list) and len(v) == 2:
        return (v[0] + v[1]) / 2.0
    return None

def val_to_y(val, val_top, val_bot, y_top, y_bot):
    if abs(val_top - val_bot) < 1e-9:
        return y_top
    frac = (val - val_top) / (val_bot - val_top)
    return int(y_top + max(0.0, min(1.0, frac)) * (y_bot - y_top))

def compute_layout(cal, rev):
    if not rev:
        return {"val_top": cal_centre(cal, "TOGA") or -1.0,
                "val_bot": cal_centre(cal, "IDLE") or  1.0,
                "y_top": TOP_Y, "y_bot": BOT_Y, "detents": FWD_DETENTS}
    return {"val_top": cal_centre(cal, "REV_FULL") or -1.0,
            "val_bot": cal_centre(cal, "REV_IDLE") or  1.0,
            "y_top": TOP_Y, "y_bot": BOT_Y, "detents": REV_DETENTS}

def detent_y(label, layout, cal):
    v = cal_centre(cal, label)
    if v is None: return None
    return val_to_y(v, layout["val_top"], layout["val_bot"],
                    layout["y_top"], layout["y_bot"])

def get_label(val, cal, rev):
    for label in (REV_DETENTS if rev else FWD_DETENTS):
        limits = cal.get(label)
        if isinstance(limits, list) and len(limits) == 2:
            if min(limits) <= val <= max(limits):
                return label
    return "---"

def sc_mode_from_lever(v):
    if v is None:          return "unknown"
    if v >  SC_NRM_THRESHOLD: return "normal"
    if v <  SC_REV_THRESHOLD: return "reverse"
    return "unknown"       # dead zone near 0 — don't switch on this


# ── SimConnect thread ─────────────────────────────────────────────────────────
class SimReader(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.thr_val    = None
        self.rev_active = False
        self.connected  = False
        self.running    = True

    def run(self):
        while self.running:
            try:
                sm = SimConnect()
                aq = AircraftRequests(sm, _time=0)
                self.connected = True
                print("[SC] Connected to MSFS", flush=True)

                pending_mode = None
                mode_counter = 0

                while self.running:
                    val  = aq.get("GENERAL_ENG_THROTTLE_LEVER_POSITION:1")
                    mode = sc_mode_from_lever(val)
                    self.thr_val = val

                    # Debounce — commit only after N stable reads
                    if mode == pending_mode:
                        mode_counter += 1
                    else:
                        pending_mode = mode
                        mode_counter = 1

                    if mode_counter >= DEBOUNCE_N and pending_mode != "unknown":
                        new_rev = (pending_mode == "reverse")
                        if new_rev != self.rev_active:
                            print(f"[SC] Mode → {pending_mode.upper()}  "
                                  f"lever={val:.3f}", flush=True)
                        self.rev_active = new_rev

                    time.sleep(1.0 / SC_POLL_HZ)
                sm.exit()
            except Exception as e:
                self.connected  = False
                self.thr_val    = None
                self.rev_active = False
                print(f"[SC] Lost connection ({e}) — retrying in 3s", flush=True)
                time.sleep(3.0)

    def wait_for_connection(self, timeout=SC_TIMEOUT):
        """Block until connected or timeout (seconds). Returns True if connected."""
        print(f"[SC] Waiting for SimConnect (timeout {timeout}s)...", flush=True)
        elapsed = 0.0
        interval = 0.25
        while not self.connected:
            time.sleep(interval)
            elapsed += interval
            remaining = timeout - elapsed
            if elapsed % 2.0 < interval:   # print every 2s
                print(f"[SC] Still waiting... {remaining:.0f}s remaining", flush=True)
            if elapsed >= timeout:
                return False
        return True

    def stop(self):
        self.running = False


# ── Settings Dialog ───────────────────────────────────────────────────────────
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, current_cal, sim_reader, on_save):
        super().__init__(parent)
        self.title("Throttle Overlay — Settings")
        self.attributes("-topmost", True)
        self.configure(bg=BG_COLOR)
        self.resizable(False, False)
        self.on_save    = on_save
        self.sim_reader = sim_reader
        self.entries    = {}
        self._listening = False
        self._bound_btn = current_cal.get("rev_button", None)
        row = 0

        # Controller
        tk.Label(self, text="Controller", font=("Arial", 9, "bold"),
                 bg=BG_COLOR, fg="#7fa8c0").grid(row=row, columnspan=3, pady=(12,2)); row+=1
        self.devices = [pygame.joystick.Joystick(i).get_name()
                        for i in range(pygame.joystick.get_count())] or ["No controllers found"]
        self.combo = ttk.Combobox(self, values=self.devices, state="readonly", width=26)
        self.combo.grid(row=row, columnspan=3, padx=12, pady=(0,8)); row+=1
        saved = current_cal.get("device_index", 0)
        self.combo.current(saved if saved < len(self.devices) else 0)

        # Axis ranges
        tk.Label(self, text="Joystick Axis Ranges  (−1.0 → +1.0)",
                 font=("Arial", 9, "bold"), bg=BG_COLOR, fg="#7fa8c0").grid(
                     row=row, columnspan=3, pady=(4,2)); row+=1
        tk.Label(self, text="Min", bg=BG_COLOR, fg="#7fa8c0").grid(row=row, column=1)
        tk.Label(self, text="Max", bg=BG_COLOR, fg="#7fa8c0").grid(row=row, column=2); row+=1

        for gate in ["TOGA", "FLX", "CLB", "IDLE", "REV_IDLE", "REV_FULL"]:
            tk.Label(self, text=gate, bg=BG_COLOR,
                     fg=COLORS.get(gate, "#dce8f0")).grid(
                         row=row, column=0, padx=10, pady=2, sticky="e")
            gr = current_cal.get(gate, [0.0, 0.0])
            if not isinstance(gr, list): gr = [gr, gr]
            em = tk.Entry(self, width=8, bg="#1a1f24", fg="white", insertbackground="white")
            em.insert(0, str(gr[0])); em.grid(row=row, column=1, padx=5, pady=2)
            ex = tk.Entry(self, width=8, bg="#1a1f24", fg="white", insertbackground="white")
            ex.insert(0, str(gr[1])); ex.grid(row=row, column=2, padx=5, pady=2)
            self.entries[gate] = (em, ex); row+=1

        # Separator
        tk.Frame(self, bg="#2a3540", height=1).grid(
            row=row, columnspan=3, sticky="ew", padx=10, pady=8); row+=1

        # Reverse button bind
        tk.Label(self, text="Reverse Thrust Button Bind",
                 font=("Arial", 9, "bold"), bg=BG_COLOR, fg="#7fa8c0").grid(
                     row=row, columnspan=3, pady=(0,4)); row+=1
        tk.Label(self,
                 text="Click BIND then press the reverse button\non your controller.",
                 bg=BG_COLOR, fg="#5a7a90", font=("Arial", 8),
                 justify="left").grid(row=row, columnspan=3, padx=12, pady=(0,6)); row+=1

        bf = tk.Frame(self, bg=BG_COLOR)
        bf.grid(row=row, columnspan=3, pady=(0,4)); row+=1
        lbl_txt = f"Button {self._bound_btn}" if self._bound_btn is not None else "Not bound"
        self._btn_var = tk.StringVar(value=lbl_txt)
        self._btn_lbl = tk.Label(bf, textvariable=self._btn_var,
                                 bg="#111820", fg=COLORS["REV_IDLE"],
                                 font=("Consolas", 9), width=12, anchor="center", pady=3)
        self._btn_lbl.pack(side="left", padx=(0,6))
        self._bind_btn = tk.Button(bf, text="BIND", command=self._start_listen,
                                   bg="#1a2a3a", fg="#7fa8c0", relief="flat",
                                   font=("Arial", 8, "bold"), padx=6)
        self._bind_btn.pack(side="left", padx=(0,4))
        tk.Button(bf, text="CLEAR", command=self._clear_bind,
                  bg="#2a1a1a", fg="#d43a2a", relief="flat",
                  font=("Arial", 8, "bold"), padx=6).pack(side="left")

        self._sc_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._sc_var,
                 bg=BG_COLOR, fg="#6a9ab0",
                 font=("Consolas", 8)).grid(row=row, columnspan=3, pady=(0,4)); row+=1

        tk.Button(self, text="SAVE & CLOSE", command=self._save,
                  bg="#1a7a4a", fg="white", width=18,
                  font=("Arial", 9, "bold")).grid(row=row, columnspan=3, pady=12)

        self._poll()

    def _start_listen(self):
        self._listening = True
        self._btn_var.set("waiting...")
        self._bind_btn.config(fg="#ffaa00")
        self._sc_var.set("Press the reverse button on your controller...")

    def _clear_bind(self):
        self._bound_btn = None
        self._listening = False
        self._btn_var.set("Not bound")
        self._bind_btn.config(fg="#7fa8c0")
        self._sc_var.set("")

    def _poll(self):
        if not self.winfo_exists(): return
        if self._listening:
            pygame.event.pump()
            joy_idx = self.combo.current()
            if 0 <= joy_idx < pygame.joystick.get_count():
                joy = pygame.joystick.Joystick(joy_idx)
                joy.init()
                for b in range(joy.get_numbuttons()):
                    if joy.get_button(b):
                        self._bound_btn = b
                        self._btn_var.set(f"Button {b}")
                        self._bind_btn.config(fg="#7fa8c0")
                        self._listening = False
                        # Confirm with SC
                        if self.sim_reader and self.sim_reader.thr_val is not None:
                            v = self.sim_reader.thr_val
                            m = sc_mode_from_lever(v)
                            self._sc_var.set(f"✓ Bound!  SC lever={v:+.2f}  → {m.upper()}")
                        else:
                            self._sc_var.set("✓ Bound!  (SC not live)")
                        break
            if self.sim_reader and self.sim_reader.thr_val is not None:
                v = self.sim_reader.thr_val
                self._sc_var.set(f"SC lever: {v:+.3f}  [{sc_mode_from_lever(v)}]")
        self.after(50, self._poll)

    def _save(self):
        try:
            new_cal = {}
            for k, (em, ex) in self.entries.items():
                new_cal[k] = [float(em.get()), float(ex.get())]
            idx = self.combo.current()
            new_cal["device_index"] = idx if idx != -1 else 0
            new_cal["rev_button"]   = self._bound_btn
            self.on_save(new_cal)
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Enter decimal numbers only (e.g. -0.95)")


# ── Main App ──────────────────────────────────────────────────────────────────
class ThrottleApp:
    def __init__(self):
        self.cal         = self._load_cal()
        self.current_val = 0.0
        self.running     = True
        self._prev_btn   = False

        # ── Print startup info ───────────────────────────────────────────────
        print("=" * 55, flush=True)
        print("  A32NX Throttle Overlay", flush=True)
        print("=" * 55, flush=True)
        dev_idx = self.cal.get("device_index", 0)
        rev_btn = self.cal.get("rev_button", None)
        if pygame.joystick.get_count() > 0 and dev_idx < pygame.joystick.get_count():
            joy_name = pygame.joystick.Joystick(dev_idx).get_name()
        else:
            joy_name = "No controller found"
        print(f"  Controller   : {joy_name}", flush=True)
        print(f"  Axis index   : {AXIS_ENG}", flush=True)
        print(f"  Rev button   : {'Button ' + str(rev_btn) if rev_btn is not None else 'Not bound'}", flush=True)
        print(f"  Cal file     : {CAL_FILE}", flush=True)
        print("-" * 55, flush=True)
        print("  Detent axis ranges (joystick):", flush=True)
        for gate in ["TOGA", "FLX", "CLB", "IDLE", "REV_IDLE", "REV_FULL"]:
            v = self.cal.get(gate, "not set")
            print(f"    {gate:<10} {v}", flush=True)
        print("=" * 55, flush=True)

        # ── SimConnect — wait or abort ───────────────────────────────────────
        if not SIMCONNECT_AVAILABLE:
            print("\n[ERROR] SimConnect not installed.", flush=True)
            print("  Run:  pip install SimConnect", flush=True)
            sys.exit(1)

        self.sim = SimReader()
        self.sim.start()
        connected = self.sim.wait_for_connection(timeout=SC_TIMEOUT)

        if not connected:
            print(f"\n[ERROR] Could not connect to SimConnect after {SC_TIMEOUT}s.", flush=True)
            print("  Make sure Microsoft Flight Simulator is running", flush=True)
            print("  and you are loaded into a flight, then restart this app.", flush=True)
            self.sim.stop()
            sys.exit(1)

        # ── Build UI ─────────────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", ALPHA)
        self.root.configure(bg=BG_COLOR)
        self.root.geometry(f"{CANVAS_W}x{CANVAS_H}+100+100")

        self._setup_ui()
        self.root.bind("<ButtonPress-1>",
            lambda e: (setattr(self, '_dx', e.x), setattr(self, '_dy', e.y)))
        self.root.bind("<B1-Motion>", self._drag)
        self.root.bind("<Button-3>",
            lambda e: SettingsDialog(self.root, self.cal, self.sim, self._update_cal))

        threading.Thread(target=self._joy_loop, daemon=True).start()
        self._draw()

    def _drag(self, e):
        self.root.geometry(
            f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}")

    def _setup_ui(self):
        c = tk.Canvas(self.root, width=CANVAS_W, height=CANVAS_H,
                      bg=BG_COLOR, highlightthickness=0)
        c.pack()
        self.c = c
        c.create_rectangle(BAR_L, TOP_Y, BAR_R, BOT_Y, fill="#141a1f", outline="")
        self.bar = c.create_rectangle(BAR_L, BOT_Y, BAR_R, BOT_Y,
                                      fill=COLORS["IDLE"], outline="")
        self.ticks = {}
        for lbl in FWD_DETENTS + REV_DETENTS:
            col = COLORS.get(lbl, "#555")
            li = c.create_line(TICK_R, 0, TICK_R+7, 0, fill=col, width=1, state="hidden")
            ti = c.create_text(LABEL_X, 0, text=lbl, anchor="w",
                               font=("Consolas", 7), fill=col, state="hidden")
            self.ticks[lbl] = (li, ti)

        self.pos_txt   = c.create_text(8, 10, text="IDLE", fill=COLORS["IDLE"],
                                       font=("Consolas", 10, "bold"), anchor="w")
        self.val_txt   = c.create_text(CANVAS_W//2, CANVAS_H-18, text="+0.00",
                                       fill="#7fa8c0", font=("Consolas", 8))
        self.sc_txt    = c.create_text(CANVAS_W//2, CANVAS_H-8, text="SC --",
                                       fill="#334", font=("Consolas", 7))
        self.rev_badge = c.create_text(CANVAS_W-4, CANVAS_H-6, text="REV",
                                       fill="#1a0830",
                                       font=("Consolas", 8, "bold"), anchor="se")
        self.sc_dot    = c.create_oval(4, CANVAS_H-12, 10, CANVAS_H-6,
                                       fill="#222", outline="")
        tk.Button(self.root, text="✕", command=self._exit,
                  bg="#2a1a1a", fg="#d43a2a", relief="flat",
                  font=("Arial", 7, "bold"), padx=2, pady=0).place(x=CANVAS_W-15, y=1)

    def _joy_loop(self):
        cur_idx = -1
        joy     = None
        n_axes  = n_btns = 0

        while self.running:
            pygame.event.pump()
            target = self.cal.get("device_index", 0)
            if target != cur_idx and pygame.joystick.get_count() > 0:
                if target < pygame.joystick.get_count():
                    joy    = pygame.joystick.Joystick(target)
                    joy.init()
                    n_axes = joy.get_numaxes()
                    n_btns = joy.get_numbuttons()
                cur_idx = target

            if joy and pygame.joystick.get_count() > 0:
                self.current_val = joy.get_axis(AXIS_ENG) if n_axes > AXIS_ENG else 0.0

                # Bound button — log on press
                rev_btn = self.cal.get("rev_button", None)
                if rev_btn is not None and n_btns > rev_btn:
                    btn_now = bool(joy.get_button(rev_btn))
                    if btn_now and not self._prev_btn:
                        v    = self.sim.thr_val
                        mode = sc_mode_from_lever(v) if v is not None else "no-sc"
                        sc_str = f"{v:.3f}" if v is not None else "N/A"
                        print(f"[BTN] Button {rev_btn} pressed — "
                              f"SC lever={sc_str}  mode={mode}", flush=True)
                    self._prev_btn = btn_now
            else:
                self.current_val = 0.0

            time.sleep(1 / POLL_HZ)

    def _draw(self):
        if not self.running: return
        val = self.current_val
        rev = self.sim.rev_active
        sc_connected = self.sim.connected
        sc_val = self.sim.thr_val

        layout = compute_layout(self.cal, rev)
        label  = get_label(val, self.cal, rev)
        color  = COLORS.get(label, COLORS["---"])

        y = val_to_y(val, layout["val_top"], layout["val_bot"],
                     layout["y_top"], layout["y_bot"])
        self.c.coords(self.bar, BAR_L, y, BAR_R, BOT_Y)
        self.c.itemconfig(self.bar, fill=color)

        active = layout["detents"]
        for det, (li, ti) in self.ticks.items():
            if det in active:
                dy = detent_y(det, layout, self.cal)
                if dy is not None and TOP_Y <= dy <= BOT_Y:
                    self.c.coords(li, TICK_R, dy, TICK_R+7, dy)
                    self.c.coords(ti, LABEL_X, dy)
                    self.c.itemconfig(li, state="normal")
                    self.c.itemconfig(ti, state="normal")
                    continue
            self.c.itemconfig(li, state="hidden")
            self.c.itemconfig(ti, state="hidden")

        self.c.itemconfig(self.pos_txt, text=label, fill=color)
        self.c.itemconfig(self.val_txt, text=f"{val:+.2f}")
        self.c.itemconfig(self.sc_txt,
            text=f"SC {sc_val:+.1f}" if sc_val is not None else "SC --",
            fill="#4a6a80" if sc_val is not None else "#333a42")
        self.c.itemconfig(self.rev_badge, fill="#cc44ff" if rev else "#1a0830")
        self.c.itemconfig(self.sc_dot,   fill="#1a7a4a" if sc_connected else "#3a1a1a")

        self.root.after(50, self._draw)

    def _load_cal(self):
        if CAL_FILE.exists():
            return json.loads(CAL_FILE.read_text())
        return {
            "device_index": 0, "rev_button": None,
            "TOGA":     [-1.00, -0.95], "FLX":  [-0.85, -0.75],
            "CLB":      [-0.55, -0.45], "IDLE": [-0.05,  0.05],
            "REV_IDLE": [ 0.75,  0.85], "REV_FULL": [-0.95, -1.00],
        }

    def _update_cal(self, new_cal):
        self.cal = new_cal
        CAL_FILE.write_text(json.dumps(new_cal, indent=2))

    def _exit(self):
        self.running = False
        self.sim.stop()
        self.root.quit()


if __name__ == "__main__":
    print("\n⚠  Start Microsoft Flight Simulator and load into a flight FIRST.", flush=True)
    print("   Then run this app. Waiting for SimConnect...\n", flush=True)
    app = ThrottleApp()
    app.root.mainloop()