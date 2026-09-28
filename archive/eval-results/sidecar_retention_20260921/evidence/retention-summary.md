# Retention: cinque delta consecutivi

Run e sampler completati (exit 0); PID main 31304, reader pinned 33564. Fingerprint pinned invariata in cinque CHECK e reader chiuso prima del prune finale.

| stato | versioni | logical bytes | physical allocated dedup bytes | allocation errors |
|---|---|---:|---:|---|
| baseline | 1 | 588344 | 626984 | null |
| step 1 | 2 | 1176563 | 725504 | null |
| step 2 | 3 | 1764779 | 828120 | null |
| step 3 | 4 | 2352990 | 934832 | null |
| step 4 | 4 | 2356983 | 996272 | null |
| step 5 | 4 | 2360970 | 1057712 | null |
| post-close | 3 | 1776041 | 844504 | null |

Baseline version: `v20260921T135520`; retained through step 5, removed after pinned reader close. Post-close versions: v20260921T135550, v20260921T135554, v20260921T135558.

Sampled main PID maxima (MiB): RSS 4008.414, private 6518.410, USS 1467.680; 438 samples.
Sampled pinned PID maxima (MiB): RSS 59.289, private 142.336, USS 43.641; 119 samples.

| step | request window s | main samples | main RSS max MiB | queries overlapping | queries contained | empty/errors overlapping |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4.148 | 23 | 3944.973 | 3 | 1 | 0/0 |
| 2 | 3.840 | 20 | 3961.227 | 3 | 2 | 0/0 |
| 3 | 3.588 | 19 | 3980.863 | 4 | 2 | 0/0 |
| 4 | 3.853 | 20 | 3996.859 | 3 | 3 | 0/0 |
| 5 | 4.101 | 22 | 4008.414 | 5 | 3 | 0/0 |

Queries globali: 19, empty 0, errors 0. Overlap uses interval intersection, so counts across steps must not be summed.
Qdrant container, separate sampled maxima (MiB): RSS 461.312, private 459.277, cgroup usage 513.910; 68 sonde distinte (incl. sonda finale), 436 righe campionate con valori Qdrant anche cached.

Sampled memory peaks are lower bounds. Step windows span request to HTTP response, not the full writer/readiness phase. Disk inventory uses file identity to deduplicate hardlinks; `physical_allocation_errors: null` means no allocation error was reported by the inventory.
