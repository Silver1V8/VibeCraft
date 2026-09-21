"""Read-only logical and physically allocated inventory for a dedicated sandbox."""
import argparse
import ctypes
import json
import os
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2]


def fail(message):
    raise ValueError(message)


def within(path, parent):
    return path == parent or parent in path.parents


def safe_root(value):
    raw, results = Path(value).absolute(), RESULTS.resolve(strict=True)
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        fail(f"root unavailable: {exc}")
    if not within(root, results):
        fail("root escapes rag/eval/results")
    parts = root.relative_to(results).parts
    if len(parts) < 3 or parts[1] != "sandbox":
        fail("root must be inside rag/eval/results/<run>/sandbox")
    for path in (raw, *raw.parents):
        if path == results.parent:
            break
        if path.is_symlink():
            fail(f"symlink root component rejected: {path}")
    return root


def allocated(path, stat, open_file=None):
    try:
        if os.name != "nt":
            blocks = getattr(stat, "st_blocks", None)
            return (blocks * 512, None) if blocks is not None else (None, "st_blocks unavailable")
        import msvcrt
        class StandardInfo(ctypes.Structure):
            _fields_ = [("allocation_size", ctypes.c_longlong), ("end_of_file", ctypes.c_longlong),
                       ("number_of_links", ctypes.c_ulong), ("delete_pending", ctypes.c_byte), ("directory", ctypes.c_byte)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True); func = kernel.GetFileInformationByHandleEx
        func.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong); func.restype = ctypes.c_int
        with (open_file or path.open)("rb") as file:
            info = StandardInfo(); ctypes.set_last_error(0)
            ok = func(ctypes.c_void_p(msvcrt.get_osfhandle(file.fileno())), 1, ctypes.byref(info), ctypes.sizeof(info))
        return (info.allocation_size, None) if ok else (None, f"GetFileInformationByHandleEx error {ctypes.get_last_error()}")
    except (OSError, AttributeError) as exc:
        return None, f"allocation unavailable: {type(exc).__name__}: {exc}"


def inventory(value):
    root = safe_root(value); files, physical, errors = [], {}, []
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"symlink inside root rejected: {path}")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if not within(resolved, root):
            fail(f"file escapes root: {path}")
        stat = path.stat(); identity = f"{stat.st_dev}:{stat.st_ino}"
        amount, error = allocated(path, stat)
        row = {"relative_path": path.relative_to(root).as_posix(), "identity": identity,
               "device": stat.st_dev, "inode": stat.st_ino, "link_count": stat.st_nlink,
               "logical_size_bytes": stat.st_size, "allocated_bytes": amount, "allocation_error": error}
        files.append(row)
        if error:
            errors.append(f"{row['relative_path']}: {error}")
        elif identity in physical and physical[identity] != amount:
            errors.append(f"{row['relative_path']}: allocation differs for identity {identity}")
        else:
            physical[identity] = amount
    return {"root": str(root), "read_only": True, "files": sorted(files, key=lambda x: x["relative_path"]),
            "logical_size_bytes": sum(x["logical_size_bytes"] for x in files),
            "physical_allocated_bytes_deduplicated": None if errors else sum(physical.values()),
            "physical_allocation_errors": errors or None,
            "allocation_method": "GetFileInformationByHandleEx(FileStandardInfo)" if os.name == "nt" else "st_blocks*512"}


def selfcheck():
    root = RESULTS / "sidecar_retention_20260921" / "sandbox" / "disk-inventory-allocation-selfcheck"
    if root.exists():
        fail(f"selfcheck root already exists: {root}")
    root.mkdir(parents=True); source = root / "one.bin"; source.write_bytes(b"x" * 10001)
    linked, fallback = root / "same.bin", None
    try:
        os.link(source, linked)
    except OSError as exc:
        fallback = str(exc)
    report = inventory(root)
    if fallback is None:
        assert len(report["files"]) == 2 and report["logical_size_bytes"] == 2 * source.stat().st_size
        if report["physical_allocated_bytes_deduplicated"] is not None:
            assert report["physical_allocated_bytes_deduplicated"] == report["files"][0]["allocated_bytes"]
            assert report["physical_allocated_bytes_deduplicated"] >= 10001
    else:
        assert len(report["files"]) == 1
    if os.name == "nt":
        def unavailable(_): raise OSError("injected allocation failure")
        amount, error = allocated(source, source.stat(), unavailable)
        assert amount is None and "injected allocation failure" in error
    report["synthetic_selfcheck"] = True; report["hardlink_fallback"] = fallback
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--root"); parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        if args.root: fail("--selfcheck takes no root")
        selfcheck()
    elif args.root:
        print(json.dumps(inventory(args.root), indent=2))
    else:
        fail("--root is required")


if __name__ == "__main__":
    main()
