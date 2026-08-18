# neomom_Zin.py
#
# Purpose: NeoMOM impedance sweep viewer — multi-dataset overlay.
#
# Supports NeoMoM _Zin.csv and EZNEC .txt sweep files.
# Multiple datasets can be loaded and overlaid on the same plot.
#
# Usage:
#   neomom_Zin <file>       ← launched by engine or manual
#   python3 neomom_Zin.py   ← opens file dialog

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import os
import platform

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from Zin_reader  import sweep_from_file
from Zin_plots   import plot_RX, plot_GB, plot_SWR
from sweep_data  import SweepData, next_color, next_linestyle


# ------------------------------------------------------------------
# Port-extension dialog -- shown when importing a VNA .s1p file
# ------------------------------------------------------------------
class PortExtensionDialog(tk.Toplevel):
    """
    Modal dialog to collect feedline parameters for a VNA measurement,
    so the sweep can be rotated (and optionally loss-corrected) back
    to the antenna terminals before plotting alongside model data.

    Set self.result to (length_m, vf, loss_db_per_100m) on OK,
    or None on Cancel / window close.
    """

    # A few common coax velocity factors, for the dropdown
    VF_PRESETS = [
        ('Custom',            None),
        ('RG-58 (0.66)',      0.66),
        ('RG-8X (0.78)',      0.78),
        ('RG-213 (0.66)',     0.66),
        ('LMR-400 (0.85)',    0.85),
        ('Foam coax (0.80)',  0.80),
        ('Hardline (0.90)',   0.90),
    ]

    def __init__(self, parent, filename):
        super().__init__(parent)
        self.title('VNA Import — Feedline Correction')
        self.resizable(False, False)
        self.transient(parent)
        self.result = None

        pad = dict(padx=8, pady=4)

        ttk.Label(self, text=f'Importing: {filename}',
                  font=('TkDefaultFont', 9, 'bold')).grid(
            row=0, column=0, columnspan=3, sticky='w', **pad)

        ttk.Label(self, text=(
            'This is raw VNA data, measured through your feedline (and\n'
            'balun, if any) -- not yet referenced to the antenna terminals.\n'
            'Enter cable length to rotate (de-embed) it back to the feed-\n'
            'point, so it can be compared directly to model predictions.\n'
            'Leave length at 0 to skip correction and plot the raw sweep.'
        ), justify='left', foreground='#555555').grid(
            row=1, column=0, columnspan=3, sticky='w', **pad)

        ttk.Separator(self).grid(row=2, column=0, columnspan=3,
                                  sticky='ew', pady=4)

        # Cable length
        ttk.Label(self, text='Cable length [m]:').grid(
            row=3, column=0, sticky='e', **pad)
        self._len_var = tk.StringVar(value='0.0')
        ttk.Entry(self, textvariable=self._len_var, width=10).grid(
            row=3, column=1, sticky='w', **pad)

        # Velocity factor
        ttk.Label(self, text='Velocity factor:').grid(
            row=4, column=0, sticky='e', **pad)
        self._vf_var = tk.StringVar(value='0.66')
        vf_entry = ttk.Entry(self, textvariable=self._vf_var, width=10)
        vf_entry.grid(row=4, column=1, sticky='w', **pad)

        self._vf_preset_var = tk.StringVar(value='RG-58 (0.66)')
        vf_combo = ttk.Combobox(
            self, textvariable=self._vf_preset_var, state='readonly',
            width=16, values=[p[0] for p in self.VF_PRESETS[1:]])
        vf_combo.grid(row=4, column=2, sticky='w', **pad)
        vf_combo.bind('<<ComboboxSelected>>', self._on_vf_preset)

        # Loss
        ttk.Label(self, text='Matched loss [dB/100m]:').grid(
            row=5, column=0, sticky='e', **pad)
        self._loss_var = tk.StringVar(value='0.0')
        ttk.Entry(self, textvariable=self._loss_var, width=10).grid(
            row=5, column=1, sticky='w', **pad)
        ttk.Label(self, text='(0 = phase-only correction)',
                  foreground='#888888', font=('TkDefaultFont', 8)).grid(
            row=5, column=2, sticky='w', **pad)

        ttk.Separator(self).grid(row=6, column=0, columnspan=3,
                                  sticky='ew', pady=4)

        btns = ttk.Frame(self)
        btns.grid(row=7, column=0, columnspan=3, pady=(4, 8))
        ttk.Button(btns, text='OK', command=self._on_ok).pack(
            side='left', padx=4)
        ttk.Button(btns, text='Skip correction',
                   command=self._on_skip).pack(side='left', padx=4)
        ttk.Button(btns, text='Cancel', command=self._on_cancel).pack(
            side='left', padx=4)

        self.protocol('WM_DELETE_WINDOW', self._on_cancel)
        self.grab_set()
        self.wait_window(self)

    def _on_vf_preset(self, event=None):
        for label, vf in self.VF_PRESETS:
            if label == self._vf_preset_var.get() and vf is not None:
                self._vf_var.set(str(vf))
                return

    def _on_ok(self):
        try:
            length_m = float(self._len_var.get())
            vf       = float(self._vf_var.get())
            loss     = float(self._loss_var.get())
        except ValueError:
            messagebox.showerror(
                'Invalid input', 'Length, velocity factor, and loss must be numbers.')
            return
        if length_m < 0 or not (0.0 < vf <= 1.0) or loss < 0:
            messagebox.showerror(
                'Invalid input',
                'Length and loss must be >= 0; velocity factor must be in (0, 1].')
            return
        self.result = (length_m, vf, loss)
        self.destroy()

    def _on_skip(self):
        self.result = (0.0, 0.66, 0.0)
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


# ------------------------------------------------------------------
# Display scaling
# ------------------------------------------------------------------
def _get_scale():
    root = tk.Tk(); root.withdraw()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.destroy()
    if platform.system() == 'Windows':
        return (6.0, 5.0), 100
    if sw >= 3500 and sh >= 2000:
        return (7.5, 6.0), 180
    elif sw >= 2500 and sh >= 1400:
        return (6.5, 5.5), 130
    else:
        return (6.0, 5.0), 100


# ------------------------------------------------------------------
# Dataset panel row
# ------------------------------------------------------------------
class DatasetRow(ttk.Frame):
    """One row in the dataset panel — checkbox + colour swatch + name."""

    def __init__(self, parent, ds, on_toggle):
        super().__init__(parent)
        self._ds = ds
        self._var = tk.BooleanVar(value=ds.visible)

        # Colour swatch
        swatch = tk.Label(self, bg=ds.color, width=2, relief='solid')
        swatch.pack(side='left', padx=(2, 4))

        # Visibility checkbox
        cb = ttk.Checkbutton(self, variable=self._var,
                             command=lambda: self._on_toggle(on_toggle))
        cb.pack(side='left')

        # Name label
        ttk.Label(self, text=ds.name, width=18,
                  anchor='w').pack(side='left', padx=2)

    def _on_toggle(self, callback):
        self._ds.visible = self._var.get()
        callback()


# ------------------------------------------------------------------
# Main application
# ------------------------------------------------------------------
class NeoMoMZin(tk.Tk):

    # Default per-tab Y-axis range: (ymin, ymax), either may be None for
    # auto. Indexed by tab: 0=R/X, 1=G/B, 2=SWR. SWR can't go below 1.0,
    # so it's preset as a sensible starting floor -- still user-editable,
    # and what "Auto" reverts to on that tab.
    _YLIM_DEFAULTS = [(None, None), (None, None), (1.0, None)]

    def __init__(self, csv_path=None):
        super().__init__()
        self.title('NeoMoM — Impedance Sweep Viewer')
        self.protocol('WM_DELETE_WINDOW', self.destroy)

        self._fig_size, self._dpi = _get_scale()
        self._datasets    = []          # list of SweepData
        self._show_bands  = tk.BooleanVar(value=True)
        self._Z0_var      = tk.StringVar(value='50.0')
        self._active_tab  = 0

        self._ylim_settings = list(self._YLIM_DEFAULTS)

        self._build_menu()
        self._build_main()

        if csv_path and os.path.exists(csv_path):
            self._load_file(csv_path)

    # ----------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        fm = tk.Menu(menubar, tearoff=0)
        fm.add_command(label='Open / Import...', accelerator='Ctrl+O',
                       command=self._prompt_open)
        fm.add_command(label='Clear all datasets',
                       command=self._clear_datasets)
        fm.add_separator()
        fm.add_command(label='Exit', command=self.destroy)
        menubar.add_cascade(label='File', menu=fm)
        self.config(menu=menubar)
        self.bind('<Control-o>', lambda e: self._prompt_open())

    def _build_main(self):
        """Build side panel + plot area side by side."""
        # Outer container
        outer = ttk.Frame(self)
        outer.pack(fill='both', expand=True)

        # ── Left: dataset panel ──────────────────────────────────
        left = ttk.Frame(outer, width=200, relief='groove', padding=4)
        left.pack(side='left', fill='y', padx=(4, 0), pady=4)
        left.pack_propagate(False)

        ttk.Label(left, text='Datasets', font=('TkDefaultFont', 9, 'bold')
                  ).pack(anchor='w', pady=(0, 4))

        self._ds_frame = ttk.Frame(left)
        self._ds_frame.pack(fill='both', expand=True)

        ttk.Separator(left).pack(fill='x', pady=6)
        ttk.Button(left, text='Import file...',
                   command=self._prompt_open).pack(fill='x')
        ttk.Button(left, text='Clear all',
                   command=self._clear_datasets).pack(fill='x', pady=(2, 0))

        # ── Right: toolbar + plot + status ───────────────────────
        right = ttk.Frame(outer)
        right.pack(side='left', fill='both', expand=True, padx=4, pady=4)

        self._build_toolbar(right)
        self._build_plot(right)
        self._build_status(right)

    def _build_toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(side='top', fill='x', pady=(0, 4))

        # Tab buttons
        self._tab_btns = []
        for i, label in enumerate(['R / X', 'G / B', 'SWR']):
            btn = ttk.Button(bar, text=label, width=8,
                             command=lambda i=i: self._switch_tab(i))
            btn.pack(side='left', padx=2)
            self._tab_btns.append(btn)

        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=8)

        # Ham bands checkbox
        ttk.Checkbutton(bar, text='Ham Bands',
                        variable=self._show_bands,
                        command=self._redraw).pack(side='left', padx=2)

        # Z0 field — always visible for SWR
        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=8)
        self._Z0_label = ttk.Label(bar, text='Z\u2080 [\u03a9]:')
        self._Z0_label.pack(side='left', padx=(4, 2))
        self._Z0_entry = ttk.Entry(bar, textvariable=self._Z0_var, width=7)
        self._Z0_entry.pack(side='left', padx=2)
        self._Z0_entry.bind('<Return>',   lambda e: self._redraw())
        self._Z0_entry.bind('<FocusOut>', lambda e: self._redraw())

        # Y-axis range override — applies to whichever tab is active
        ttk.Separator(bar, orient='vertical').pack(
            side='left', fill='y', padx=8)
        ttk.Label(bar, text='Y range:').pack(side='left', padx=(4, 2))
        self._ymin_var = tk.StringVar(value='')
        self._ymax_var = tk.StringVar(value='')
        ttk.Label(bar, text='min').pack(side='left')
        self._ymin_entry = ttk.Entry(bar, textvariable=self._ymin_var, width=7)
        self._ymin_entry.pack(side='left', padx=2)
        ttk.Label(bar, text='max').pack(side='left')
        self._ymax_entry = ttk.Entry(bar, textvariable=self._ymax_var, width=7)
        self._ymax_entry.pack(side='left', padx=2)
        for entry in (self._ymin_entry, self._ymax_entry):
            entry.bind('<Return>',   lambda e: self._on_ylim_changed())
            entry.bind('<FocusOut>', lambda e: self._on_ylim_changed())
        ttk.Button(bar, text='Auto', width=5,
                   command=self._reset_ylim).pack(side='left', padx=(2, 0))

        self._switch_tab(0)

    def _build_plot(self, parent):
        w, h = self._fig_size
        self._fig = Figure(figsize=(w, h), dpi=self._dpi)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.get_tk_widget().pack(fill='both', expand=True)

    def _build_status(self, parent):
        bar = ttk.Frame(parent, relief='sunken')
        bar.pack(side='bottom', fill='x')
        self._status_text = tk.StringVar(value='No data loaded')
        ttk.Label(bar, textvariable=self._status_text,
                  anchor='w').pack(side='left', padx=8, pady=2)

    # ----------------------------------------------------------
    # Tab switching
    # ----------------------------------------------------------

    def _switch_tab(self, idx):
        self._active_tab = idx
        for i, btn in enumerate(self._tab_btns):
            btn.state(['pressed'] if i == idx else ['!pressed'])

        # Z0 field shown on all tabs — useful for any derived SWR reference
        # but particularly relevant on SWR tab
        self._Z0_label.config(
            foreground='black' if idx == 2 else 'grey')

        self._show_ylim_fields(idx)
        self._redraw()

    def _show_ylim_fields(self, idx):
        """Reflect a tab's stored Y-range in the min/max entry fields."""
        ymin, ymax = self._ylim_settings[idx]
        self._ymin_var.set('' if ymin is None else f'{ymin:g}')
        self._ymax_var.set('' if ymax is None else f'{ymax:g}')

    def _on_ylim_changed(self):
        """Parse the Y min/max entries and store them for the active tab."""
        def parse(strvar, label):
            s = strvar.get().strip()
            if not s:
                return None, True
            try:
                return float(s), True
            except ValueError:
                messagebox.showerror('Invalid Y range',
                                      f'{label} must be a number or blank.')
                return None, False

        ymin, ok = parse(self._ymin_var, 'Y min')
        if not ok:
            return
        ymax, ok = parse(self._ymax_var, 'Y max')
        if not ok:
            return
        if ymin is not None and ymax is not None and ymin >= ymax:
            messagebox.showerror('Invalid Y range',
                                  'Y min must be less than Y max.')
            return

        self._ylim_settings[self._active_tab] = (ymin, ymax)
        self._redraw()

    def _reset_ylim(self):
        """Revert the active tab's Y-range to its default (SWR: min=1.0)."""
        self._ylim_settings[self._active_tab] = self._YLIM_DEFAULTS[self._active_tab]
        self._show_ylim_fields(self._active_tab)
        self._redraw()

    # ----------------------------------------------------------
    # Redraw
    # ----------------------------------------------------------

    def _redraw(self):
        if not self._datasets:
            return

        self._fig.clf()
        self._ax = self._fig.add_subplot(111)

        bands = self._show_bands.get()
        Z0 = self._get_Z0()
        ds = [d for d in self._datasets if d.visible]

        if not ds:
            self._canvas.draw()
            return

        # User-specified Y range, if any, for the active tab. Passed into
        # the plot function so it's applied *before* the band overlay --
        # overlay_bands() positions its labels from ax.get_ylim(), so
        # setting this afterward here would leave labels anchored to the
        # old autoscaled range and break tight_layout.
        ymin, ymax = self._ylim_settings[self._active_tab]
        ylim = (ymin, ymax) if (ymin is not None or ymax is not None) else None

        if self._active_tab == 0:
            plot_RX (self._ax, ds, show_bands=bands, ylim=ylim)
        elif self._active_tab == 1:
            plot_GB (self._ax, ds, show_bands=bands, ylim=ylim)
        else:
            plot_SWR(self._ax, ds, show_bands=bands, Z0=Z0, ylim=ylim)

        self._fig.tight_layout()
        self._canvas.draw()
        self._update_status(Z0)

    def _get_Z0(self):
        try:
            z = float(self._Z0_var.get())
            return z if z > 0 else 50.0
        except ValueError:
            return 50.0

    # ----------------------------------------------------------
    # Dataset panel
    # ----------------------------------------------------------

    def _refresh_ds_panel(self):
        """Rebuild the dataset panel rows."""
        for w in self._ds_frame.winfo_children():
            w.destroy()
        for ds in self._datasets:
            row = DatasetRow(self._ds_frame, ds, self._redraw)
            row.pack(fill='x', pady=1)

    def _clear_datasets(self):
        self._datasets.clear()
        self._refresh_ds_panel()
        self._fig.clf()
        self._ax = self._fig.add_subplot(111)
        self._canvas.draw()
        self._status_text.set('No data loaded')

    # ----------------------------------------------------------
    # Status bar
    # ----------------------------------------------------------

    def _update_status(self, Z0):
        visible = [ds for ds in self._datasets if ds.visible]
        if not visible:
            self._status_text.set('No visible datasets')
            return
        lines = [ds.status_text(Z0) for ds in visible]
        self._status_text.set('   |   '.join(lines))

    # ----------------------------------------------------------
    # File loading
    # ----------------------------------------------------------

    def _prompt_open(self):
        path = filedialog.askopenfilename(
            title='Open impedance sweep file',
            filetypes=[
                ('NeoMoM Zin CSV', '*_Zin.csv'),
                ('EZNEC sweep',    '*.txt'),
                ('VNA Touchstone', '*.s1p;*.s2p'),
                ('CSV files',      '*.csv'),
                ('All files',      '*.*'),
            ]
        )
        if path:
            self._load_file(path)

    def _load_file(self, path):
        # Detect a friendly name from the source type
        fname = os.path.splitext(os.path.basename(path))[0]
        ext   = os.path.splitext(path)[1].lower()
        is_vna = ext in ('.s1p', '.s2p')

        port_ext_kwargs = {}

        if is_vna:
            default_name = f'VNA — {fname}'
            dlg = PortExtensionDialog(self, os.path.basename(path))
            if dlg.result is None:
                return   # user cancelled
            length_m, vf, loss = dlg.result
            port_ext_kwargs = dict(
                port_ext_length_m=length_m,
                port_ext_vf=vf,
                port_ext_loss_db_per_100m=loss,
            )
            if length_m > 0:
                default_name += f'  ({length_m:.1f}m corrected)'
        else:
            # Guess source for default name
            try:
                with open(path, 'r', errors='ignore') as f:
                    first = f.readline()
                if 'EZNEC' in first.upper():
                    default_name = f'EZNEC — {fname}'
                else:
                    default_name = f'NeoMoM — {fname}'
            except Exception:
                default_name = fname

        try:
            color = next_color(self._datasets)
            ls    = next_linestyle(self._datasets)
            ds    = sweep_from_file(path,
                                    name=default_name,
                                    color=color,
                                    linestyle=ls,
                                    **port_ext_kwargs)
        except Exception as e:
            messagebox.showerror('Load error', str(e))
            return

        self._datasets.append(ds)
        self._refresh_ds_panel()
        self.title(f'NeoMoM Impedance Viewer  |  {len(self._datasets)} dataset(s)')
        self._redraw()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = NeoMoMZin(csv_path=csv_path)
    app.mainloop()


if __name__ == '__main__':
    main()