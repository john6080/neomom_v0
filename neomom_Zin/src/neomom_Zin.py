# neomom_Zin.py
#
# Purpose: NeoMOM impedance sweep viewer.
#          Tabbed GUI showing R/X, G/B, and SWR vs frequency.
#
# Usage:
#   neomom_Zin <_Zin.csv>       ← launched by engine after sweep
#   python3 neomom_Zin.py       ← manual launch, opens file dialog
#
# Layout:
#   ┌─────────────────────────────────┐
#   │  [R/X] [G/B] [SWR]  [☐ Bands] │  ← tab bar + controls
#   ├─────────────────────────────────┤
#   │                                 │
#   │         plot area               │
#   │                                 │
#   ├─────────────────────────────────┤
#   │  Resonance: 7.2573 MHz          │  ← status bar
#   │  Rin: 71.9 Ω   SWR min: 1.43   │
#   └─────────────────────────────────┘

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
import sys
import os
import platform

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from Zin_reader import read_Zin_file
from Zin_plots  import plot_RX, plot_GB, plot_SWR


# ------------------------------------------------------------------
# Display scaling — mirrors display_config.py approach
# ------------------------------------------------------------------
def _get_scale():
    """Return (fig_size, mpl_dpi) based on screen resolution."""
    root = tk.Tk()
    root.withdraw()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.destroy()

    if platform.system() == 'Windows':
        return (5.5, 5.0), 100
    if sw >= 3500 and sh >= 2000:
        return (7.0, 6.0), 180    # 4K
    elif sw >= 2500 and sh >= 1400:
        return (6.0, 5.5), 130    # 1440p
    else:
        return (5.5, 5.0), 100    # 1080p


# ------------------------------------------------------------------
# Main application
# ------------------------------------------------------------------
class NeoMoMZin(tk.Tk):

    def __init__(self, csv_path=None):
        super().__init__()

        self.title('NeoMoM — Impedance Sweep Viewer')
        self.protocol('WM_DELETE_WINDOW', self.destroy)

        # ---- display scaling ----
        self._fig_size, self._dpi = _get_scale()

        # ---- state ----
        self._meta       = None
        self._data       = None
        self._csv_path   = None
        self._show_bands = tk.BooleanVar(value=True)
        self._Z0_var     = tk.StringVar(value='50.0')
        self._active_tab = 0          # 0=RX, 1=GB, 2=SWR

        # ---- build UI ----
        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self._build_status()

        # ---- load file ----
        if csv_path and os.path.exists(csv_path):
            self._load_file(csv_path)
        else:
            self._prompt_open()

    # ----------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label='Open...', accelerator='Ctrl+O',
                             command=self._prompt_open)
        filemenu.add_separator()
        filemenu.add_command(label='Exit', command=self.destroy)
        menubar.add_cascade(label='File', menu=filemenu)
        self.config(menu=menubar)
        self.bind('<Control-o>', lambda e: self._prompt_open())

    def _build_toolbar(self):
        """Tab buttons + band overlay checkbox in one toolbar row."""
        bar = ttk.Frame(self, relief='flat')
        bar.pack(side='top', fill='x', padx=4, pady=(4, 0))

        # Tab buttons
        self._tab_btns = []
        for i, label in enumerate(['R / X', 'G / B', 'SWR']):
            btn = ttk.Button(bar, text=label, width=8,
                             command=lambda i=i: self._switch_tab(i))
            btn.pack(side='left', padx=2)
            self._tab_btns.append(btn)

        # Separator
        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=8)

        # Band overlay checkbox
        ttk.Checkbutton(
            bar, text='Ham Bands',
            variable=self._show_bands,
            command=self._redraw_current
        ).pack(side='left', padx=2)

        # Z0 reference — shown only on SWR tab
        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=8)
        self._Z0_label = ttk.Label(bar, text='Z₀ [Ω]:')
        self._Z0_label.pack(side='left', padx=(4, 2))
        self._Z0_entry = ttk.Entry(bar, textvariable=self._Z0_var, width=7)
        self._Z0_entry.pack(side='left', padx=2)
        self._Z0_entry.bind('<Return>',   lambda e: self._redraw_current())
        self._Z0_entry.bind('<FocusOut>', lambda e: self._redraw_current())
        # Hidden by default — shown only when SWR tab active
        self._Z0_label.pack_forget()
        self._Z0_entry.pack_forget()

        # File label (right side)
        self._file_label = ttk.Label(bar, text='No file loaded',
                                     foreground='grey')
        self._file_label.pack(side='right', padx=8)

    def _build_tabs(self):
        """Single plot canvas — content swapped on tab switch."""
        frame = ttk.Frame(self)
        frame.pack(side='top', fill='both', expand=True, padx=4, pady=4)

        w, h = self._fig_size
        self._fig = Figure(figsize=(w, h), dpi=self._dpi)
        self._ax  = self._fig.add_subplot(111)

        self._canvas = FigureCanvasTkAgg(self._fig, master=frame)
        self._canvas.get_tk_widget().pack(fill='both', expand=True)

        self._switch_tab(0)

    def _build_status(self):
        """Status bar at bottom showing key derived values."""
        bar = ttk.Frame(self, relief='sunken')
        bar.pack(side='bottom', fill='x')

        self._status_res  = ttk.Label(bar, text='Resonance: —')
        self._status_rin  = ttk.Label(bar, text='Rin: —')
        self._status_swr  = ttk.Label(bar, text='SWR min: —')
        self._status_file = ttk.Label(bar, text='', foreground='grey')

        self._status_res.pack(side='left',  padx=12, pady=2)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', pady=2)
        self._status_rin.pack(side='left',  padx=12, pady=2)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', pady=2)
        self._status_swr.pack(side='left',  padx=12, pady=2)
        self._status_file.pack(side='right', padx=12, pady=2)

    # ----------------------------------------------------------
    # Tab switching
    # ----------------------------------------------------------

    def _switch_tab(self, idx):
        self._active_tab = idx

        # Highlight active button
        style = ttk.Style()
        for i, btn in enumerate(self._tab_btns):
            btn.state(['pressed'] if i == idx else ['!pressed'])

        # Show Z0 field only on SWR tab (idx=2)
        if idx == 2:
            self._Z0_label.pack(side='left', padx=(4, 2))
            self._Z0_entry.pack(side='left', padx=2)
        else:
            self._Z0_label.pack_forget()
            self._Z0_entry.pack_forget()

        self._redraw_current()

    def _redraw_current(self):
        """Clear axes and redraw the active tab's plot."""
        if self._data is None:
            return

        self._fig.clf()
        self._ax = self._fig.add_subplot(111)

        bands = self._show_bands.get()

        if self._active_tab == 0:
            plot_RX (self._ax, self._data, self._meta, show_bands=bands)
        elif self._active_tab == 1:
            plot_GB (self._ax, self._data, self._meta, show_bands=bands)
        else:
            try:
                Z0 = float(self._Z0_var.get())
                if Z0 <= 0:
                    Z0 = 50.0
            except ValueError:
                Z0 = 50.0
            plot_SWR(self._ax, self._data, self._meta,
                     show_bands=bands, Z0=Z0)

        self._fig.tight_layout()
        self._canvas.draw()

    # ----------------------------------------------------------
    # File loading
    # ----------------------------------------------------------

    def _prompt_open(self):
        path = filedialog.askopenfilename(
            title='Open NeoMOM Impedance Sweep CSV',
            filetypes=[('NeoMOM Zin CSV', '*_Zin.csv'),
                       ('CSV files', '*.csv'),
                       ('All files', '*.*')]
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            meta, data = read_Zin_file(path)
        except Exception as e:
            messagebox.showerror('Load error', str(e))
            return

        self._meta     = meta
        self._data     = data
        self._csv_path = path

        # Update file labels
        fname = os.path.basename(path)
        self._file_label.config(text=fname, foreground='black')
        self._status_file.config(text=fname)

        # Update title
        title = meta.get('title', fname)
        self.title(f'NeoMoM Zin — {title}')

        # Update status bar
        f_res = meta.get('f_res_mhz')
        if f_res:
            self._status_res.config(
                text=f'Resonance: {f_res:.4f} MHz')
            Rin_res = meta.get('Rin_res')
            if Rin_res:
                self._status_rin.config(
                    text=f'Rin: {Rin_res:.1f} Ω')
        else:
            self._status_res.config(text='Resonance: not in range')
            self._status_rin.config(text='Rin: —')

        swr_min = meta.get('swr_min')
        f_swr   = meta.get('f_swr_min_mhz')
        if swr_min and f_swr:
            self._status_swr.config(
                text=f'SWR min: {swr_min:.3f} @ {f_swr:.4f} MHz')

        # Draw initial tab
        self._redraw_current()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = NeoMoMZin(csv_path=csv_path)
    app.mainloop()


if __name__ == '__main__':
    main()