# F6 disk inventory — prepared

`disk_inventory.py` inventories only a root under `rag/eval/results/<run>/sandbox`; it rejects a root or child symlink that escapes that boundary. It emits JSON to stdout and does not modify the tree it inventories.

Each file records its relative path, device/inode identity, link count, logical size, and allocation. Linux uses `st_blocks * 512`. Windows opens the file read-only and calls `GetFileInformationByHandleEx(FileStandardInfo)` through stdlib `ctypes`, taking `FILE_STANDARD_INFO.AllocationSize`. `GetCompressedFileSizeW` is deliberately not used: for a noncompressed, nonsparse file it returns the logical file size. An open/API `OSError` or `AttributeError` produces `null` plus the reason; it is never treated as zero. The physical total becomes null when any allocation is unavailable and deduplicates only equal device/inode identities otherwise.

`--selfcheck` creates a single exclusive sandbox fixture with one 10,001-byte file and a hard link when the filesystem permits it. It proves logical double-counting and physical identity de-duplication, requires a non-null allocation to be at least the logical size, and injects an unreadable-handle failure to assert `null` plus its error. A hard-link failure is reported as a fallback, not hidden. The fixture is synthetic and not a benchmark or an NPZ/NPY format decision.

References: [GetCompressedFileSizeW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getcompressedfilesizew), [FILE_STANDARD_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info).
