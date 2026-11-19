"""Emulate the S5 metadata ECDSA verifier with real V2.9 firmware data.

Confirms (a) the function at phys 0x868c08c6 really is the P-256 ECDSA verifier,
(b) its return convention, and (c) that the proposed always-valid patch works.
No camera involvement.
"""
import hashlib

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

BIN = r"E:\desktop\LUMIX\program_0x86280000.bin"
FW = r"E:\desktop\LUMIX\S5___V29.bin"
VIRT_BASE = 0x06280000
PHYS_BASE = 0x86280000
VERIFY_PHYS = 0x868C08C6
PUBKEY_VIRT = 0x06F53722
SCRATCH = 0x0B000000
STACK = 0x0C000000
SENTINEL = 0x09000000

image = open(BIN, "rb").read()
fw = open(FW, "rb").read(0x2000)
signature = fw[0x220:0x260]
digest = hashlib.sha256(fw[0x2A0:0x142C]).digest()


def run(hash_bytes, sig_bytes, patched=False, max_ins=400_000_000):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(VIRT_BASE, (len(image) + 0xFFF) & ~0xFFF)
    uc.mem_write(VIRT_BASE, image)
    uc.mem_map(PHYS_BASE, (len(image) + 0xFFF) & ~0xFFF)
    uc.mem_write(PHYS_BASE, image)
    uc.mem_map(SCRATCH, 0x10000)
    uc.mem_map(STACK, 0x100000)
    uc.mem_map(SENTINEL, 0x1000)
    uc.mem_write(SCRATCH, hash_bytes)
    uc.mem_write(SCRATCH + 0x100, sig_bytes)
    if patched:
        # movs r0, #0 ; bx lr  == always report "signature valid" (0 = valid)
        uc.mem_write(VERIFY_PHYS, bytes.fromhex("00207047"))
        uc.mem_write(VERIFY_PHYS - PHYS_BASE + VIRT_BASE, bytes.fromhex("00207047"))
    uc.reg_write(UC_ARM_REG_R0, PUBKEY_VIRT)
    uc.reg_write(UC_ARM_REG_R1, SCRATCH)
    uc.reg_write(UC_ARM_REG_R2, SCRATCH + 0x100)
    uc.reg_write(UC_ARM_REG_SP, STACK + 0x80000)
    uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)
    try:
        from unicorn.arm_const import UC_ARM_REG_FPEXC
        uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    except Exception as exc:  # noqa: BLE001
        print("fpu enable warning:", exc)
    count = [0]

    def stop_at_sentinel(uc, address, size, user):
        count[0] += 1
        if address == SENTINEL:
            uc.emu_stop()
        elif address == 0x866C261C:
            # firmware memset uses VFP registers; emulate it in Python instead
            # __aeabi_memclr(dst=r0, n=r1): zero-fill, uses VFP in this build
            dst = uc.reg_read(UC_ARM_REG_R0)
            val = 0
            n = uc.reg_read(UC_ARM_REG_R1)
            if n > 0x100000:
                print(f"suspicious memset dst=0x{dst:08x} n=0x{n:x}")
            try:
                uc.mem_write(dst, bytes([val]) * n)
            except Exception:  # noqa: BLE001
                # map scratch RAM on demand for work buffers outside the image
                page = dst & ~0xFFF
                uc.mem_map(page, ((n + (dst - page)) + 0xFFF) & ~0xFFF)
                uc.mem_write(dst, bytes([val]) * n)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, stop_at_sentinel)
    try:
        uc.emu_start(VERIFY_PHYS | 1, SENTINEL, count=max_ins)
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}", count[0]
    return uc.reg_read(UC_ARM_REG_R0), count[0]


def main():
    le_digest = digest[::-1]
    print("valid signature, little-endian digest ->", run(le_digest, signature))
    bad = bytearray(le_digest)
    bad[0] ^= 1
    print("corrupted digest                 ->", run(bytes(bad), signature))
    badsig = bytearray(signature)
    badsig[0] ^= 1
    print("corrupted signature              ->", run(bytes(le_digest), bytes(badsig)))
    print("PATCHED, corrupted signature     ->", run(bytes(le_digest), bytes(badsig), patched=True))


if __name__ == "__main__":
    main()

