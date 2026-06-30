#!/usr/bin/env python3
"""Tkinter GUI for PDF black-and-white conversion with live threshold preview."""

import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from pdf2bw import pdf_to_bw_bytes, render_first_page_preview


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF to Black & White")
        self.geometry("1200x800")
        self._preview_photo: Optional[tk.PhotoImage] = None
        self._converting = False
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0, minsize=300)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Left panel -------------------------------------------------------
        left = ttk.Frame(self, padding=12)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        # -- Input section
        in_frame = ttk.LabelFrame(left, text="Input PDF", padding=8)
        in_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        in_frame.columnconfigure(0, weight=1)

        self._input_var = tk.StringVar()
        ttk.Entry(in_frame, textvariable=self._input_var) \
            .grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(in_frame, text="Browse…", command=self._browse_input) \
            .grid(row=1, column=0, sticky="w")

        # -- Threshold section
        th_frame = ttk.LabelFrame(left, text="Threshold", padding=8)
        th_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        th_frame.columnconfigure(0, weight=1)

        self._threshold_var = tk.IntVar(value=50)
        self._threshold_label = ttk.Label(th_frame, text="50%")
        self._threshold_label.grid(row=0, column=0, sticky="w")

        tk.Scale(
            th_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            variable=self._threshold_var, showvalue=False,
            command=self._on_threshold_change,
        ).grid(row=1, column=0, sticky="ew")

        # -- Output section
        out_frame = ttk.LabelFrame(left, text="Save As", padding=8)
        out_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        out_frame.columnconfigure(0, weight=1)

        self._output_var = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self._output_var) \
            .grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(out_frame, text="Browse…", command=self._browse_output) \
            .grid(row=1, column=0, sticky="w")

        # -- Actions section
        actions = ttk.Frame(left)
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        self._convert_btn = ttk.Button(
            actions, text="Convert All Pages",
            command=self._convert, style="Accent.TButton",
        )
        self._convert_btn.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self._progress = ttk.Progressbar(actions, mode="determinate")
        self._progress.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._progress.grid_remove()  # hidden until conversion starts

        self._status = ttk.Label(actions, text="")
        self._status.grid(row=2, column=0, sticky="ew")

        # Right panel (preview) --------------------------------------------
        right = ttk.Frame(self, padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(right, text="Preview (page 1)", font=("", 11, "bold")) \
            .grid(row=0, column=0, sticky="w", pady=(0, 6))

        self._preview_label = ttk.Label(right, anchor="center",
                                        text="Open a PDF to see preview")
        self._preview_label.grid(row=1, column=0, sticky="nsew")

    # ── Callbacks ────────────────────────────────────────────────────────

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            self._input_var.set(path)
            if not self._output_var.get():
                self._output_var.set(path.replace(".pdf", "_bw.pdf"))
            self._update_preview()

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save PDF as…",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            self._output_var.set(path)

    def _on_threshold_change(self, _=None) -> None:
        val = self._threshold_var.get()
        self._threshold_label.config(text=f"{val}%")
        self._update_preview()

    # ── Preview ──────────────────────────────────────────────────────────

    def _update_preview(self) -> None:
        path = self._input_var.get()
        if not path or not os.path.isfile(path):
            return
        try:
            threshold = int(self._threshold_var.get() * 255 / 100)
            img = render_first_page_preview(path, threshold)
        except Exception:
            return
        if img is None:
            return
        buf = io.BytesIO()
        img.save(buf, format="PPM")
        buf.seek(0)
        self._preview_photo = tk.PhotoImage(data=buf.read())
        self._preview_label.config(image=self._preview_photo, text="")

    # ── Conversion (background thread) ───────────────────────────────────

    def _convert(self) -> None:
        src = self._input_var.get()
        dst = self._output_var.get()

        if not src or not os.path.isfile(src):
            messagebox.showerror("Error", "Please select a valid input PDF.")
            return
        if not dst:
            messagebox.showerror("Error", "Please specify a save path.")
            return
        if self._converting:
            return

        self._converting = True
        self._convert_btn.config(state="disabled")
        self._status.config(text="Converting…")
        self._progress.configure(value=0, maximum=100)
        self._progress.grid()

        threshold = int(self._threshold_var.get() * 255 / 100)
        t = threading.Thread(
            target=self._do_convert,
            args=(src, dst, threshold),
            daemon=True,
        )
        t.start()

    def _do_convert(self, src: str, dst: str, threshold: int) -> None:
        try:
            def _progress(current: int, total: int) -> None:
                self.after(0, lambda: self._progress.configure(
                    value=current, maximum=total))

            pdf_bytes = pdf_to_bw_bytes(src, threshold,
                                         progress_callback=_progress)
            self.after(0, self._on_convert_done, pdf_bytes, None, dst)
        except Exception as exc:
            self.after(0, self._on_convert_done, None, str(exc), dst)

    def _on_convert_done(self, pdf_bytes: Optional[bytes],
                         error: Optional[str], dst: str) -> None:
        self._converting = False
        self._convert_btn.config(state="normal")
        self._progress.grid_remove()

        if error:
            self._status.config(text="Conversion failed")
            messagebox.showerror("Error", error)
            return

        if pdf_bytes is None:
            self._status.config(text="")
            messagebox.showerror("Error", "Input PDF has no pages.")
            return

        try:
            with open(dst, "wb") as f:
                f.write(pdf_bytes)
        except OSError as exc:
            self._status.config(text="Save failed")
            messagebox.showerror("Error", f"Cannot write output:\n{exc}")
            return

        self._status.config(text=f"Saved: {os.path.basename(dst)}")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
