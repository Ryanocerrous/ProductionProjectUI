"""Tkinter-based main window for the ByteBite UI."""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

try:
    from ttkbootstrap import Style as TBStyle
except Exception:  # pragma: no cover - optional dependency
    TBStyle = None

try:
    from ttkthemes import ThemedStyle
except Exception:  # pragma: no cover - optional dependency
    ThemedStyle = None

try:
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageTk = None

from logic import controls
from logic.system_info import get_battery_percentage


PALETTE = {
    "bg": "#14171f",
    "panel": "#1a1e28",
    "text": "#f8f9fa",
    "muted": "#a4acb7",
    "primary": "#2a9fd6",  # Cyborg blue
    "accent": "#77b300",  # Cyborg green
    "danger": "#df3e3e",
    "hover": "#232a35",
}
BOOTSTRAP_ACTIVE = False


def _configure_style(master: tk.Tk) -> None:
    global PALETTE, BOOTSTRAP_ACTIVE
    BOOTSTRAP_ACTIVE = False
    style = None
    # Prefer ttkbootstrap Cyborg theme if available
    if TBStyle:
        try:
            style = TBStyle("cyborg")
            BOOTSTRAP_ACTIVE = True
            colors = style.colors
            PALETTE = {
                "bg": colors.bg,
                "panel": colors.secondary,
                "text": colors.fg,
                "muted": colors.muted,
                "primary": colors.primary,
                "accent": colors.success,
                "danger": colors.danger,
                "hover": colors.selectbg,
            }
        except Exception:
            style = None
    if style is None:
        style = ThemedStyle(master) if ThemedStyle else ttk.Style(master)
        if ThemedStyle:
            try:
                style.set_theme("equilux")
            except Exception:
                style.set_theme("clam")
        else:
            style.theme_use("clam")
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["text"])
    style.configure("Panel.TFrame", background=PALETTE["bg"])
    style.configure("Bg.TFrame", background=PALETTE["bg"])

    if BOOTSTRAP_ACTIVE:
        return

    style.configure(
        "Menu.TButton",
        font=("Helvetica", 20, "bold"),
        padding=(28, 22),
        background=PALETTE["panel"],
        foreground=PALETTE["text"],
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "Selected.TButton",
        font=("Helvetica", 20, "bold"),
        padding=(28, 22),
        background=PALETTE["primary"],
        foreground=PALETTE["bg"],
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "Accent.TButton",
        font=("Helvetica", 13, "bold"),
        padding=(14, 10),
        background=PALETTE["accent"],
        foreground="#ffffff",
        borderwidth=1,
        relief="flat",
    )
    style.configure(
        "Danger.TButton",
        font=("Helvetica", 13, "bold"),
        padding=(14, 10),
        background=PALETTE["danger"],
        foreground="#ffffff",
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Menu.TButton",
        background=[("active", PALETTE["hover"])],
        foreground=[("disabled", "#6f7c90")],
    )
    style.map(
        "Accent.TButton",
        background=[("active", "#5c9b00")],
        foreground=[("disabled", "#6f7c90")],
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#b03030")],
        foreground=[("disabled", "#6f7c90")],
    )


class MainWindow(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        _configure_style(master)
        super().__init__(master, padding=2)
        self.configure(style="Bg.TFrame")
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.menu_items: List[Dict[str, Callable[[], None]]] = []
        self.selected_index = 0
        self.current_screen = "home"
        self.logo_img: Optional[tk.PhotoImage] = self._load_logo()
        self.splash_img: Optional[tk.PhotoImage] = self._load_image("src/assets/bb.png")
        self.bg_img: Optional[tk.PhotoImage] = self._load_image("src/assets/bg.jpg", size=(800, 480))
        self.bg_label: Optional[tk.Label] = None
        self.theme = tk.StringVar(value="dark")
        self.settings_state = {
            "dark_mode": tk.BooleanVar(value=True),
            "sound_alerts": tk.BooleanVar(value=False),
            "auto_refresh": tk.BooleanVar(value=True),
        }
        self.progress_var: Optional[tk.DoubleVar] = None
        self.current_action_command: Optional[Callable[[], None]] = None
        self.splash_after_id: Optional[str] = None
        self.center_frame: Optional[ttk.Frame] = None  # deprecated (kept for cleanup)

        self.battery_var = tk.StringVar(value="Battery: --%")
        self.status_var = tk.StringVar(value="Use Left/Right to navigate. Enter to select.")

        self._build_layout()
        self._bind_keys(master)
        self._refresh_battery()

    # Layout builders
    def _build_layout(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self._build_top_bar()
        self.content_frame = ttk.Frame(self, style="Bg.TFrame")
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        for i in range(3):
            self.content_frame.columnconfigure(i, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        self._build_bottom_bar()

        self._show_splash()

    def _build_top_bar(self) -> None:
        top = ttk.Frame(self, style="Bg.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=2)
        top.columnconfigure(2, weight=1)

        title = ttk.Label(top, text="BYTEBITE", anchor="center", font=("Helvetica", 20, "bold"))
        title.grid(row=0, column=1, sticky="n", pady=(6, 2))

        battery_frame = ttk.Frame(top)
        battery_frame.grid(row=0, column=2, sticky="e", padx=(0, 12), pady=(10, 0))
        self.battery_bar = ttk.Progressbar(battery_frame, length=100, mode="determinate", maximum=100)
        self.battery_bar.grid(row=0, column=0, sticky="e")
        battery_label = ttk.Label(battery_frame, textvariable=self.battery_var, font=("Helvetica", 10))
        battery_label.grid(row=1, column=0, sticky="e", pady=(4, 0))

    def _build_bottom_bar(self) -> None:
        status = ttk.Label(self, textvariable=self.status_var, font=("Helvetica", 11), foreground=PALETTE["muted"])
        status.grid(row=2, column=0, sticky="we")
        self.columnconfigure(0, weight=1)

    def _clear_content(self) -> None:
        for child in self.content_frame.winfo_children():
            child.destroy()
        self.menu_items = []
        self.selected_index = 0
        self.current_action_command = None
        if self.splash_after_id:
            self.after_cancel(self.splash_after_id)
            self.splash_after_id = None
        if self.bg_label:
            self.bg_label.destroy()
            self.bg_label = None
        if self.center_frame:
            self.center_frame.destroy()
            self.center_frame = None

    def _show_home(self) -> None:
        self.current_screen = "home"
        self._clear_content()
        self.status_var.set("Use Left/Right to navigate. Enter to select.")

        self._set_background()

        if self.logo_img:
            logo_label = ttk.Label(self.content_frame, image=self.logo_img, anchor="center", style="Bg.TFrame")
            logo_label.place(relx=0.5, rely=0.2, anchor="center")

        # Place buttons individually on the background (no shared container)
        self._add_menu_button(
            self.content_frame, label="Forensic", command=self._on_forensic, relx=0.35, rely=0.5, width=30, ipady=30
        )
        self._add_menu_button(
            self.content_frame, label="Offensive", command=self._on_offensive, relx=0.65, rely=0.5, width=30, ipady=30
        )
        self._add_menu_button(
            self.content_frame, label="Settings", command=self._on_settings, relx=0.05, rely=0.9, align="w", width=12
        )
        self._add_menu_button(
            self.content_frame, label="About", command=self._on_about, relx=0.95, rely=0.9, align="e", width=12
        )

        self._update_selection()

    def _show_splash(self) -> None:
        self.current_screen = "splash"
        self._clear_content()
        if self.splash_after_id:
            self.after_cancel(self.splash_after_id)

        splash = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=24)
        splash.grid(row=0, column=1, sticky="n")
        splash.columnconfigure(0, weight=1)

        if self.splash_img:
            logo = ttk.Label(splash, image=self.splash_img, anchor="center")
            logo.grid(row=0, column=0, pady=(10, 18))
        else:
            fallback = ttk.Label(
                splash,
                text="BYTEBITE",
                anchor="center",
                font=("Helvetica", 24, "bold"),
                foreground=PALETTE["text"],
            )
            fallback.grid(row=0, column=0, pady=(10, 18))

        tagline = ttk.Label(
            splash,
            text="Loading ByteBite...",
            anchor="center",
            font=("Helvetica", 12),
            foreground=PALETTE["muted"],
        )
        tagline.grid(row=1, column=0, pady=(0, 6))

        self.splash_after_id = self.after(2000, self._show_home)

    def _show_detail_screen(self, title: str, body: str) -> None:
        self.current_screen = title.lower()
        self._clear_content()
        self._set_background()
        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        detail = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        detail.grid(row=0, column=0, sticky="n")
        detail.columnconfigure(0, weight=1)

        heading = ttk.Label(detail, text=title, font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, sticky="n", pady=(0, 12))

        text = ttk.Label(detail, text=body, justify="center", wraplength=720, font=("Helvetica", 12))
        text.grid(row=1, column=0, sticky="n", pady=(0, 24))

        back_hint = ttk.Label(
            detail,
            text="Press Enter to return home.",
            font=("Helvetica", 11),
            foreground="#c6d2df",
        )
        back_hint.grid(row=2, column=0, sticky="n")

    def _show_toggle_screen(
        self, title: str, options: Dict[str, tk.BooleanVar], action_label: str, action_command: Callable[[], None]
    ) -> None:
        self.current_screen = title.lower()
        self._clear_content()
        self._set_background()

        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        wrapper = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        wrapper.grid(row=0, column=0, sticky="n")
        wrapper.columnconfigure(0, weight=1)

        heading = ttk.Label(wrapper, text=title, font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, pady=(0, 8))

        subtitle = ttk.Label(
            wrapper,
            text="Toggle targets and press Enter on the action button below.",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        subtitle.grid(row=1, column=0, pady=(0, 18))

        options_frame = ttk.Frame(wrapper, style="Bg.TFrame")
        options_frame.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        options_frame.columnconfigure(0, weight=1)

        row = 0
        for label, var in options.items():
            line = ttk.Frame(options_frame)
            line.grid(row=row, column=0, sticky="ew", pady=6)
            line.columnconfigure(0, weight=1)
            lbl = ttk.Label(line, text=label, font=("Helvetica", 13))
            lbl.grid(row=0, column=0, sticky="w")
            toggle = ToggleSwitch(line, var=var)
            toggle.grid(row=0, column=1, sticky="e")
            row += 1

        if BOOTSTRAP_ACTIVE:
            bootstyle = "success" if action_label.lower().startswith("extract") else "primary"
            action_btn = ttk.Button(wrapper, text=action_label, command=action_command, takefocus=False, bootstyle=bootstyle)
        else:
            action_btn = ttk.Button(
                wrapper,
                text=action_label,
                command=action_command,
                style="Accent.TButton",
            )
        action_btn.grid(row=3, column=0, pady=(10, 0), ipadx=12, ipady=8, sticky="n")
        self.current_action_command = action_command

        back_hint = ttk.Label(
            wrapper,
            text="Press Esc or Enter on action to return home.",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=4, column=0, pady=(12, 0))

    def _show_progress_screen(self, title: str, on_cancel: Callable[[], None]) -> None:
        self.current_screen = f"{title.lower()}_progress"
        self._clear_content()
        wrap = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=8)
        wrap.grid(row=0, column=1, sticky="n")
        wrap.columnconfigure(0, weight=1)

        heading = ttk.Label(wrap, text=f"{title} in progress", font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, pady=(0, 10))

        self.progress_var = tk.DoubleVar(value=0)
        bar = ttk.Progressbar(wrap, variable=self.progress_var, mode="determinate", maximum=100, length=400)
        bar.grid(row=1, column=0, pady=(6, 12))

        if BOOTSTRAP_ACTIVE:
            cancel_btn = ttk.Button(wrap, text="Cancel", command=on_cancel, takefocus=False, bootstyle="danger")
        else:
            cancel_btn = ttk.Button(wrap, text="Cancel", command=on_cancel, style="Danger.TButton")
        cancel_btn.grid(row=2, column=0, pady=(6, 0), ipadx=12, ipady=6, sticky="n")

        self._simulate_progress()
        self.current_action_command = on_cancel

    def _add_menu_button(
        self,
        parent: ttk.Frame,
        label: str,
        command: Callable[[], None],
        row: Optional[int] = None,
        col: Optional[int] = None,
        relx: Optional[float] = None,
        rely: Optional[float] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        align: str | None = None,
        width: Optional[int] = None,
        sticky: str | None = None,
        ipady: Optional[int] = None,
    ) -> None:
        if BOOTSTRAP_ACTIVE:
            btn = ttk.Button(
                parent,
                text=label,
                command=command,
                takefocus=False,
                bootstyle="secondary",
                width=width or 18,
            )
        else:
            btn = ttk.Button(
                parent,
                text=label,
                style="Menu.TButton",
                command=command,
                takefocus=False,
                width=width or 18,
            )
        sticky = "nsew"
        if sticky:
            sticky = sticky
        if align == "w":
            sticky = "w"
        elif align == "e":
            sticky = "e"
        if relx is not None and rely is not None:
            anchor = "center"
            if sticky in ("w", "e", "n", "s", "nw", "ne", "sw", "se"):
                anchor = sticky
            btn.place(relx=relx, rely=rely, anchor=anchor)
        elif x is not None and y is not None:
            anchor = "center"
            if sticky in ("w", "e", "n", "s", "nw", "ne", "sw", "se"):
                anchor = sticky
            btn.place(x=x, y=y, anchor=anchor)
        else:
            btn.grid(row=row or 0, column=col or 0, padx=22, pady=16, sticky=sticky or "nsew", ipady=ipady or 16)
        self.menu_items.append({"button": btn, "command": command})

    # Navigation
    def _bind_keys(self, master: tk.Tk) -> None:
        master.bind("<Left>", lambda _: self._handle_left())
        master.bind("<Right>", lambda _: self._handle_right())
        master.bind("<Return>", lambda _: self._activate_selection())
        master.bind("<KP_Enter>", lambda _: self._activate_selection())
        master.bind("<Escape>", lambda _: self._show_home())

    def _handle_left(self) -> None:
        if self.current_screen != "home":
            self._show_home()
            return
        self._move_selection(-1)

    def _handle_right(self) -> None:
        if self.current_screen != "home":
            self._show_home()
            return
        self._move_selection(1)

    def _move_selection(self, delta: int) -> None:
        if not self.menu_items:
            return
        self.selected_index = (self.selected_index + delta) % len(self.menu_items)
        self._update_selection()

    def _activate_selection(self) -> None:
        if self.current_screen == "splash":
            self._show_home()
            return
        if self.current_screen != "home":
            if self.current_action_command:
                self.current_action_command()
            else:
                self._show_home()
            return
        if not self.menu_items:
            return
        item = self.menu_items[self.selected_index]
        command = item.get("command")
        if callable(command):
            command()

    def _update_selection(self) -> None:
        if not self.menu_items:
            return
        for idx, item in enumerate(self.menu_items):
            btn: ttk.Button = item["button"]
            is_selected = idx == self.selected_index
            btn.state(["!disabled"])
            if BOOTSTRAP_ACTIVE:
                btn.configure(bootstyle="primary" if is_selected else "secondary")
            else:
                btn.configure(style="Selected.TButton" if is_selected else "Menu.TButton")

    # Actions
    def _on_forensic(self) -> None:
        options = {
            "Photos": tk.BooleanVar(value=True),
            "Video": tk.BooleanVar(value=False),
            "Documents": tk.BooleanVar(value=False),
            "Messages": tk.BooleanVar(value=False),
            "All": tk.BooleanVar(value=False),
        }
        self.status_var.set("Select forensic targets and press Extract.")
        self._show_toggle_screen("Forensic", options, "Extract", lambda: self._start_task("Forensic", options))

    def _on_offensive(self) -> None:
        options = {
            "Keylogger": tk.BooleanVar(value=True),
            "Malware injection": tk.BooleanVar(value=False),
            "Network scan": tk.BooleanVar(value=False),
        }
        self.status_var.set("Select offensive tools and press Launch.")
        self._show_toggle_screen("Offensive", options, "Launch", lambda: self._start_task("Offensive", options))

    def _on_settings(self) -> None:
        options = {
            "Dark mode": self.settings_state["dark_mode"],
            "Sound alerts": self.settings_state["sound_alerts"],
            "Auto-refresh": self.settings_state["auto_refresh"],
        }
        self.status_var.set("Toggle settings and press Apply.")
        self._show_toggle_screen("Settings", options, "Apply", self._apply_settings)

    def _on_about(self) -> None:
        message = controls.show_about()
        self.status_var.set("About")
        self._show_detail_screen("About", message)

    # Battery
    def _refresh_battery(self) -> None:
        value = get_battery_percentage()
        if value is None:
            self.battery_var.set("Battery: n/a")
            self.battery_bar["value"] = 0
        else:
            self.battery_var.set(f"Battery: {value}%")
            self.battery_bar["value"] = value
        self.after(15000, self._refresh_battery)

    def _load_logo(self) -> Optional[tk.PhotoImage]:
        return self._load_image("src/assets/logo.png")

    def _load_image(self, path: str, size: Optional[tuple[int, int]] = None) -> Optional[tk.PhotoImage]:
        if Image is None or ImageTk is None:
            try:
                return tk.PhotoImage(file=path)
            except Exception:
                return None
        try:
            img = Image.open(path)
            if size:
                img = img.resize(size, Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _set_background(self) -> None:
        if not self.bg_img:
            return
        self.bg_label = tk.Label(self.content_frame, image=self.bg_img, borderwidth=0, highlightthickness=0)
        self.bg_label.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)

    # Task orchestration (stubbed)
    def _start_task(self, title: str, options: Dict[str, tk.BooleanVar]) -> None:
        selected = [key for key, var in options.items() if var.get()]
        self.status_var.set(f"{title} task started with: {', '.join(selected) if selected else 'none'}")
        self._show_progress_screen(title, lambda: self._cancel_task(title))

    def _simulate_progress(self) -> None:
        if not hasattr(self, "progress_var"):
            return
        current = self.progress_var.get()
        if current >= 100:
            self.status_var.set("Task complete.")
            self.after(800, self._show_home)
            return
        self.progress_var.set(min(current + 7, 100))
        self.after(400, self._simulate_progress)

    def _cancel_task(self, title: str) -> None:
        self.status_var.set(f"{title} task canceled.")
        self._show_home()

    def _apply_settings(self) -> None:
        # In a real implementation, persist settings and re-apply theme/sound/refresh behavior here.
        dark = self.settings_state["dark_mode"].get()
        sound = self.settings_state["sound_alerts"].get()
        auto = self.settings_state["auto_refresh"].get()
        self.status_var.set(
            f"Settings applied (dark: {'on' if dark else 'off'}, sound: {'on' if sound else 'off'}, auto-refresh: {'on' if auto else 'off'})."
        )
        self._show_home()


class ToggleSwitch(tk.Canvas):
    """Simple canvas-based toggle switch to mimic a sliding bar."""

    def __init__(self, master: tk.Widget, var: tk.BooleanVar, width: int = 56, height: int = 28) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=PALETTE["bg"],
        )
        self.var = var
        self.width = width
        self.height = height
        self.radius = height // 2
        self.pad = 3
        self.bind("<Button-1>", lambda _: self._toggle())
        self.var.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self) -> None:
        self.var.set(not self.var.get())
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        on = self.var.get()
        track_color = PALETTE["primary"] if on else PALETTE["hover"]
        knob_color = PALETTE["bg"] if on else PALETTE["muted"]
        self._round_rect(self.pad, self.pad, self.width - self.pad, self.height - self.pad, self.radius, track_color)
        knob_radius = self.radius - 3
        knob_x = self.width - self.radius if on else self.radius
        self.create_oval(
            knob_x - knob_radius,
            self.height / 2 - knob_radius,
            knob_x + knob_radius,
            self.height / 2 + knob_radius,
            fill=knob_color,
            outline=knob_color,
        )

    def _round_rect(self, x1: int, y1: int, x2: int, y2: int, r: int, color: str) -> None:
        self.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=color, outline=color)
        self.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=color, outline=color)
        self.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=color, outline=color)
        self.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=color, outline=color)
        self.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        self.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
