"""
estate_search_gui.py
-------------------
Main GUI for Maryland Register of Wills estate search scraper.
"""

import os
import json
import threading
import tkinter as tk
from tkinter import ttk

from tkcalendar import DateEntry

from search_logger import get_logger, log_search_filters, log_event

logger = get_logger()

# ---------------------------------------------------------------------------
# Color palette / style constants
# ---------------------------------------------------------------------------
COLOR_BG = "#f0f2f5"
COLOR_CARD = "#ffffff"
COLOR_HEADER = "#1a2a4a"
COLOR_HEADER_TEXT = "#ffffff"
COLOR_ACCENT = "#2f6fed"
COLOR_ACCENT_DARK = "#1a4fc4"
COLOR_TEXT = "#1a1a2e"
COLOR_MUTED = "#6b7280"
COLOR_BORDER = "#d1d5db"
COLOR_SUCCESS = "#22c55e"
COLOR_ERROR = "#ef4444"
COLOR_ERROR_DARK = "#dc2626"
COLOR_HOVER = "#e8edf5"
COLOR_FIELD_BG = "#fafbfc"

FONT_FAMILY = "Segoe UI"

# Window size - larger for better spacing
INITIAL_WIDTH = 1500
INITIAL_HEIGHT = 1500
MIN_WIDTH = 1200
MIN_HEIGHT = 800


# ---------------------------------------------------------------------------
# Multi-select "combobox" widget - ENHANCED WITH MINIMIZE DETECTION
# ---------------------------------------------------------------------------
class MultiSelectCombobox(ttk.Frame):
    """Professional multi-select dropdown with reliable mouse/keyboard behavior.

    The popup:
    - stays interactive while selecting checkboxes
    - closes when clicking outside it
    - closes on Escape
    - closes when the main window is minimized
    - closes when the main window is closed
    - never remains floating after the main window is hidden/destroyed
    """

    def __init__(self, parent, options, placeholder="Any", **kwargs):
        super().__init__(parent, style="Card.TFrame", **kwargs)

        self.options = [o for o in options if o]
        self.placeholder = placeholder
        self.check_vars = {
            opt: tk.BooleanVar(master=self, value=False)
            for opt in self.options
        }

        self._popup = None
        self._popup_open = False
        self._popup_generation = 0
        self._parent_window = self.winfo_toplevel()

        self.display_var = tk.StringVar(value=self.placeholder)

        self.grid_columnconfigure(0, weight=1)

        self.button = tk.Button(
            self,
            textvariable=self.display_var,
            bg=COLOR_FIELD_BG,
            fg=COLOR_TEXT,
            activebackground=COLOR_HOVER,
            activeforeground=COLOR_TEXT,
            font=(FONT_FAMILY, 10),
            anchor="w",
            padx=14,
            pady=9,
            relief="solid",
            bd=1,
            highlightthickness=0,
            cursor="hand2",
            command=self._toggle_popup,
        )
        self.button.pack(fill=tk.BOTH, expand=True)

        self.button.bind("<Enter>", lambda e: self.button.configure(bg="#f4f7fb"))
        self.button.bind("<Leave>", lambda e: self.button.configure(bg=COLOR_FIELD_BG))

        # Window-level events are more reliable than relying on FocusOut
        # from an overrideredirect Toplevel.
        self._parent_window.bind("<Unmap>", self._on_parent_unmap, add="+")
        self._parent_window.bind("<Destroy>", self._on_parent_destroy, add="+")
        self._parent_window.bind("<Map>", self._on_parent_map, add="+")

        self._update_display()

    def _update_button_state(self):
        """Visual indication that the dropdown is open."""
        try:
            if not self.button.winfo_exists():
                return
        except tk.TclError:
            return

        if self._popup_open:
            self.button.configure(
                bg="#eef4ff",
                highlightbackground=COLOR_ACCENT,
                highlightcolor=COLOR_ACCENT,
                highlightthickness=1,
            )
        else:
            self.button.configure(
                bg=COLOR_FIELD_BG,
                highlightbackground=COLOR_BORDER,
                highlightcolor=COLOR_ACCENT,
                highlightthickness=0,
            )

    def _on_parent_unmap(self, event=None):
        """Close the popup when the main window is minimized/hidden."""
        if self._popup_open:
            self._close_popup()

    def _on_parent_map(self, event=None):
        pass

    def _on_parent_destroy(self, event=None):
        """Make sure the popup cannot outlive the main application."""
        # Just close the popup without trying to update the button
        if self._popup_open:
            popup = self._popup
            self._popup = None
            self._popup_open = False
            
            if popup is not None:
                try:
                    if popup.winfo_exists():
                        popup.grab_release()
                        popup.destroy()
                except tk.TclError:
                    pass

    def _toggle_popup(self):
        if self._popup_open:
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        if self._popup_open:
            return

        if not self._parent_window.winfo_exists():
            return

        try:
            if not self._parent_window.winfo_viewable():
                return
        except tk.TclError:
            return

        # Make sure the button has a real on-screen position.
        self.update_idletasks()

        self._popup_generation += 1

        popup = tk.Toplevel(self._parent_window)
        self._popup = popup
        self._popup_open = True

        # A normal Toplevel is deliberately used instead of overrideredirect().
        # This gives Tk/Windows much more reliable focus, mouse and minimize behavior.
        popup.title("Select Options")
        popup.transient(self._parent_window)
        popup.configure(bg=COLOR_CARD)
        popup.resizable(False, False)

        # Position directly below the control, keeping the popup on-screen.
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 4

        popup_width = max(320, self.button.winfo_width() + 20)
        popup_height = min(430, max(260, len(self.options) * 34 + 145))

        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()

        if x + popup_width > screen_w - 10:
            x = max(10, screen_w - popup_width - 10)

        if y + popup_height > screen_h - 10:
            y = self.button.winfo_rooty() - popup_height - 4
            if y < 10:
                y = 10

        popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

        # Card-style popup.
        outer = tk.Frame(
            popup,
            bg=COLOR_CARD,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_BORDER,
            highlightthickness=1,
            bd=0,
        )
        outer.pack(fill=tk.BOTH, expand=True)

        # Header
        header = tk.Frame(outer, bg=COLOR_CARD)
        header.pack(fill=tk.X, padx=16, pady=(14, 8))

        tk.Label(
            header,
            text=self.placeholder,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            font=(FONT_FAMILY, 11, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(
            header,
            text="×",
            bg=COLOR_CARD,
            fg=COLOR_MUTED,
            activebackground=COLOR_HOVER,
            activeforeground=COLOR_TEXT,
            font=(FONT_FAMILY, 16),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=6,
            pady=0,
            command=self._close_popup,
        ).pack(side=tk.RIGHT)

        # Selection summary
        self._popup_summary_var = tk.StringVar()
        tk.Label(
            outer,
            textvariable=self._popup_summary_var,
            bg=COLOR_CARD,
            fg=COLOR_MUTED,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(0, 8))

        # Actions
        action_row = tk.Frame(outer, bg=COLOR_CARD)
        action_row.pack(fill=tk.X, padx=16, pady=(0, 10))

        tk.Button(
            action_row,
            text="Select all",
            bg=COLOR_ACCENT,
            fg="white",
            activebackground=COLOR_ACCENT_DARK,
            activeforeground="white",
            font=(FONT_FAMILY, 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._select_all,
        ).pack(side=tk.LEFT)

        tk.Button(
            action_row,
            text="Clear",
            bg="#eef1f6",
            fg=COLOR_TEXT,
            activebackground="#e2e6ee",
            activeforeground=COLOR_TEXT,
            font=(FONT_FAMILY, 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._clear_all,
        ).pack(side=tk.LEFT, padx=(7, 0))

        # List
        list_container = tk.Frame(outer, bg=COLOR_CARD)
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        canvas = tk.Canvas(
            list_container,
            bg=COLOR_CARD,
            highlightthickness=0,
            bd=0,
        )
        scrollbar = ttk.Scrollbar(
            list_container,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        inner = tk.Frame(canvas, bg=COLOR_CARD)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def _on_mousewheel(event):
            try:
                # Check if the event widget is within our popup
                widget = event.widget
                while widget:
                    if widget == popup or widget == canvas or widget == inner:
                        canvas.yview_scroll(int(-event.delta / 120), "units")
                        return "break"
                    widget = widget.master if hasattr(widget, 'master') else None
            except (tk.TclError, AttributeError):
                pass
            return "break"

        # Bind to all widgets in the popup
        for child in popup.winfo_children():
            child.bind("<MouseWheel>", _on_mousewheel, add="+")
            for subchild in child.winfo_children():
                subchild.bind("<MouseWheel>", _on_mousewheel, add="+")

        # Also bind to the popup itself
        popup.bind("<MouseWheel>", _on_mousewheel, add="+")

        for opt in self.options:
            row = tk.Frame(inner, bg=COLOR_CARD)
            row.pack(fill=tk.X, padx=2, pady=1)

            cb = tk.Checkbutton(
                row,
                text=opt,
                variable=self.check_vars[opt],
                bg=COLOR_CARD,
                fg=COLOR_TEXT,
                activebackground=COLOR_HOVER,
                activeforeground=COLOR_TEXT,
                selectcolor=COLOR_CARD,
                font=(FONT_FAMILY, 10),
                anchor="w",
                padx=10,
                pady=7,
                relief="flat",
                bd=0,
                cursor="hand2",
                command=self._update_display,
            )
            cb.pack(fill=tk.X, expand=True)

            def enter(event, widget=cb):
                widget.configure(bg=COLOR_HOVER)

            def leave(event, widget=cb):
                widget.configure(bg=COLOR_CARD)

            cb.bind("<Enter>", enter)
            cb.bind("<Leave>", leave)

        # Footer
        footer = tk.Frame(
            outer,
            bg="#f7f9fc",
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        footer.pack(fill=tk.X, padx=1, pady=1)

        tk.Button(
            footer,
            text="Done",
            bg=COLOR_ACCENT,
            fg="white",
            activebackground=COLOR_ACCENT_DARK,
            activeforeground="white",
            font=(FONT_FAMILY, 10, "bold"),
            relief="flat",
            bd=0,
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._close_popup,
        ).pack(fill=tk.X, padx=10, pady=8)

        # Important: DO NOT use grab_set() here.
        # grab_set() was making normal checkbox/outside-window interaction
        # unnecessarily fragile on some Windows/Tk combinations.
        popup.protocol("WM_DELETE_WINDOW", self._close_popup)
        popup.bind("<Escape>", lambda e: self._close_popup())

        # Close if the popup itself is destroyed by Windows/Tk.
        popup.bind("<Destroy>", self._on_popup_destroy, add="+")

        popup.focus_force()
        popup.lift()
        self._update_button_state()
        self._update_popup_summary()

    def _on_popup_destroy(self, event=None):
        """Reset state if the popup is closed externally."""
        if self._popup is not None:
            try:
                if event is not None and event.widget != self._popup:
                    return
            except tk.TclError:
                pass

        self._popup = None
        self._popup_open = False
        self._update_button_state()

    def _update_popup_summary(self):
        if not self._popup_open:
            return

        try:
            selected = self.get()
            if not selected:
                text = "No options selected"
            elif len(selected) == len(self.options):
                text = "All options selected"
            else:
                text = f"{len(selected)} of {len(self.options)} selected"

            if hasattr(self, "_popup_summary_var"):
                self._popup_summary_var.set(text)
        except tk.TclError:
            pass

    def _close_popup(self):
        popup = self._popup
        self._popup = None
        self._popup_open = False

        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.grab_release()
                    popup.destroy()
            except tk.TclError:
                pass

        self._update_button_state()

    def _select_all(self):
        for var in self.check_vars.values():
            var.set(True)
        self._update_display()

    def _clear_all(self):
        for var in self.check_vars.values():
            var.set(False)
        self._update_display()

    def _update_display(self):
        selected = self.get()

        if not selected:
            text = self.placeholder
        elif len(selected) == len(self.options):
            text = "All Selected"
        elif len(selected) <= 2:
            text = ", ".join(selected)
        else:
            text = f"{len(selected)} selected"

        self.display_var.set(f"{text}  ▾")
        self._update_popup_summary()

    def get(self):
        """Return a list of currently checked options."""
        return [
            opt for opt in self.options
            if self.check_vars[opt].get()
        ]

    def set(self, values):
        """Set selected values from a list/tuple or comma-separated string."""
        if isinstance(values, str):
            values = [v.strip() for v in values.split(",") if v.strip()]

        values = set(values or [])

        for opt, var in self.check_vars.items():
            var.set(opt in values)

        self._update_display()


class EstateSearchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Maryland Estate Search")
        self.root.geometry(f"{INITIAL_WIDTH}x{INITIAL_HEIGHT}")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.configure(bg=COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.config_file = "estate_search_config.json"
        self.saved_values = self.load_saved_values()
        self.is_running = False

        self.county_options = [
            "", "Allegany", "Anne Arundel", "Baltimore", "Baltimore City",
            "Calvert", "Caroline", "Carroll", "Cecil", "Charles",
            "Dorchester", "Frederick", "Garrett", "Harford", "Howard",
            "Kent", "Montgomery", "Prince George's", "Queen Anne's",
            "Somerset", "St. Mary's", "Talbot", "Washington",
            "Wicomico", "Worcester",
        ]
        self.status_options = ["", "ARCHIV", "CLOSED (includes ARCHIVED)", "OPEN", "PENDIN"]
        self.party_type_options = ["Decedent", "Personal Representative"]
        self.estate_type_options = ["", "FP", "LO", "MA", "MV", "NP", "RE", "RJ", "SE", "SJ", "UN"]

        self.mode_var = tk.StringVar(value="input_file")

        self._setup_styles()
        self._build_layout()
        self.load_values_to_form()
        self.refresh_layout()

        log_event("Estate Search GUI started")

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------
    def _setup_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD)

        style.configure(
            "Header.TLabel", background=COLOR_HEADER, foreground=COLOR_HEADER_TEXT,
            font=(FONT_FAMILY, 22, "bold"),
        )
        style.configure(
            "SubHeader.TLabel", background=COLOR_HEADER, foreground="#c9d6ea",
            font=(FONT_FAMILY, 11),
        )
        style.configure(
            "SectionTitle.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT,
            font=(FONT_FAMILY, 13, "bold"),
        )
        style.configure(
            "FieldLabel.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED,
            font=(FONT_FAMILY, 10, "bold"),
        )
        style.configure(
            "Status.TLabel", background=COLOR_BG, foreground=COLOR_MUTED,
            font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Error.TLabel", background=COLOR_BG, foreground=COLOR_ERROR,
            font=(FONT_FAMILY, 10),
        )

        style.configure("TEntry", fieldbackground=COLOR_FIELD_BG, padding=8)
        style.configure("TCombobox", fieldbackground=COLOR_FIELD_BG, padding=8)

        style.configure(
            "Primary.TButton", background=COLOR_ACCENT, foreground="#ffffff",
            font=(FONT_FAMILY, 11, "bold"), padding=(20, 14), borderwidth=0,
        )
        style.map("Primary.TButton", background=[("active", COLOR_ACCENT_DARK)])

        style.configure(
            "Running.TButton", background=COLOR_SUCCESS, foreground="#ffffff",
            font=(FONT_FAMILY, 11, "bold"), padding=(20, 14), borderwidth=0,
        )
        style.map("Running.TButton", background=[("active", "#16a34a")])

        style.configure(
            "Error.TButton", background=COLOR_ERROR, foreground="#ffffff",
            font=(FONT_FAMILY, 11, "bold"), padding=(20, 14), borderwidth=0,
        )
        style.map("Error.TButton", background=[("active", COLOR_ERROR_DARK)])

        style.configure(
            "Secondary.TButton", background="#eef1f6", foreground=COLOR_TEXT,
            font=(FONT_FAMILY, 10), padding=(14, 10), borderwidth=0,
        )
        style.map("Secondary.TButton", background=[("active", "#e2e6ee")])

        # Mode toggle buttons
        style.configure(
            "ModeSelected.TButton", background=COLOR_ACCENT, foreground="#ffffff",
            font=(FONT_FAMILY, 12, "bold"), padding=(25, 16), borderwidth=0,
        )
        style.map("ModeSelected.TButton", background=[("active", COLOR_ACCENT_DARK)])

        style.configure(
            "ModeUnselected.TButton", background="#eef1f6", foreground=COLOR_TEXT,
            font=(FONT_FAMILY, 12), padding=(25, 16), borderwidth=0,
        )
        style.map("ModeUnselected.TButton", background=[("active", "#e2e6ee")])

        style.configure(
            "Card.TLabelframe", background=COLOR_CARD, bordercolor=COLOR_BORDER,
            relief="solid", borderwidth=1,
        )
        style.configure(
            "Card.TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_TEXT,
            font=(FONT_FAMILY, 11, "bold"),
        )

        style.configure("TRadiobutton", background=COLOR_CARD, foreground=COLOR_TEXT, font=(FONT_FAMILY, 10))
        style.configure("TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT, font=(FONT_FAMILY, 10))

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # ---- Header banner with better padding ------------------------------
        header = tk.Frame(self.root, bg=COLOR_HEADER, height=100)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        header_inner = tk.Frame(header, bg=COLOR_HEADER)
        header_inner.pack(fill=tk.BOTH, expand=True, padx=40, pady=18)

        ttk.Label(header_inner, text="Maryland Scraper", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header_inner, 
            text="Search estate records and run the automated web scraper",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # ---- Scrollable body ------------------------------------------------
        body_container = tk.Frame(self.root, bg=COLOR_BG)
        body_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(body_container, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.body = ttk.Frame(canvas, padding=30)
        body_window = canvas.create_window((0, 0), window=self.body, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(body_window, width=event.width)

        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", _on_configure)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # ---- Run Mode Card -------------------------------------------------
        mode_card = self._create_card(self.body)
        mode_inner = ttk.Frame(mode_card, style="Card.TFrame", padding=25)
        mode_inner.pack(fill=tk.BOTH, expand=True)

        ttk.Label(mode_inner, text="Run Mode", style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 16))

        mode_btn_row = ttk.Frame(mode_inner, style="Card.TFrame")
        mode_btn_row.pack(fill=tk.X)
        mode_btn_row.grid_columnconfigure(0, weight=1)
        mode_btn_row.grid_columnconfigure(1, weight=1)

        self.mode_btn_input = ttk.Button(
            mode_btn_row, text="Input File", style="ModeSelected.TButton",
            command=lambda: self._select_mode("input_file"),
        )
        self.mode_btn_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.mode_btn_main = ttk.Button(
            mode_btn_row, text="Main Data", style="ModeUnselected.TButton",
            command=lambda: self._select_mode("main_data"),
        )
        self.mode_btn_main.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # ---- Search Criteria Card -------------------------------------------
        self.search_card = self._create_card(self.body)
        search_inner = ttk.Frame(self.search_card, style="Card.TFrame", padding=25)
        search_inner.pack(fill=tk.BOTH, expand=True)

        ttk.Label(search_inner, text="Search Criteria", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 18)
        )
        self._build_criteria_fields(search_inner)

        # ---- Filing Date Card -----------------------------------------------
        self.date_card = self._create_card(self.body)
        date_inner = ttk.Frame(self.date_card, style="Card.TFrame", padding=25)
        date_inner.pack(fill=tk.BOTH, expand=True)

        ttk.Label(date_inner, text="Filing Date", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        ttk.Label(
            date_inner, text="Choose a date range, or an exact date. Format: MM/DD/YYYY.",
            style="FieldLabel.TLabel", font=(FONT_FAMILY, 9),
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 18))

        self._build_date_fields(date_inner)

        # ---- Scraping Options Card ------------------------------------------
        self.options_card = self._create_card(self.body)
        options_inner = ttk.Frame(self.options_card, style="Card.TFrame", padding=25)
        options_inner.pack(fill=tk.BOTH, expand=True)

        ttk.Label(options_inner, text="Scraping Options", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 18)
        )
        self._build_options_fields(options_inner)

        # ---- Start Button -------------------------------------------------
        button_bar = ttk.Frame(self.body, style="TFrame")
        button_bar.pack(fill=tk.X, pady=(8, 20))
        button_bar.grid_columnconfigure(0, weight=1)

        self.start_button = ttk.Button(
            button_bar, text="Start", style="Primary.TButton", command=self.start_run,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", ipady=5)

        # Error message label
        self.error_label = ttk.Label(
            button_bar, text="Scraper is facing some issues. Please contact the developer.",
            style="Error.TLabel", wraplength=800
        )
        self.error_label.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.error_label.grid_remove()

        # ---- Status Bar -------------------------------------------------
        status_bar = tk.Frame(self.root, bg=COLOR_BG, height=40)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_inner = ttk.Frame(status_bar, style="TFrame", padding=(30, 8))
        status_inner.pack(fill=tk.X)

        self.status_label = ttk.Label(status_inner, text="Ready", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(status_inner, mode="indeterminate", length=200)
        self.progress.pack(side=tk.RIGHT)

    def _create_card(self, parent):
        """Create a card-style frame."""
        card = tk.Frame(
            parent, 
            bg=COLOR_CARD, 
            highlightbackground=COLOR_BORDER,
            highlightthickness=1, 
            bd=0
        )
        card.pack(fill=tk.X, pady=(0, 20))
        return card

    # ------------------------------------------------------------------
    # Field builders
    # ------------------------------------------------------------------
    @staticmethod
    def _add_field(parent, row, col, label_text, colspan=1):
        ttk.Label(parent, text=label_text, style="FieldLabel.TLabel").grid(
            row=row, column=col, sticky="w", padx=(0, 14), pady=(0, 6), columnspan=colspan
        )
        return row + 1

    def _build_criteria_fields(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        r = self._add_field(parent, 1, 0, "ESTATE NUMBER")
        self.estate_number_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.estate_number_var).grid(
            row=r, column=0, sticky="ew", padx=(0, 14), pady=(0, 18))

        self._add_field(parent, 1, 1, "COUNTY (multi-select)")
        self.county_multiselect = MultiSelectCombobox(
            parent, self.county_options, placeholder="Any County")
        self.county_multiselect.grid(row=r, column=1, sticky="ew", pady=(0, 18))

        r = self._add_field(parent, 3, 0, "ESTATE STATUS (multi-select)")
        self.estate_status_multiselect = MultiSelectCombobox(
            parent, self.status_options, placeholder="Any Status")
        self.estate_status_multiselect.grid(row=r, column=0, sticky="ew", padx=(0, 14), pady=(0, 18))

        self._add_field(parent, 3, 1, "ESTATE TYPE (multi-select)")
        self.estate_type_multiselect = MultiSelectCombobox(
            parent, self.estate_type_options, placeholder="Any Type")
        self.estate_type_multiselect.grid(row=r, column=1, sticky="ew", pady=(0, 18))

        r = self._add_field(parent, 5, 0, "PARTY TYPE")
        self.party_type_var = tk.StringVar()
        combo = ttk.Combobox(
            parent, 
            textvariable=self.party_type_var, 
            values=self.party_type_options,
            state="readonly"
        )
        combo.grid(row=r, column=0, sticky="ew", padx=(0, 14), pady=(0, 18))
        combo.set("Decedent")

        r = self._add_field(parent, 7, 0, "LAST NAME")
        self.last_name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.last_name_var).grid(
            row=r, column=0, sticky="ew", padx=(0, 14), pady=(0, 18))

        self._add_field(parent, 7, 1, "FIRST NAME")
        self.first_name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.first_name_var).grid(
            row=r, column=1, sticky="ew", pady=(0, 18))

    def _build_date_fields(self, parent):
        for col in range(4):
            parent.grid_columnconfigure(col, weight=1 if col in (0, 1) else 0)

        self.date_type_var = tk.StringVar(value="range")

        ttk.Radiobutton(
            parent, text="Date Range", variable=self.date_type_var, value="range",
            command=self.toggle_date_fields,
        ).grid(row=2, column=0, sticky="w", pady=(0, 8))

        from_frame = ttk.Frame(parent, style="Card.TFrame")
        from_frame.grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 20))

        ttk.Label(from_frame, text="From", style="FieldLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(from_frame, text="To", style="FieldLabel.TLabel").grid(row=0, column=1, sticky="w", padx=(25, 0))

        self.filing_date_from_var = tk.StringVar()
        self.filing_date_from_entry = DateEntry(
            from_frame, width=16, date_pattern="mm/dd/yyyy", font=(FONT_FAMILY, 10),
            background=COLOR_ACCENT, foreground="white", borderwidth=1,
            textvariable=self.filing_date_from_var,
        )
        self.filing_date_from_entry.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.filing_date_from_entry.delete(0, "end")

        self.filing_date_to_var = tk.StringVar()
        self.filing_date_to_entry = DateEntry(
            from_frame, width=16, date_pattern="mm/dd/yyyy", font=(FONT_FAMILY, 10),
            background=COLOR_ACCENT, foreground="white", borderwidth=1,
            textvariable=self.filing_date_to_var,
        )
        self.filing_date_to_entry.grid(row=1, column=1, sticky="w", padx=(25, 0), pady=(6, 0))
        self.filing_date_to_entry.delete(0, "end")

        divider = ttk.Frame(parent, style="Card.TFrame")
        divider.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 12))
        ttk.Separator(divider, orient="horizontal").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(divider, text="  OR  ", style="FieldLabel.TLabel").pack(side=tk.LEFT)
        ttk.Separator(divider, orient="horizontal").pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Radiobutton(
            parent, text="Exact Date", variable=self.date_type_var, value="exact",
            command=self.toggle_date_fields,
        ).grid(row=5, column=0, sticky="w", pady=(0, 8))

        exact_frame = ttk.Frame(parent, style="Card.TFrame")
        exact_frame.grid(row=6, column=0, columnspan=4, sticky="w")

        self.filing_date_exact_var = tk.StringVar()
        self.filing_date_exact_entry = DateEntry(
            exact_frame, width=16, date_pattern="mm/dd/yyyy", font=(FONT_FAMILY, 10),
            background=COLOR_ACCENT, foreground="white", borderwidth=1,
            textvariable=self.filing_date_exact_var,
        )
        self.filing_date_exact_entry.grid(row=0, column=0, sticky="w", pady=(6, 0))
        self.filing_date_exact_entry.delete(0, "end")

    def _build_options_fields(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, weight=1)

        checkbox_row = ttk.Frame(parent, style="Card.TFrame")
        checkbox_row.grid(row=1, column=0, columnspan=4, sticky="w")

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            checkbox_row, 
            text="Run in Background (Headless)",
            variable=self.headless_var,
            style="TCheckbutton"
        ).pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=True)

        # Limit Result range
        self.limit_section = ttk.Frame(parent, style="Card.TFrame")

        ttk.Label(self.limit_section, text="LIMIT RESULTS", style="FieldLabel.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(20, 6))

        range_row = ttk.Frame(self.limit_section, style="Card.TFrame")
        range_row.grid(row=1, column=0, sticky="w")

        ttk.Label(range_row, text="From", style="FieldLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(range_row, text="To", style="FieldLabel.TLabel").grid(row=0, column=1, sticky="w", padx=(25, 0))

        self.limit_from_var = tk.StringVar()
        ttk.Entry(range_row, textvariable=self.limit_from_var, width=16).grid(
            row=1, column=0, sticky="w", pady=(6, 0))

        self.limit_to_var = tk.StringVar()
        ttk.Entry(range_row, textvariable=self.limit_to_var, width=16).grid(
            row=1, column=1, sticky="w", padx=(25, 0), pady=(6, 0))

    # ------------------------------------------------------------------
    # Button state management
    # ------------------------------------------------------------------
    def set_button_running(self):
        """Set button to 'Running' state."""
        self.start_button.configure(text="Running", style="Running.TButton")
        self.is_running = True
        self.error_label.grid_remove()

    def set_button_error(self, error_message=None):
        """Set button to 'Failed' state with error message."""
        self.start_button.configure(text="Failed", style="Error.TButton")
        self.is_running = False
        if error_message:
            self.error_label.configure(text=f"⚠ Scraper is facing some issues: {error_message}")
        else:
            self.error_label.configure(text="⚠ Scraper is facing some issues. Please contact the developer.")
        self.error_label.grid()

    def set_button_ready(self):
        """Set button back to 'Start' state."""
        self.start_button.configure(text="Start", style="Primary.TButton")
        self.is_running = False
        self.error_label.grid_remove()

    # ------------------------------------------------------------------
    # Run Mode switching
    # ------------------------------------------------------------------
    def _select_mode(self, mode):
        self.mode_var.set(mode)
        self.refresh_layout()
        log_event(f"Run mode changed to: {mode}")

    def refresh_layout(self):
        mode = self.mode_var.get()

        # Toggle mode button styles
        if mode == "input_file":
            self.mode_btn_input.configure(style="ModeSelected.TButton")
            self.mode_btn_main.configure(style="ModeUnselected.TButton")
        else:
            self.mode_btn_input.configure(style="ModeUnselected.TButton")
            self.mode_btn_main.configure(style="ModeSelected.TButton")

        # Show/hide Search Criteria + Filing Date
        self.search_card.pack_forget()
        self.date_card.pack_forget()
        self.limit_section.grid_remove()

        if mode == "input_file":
            self.search_card.pack(fill=tk.X, pady=(0, 20), before=self.options_card)
            self.date_card.pack(fill=tk.X, pady=(0, 20), before=self.options_card)
        else:
            self.limit_section.grid(row=2, column=0, columnspan=4, sticky="ew")

    # ------------------------------------------------------------------
    # Date field toggling
    # ------------------------------------------------------------------
    def toggle_date_fields(self):
        if self.date_type_var.get() == "range":
            self.filing_date_from_entry.config(state="normal")
            self.filing_date_to_entry.config(state="normal")
            self.filing_date_exact_entry.config(state="disabled")
        else:
            self.filing_date_from_entry.config(state="disabled")
            self.filing_date_to_entry.config(state="disabled")
            self.filing_date_exact_entry.config(state="normal")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load_saved_values(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save_values_to_file(self):
        values = {
            "mode": self.mode_var.get(),
            "estate_number": self.estate_number_var.get(),
            "county": ",".join(self.county_multiselect.get()),
            "estate_status": ",".join(self.estate_status_multiselect.get()),
            "estate_type": ",".join(self.estate_type_multiselect.get()),
            "party_type": self.party_type_var.get(),
            "last_name": self.last_name_var.get(),
            "first_name": self.first_name_var.get(),
            "filing_date_type": self.date_type_var.get(),
            "filing_date_from": self.filing_date_from_var.get(),
            "filing_date_to": self.filing_date_to_var.get(),
            "filing_date_exact": self.filing_date_exact_var.get(),
            "limit_from": self.limit_from_var.get(),
            "limit_to": self.limit_to_var.get(),
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(values, f, indent=2)
        except OSError as exc:
            log_event(f"Could not save config file: {exc}", level="warning")

    def _load_multiselect_values(self, v):
        """Load multiselect values after widgets are ready."""
        self.county_multiselect.set(v.get("county", ""))
        self.estate_status_multiselect.set(v.get("estate_status", ""))
        self.estate_type_multiselect.set(v.get("estate_type", ""))

    def load_values_to_form(self):
        v = self.saved_values or {}

        self.mode_var.set(v.get("mode", "input_file"))
        self.estate_number_var.set(v.get("estate_number", ""))
        
        # Load multiselect values with a slight delay to ensure widgets are ready
        self.root.after(100, lambda: self._load_multiselect_values(v))
        
        self.party_type_var.set(v.get("party_type", "Decedent"))
        self.last_name_var.set(v.get("last_name", ""))
        self.first_name_var.set(v.get("first_name", ""))
        self.date_type_var.set(v.get("filing_date_type", "range"))
        self.filing_date_from_var.set(v.get("filing_date_from", ""))
        self.filing_date_to_var.set(v.get("filing_date_to", ""))
        self.filing_date_exact_var.set(v.get("filing_date_exact", ""))
        self.limit_from_var.set(v.get("limit_from", ""))
        self.limit_to_var.set(v.get("limit_to", ""))

        self.toggle_date_fields()

    # ------------------------------------------------------------------
    # Form values / run
    # ------------------------------------------------------------------
    def get_form_values(self):
        mode = self.mode_var.get()
        values = {
            "mode": mode,
            "headless": self.headless_var.get(),
            "debug": self.debug_var.get(),
        }

        if mode == "input_file":
            values.update({
                "estate_number": self.estate_number_var.get().strip(),
                "county": self.county_multiselect.get(),
                "estate_status": self.estate_status_multiselect.get(),
                "estate_type": self.estate_type_multiselect.get(),
                "party_type": self.party_type_var.get().strip(),
                "last_name": self.last_name_var.get().strip(),
                "first_name": self.first_name_var.get().strip(),
                "filing_date_type": self.date_type_var.get(),
                "filing_date_from": self.filing_date_from_var.get().strip(),
                "filing_date_to": self.filing_date_to_var.get().strip(),
                "filing_date_exact": self.filing_date_exact_var.get().strip(),
            })
        else:
            values.update({
                "limit_from": self.limit_from_var.get().strip(),
                "limit_to": self.limit_to_var.get().strip(),
            })

        return values

    def update_status(self, message):
        self.status_label.config(text=message)
        self.root.update_idletasks()

    def start_run(self):
        if self.is_running:
            return

        self.set_button_ready()
        self.save_values_to_file()
        params = self.get_form_values()

        log_search_filters(params)

        self.set_button_running()
        self.update_status("Running...")
        self.show_search_params(params)

        # Run the scraper in a background thread so the GUI stays responsive.
        self.run_scraper(params)

    def show_search_params(self, params):
        print("\n" + "=" * 50)
        print("Run Parameters:")
        for key, value in params.items():
            if value in (None, "", False, []):
                continue
            display_key = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(value)
            print(f"  {display_key}: {value}")
        print("=" * 50 + "\n")

    def run_scraper(self, params):
        self.progress.start()
        self.update_status("Scraping in progress...")
        log_event("Scraper starting")

        # IMPORTANT:
        # Do not run the scraper directly on the Tkinter main thread.
        # Otherwise the GUI cannot repaint/respond while Playwright is running.
        thread = threading.Thread(
            target=self.execute_scraper,
            args=(params,),
            daemon=True,
        )
        thread.start()

    def execute_scraper(self, params):
        """
        Execute the appropriate scraper based on the selected mode.
        """
        mode = params.get("mode", "input_file")
        
        try:
            if mode == "input_file":
                # Use the existing input file scraper
                from extract_input_file import run_estate_search
                
                with open("last_search_params.json", "w") as f:
                    json.dump(params, f, indent=2)
                
                results = run_estate_search(params)
                
                if results["success"]:
                    log_event(
                        f"Scraping completed: {results['total_results']} results "
                        f"saved to {results['output_file']}"
                    )
                    print(
                        f"\n✔ Scraping completed! Found {results['total_results']} results.\n"
                        f"  Saved to: {results['output_file']}\n"
                    )
                    self.root.after(0, lambda r=results: self.on_scraping_complete(r))
                else:
                    error_msg = results.get("error", "Unknown error")
                    log_event(f"Scraping failed: {error_msg}", level="error")
                    print(f"\n✘ Scraping failed: {error_msg}\n")
                    self.root.after(0, lambda: self.update_status(f"Failed: {error_msg}"))
                    self.root.after(0, lambda: self.set_button_error(error_msg))
                    self.root.after(0, self.progress.stop)
                    
            elif mode == "main_data":
                # Use the main data scraper (with limit range)
                from extract_main_file import run_main_data_scraper
                
                # Save params for reference
                with open("last_search_params.json", "w") as f:
                    json.dump(params, f, indent=2)
                
                # Extract limit values
                limit_from = params.get("limit_from", "")
                limit_to = params.get("limit_to", "")
                print("Headless : " ,self.headless_var)
                results = run_main_data_scraper(start=limit_from, end=limit_to, headless=self.headless_var.get(), params=params)
                # results = run_main_data_scraper(start=limit_from, end=limit_to,headless=self.headless_var,params= params)
                
                if results["success"]:
                    log_event(
                        f"Main data scraping completed: {results['total_results']} results "
                        f"saved to {results['output_file']}"
                    )
                    print(
                        f"\n✔ Main data scraping completed! Found {results['total_results']} results.\n"
                        f"  Saved to: {results['output_file']}\n"
                    )
                    self.root.after(0, lambda r=results: self.on_scraping_complete(r))
                else:
                    error_msg = results.get("error", "Unknown error")
                    log_event(f"Main data scraping failed: {error_msg}", level="error")
                    print(f"\n✘ Main data scraping failed: {error_msg}\n")
                    self.root.after(0, lambda: self.update_status(f"Failed: {error_msg}"))
                    self.root.after(0, lambda: self.set_button_error(error_msg))
                    self.root.after(0, self.progress.stop)
            else:
                raise ValueError(f"Unknown mode: {mode}")
                
        except ImportError as e:
            error_msg = f"Could not import scraper module for mode '{mode}': {str(e)}"
            log_event(error_msg, level="error")
            print(f"\n✘ {error_msg}\n")
            self.root.after(0, lambda: self.update_status("Error: Missing scraper module"))
            self.root.after(0, lambda: self.set_button_error(error_msg))
            self.root.after(0, self.progress.stop)
            
        except Exception as e:
            error_msg = str(e)
            log_event(f"Error during scraping: {error_msg}", level="error")
            print(f"\n✘ Error during scraping: {error_msg}\n")
            self.root.after(0, lambda: self.update_status("Error occurred during scraping"))
            self.root.after(0, lambda: self.set_button_error(error_msg))
            self.root.after(0, self.progress.stop)

    def on_scraping_complete(self, results=None):
        """Finish the run and automatically close the GUI on success."""
        self.progress.stop()

        # If the scraper completed successfully, close the application.
        # The CSV has already been written by the scraper before this
        # callback is scheduled, so closing here does not interrupt the save.
        if results is not None and results.get("success"):
            total = results.get("total_results", 0)
            output_file = results.get("output_file", "")

            log_event(
                f"Scraping completed: {total} results saved to {output_file}"
            )

            self.update_status(
                f"Completed — {total} results saved."
            )

            # Give Tkinter one event-loop cycle to process the final status,
            # then close all GUI windows.
            self.root.after(150, self._on_close)
            return

        self.update_status("Scraping completed successfully!")
        self.set_button_ready()

    def _on_close(self):
        """Close any open dropdowns before terminating the application."""
        for widget in (
            getattr(self, "county_multiselect", None),
            getattr(self, "estate_status_multiselect", None),
            getattr(self, "estate_type_multiselect", None),
        ):
            if widget is not None:
                try:
                    widget._close_popup()
                except tk.TclError:
                    pass

        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main():
    root = tk.Tk()
    EstateSearchGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()