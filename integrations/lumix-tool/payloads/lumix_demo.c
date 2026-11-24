/* Demo program to be placed on the SD card as LUMIX.BIN.
 *
 * fat_load.bin reads it from the card, loads it at 0x86360000 and jumps here.
 * It writes a recognizable pattern so the host can confirm that the program
 * really came from the SD card.
 */
#define REG32(a) (*(volatile unsigned int *)(a))
typedef unsigned int u32;

void _start(void) {
    /* 0x8F3000A0: written only by this demo, so seeing it proves the chain. */
    REG32(0x8F3000A0) = 0x5A5A5A5Au;
    REG32(0x8F3000A4) = 0x1234ABCDu;
}
