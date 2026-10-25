"""Synchronize the public SF6 workbook into Bub's runtime ODS file.

The Google workbook is the source for the normal/stat/move sheets, including
per-move range values on each character sheet. Local-only sheets are carried
forward without requiring the legacy ``ranges`` sheet. The target is replaced
only after merged-workbook validation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

SPREADSHEET_ID = "1JncPFer0RELkKvA9boqHzZ7SqvqTNiX9QLOy9QKzEOM"
SOURCE_SHEET_GID = "1516198958"
SOURCE_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=ods"
DEFAULT_TARGET = Path("FAT - SF6 Frame Data.ods")
DEFAULT_PRESERVE_SHEET = None


def _read_book(path: Path, engine: str) -> tuple[list[str], dict[str, pd.DataFrame]]:
    workbook = pd.ExcelFile(path, engine=engine)
    try:
        sheet_names = list(workbook.sheet_names)
        frames = {
            sheet_name: pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                engine=engine,
                dtype=object,
                keep_default_na=False,
                na_filter=False,
            )
            for sheet_name in sheet_names
        }
    finally:
        workbook.close()
    return sheet_names, frames


def _validate_source(
    sheet_names: list[str],
    frames: dict[str, pd.DataFrame],
    *,
    required_sheets: list[str] | None = None,
) -> None:
    missing_sheets = sorted(set(required_sheets or ()) - set(sheet_names))
    if missing_sheets:
        raise RuntimeError(f"Google export is missing runtime sheets: {missing_sheets}")
    normal_sheets = [name for name in sheet_names if name.endswith("Normal")]
    if not normal_sheets:
        raise RuntimeError("Google export contains no *Normal SF6 move sheets")
    for sheet_name in normal_sheets:
        frame = frames[sheet_name]
        missing = {"moveName", "numCmd"}.difference(frame.columns)
        if missing:
            raise RuntimeError(f"Google sheet {sheet_name} is missing columns: {sorted(missing)}")
        if frame.empty:
            raise RuntimeError(f"Google sheet {sheet_name} is empty")
    stats_sheets = [name for name in sheet_names if name.endswith("Stats") and not name.startswith("_OLD")]
    if not stats_sheets:
        raise RuntimeError("Google export contains no *Stats SF6 sheets")
    for sheet_name in stats_sheets:
        missing = {"name", "stat"}.difference(frames[sheet_name].columns)
        if missing:
            raise RuntimeError(f"Google sheet {sheet_name} is missing columns: {sorted(missing)}")


def _validate_preserved_sheet(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    sheet_name: str,
) -> None:
    try:
        pd.testing.assert_frame_equal(
            expected,
            actual,
            check_dtype=False,
            check_exact=False,
            check_names=True,
        )
    except AssertionError as error:
        raise RuntimeError(f"Preserved sheet {sheet_name} changed during merge") from error


def _dataframes_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(
            left,
            right,
            check_dtype=False,
            check_exact=False,
            check_names=True,
            rtol=0,
            atol=0,
        )
    except AssertionError:
        return False
    return True


def _workbooks_equal(
    left_names: list[str],
    left_frames: dict[str, pd.DataFrame],
    right_names: list[str],
    right_frames: dict[str, pd.DataFrame],
) -> bool:
    if left_names != right_names:
        return False
    return all(_dataframes_equal(left_frames[name], right_frames[name]) for name in left_names)


def merge_workbooks(
    source_path: Path,
    target_path: Path,
    output_path: Path,
    *,
    preserve_sheet: str | None = DEFAULT_PRESERVE_SHEET,
) -> dict[str, Any]:
    """Write a merged ODS and return counts without changing ``target_path``."""

    source_names, source_frames = _read_book(source_path, "odf")
    target_names, target_frames = _read_book(target_path, "odf")
    required_source_sheets = [
        name
        for name in target_names
        if (name.endswith("Normal") or name.endswith("Stats")) and not name.startswith("_OLD")
    ]
    _validate_source(
        source_names,
        source_frames,
        required_sheets=required_source_sheets,
    )
    if preserve_sheet is not None and preserve_sheet not in target_frames:
        raise RuntimeError(
            f"Required local sheet {preserve_sheet!r} is missing from {target_path}"
        )

    target_only_names = [name for name in target_names if name not in source_frames]
    output_names = source_names + target_only_names
    output_frames = {
        **source_frames,
        **{name: target_frames[name] for name in target_only_names},
    }

    changed = not _workbooks_equal(
        target_names,
        target_frames,
        output_names,
        output_frames,
    )
    if not changed:
        return {
            "changed": False,
            "source_sheets": len(source_names),
            "target_sheets": len(target_names),
            "output_sheets": len(output_names),
            "preserved_sheets": target_only_names,
            "source_rows": sum(len(frame) for frame in source_frames.values()),
        }

    output_path.unlink(missing_ok=True)
    with pd.ExcelWriter(output_path, engine="odf") as writer:
        for sheet_name in output_names:
            output_frames[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)

    written_names, written_frames = _read_book(output_path, "odf")
    if written_names != output_names:
        raise RuntimeError("Merged workbook sheet order changed during write")
    if preserve_sheet is not None:
        _validate_preserved_sheet(
            target_frames[preserve_sheet],
            written_frames[preserve_sheet],
            preserve_sheet,
        )
    return {
        "changed": True,
        "source_sheets": len(source_names),
        "target_sheets": len(target_names),
        "output_sheets": len(output_names),
        "preserved_sheets": target_only_names,
        "source_rows": sum(len(frame) for frame in source_frames.values()),
    }


def download_source(destination: Path, *, url: str = SOURCE_URL, timeout: int = 120) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Bub-SF6-Workbook-Sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
    try:
        with zipfile.ZipFile(destination) as archive:
            mimetype = archive.read("mimetype").decode("ascii")
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise RuntimeError("Google export was not a valid ODS workbook") from error
    if mimetype != "application/vnd.oasis.opendocument.spreadsheet":
        raise RuntimeError("Google export was not a valid ODS workbook")


def sync_workbook(
    target_path: Path,
    *,
    backup_path: Path | None = None,
    preserve_sheet: str | None = DEFAULT_PRESERVE_SHEET,
    source_url: str = SOURCE_URL,
    timeout: int = 120,
) -> dict[str, Any]:
    target_path = target_path.resolve()
    if not target_path.exists():
        raise FileNotFoundError(target_path)
    backup_path = backup_path or target_path.with_name(f"{target_path.stem}.backup{target_path.suffix}")
    output_fd, output_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.sync.",
        suffix=".ods",
        dir=target_path.parent,
    )
    os.close(output_fd)
    output_path = Path(output_name)
    target_mode = target_path.stat().st_mode & 0o777

    try:
        with tempfile.TemporaryDirectory(prefix="bub-sf6-source-") as temp_dir:
            source_path = Path(temp_dir) / "sf6-source.ods"
            download_source(source_path, url=source_url, timeout=timeout)
            report = merge_workbooks(
                source_path,
                target_path,
                output_path,
                preserve_sheet=preserve_sheet,
            )
        if report["changed"]:
            output_path.chmod(target_mode)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_fd, backup_name = tempfile.mkstemp(
                prefix=f".{backup_path.name}.",
                suffix=".tmp",
                dir=backup_path.parent,
            )
            os.close(backup_fd)
            backup_temp = Path(backup_name)
            try:
                shutil.copy2(target_path, backup_temp)
                os.replace(backup_temp, backup_path)
            finally:
                backup_temp.unlink(missing_ok=True)
            output_path.replace(target_path)
        return report
    finally:
        output_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--preserve-sheet", default=DEFAULT_PRESERVE_SHEET)
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    report = sync_workbook(
        args.target,
        backup_path=args.backup,
        preserve_sheet=args.preserve_sheet,
        source_url=args.source_url,
        timeout=args.timeout,
    )
    print(
        "SF6 workbook sync complete: "
        f"changed={report['changed']}, "
        f"{report['source_sheets']} source sheets, "
        f"{report['output_sheets']} output sheets, "
        f"preserved={report['preserved_sheets']}, "
        f"source_rows={report['source_rows']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
