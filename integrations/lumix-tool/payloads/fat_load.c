/* FAT32 reader payload for the Panasonic S5.
 *
 * Reads a file from the SD card using the camera's own SD driver (SDD_Read),
 * loads it to OUT_BUF and records progress in the marker area. The caller can
 * then jump to OUT_BUF.
 *
 * Build with payloads/build.ps1 (load address 0x86370000).
 *
 * Memory (physical):
 *   0x8F303000  scratch offset for SDD_Read
 *   0x8F310000  sector buffer (4 KiB)
 *   0x8F320000  cluster buffer (64 KiB)
 *   0x86360000  output (file contents, executable, max 60 KiB)
 *   0x8F300040  markers: [0]=state, [1]=result, [2]=file size, [3]=first cluster
 *
 * All addresses handed to firmware functions use the virtual form
 * (physical - 0x80000000).
 */
#define REG32(a) (*(volatile unsigned int *)(a))
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define SD_CTX_V      0x08AB07A4u
#define OFF_PHYS      0x8F303000u
#define SEC_PHYS      0x8F310000u
#define CLU_PHYS      0x8F320000u
#define OUT_PHYS      0x86360000u  /* executable hole, below the loader */
#define MARK          0x8F300040u

typedef int (*sd_read_t)(u32 ctx, u32 off_ptr, u32 buffer, u32 count);
static sd_read_t const g_read = (sd_read_t)0x863C0505u;

/* Target file name in 8.3 form (11 bytes, space padded). */
static const u8 k_name[11] = { 'L','U','M','I','X',' ',' ',' ','B','I','N' };

static u32 rd8(u32 a)  { return *(volatile u8 *)a; }
static u32 rd16(u32 a) { return *(volatile u16 *)a; }
static u32 rd32(u32 a) { return *(volatile u32 *)a; }

static int sd_read(u32 byte_offset, u32 buf_phys, u32 bytes) {
    REG32(OFF_PHYS) = byte_offset;
    return g_read(SD_CTX_V, OFF_PHYS - 0x80000000u, buf_phys - 0x80000000u, bytes);
}

/* FAT32 layout, discovered from the boot sector. */
/* No .bss: keep the FAT layout in fixed scratch words (they are always
   written by parse_boot before use). */
#define G_DATA_START  0x8F300060u
#define G_SPC         0x8F300064u
#define G_FAT_START   0x8F300068u
#define G_ROOT_CLU    0x8F30006Cu

static int next_cluster(u32 clus) {
    u32 off = (clus * 4u) % 512u;
    u32 sec = REG32(G_FAT_START) + (clus * 4u) / 512u;
    if (sd_read(sec * 512u, SEC_PHYS, 512)) return -1;
    return (int)(rd32(SEC_PHYS + off) & 0x0FFFFFFFu);
}

static u32 cluster_sector(u32 clus) {
    return REG32(G_DATA_START) + (clus - 2u) * REG32(G_SPC);
}

static int parse_boot(u32 lba) {
    if (sd_read(lba * 512u, SEC_PHYS, 512)) return -1;
    if (rd16(SEC_PHYS + 510) != 0xAA55) return -2;
    REG32(G_SPC) = rd8(SEC_PHYS + 13);
    u32 reserved = rd16(SEC_PHYS + 14);
    u32 nfats    = rd8(SEC_PHYS + 16);
    u32 fat_sz   = rd32(SEC_PHYS + 36);
    REG32(G_ROOT_CLU) = rd32(SEC_PHYS + 44);
    if (!REG32(G_SPC) || !fat_sz || !REG32(G_ROOT_CLU)) return -3;
    REG32(G_FAT_START) = lba + reserved;
    REG32(G_DATA_START) = REG32(G_FAT_START) + nfats * fat_sz;
    return 0;
}

/* Look for k_name in one directory cluster; returns the entry address or 0. */
static u32 scan_dir_cluster(u32 clus) {
    if (sd_read(cluster_sector(clus) * 512u, CLU_PHYS, REG32(G_SPC) * 512u)) return 0;
    u32 bytes = REG32(G_SPC) * 512u;
    for (u32 off = 0; off + 32 <= bytes; off += 32) {
        u32 e = CLU_PHYS + off;
        u8 first = (u8)rd8(e);
        if (first == 0x00) return 0;          /* end of directory */
        if (first == 0xE5) continue;          /* deleted */
        if ((rd8(e + 11) & 0x3F) == 0x0F) continue;  /* LFN entry */
        int match = 1;
        for (int i = 0; i < 11; i++) {
            if ((u8)rd8(e + i) != k_name[i]) { match = 0; break; }
        }
        if (match) return e;
    }
    return 0;
}

void _start(void) {
    volatile u32 *mark = (volatile u32 *)MARK;
    mark[0] = 0x0000B1B1u;   /* started */
    mark[1] = 0;
    mark[2] = 0;
    mark[3] = 0;

    /* Read sector 0: either a VBR or an MBR. */
    if (sd_read(0, SEC_PHYS, 512)) { mark[1] = 0xE001; return; }

    u32 lba = 0;
    int is_vbr = (rd16(SEC_PHYS + 11) == 512 && rd8(SEC_PHYS + 13) >= 1 &&
                  rd32(SEC_PHYS + 36) != 0);
    if (!is_vbr) {
        int found = 0;
        for (int i = 0; i < 4; i++) {
            u32 e = SEC_PHYS + 446 + i * 16;
            u8 type = (u8)rd8(e + 4);
            if (type == 0x0B || type == 0x0C || type == 0x0E) {
                lba = rd32(e + 8);
                found = 1;
                break;
            }
        }
        if (!found) { mark[1] = 0xE002; return; }
    }

    if (parse_boot(lba)) { mark[1] = 0xE003; return; }
    mark[0] = 0x0000B2B2u;   /* boot sector parsed */

    /* Walk the root directory. */
    u32 clus = REG32(G_ROOT_CLU);
    u32 entry = 0;
    for (int guard = 0; guard < 64 && clus >= 2 && clus < 0x0FFFFFF8u; guard++) {
        entry = scan_dir_cluster(clus);
        if (entry) break;
        int nxt = next_cluster(clus);
        if (nxt <= 0) break;
        clus = (u32)nxt;
    }
    if (!entry) { mark[1] = 0xE004; return; }

    u32 first = (rd16(entry + 26) | (rd16(entry + 20) << 16));
    u32 size  = rd32(entry + 28);
    mark[2] = size;
    mark[3] = first;
    /* Keep below the loader at 0x86370000 (60 KiB max). */
    if (!first || !size || size > 0xF000u) { mark[1] = 0xE005; return; }

    /* Copy the cluster chain to OUT_PHYS. */
    u32 copied = 0;
    clus = first;
    for (int guard = 0; guard < 4096 && clus >= 2 && clus < 0x0FFFFFF8u; guard++) {
        if (sd_read(cluster_sector(clus) * 512u, OUT_PHYS + copied, REG32(G_SPC) * 512u)) {
            mark[1] = 0xE006;
            return;
        }
        copied += REG32(G_SPC) * 512u;
        if (copied >= size) break;
        int nxt = next_cluster(clus);
        if (nxt <= 0) break;
        clus = (u32)nxt;
    }

    mark[1] = 0x0000B0B0u;   /* file ready at OUT_PHYS */

    /* Hand control to the program we just loaded. */
    void (*run)(void) = (void (*)(void))(OUT_PHYS | 1u);
    run();
}
