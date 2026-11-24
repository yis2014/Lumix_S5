/* Minimal test payload: write a marker and return.
 * Built with:
 *   arm-none-eabi-gcc -mcpu=cortex-a7 -mthumb -O2 -nostdlib -ffreestanding \
 *     -fno-builtin -Ttext=0x86370000 -Wl,-e,_start -o test_marker.elf test_marker.c
 */
#define REG32(a) (*(volatile unsigned int *)(a))

void _start(void) {
    REG32(0x8F300010) = 0xCAFEBABE;
}
