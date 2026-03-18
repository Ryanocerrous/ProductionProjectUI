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
from logic.forensic_search import ForensicSearchResult, run_forensic_keyword_search
from logic.runtime_paths import build_default_config, load_or_create_config, resolve_config_path
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
        self.auto_forensic_keywords = self._load_auto_forensic_keywords()

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
        # Keep the two primary actions horizontally aligned with the bottom buttons
        # but reduce their width so they stay fully on screen on the 800x480 panel.
        self._add_menu_button(
            self.content_frame, label="Forensic", command=self._on_forensic, relx=0.2, rely=0.5, width=20, ipady=24
        )
        self._add_menu_button(
            self.content_frame, label="Offensive", command=self._on_offensive, relx=0.8, rely=0.5, width=20, ipady=24
        )
        self._add_menu_button(
            self.content_frame, label="Settings", command=self._on_settings, relx=0.2, rely=0.9, width=12
        )
        self._add_menu_button(
            self.content_frame, label="About", command=self._on_about, relx=0.8, rely=0.9, width=12
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
            text="Left = Back  |  Right = Move  |  Enter = Toggle/Execute",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=4, column=0, pady=(12, 0))
        self.selected_index = 0
        self._update_selection()

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
        self.menu_items.append({"type": "button", "name": label, "button": btn, "command": command})

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
            self._move_selection(1)
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
        self.status_var.set(f"Selected: {selected}. Left=Back, Right=Move, Enter=Toggle/Execute.")

    # Actions
    def _on_forensic(self) -> None:
        self.status_var.set("Forensic: Left=Back, Right=Move, Enter=Toggle/Execute.")
        self._show_forensic_screen()

    def _on_offensive(self) -> None:
        options = {
            "Keylogger": tk.BooleanVar(value=True),
            "Malware injection": tk.BooleanVar(value=False),
            "Network scan": tk.BooleanVar(value=False),
        }
        self.status_var.set("Offensive: Left=Back, Right=Move, Enter=Toggle/Execute.")
        self._show_toggle_screen("Offensive", options, "Launch", lambda: self._start_task("Offensive", options))

    def _on_settings(self) -> None:
        options = {
            "Dark mode": self.settings_state["dark_mode"],
            "Sound alerts": self.settings_state["sound_alerts"],
            "Auto-refresh": self.settings_state["auto_refresh"],
        }
        self.status_var.set("Settings: Left=Back, Right=Move, Enter=Toggle/Execute.")
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

        self.center_frame = ttk.Frame(self.content_frame, style="Bg.TFrame", padding=0)
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")
        wrapper = ttk.Frame(self.center_frame, style="Bg.TFrame", padding=8)
        wrapper.grid(row=0, column=0, sticky="n")
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)

        heading = ttk.Label(wrapper, text="Forensic Search", font=("Helvetica", 20, "bold"), anchor="center")
        heading.grid(row=0, column=0, columnspan=2, pady=(0, 6))

        subtitle = ttk.Label(
            wrapper,
            text="Use category toggles, then Execute. Keywords/root are automatic for button-only navigation.",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        subtitle.grid(row=1, column=0, columnspan=2, pady=(0, 12))

        options_frame = ttk.Frame(wrapper, style="Bg.TFrame")
        options_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        for i in range(5):
            options_frame.columnconfigure(i, weight=1)

        for idx, (label, var) in enumerate(self.forensic_options.items()):
            item = ttk.Frame(options_frame, style="Bg.TFrame")
            item.grid(row=0, column=idx, padx=6, sticky="ew")
            text = ttk.Label(item, text=label, font=("Helvetica", 11))
            text.grid(row=0, column=0, padx=(0, 4))
            toggle = ToggleSwitch(item, var=var, width=46, height=24)
            toggle.grid(row=0, column=1)
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
        self.forensic_search_button.grid(row=3, column=0, columnspan=2, pady=(6, 10), ipadx=12, ipady=6)
        self.menu_items.append(
            {
                "type": "action",
                "name": "Execute",
                "button": self.forensic_search_button,
                "command": self._trigger_forensic_search,
            }
        )

        results_wrap = ttk.Frame(wrapper, style="Bg.TFrame")
        results_wrap.grid(row=4, column=0, columnspan=2, sticky="nsew")
        results_wrap.columnconfigure(0, weight=1)
        results_wrap.rowconfigure(0, weight=1)

        self.forensic_results_text = tk.Text(
            results_wrap,
            height=12,
            width=98,
            wrap="word",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            borderwidth=1,
            relief="solid",
        )
        self.forensic_results_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(results_wrap, orient="vertical", command=self.forensic_results_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.forensic_results_text.configure(yscrollcommand=scroll.set)
        auto_keywords = ", ".join(self.auto_forensic_keywords[:8]) + ", ..."
        self._set_forensic_results_text(
            "Ready.\n"
            f"Search root (auto): {Path(self._default_search_root()).expanduser()}\n"
            f"Keyword profile (auto): {auto_keywords}\n"
            "Use Right to move, Enter to toggle/execute, Left to go back."
        )

        back_hint = ttk.Label(
            wrapper,
            text="Left = Back  |  Right = Move  |  Enter = Toggle/Execute",
            font=("Helvetica", 11),
            foreground=PALETTE["muted"],
        )
        back_hint.grid(row=5, column=0, columnspan=2, pady=(8, 0))
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
