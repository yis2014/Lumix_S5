# Lumix S5 reverse-engineering bundle

This repository contains the 2026-11-19 DC-S5 research handoff, firmware samples, RAM dumps, extracted Linux images, Service USB tools, probe backups, and public key material.

## Start here

- `HANDOFF_LUMIX_S5_20261119.md` gives the current state, memory map, evidence boundaries, and the first read-only checks for a new investigator.
- `keys/KEY_MATERIAL_PUBLIC.md` lists recovered material and identifies the body payload key status.
- `firmware/` contains official and experimental packages.
- `dumps/` contains the main-core, low-memory, high-memory, rootfs, DTB, and probe-related captures.
- `lumix_ml/` contains the Service USB transport and analysis tools.
- `analysis/root/` contains the current dated reports and structured results.

Large binary files are managed with Git LFS. Verify the SHA-256 values in `MANIFEST_SHA256.txt` before using any artifact.

The package preserves raw files for research. A backup JSON records a planned write and does not prove that the same bytes remain in the camera. Read back the target before every new hardware action.
