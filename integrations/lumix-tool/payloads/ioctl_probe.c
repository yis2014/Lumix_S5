/* Safe SD probe: ask the driver for the sector size via SDD_Ioctl(cmd=0x08).
 *
 * This path is read-only (the handler just copies [card+0xC] to the out
 * pointer), so it validates the context pointer and the calling convention
 * without touching the card.
 *
 * Results at 0x8F300080:
 *   [0] 0xC1C1C1C1 entered
 *   [1] return value
 *   [2] sector size written by the driver (expect 0x200)
 *   [3] 0xC2C2C2C2 returned
 */
#define REG32(a) (*(volatile unsigned int *)(a))
typedef unsigned int u32;

typedef int (*sd_ioctl_t)(u32 ctx, u32 cmd, u32 arg1, u32 arg2);

#define SD_CTX_V    0x08AB07A4u
#define OUT_PHYS    0x8F303000u
#define OUT_VIRT    0x0F303000u
#define MARK        0x8F300080u

void _start(void) {
    volatile u32 *m = (volatile u32 *)MARK;
    m[0] = 0xC1C1C1C1u;
    m[1] = 0;
    m[2] = 0;
    m[3] = 0;

    REG32(OUT_PHYS) = 0;
    sd_ioctl_t ioctl = (sd_ioctl_t)0x863BFE17u;
    int ret = ioctl(SD_CTX_V, 0x08u, OUT_VIRT, 0u);

    m[1] = (u32)ret;
    m[2] = REG32(OUT_PHYS);
    m[3] = 0xC2C2C2C2u;
}
