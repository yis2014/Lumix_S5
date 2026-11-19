# Dump bundle

The filenames retain the source capture names and address ranges. Address interpretation is documented in `HANDOFF_LUMIX_S5_20261119.md`.

- `program_*`  main-core plaintext captures
- `lowmem_*`  low-address boot, kernel, and postboot-time captures
- `highmem_*`  high-memory and video/DMA-adjacent captures
- `rootfs*`  decrypted SquashFS images extracted from RAM
- `dtb_*`  device-tree copies
- `hidden_*`, `keyregion*`, `a7_region.bin`  focused read-only windows

Use the hash manifest before comparing two captures.
