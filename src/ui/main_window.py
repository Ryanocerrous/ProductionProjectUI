"""Tkinter-based main window for the ByteBite UI."""
from pathlib import Path
import queue
import threading
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
from logic.adb import Adb
from logic.forensic_search import ForensicSearchResult, run_forensic_keyword_search
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path


DARK_PALETTE = {
    "bg": "#14171f",
    "panel": "#1a1e28",
    "text": "#f8f9fa",
    "on_primary": "#ffffff",
    "muted": "#a4acb7",
    "primary": "#2a9fd6",  # Cyborg blue
    "accent": "#77b300",  # Cyborg green
    "danger": "#df3e3e",
    "hover": "#232a35",
}
LIGHT_PALETTE = {
    "bg": "#eaf2fb",
    "panel": "#f4f8fd",
    "text": "#122033",
    "on_primary": "#ffffff",
    "muted": "#3f5168",
    "primary": "#2e648f",
    "accent": "#2f9a40",
    "danger": "#c23a3a",
    "hover": "#d8e4f2",
}
PALETTE = dict(DARK_PALETTE)
BOOTSTRAP_ACTIVE = False
DEFAULT_AUTO_FORENSIC_KEYWORDS = [
    "murder",
    "kill",
    "knife",
    "gun",
    "firearm",
    "bomb",
    "explosive",
    "kidnap",
    "ransom",
    "burner",
    "encrypted",
    "vault",
    "wipe",
    "delete",
    "crypto",
    "drugs",
    "weapon",
    "hide",
]


def _configure_style(master: tk.Tk, dark_mode: bool = True) -> None:
    global PALETTE, BOOTSTRAP_ACTIVE
    PALETTE = dict(DARK_PALETTE if dark_mode else LIGHT_PALETTE)
    BOOTSTRAP_ACTIVE = False
    style = None
    # Prefer ttkbootstrap when available, with explicit light/dark theme choice.
    if TBStyle:
        theme_candidates = ["cyborg"] if dark_mode else ["flatly", "litera", "minty", "cosmo", "journal", "clam"]
        for theme_name in theme_candidates:
            try:
                style = TBStyle(theme_name)
                BOOTSTRAP_ACTIVE = True
                break
            except Exception:
                style = None
    if style is None:
        style = ThemedStyle(master) if ThemedStyle else ttk.Style(master)
        if ThemedStyle:
            try:
                style.set_theme("equilux" if dark_mode else "clam")
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
        foreground=PALETTE["on_primary"],
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
        _configure_style(master, dark_mode=True)
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
        self.home_canvas: Optional[tk.Canvas] = None
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
        self.forensic_running = False
        self.forensic_search_button: Optional[ttk.Button] = None
        self.forensic_results_text: Optional[tk.Text] = None
        self.forensic_result_queue: "queue.Queue[tuple[Path, ForensicSearchResult]]" = queue.Queue()
        self.forensic_options = {
            "Photos": tk.BooleanVar(value=True),
            "Video": tk.BooleanVar(value=False),
            "Documents": tk.BooleanVar(value=False),
            "Messages": tk.BooleanVar(value=False),
            "All": tk.BooleanVar(value=False),
        }
        self.adb = Adb()
        self.victim_connected = False
        self.connection_border: dict[str, tk.Frame] = {}
        self._conn_check_inflight = False
        self.auto_forensic_keywords = self._load_auto_forensic_keywords()

        self.status_var = tk.StringVar(value="Use Left/Right to navigate. Enter to select.")

        self._build_layout()
        self._bind_keys(master)
        self._poll_victim_connection()

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
        self._build_connection_border()

        self._show_splash()

    def _build_top_bar(self) -> None:
        top = ttk.Frame(self, style="Bg.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=0)
        top.columnconfigure(2, weight=1)

        title = ttk.Label(top, text="BYTEBITE", anchor="center", font=("Helvetica", 20, "bold"))
        title.grid(row=0, column=1, sticky="n", pady=(6, 2))

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
        if self.home_canvas:
            self.home_canvas.destroy()
            self.home_canvas = None
        if self.center_frame:
            self.center_frame.destroy()
            self.center_frame = None

    def _show_home(self) -> None:
        self.current_screen = "home"
        self._clear_content()
        self.status_var.set("Use Left/Right to navigate. Enter to select.")

        self._set_background()
        self.content_frame.update_idletasks()
        frame_w = max(1, int(self.content_frame.winfo_width()))
        frame_h = max(1, int(self.content_frame.winfo_height()))
        self.home_canvas = tk.Canvas(
            self.content_frame,
            width=frame_w,
            height=frame_h,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=PALETTE["bg"],
        )
        self.home_canvas.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)
        if self.bg_img:
            self.home_canvas.create_image(frame_w // 2, frame_h // 2, image=self.bg_img, anchor="center")
        if self.logo_img:
            self.home_canvas.create_image(frame_w // 2, int(frame_h * 0.20), image=self.logo_img, anchor="center")
        self._add_home_canvas_button("Forensic", self._on_forensic, 0.25, 0.38, 292, 130)
        self._add_home_canvas_button("Offensive", self._on_offensive, 0.75, 0.38, 292, 130)
        self._add_home_canvas_button("Settings", self._on_settings, 0.24, 0.73, 200, 92)
        self._add_home_canvas_button("About", self._on_about, 0.76, 0.73, 200, 92)
        self._update_connection_border()
        self._update_selection()

    def _show_splash(self) -> None:
        self.current_screen = "splash"
        self._clear_content()
        self._update_connection_border()
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
        self._update_connection_border()
        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        detail = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        detail.grid(row=0, column=0, sticky="n")
        detail.columnconfigure(0, weight=1)

        is_about = title.strip().lower() == "about"
        heading_size = 30 if is_about else 20
        body_size = 18 if is_about else 12
        hint_size = 16 if is_about else 11

        heading = ttk.Label(detail, text=title, font=("Helvetica", heading_size, "bold"), anchor="center")
        heading.grid(row=0, column=0, sticky="n", pady=(0, 12))

        text = ttk.Label(detail, text=body, justify="center", wraplength=720, font=("Helvetica", body_size))
        text.grid(row=1, column=0, sticky="n", pady=(0, 24))

        back_hint = ttk.Label(
            detail,
            text="Left = Back",
            font=("Helvetica", hint_size),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=2, column=0, sticky="n")

    def _show_toggle_screen(
        self, title: str, options: Dict[str, tk.BooleanVar], action_label: str, action_command: Callable[[], None]
    ) -> None:
        self.current_screen = title.lower()
        self._clear_content()
        self._set_background()
        self._update_connection_border()

        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        wrapper = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        wrapper.grid(row=0, column=0, sticky="n")
        wrapper.columnconfigure(0, weight=1)

        heading = ttk.Label(wrapper, text=title, font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, pady=(0, 8))

        subtitle = ttk.Label(
            wrapper,
            text="Use Right to move, Enter to toggle or execute, Left to go back.",
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
            self.menu_items.append({"type": "toggle", "name": label, "var": var, "label": lbl, "toggle": toggle})
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
        self.menu_items.append({"type": "action", "name": action_label, "button": action_btn, "command": action_command})
        self.current_action_command = action_command

        back_hint = ttk.Label(
            wrapper,
            text="Left = Back  |  Right = Move Down  |  Enter = Toggle/Execute",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=4, column=0, pady=(12, 0))
        self.selected_index = 0
        self._update_selection()

    def _show_progress_screen(self, title: str, on_cancel: Callable[[], None]) -> None:
        self.current_screen = f"{title.lower()}_progress"
        self._clear_content()
        self._update_connection_border()
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
        self.menu_items.append({"type": "button", "name": label, "button": btn, "command": command})

    def _add_home_button(
        self,
        parent: ttk.Frame,
        label: str,
        command: Callable[[], None],
        relx: float,
        rely: float,
        width_px: int,
        height_px: int,
    ) -> None:
        btn = RoundedHomeButton(
            parent,
            text=label,
            command=command,
            width=width_px,
            height=height_px,
            radius=26,
        )
        btn.place(relx=relx, rely=rely, anchor="center")
        self.menu_items.append({"type": "home_button", "name": label, "widget": btn, "command": command})

    def _add_home_canvas_button(
        self,
        label: str,
        command: Callable[[], None],
        relx: float,
        rely: float,
        width_px: int,
        height_px: int,
    ) -> None:
        if not self.home_canvas:
            return
        canvas = self.home_canvas
        frame_w = max(1, int(self.content_frame.winfo_width()))
        frame_h = max(1, int(self.content_frame.winfo_height()))
        cx = int(relx * frame_w)
        cy = int(rely * frame_h)
        x1 = cx - width_px // 2
        y1 = cy - height_px // 2
        x2 = x1 + width_px
        y2 = y1 + height_px
        tag = f"home_btn_{len(self.menu_items)}"
        fill_ids, border_ids = self._draw_canvas_rounded_rect(canvas, x1, y1, x2, y2, 26, tag)
        arc_ids = border_ids.get("arcs", [])
        line_ids = border_ids.get("lines", [])
        text_id = canvas.create_text(
            cx,
            cy,
            text=label,
            fill=PALETTE["text"],
            font=("Helvetica", 20 if height_px >= 106 else 17, "bold"),
            tags=(tag,),
        )
        canvas.tag_bind(tag, "<Button-1>", lambda _e, cmd=command: cmd())
        self.menu_items.append(
            {
                "type": "home_canvas_button",
                "name": label,
                "command": command,
                "canvas": canvas,
                "fill_ids": fill_ids,
                "border_arc_ids": arc_ids,
                "border_line_ids": line_ids,
                "text_id": text_id,
            }
        )

    def _draw_canvas_rounded_rect(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        tag: str,
    ) -> tuple[list[int], dict[str, list[int]]]:
        fill = PALETTE["panel"]
        outline = "#2f3744"
        r = max(8, min(radius, (x2 - x1) // 2 - 2, (y2 - y1) // 2 - 2))
        fill_ids = [
            canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", tags=(tag,)),
            canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", tags=(tag,)),
            canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline="", tags=(tag,)),
            canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline="", tags=(tag,)),
            canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline="", tags=(tag,)),
            canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline="", tags=(tag,)),
        ]
        arc_ids = [
            canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=outline, width=2, tags=(tag,)),
            canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=outline, width=2, tags=(tag,)),
            canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=outline, width=2, tags=(tag,)),
            canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=outline, width=2, tags=(tag,)),
        ]
        line_ids = [
            canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=2, tags=(tag,)),
            canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=2, tags=(tag,)),
            canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=2, tags=(tag,)),
            canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=2, tags=(tag,)),
        ]
        return fill_ids, {"arcs": arc_ids, "lines": line_ids}

    # Navigation
    def _bind_keys(self, master: tk.Tk) -> None:
        master.bind("<Left>", lambda _: self._handle_left())
        master.bind("<Right>", lambda _: self._handle_right())
        master.bind("<Return>", lambda _: self._activate_selection())
        master.bind("<KP_Enter>", lambda _: self._activate_selection())
        master.bind("<Escape>", lambda _: self._show_home())

    def _is_about_screen(self) -> bool:
        return self.current_screen == "about"

    def _handle_left(self) -> None:
        if self.current_screen != "home":
            self._show_home()
            return
        self._move_selection(-1)

    def _handle_right(self) -> None:
        if self._is_about_screen():
            self.status_var.set("About: Left = Back.")
            return
        if self.current_screen != "home":
            self._move_selection(1, wrap=True)
            return
        self._move_selection(1, wrap=True)

    def _move_selection(self, delta: int, wrap: bool = True) -> None:
        if not self.menu_items:
            return
        if wrap:
            self.selected_index = (self.selected_index + delta) % len(self.menu_items)
        else:
            self.selected_index = max(0, min(len(self.menu_items) - 1, self.selected_index + delta))
        self._update_selection()

    def _activate_selection(self) -> None:
        if self.current_screen == "splash":
            self._show_home()
            return
        if self._is_about_screen():
            self.status_var.set("About: Left = Back.")
            return
        if not self.menu_items:
            if self.current_screen != "home" and self.current_action_command:
                self.current_action_command()
                return
            if self.current_screen != "home":
                self._show_home()
            return
        item = self.menu_items[self.selected_index]
        item_type = str(item.get("type", "button"))
        if item_type == "toggle":
            var = item.get("var")
            if isinstance(var, tk.BooleanVar):
                var.set(not var.get())
                if self.current_screen == "forensic":
                    self._sync_forensic_options(str(item.get("name", "")))
                self._update_selection()
            return
        command = item.get("command")
        if callable(command):
            command()

    def _update_selection(self) -> None:
        if not self.menu_items:
            return
        for idx, item in enumerate(self.menu_items):
            is_selected = idx == self.selected_index
            item_type = str(item.get("type", "button"))
            if item_type in {"button", "action"}:
                btn = item.get("button")
                if not isinstance(btn, ttk.Button):
                    continue
                btn.state(["!disabled"])
                if self.current_screen == "home":
                    if BOOTSTRAP_ACTIVE:
                        btn.configure(bootstyle="primary" if is_selected else "secondary")
                    else:
                        btn.configure(style="Selected.TButton" if is_selected else "Menu.TButton")
                else:
                    if BOOTSTRAP_ACTIVE:
                        btn.configure(bootstyle="success" if is_selected else "secondary")
                    else:
                        btn.configure(style="Selected.TButton" if is_selected else "Accent.TButton")
                continue

            if item_type == "home_button":
                widget = item.get("widget")
                if isinstance(widget, RoundedHomeButton):
                    widget.set_selected(is_selected)
                continue

            if item_type == "home_canvas_button":
                canvas = item.get("canvas")
                fill_ids = item.get("fill_ids", [])
                border_arc_ids = item.get("border_arc_ids", [])
                border_line_ids = item.get("border_line_ids", [])
                text_id = item.get("text_id")
                if not isinstance(canvas, tk.Canvas):
                    continue
                fill = PALETTE["primary"] if is_selected else PALETTE["panel"]
                border = PALETTE["accent"] if is_selected else "#2f3744"
                text_color = PALETTE["on_primary"] if is_selected else PALETTE["text"]
                for obj_id in fill_ids:
                    canvas.itemconfigure(obj_id, fill=fill)
                for obj_id in border_arc_ids:
                    canvas.itemconfigure(obj_id, outline=border)
                for obj_id in border_line_ids:
                    canvas.itemconfigure(obj_id, fill=border)
                if isinstance(text_id, int):
                    canvas.itemconfigure(text_id, fill=text_color)
                continue

            if item_type == "toggle":
                lbl = item.get("label")
                name = str(item.get("name", "Option"))
                var = item.get("var")
                if isinstance(lbl, ttk.Label):
                    marker = ">" if is_selected else " "
                    state = "ON" if isinstance(var, tk.BooleanVar) and var.get() else "OFF"
                    lbl.configure(
                        text=f"{marker} {name} [{state}]",
                        foreground=PALETTE["accent"] if is_selected else PALETTE["text"],
                    )
                continue

        if self.current_screen == "home":
            selected = str(self.menu_items[self.selected_index].get("name", "Option"))
            self.status_var.set(f"Selected: {selected}. Use Left/Right to navigate. Enter to select.")
            return
        selected = str(self.menu_items[self.selected_index].get("name", "Option"))
        self.status_var.set(f"Selected: {selected}. Left=Back, Right=Move Down, Enter=Toggle/Execute.")

    # Actions
    def _on_forensic(self) -> None:
        self.status_var.set("Forensic: Left=Back, Right=Move Down, Enter=Toggle/Execute.")
        self._show_forensic_screen()

    def _on_offensive(self) -> None:
        options = {
            "Keylogger": tk.BooleanVar(value=True),
            "Malware injection": tk.BooleanVar(value=False),
            "Adware": tk.BooleanVar(value=False),
        }
        self.status_var.set("Offensive: Left=Back, Right=Move Down, Enter=Toggle/Execute.")
        self._show_toggle_screen("Offensive", options, "Launch", lambda: self._start_task("Offensive", options))

    def _on_settings(self) -> None:
        options = {
            "Dark mode": self.settings_state["dark_mode"],
            "Sound alerts": self.settings_state["sound_alerts"],
            "Auto-refresh": self.settings_state["auto_refresh"],
        }
        self.status_var.set("Settings: Left=Back, Right=Move Down, Enter=Toggle/Execute.")
        self._show_toggle_screen("Settings", options, "Apply", self._apply_settings)

    def _on_about(self) -> None:
        message = controls.show_about()
        self.status_var.set("About")
        self._show_detail_screen("About", message)

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

    def _load_pil_image(self, path: str, size: Optional[tuple[int, int]] = None):
        if Image is None:
            return None
        try:
            img = Image.open(path)
            if size:
                img = img.resize(size, Image.LANCZOS)
            return img
        except Exception:
            return None

    def _default_search_root(self) -> str:
        user_logs = Path.home() / "bytebite-data" / "logs"
        if user_logs.exists():
            return str(user_logs)
        return str((Path(__file__).resolve().parents[2] / "logs"))

    def _load_auto_forensic_keywords(self) -> list[str]:
        try:
            project_root = Path(__file__).resolve().parents[2]
            cfg_path = resolve_config_path(project_root)
            cfg = load_or_create_config(cfg_path, build_default_config())
            analysis_cfg = dict((cfg.get("forensic_analysis") or {}))
            seen: set[str] = set()
            merged: list[str] = []
            for key in ("high_priority_keywords", "suspicious_keywords"):
                values = analysis_cfg.get(key) or []
                for value in values:
                    token = str(value).strip().lower()
                    if not token or token in seen:
                        continue
                    seen.add(token)
                    merged.append(token)
            if merged:
                return merged
        except Exception:
            pass
        return list(DEFAULT_AUTO_FORENSIC_KEYWORDS)

    def _show_forensic_screen(self) -> None:
        self.current_screen = "forensic"
        self._clear_content()
        self._set_background()
        self._update_connection_border()
        self.forensic_results_text = None

        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        wrapper = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        wrapper.grid(row=0, column=0, sticky="n")
        wrapper.columnconfigure(0, weight=1)

        heading = ttk.Label(wrapper, text="Forensic Search", font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, pady=(0, 6))

        subtitle = ttk.Label(
            wrapper,
            text="Use category toggles, then Execute. Keywords/root are automatic for button-only navigation.",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        subtitle.grid(row=1, column=0, pady=(0, 12))

        options_frame = ttk.Frame(wrapper, style="Bg.TFrame")
        options_frame.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        options_frame.columnconfigure(0, weight=1)

        for idx, (label, var) in enumerate(self.forensic_options.items()):
            item = ttk.Frame(options_frame, style="Bg.TFrame")
            item.grid(row=idx, column=0, sticky="ew", pady=6)
            item.columnconfigure(0, weight=1)
            text = ttk.Label(item, text=label, font=("Helvetica", 11))
            text.grid(row=0, column=0, sticky="w", padx=(0, 8))
            toggle = ToggleSwitch(item, var=var, width=46, height=24)
            toggle.grid(row=0, column=1, sticky="e")
            self.menu_items.append({"type": "toggle", "name": label, "var": var, "label": text, "toggle": toggle})

        if BOOTSTRAP_ACTIVE:
            self.forensic_search_button = ttk.Button(
                wrapper,
                text="Execute",
                command=self._trigger_forensic_search,
                takefocus=False,
                bootstyle="success",
            )
        else:
            self.forensic_search_button = ttk.Button(
                wrapper,
                text="Execute",
                command=self._trigger_forensic_search,
                style="Accent.TButton",
            )
        self.forensic_search_button.grid(row=3, column=0, pady=(8, 10), ipadx=12, ipady=6)
        self.menu_items.append(
            {
                "type": "action",
                "name": "Execute",
                "button": self.forensic_search_button,
                "command": self._trigger_forensic_search,
            }
        )

        back_hint = ttk.Label(
            wrapper,
            text="Left = Back  |  Right = Move Down  |  Enter = Toggle/Execute",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=4, column=0, pady=(8, 0))
        self.current_action_command = self._trigger_forensic_search
        self.selected_index = 0
        self._update_selection()

    def _trigger_forensic_search(self) -> None:
        if self.forensic_running:
            return

        categories = [label.lower() for label, var in self.forensic_options.items() if var.get()]
        if not categories:
            self.status_var.set("Select at least one category.")
            self._set_forensic_results_text("No categories selected.")
            return

        root = Path(self._default_search_root()).expanduser()
        keywords = list(self.auto_forensic_keywords)
        self.forensic_running = True
        if self.forensic_search_button and self.forensic_search_button.winfo_exists():
            self.forensic_search_button.state(["disabled"])
        self.status_var.set(f"Searching forensic artifacts in {root} ...")
        selected = ", ".join(sorted("all" if c == "all" else c for c in categories))
        self._set_forensic_results_text(
            f"Running search...\nRoot: {root}\nCategories: {selected}\nKeyword profile: {', '.join(keywords)}"
        )
        self._drain_forensic_result_queue()

        worker = threading.Thread(
            target=self._run_forensic_search_worker,
            args=(root, keywords, categories),
            daemon=True,
        )
        worker.start()
        self.after(120, self._poll_forensic_search_queue)

    def _run_forensic_search_worker(self, root: Path, keywords: list[str], categories: list[str]) -> None:
        result = run_forensic_keyword_search(root, keywords, categories)
        self.forensic_result_queue.put((root, result))

    def _sync_forensic_options(self, changed_name: str) -> None:
        """Keep forensic toggle interactions consistent and meaningful."""
        changed = changed_name.strip().lower()
        all_var = self.forensic_options.get("All")
        non_all_keys = ["Photos", "Video", "Documents", "Messages"]
        if not isinstance(all_var, tk.BooleanVar):
            return

        if changed == "all":
            if all_var.get():
                for key in non_all_keys:
                    var = self.forensic_options.get(key)
                    if isinstance(var, tk.BooleanVar):
                        var.set(True)
            return

        all_selected = True
        for key in non_all_keys:
            var = self.forensic_options.get(key)
            if isinstance(var, tk.BooleanVar) and not var.get():
                all_selected = False
                break
        all_var.set(all_selected)

    def _poll_forensic_search_queue(self) -> None:
        if not self.forensic_running:
            return
        try:
            root, result = self.forensic_result_queue.get_nowait()
        except queue.Empty:
            self.after(120, self._poll_forensic_search_queue)
            return
        self._complete_forensic_search(root, result)

    def _drain_forensic_result_queue(self) -> None:
        try:
            while True:
                self.forensic_result_queue.get_nowait()
        except queue.Empty:
            return

    def _complete_forensic_search(self, root: Path, result: ForensicSearchResult) -> None:
        self.forensic_running = False
        if self.forensic_search_button and self.forensic_search_button.winfo_exists():
            self.forensic_search_button.state(["!disabled"])

        if result.hits:
            self.status_var.set(
                f"Forensic search complete: {len(result.hits)} hit(s) across {result.files_scanned} scanned file(s)."
            )
        else:
            self.status_var.set(f"Forensic search complete: no hits across {result.files_scanned} scanned file(s).")
        self._set_forensic_results_text(self._format_forensic_result(root, result))

    def _format_forensic_result(self, root: Path, result: ForensicSearchResult) -> str:
        lines = [
            f"Search root: {root}",
            f"Categories: {', '.join(result.selected_categories) if result.selected_categories else 'none'}",
            f"Keywords: {', '.join(result.keywords) if result.keywords else 'none'}",
            f"Files scanned: {result.files_scanned}",
            f"Hits: {len(result.hits)}",
            "",
        ]

        if not result.hits:
            lines.append("No keyword matches found.")
        else:
            sorted_hits = sorted(
                result.hits,
                key=lambda item: (item.category, item.file_path.lower(), item.location.lower(), item.keyword.lower()),
            )
            for idx, hit in enumerate(sorted_hits, start=1):
                lines.append(
                    f"{idx}. [{hit.category}] keyword='{hit.keyword}' source={hit.source} location={hit.location}"
                )
                lines.append(f"   file: {hit.file_path}")
                lines.append(f"   snippet: {hit.snippet}")
                lines.append("")

        if result.warnings:
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines).rstrip() + "\n"

    def _set_forensic_results_text(self, text: str) -> None:
        if not self.forensic_results_text or not self.forensic_results_text.winfo_exists():
            return
        self.forensic_results_text.configure(state="normal")
        self.forensic_results_text.delete("1.0", "end")
        self.forensic_results_text.insert("1.0", text)
        self.forensic_results_text.configure(state="disabled")
        self.forensic_results_text.see("1.0")

    def _set_background(self) -> None:
        if not self.bg_img:
            return
        self.bg_label = tk.Label(self.content_frame, image=self.bg_img, borderwidth=0, highlightthickness=0)
        self.bg_label.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)

    def _build_connection_border(self) -> None:
        thickness = 4
        self.connection_border = {
            "top": tk.Frame(self, bg="#00d26a", height=thickness),
            "bottom": tk.Frame(self, bg="#00d26a", height=thickness),
            "left": tk.Frame(self, bg="#00d26a", width=thickness),
            "right": tk.Frame(self, bg="#00d26a", width=thickness),
        }
        self._update_connection_border()

    def _set_connection_border_visible(self, visible: bool) -> None:
        if not self.connection_border:
            return
        if not visible:
            for frame in self.connection_border.values():
                frame.place_forget()
            return
        self.connection_border["top"].place(x=0, y=0, relwidth=1.0)
        self.connection_border["bottom"].place(x=0, rely=1.0, relwidth=1.0, anchor="sw")
        self.connection_border["left"].place(x=0, y=0, relheight=1.0)
        self.connection_border["right"].place(relx=1.0, y=0, relheight=1.0, anchor="ne")
        for frame in self.connection_border.values():
            frame.lift()

    def _update_connection_border(self) -> None:
        show = self.current_screen == "home" and self.victim_connected
        self._set_connection_border_visible(show)

    def _check_victim_connected(self) -> bool:
        result = self.adb.devices()
        if not result.ok:
            return False
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for line in lines[1:]:
            cols = line.split()
            if len(cols) >= 2 and cols[1] == "device":
                return True
        return False

    def _poll_victim_connection(self) -> None:
        if not self._conn_check_inflight:
            self._conn_check_inflight = True
            worker = threading.Thread(target=self._poll_victim_connection_worker, daemon=True)
            worker.start()
        self.after(2000, self._poll_victim_connection)

    def _poll_victim_connection_worker(self) -> None:
        connected = self._check_victim_connected()
        self.after(0, lambda: self._apply_connection_state(connected))

    def _apply_connection_state(self, connected: bool) -> None:
        self._conn_check_inflight = False
        if connected != self.victim_connected:
            self.victim_connected = connected
            self._update_connection_border()

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
        self.theme.set("dark" if dark else "light")
        _configure_style(self.winfo_toplevel(), dark_mode=dark)
        self.configure(style="Bg.TFrame")
        self._show_home()
        self.status_var.set(
            f"Settings applied (theme: {'dark' if dark else 'light'}, sound: {'on' if sound else 'off'}, auto-refresh: {'on' if auto else 'off'})."
        )


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


class RoundedHomeButton(tk.Canvas):
    """Canvas-based rounded button used for the home menu."""

    def __init__(
        self,
        parent,
        text: str,
        command: Callable[[], None],
        width: int = 240,
        height: int = 108,
        radius: int = 22,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            highlightthickness=0,
            highlightbackground=PALETTE["bg"],
            highlightcolor=PALETTE["bg"],
            bd=0,
            relief="flat",
            bg=PALETTE["bg"],
            takefocus=0,
        )
        self.command = command
        self.text = text
        self.radius = max(8, min(radius, min(width, height) // 2 - 2))
        self._selected = False
        self._backdrop_patch = None
        self._backdrop_photo: Optional[tk.PhotoImage] = None
        self._draw()
        self.bind("<Button-1>", lambda _e: self.command())

    def set_backdrop_patch(self, patch) -> None:
        self._backdrop_patch = patch.copy()
        self._draw()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        pad = 3

        if self._backdrop_patch is not None and ImageTk is not None:
            self._backdrop_photo = ImageTk.PhotoImage(self._backdrop_patch)
            self.create_image(w // 2, h // 2, image=self._backdrop_photo)

        fill = PALETTE["primary"] if self._selected else PALETTE["panel"]
        outline = PALETTE["accent"] if self._selected else "#2f3744"
        text_color = PALETTE["bg"] if self._selected else PALETTE["text"]

        self._create_round_rect(pad, pad, w - pad, h - pad, self.radius, fill=fill, outline=outline, width=2)
        self.create_text(
            w // 2,
            h // 2,
            text=self.text,
            fill=text_color,
            font=("Helvetica", 20 if h >= 106 else 17, "bold"),
        )

    def _create_round_rect(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        r: int,
        *,
        fill: str,
        outline: str,
        width: int = 2,
    ) -> None:
        # Fill pass (no outlines) prevents visible seam lines inside the button.
        self.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
        self.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
        self.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline="")
        self.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline="")
        self.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline="")
        self.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline="")

        # Border pass.
        if width <= 0:
            return
        off = width / 2
        ax1, ay1, ax2, ay2 = x1 + off, y1 + off, x2 - off, y2 - off
        rr = max(1, r - int(off))
        self.create_arc(ax1, ay1, ax1 + 2 * rr, ay1 + 2 * rr, start=90, extent=90, style="arc", outline=outline, width=width)
        self.create_arc(ax2 - 2 * rr, ay1, ax2, ay1 + 2 * rr, start=0, extent=90, style="arc", outline=outline, width=width)
        self.create_arc(ax2 - 2 * rr, ay2 - 2 * rr, ax2, ay2, start=270, extent=90, style="arc", outline=outline, width=width)
        self.create_arc(ax1, ay2 - 2 * rr, ax1 + 2 * rr, ay2, start=180, extent=90, style="arc", outline=outline, width=width)
        self.create_line(ax1 + rr, ay1, ax2 - rr, ay1, fill=outline, width=width)
        self.create_line(ax2, ay1 + rr, ax2, ay2 - rr, fill=outline, width=width)
        self.create_line(ax1 + rr, ay2, ax2 - rr, ay2, fill=outline, width=width)
        self.create_line(ax1, ay1 + rr, ax1, ay2 - rr, fill=outline, width=width)
