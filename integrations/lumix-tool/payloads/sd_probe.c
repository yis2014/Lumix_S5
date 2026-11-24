/* SD read probe: call SDD_Read for sector 0 and record what happened.
 *
 * Build: pwsh -File payloads/build.ps1
 *
 * Memory map used:
 *   0x8F300020  results (mark[0..3])
 *   0x8F303000  scratch: sector offset (physical)
 *   0x8F304000  read buffer (physical, 4 KiB)
 *
 * Addresses passed to the firmware use the virtual form (physical - 0x80000000).
 *
 * RISK: if the calling convention is wrong the camera may hang (battery pull to recover).
 */
#define REG32(a) (*(volatile unsigned int *)(a))
typedef unsigned int u32;

/* int SDD_Read(ctx, offset_ptr, buffer, count)  -- 0x863C0504, Thumb */
typedef int (*sd_read_t)(u32 ctx, u32 offset_ptr, u32 buffer, u32 count);

#define SD_CTX_VIRT     0x08AB07A4u   /* global 0x88AB0774 + 0x30 */
#define OFF_PHYS        0x8F303000u
#define OFF_VIRT        0x0F303000u
#define BUF_PHYS        0x8F304000u
#define BUF_VIRT        0x0F304000u
#define MARK            0x8F300020u

void _start(void) {
    volatile u32 *mark = (volatile u32 *)MARK;
    mark[0] = 0x0000A1A1u;                 /* entered */
    mark[1] = 0;
    mark[2] = 0;
    mark[3] = 0;

    REG32(OFF_PHYS) = 0;                   /* byte offset 0 */
    sd_read_t sd_read = (sd_read_t)0x863C0505u;
    int ret = sd_read(SD_CTX_VIRT, OFF_VIRT, BUF_VIRT, 512);

    mark[1] = (u32)ret;
    mark[2] = REG32(BUF_PHYS);             /* first word of sector 0 */
    mark[3] = 0x0000A2A2u;                 /* returned */
}
