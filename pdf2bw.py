#!/usr/bin/env python3
"""Convert scanned PDF pages to black and white (CLI & shared library)."""

import argparse
import io
import sys
from typing import Optional

import pymupdf
from PIL import Image
from tqdm import tqdm


def pdf_to_bw_bytes(input_path: str, threshold: int = 128,
                    dpi: int = 200,
                    progress_callback=None) -> Optional[bytes]:
    """Convert every page of a PDF to black and white, return as bytes.

    *progress_callback* — if provided, called as ``fn(current, total)``
    after each page is processed.

    Returns *None* if the input PDF has no pages.
    """
    doc = pymupdf.open(input_path)
    try:
        if len(doc) == 0:
            return None

        total = len(doc)
        out = pymupdf.open()
        try:
            for i, page in enumerate(doc, 1):
                if progress_callback:
                    progress_callback(i, total)
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", (pix.width, pix.height),
                                      pix.samples)
                img = (img
                       .convert("L")
                       .point(lambda x: 0 if x < threshold else 255, mode="1")
                       .convert("L"))

                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)

                out_page = out.new_page(width=pix.width, height=pix.height)
                out_page.insert_image(out_page.rect, stream=buf.getvalue())

            return out.tobytes(deflate=True, garbage=4)
        finally:
            out.close()
    finally:
        doc.close()


def pdf_to_bw(input_path: str, output_path: str, threshold: int = 128,
              dpi: int = 200, silent: bool = False) -> None:
    """Convert PDF to black and white and write to a file.

    When *silent* is *False* (default) a ``tqdm`` progress bar is shown.
    Errors are always printed to stderr regardless of this flag.
    """
    _pbar: Optional[tqdm] = None

    def _progress(current: int, total: int) -> None:
        nonlocal _pbar
        if silent:
            return
        if _pbar is None:
            _pbar = tqdm(
                total=total, unit="page", desc=f"0/{total}",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {elapsed}<{remaining}, {rate_fmt}",
            )
        _pbar.set_description_str(f"{current}/{total}")
        _pbar.update(1)
        if current >= total:
            _pbar.close()

    try:
        pdf_bytes = pdf_to_bw_bytes(
            input_path, threshold, dpi, progress_callback=_progress,
        )
        if pdf_bytes is None:
            print("error: input PDF has no pages", file=sys.stderr)
            sys.exit(1)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"saved: {output_path}")
    finally:
        if _pbar is not None:
            _pbar.close()


def render_first_page_preview(input_path: str, threshold: int,
                              max_size: int = 800) -> Optional[Image.Image]:
    """Render a preview of the first page with the given threshold."""
    doc = pymupdf.open(input_path)
    try:
        if len(doc) == 0:
            return None
        page = doc[0]
        pix = page.get_pixmap(dpi=100)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = (img
               .convert("L")
               .point(lambda x: 0 if x < threshold else 255, mode="1")
               .convert("L"))

        w, h = img.size
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            img = img.resize((int(w * ratio), int(h * ratio)),
                             Image.LANCZOS)
        return img
    finally:
        doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert scanned PDF pages to black and white"
    )
    parser.add_argument("input", help="Path to input PDF")
    parser.add_argument(
        "output", nargs="?",
        help="Output PDF path (default: <input>_bw.pdf)"
    )
    parser.add_argument(
        "-t", "--threshold", type=int, default=128,
        help="Binarization threshold 0-255 (default: 128)"
    )
    parser.add_argument(
        "--dpi", type=int, default=200,
        help="Render DPI (default: 200)"
    )
    parser.add_argument(
        "-s", "--silent", action="store_true",
        help="Suppress progress bar (errors still printed to stderr)"
    )
    args = parser.parse_args()

    output = args.output or args.input.replace(".pdf", "_bw.pdf")
    pdf_to_bw(args.input, output, args.threshold, args.dpi,
              silent=args.silent)


if __name__ == "__main__":
    main()
