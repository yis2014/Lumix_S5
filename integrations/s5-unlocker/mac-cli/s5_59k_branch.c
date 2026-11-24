/*
 * s5_59k_branch.c - bounded, fixed-address volatile RTOS RAM quality override tool.
 *
 * Strictly fixed to two Thumb-1 halfwords inside 0x866B492A:
 *   0x866B493C: stock 0xD009 (beq #0x866b4952) -> patched 0xE009 (b #0x866b4952)
 *   0x866B4954: stock 0x8800 (ldrh r0, [r0])   -> patched 0x20XX (movs r0, #0xXX)
 *
 * Volatile DRAM only; zero flash, EEPROM, or user-settings writes.
 *
 *   .build/s5_59k_branch verify
 *   .build/s5_59k_branch enable [59k29|59k24|59kc24|6k24|6kc24] --confirm-write
 *   .build/s5_59k_branch restore --confirm-write
 */

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/usb/IOUSBLib.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PANASONIC_VID 0x04DA
#define SERVICE_PID   0x2370
#define TIMEOUT_MS    4000
#define FRAME_BYTES   16

#define SIG_PREV_ADDR 0x866B493Au
#define BRANCH_ADDR   0x866B493Cu
#define SIG_NEXT_ADDR 0x866B493Eu
#define LDR_ADDR      0x866B4952u
#define QID_INSN_ADDR 0x866B4954u
#define POP_ADDR      0x866B4956u
#define ACTIVE_QID    0x08CC5538u
#define HDMI_RAW_FLAG 0x08CC59E6u
#define HDMI_RAW_QID  0x08CC5A06u
#define WL_SIG_LO     0x86F15E90u /* 0x00D1 */
#define WL_SIG_HI     0x86F15E92u /* 0x80D1 */
#define WL_SLOT_LO    0x86F15E94u /* 0x00D2 -> 0x00ED */
#define WL_SLOT_HI    0x86F15E96u /* 0x80D2 -> 0x80ED */
#define WL_SENTINEL   0x86F15E98u /* 0xFFFF */
#define UI_SIG_PREV   0x08A6845Cu /* 0x00D1 */
#define UI_SLOT_Q0    0x08A6846Cu /* 0x00D2 -> 0x00ED */
#define UI_SLOT_F0    0x08A6846Eu /* 0x0102 -> 0x0104 (VISIBLE) */
#define UI_SLOT_Q1    0x08A68474u /* 0x80D2 -> 0x80ED */
#define TPL_SIG_PREV  0x08A68C5Cu /* 0x00D1 (NTSC MOV source template) */
#define TPL_SLOT_Q0   0x08A68C6Cu /* 0x00D2 -> 0x00ED */
#define TPL_SLOT_Q1   0x08A68C74u /* 0x80D2 -> 0x80ED */

#define SIG_PREV_VAL  0x2801u /* cmp r0, #1 */
#define ORIG_BRANCH   0xD009u /* beq #0x866b4952 */
#define PATCH_BRANCH  0xE009u /* b   #0x866b4952 */
#define SIG_NEXT_VAL  0xB2E0u /* uxtb r0, r4 */
#define SIG_LDR_VAL   0x486Bu /* ldr r0, [pc, #0x1ac] */
#define ORIG_QID_INSN 0x8800u /* ldrh r0, [r0] */
#define SIG_POP_VAL   0xBD10u /* pop {r4, pc} */

static uint8_t g_sum(const uint8_t *p, size_t n) {
    uint8_t s = 0;
    for (size_t i = 1; i + 2 < n; ++i) s = (uint8_t)(s + p[i]);
    return s;
}

static int prepare(IOUSBInterfaceInterface300 **usb, UInt16 index) {
    IOUSBDevRequestTO r;
    memset(&r, 0, sizeof r);
    r.bmRequestType = 0x40;
    r.bRequest = 0;
    r.wIndex = index;
    r.noDataTimeout = TIMEOUT_MS;
    r.completionTimeout = TIMEOUT_MS;
    return (*usb)->ControlRequestTO(usb, 0, &r) == kIOReturnSuccess ? 0 : -1;
}

static int read_pipe(IOUSBInterfaceInterface300 **usb, UInt8 pipe,
                     void *data, UInt32 *length) {
    UInt32 cap = *length;
    IOReturn r = (*usb)->ReadPipeTO(usb, pipe, data, length, TIMEOUT_MS, TIMEOUT_MS);
    if (r != kIOReturnSuccess || *length > cap) return -1;
    return 0;
}

static int write_pipe(IOUSBInterfaceInterface300 **usb, UInt8 pipe,
                      const void *data, UInt32 length) {
    return (*usb)->WritePipeTO(usb, pipe, (void *)data, length,
                               TIMEOUT_MS, TIMEOUT_MS) == kIOReturnSuccess ? 0 : -1;
}

static int read_half(IOUSBInterfaceInterface300 **usb, UInt8 outPipe, UInt8 inPipe,
                     uint32_t addr, uint16_t *value) {
    uint8_t tx[FRAME_BYTES], rx[FRAME_BYTES], type = 0;
    UInt32 len = 1;
    memset(tx, 0, sizeof tx);
    tx[0] = 8; tx[2] = 0xFF; tx[3] = 0x9B;
    for (unsigned i = 0; i < 4; ++i) tx[4 + i] = (uint8_t)(addr >> (8 * i));
    tx[14] = g_sum(tx, sizeof tx);

    if (prepare(usb, 0) || write_pipe(usb, outPipe, tx, sizeof tx)) return -1;
    if (prepare(usb, 1) || read_pipe(usb, inPipe, &type, &len)) return -1;
    if (len != 1 || type != 8) return -1;
    if (prepare(usb, 1)) return -1;
    memset(rx, 0, sizeof rx);
    len = sizeof rx;
    if (read_pipe(usb, inPipe, rx, &len)) return -1;
    if (len != FRAME_BYTES || rx[3] != 0x36) return -1;
    if (rx[14] != g_sum(rx, sizeof rx) || rx[15] != 0) return -1;
    *value = (uint16_t)(rx[4] | (rx[5] << 8));
    return 0;
}

static int write_half(IOUSBInterfaceInterface300 **usb, UInt8 outPipe, UInt8 inPipe,
                      uint32_t addr, uint16_t value) {
    uint8_t tx[FRAME_BYTES], rx[FRAME_BYTES], type = 0;
    UInt32 len = 1;
    memset(tx, 0, sizeof tx);
    tx[0] = 8; tx[2] = 0xFF; tx[3] = 0x9C;
    for (unsigned i = 0; i < 4; ++i) tx[4 + i] = (uint8_t)(addr >> (8 * i));
    tx[8] = (uint8_t)value;
    tx[9] = (uint8_t)(value >> 8);
    tx[14] = g_sum(tx, sizeof tx);

    if (prepare(usb, 0) || write_pipe(usb, outPipe, tx, sizeof tx)) return -1;
    if (prepare(usb, 1) || read_pipe(usb, inPipe, &type, &len)) return -1;
    if (len != 1 || (type != 8 && type != 1)) return -1;
    if (prepare(usb, 1)) return -1;
    memset(rx, 0, sizeof rx);
    len = sizeof rx;
    if (read_pipe(usb, inPipe, rx, &len)) return -1;
    printf("  write ack: len=%u", (unsigned)len);
    for (UInt32 i = 0; i < len; ++i) printf(" %02X", rx[i]);
    printf("\n");
    if (len < 6 || rx[0] != 8 || rx[1] != 0 || rx[2] != 0xFF) return -1;
    if (rx[len - 2] != g_sum(rx, len) || rx[len - 1] != 0) return -1;
    if (rx[3] != 0x01 && rx[3] != 0x00) return -1;
    return 0;
}

static uint16_t preset_insn(const char *name) {
    if (!strcmp(name, "og24"))   return 0x20EDu; /* movs r0, #0xED (6K 3:2 Open Gate 23.98p, 5952x3968) */
    if (!strcmp(name, "ogc24"))  return 0x20EEu; /* movs r0, #0xEE (6K 3:2 Open Gate 24.00p, 5952x3968) */
    if (!strcmp(name, "54k25"))  return 0x20EFu; /* movs r0, #0xEF (5.4K 3:2 Open Gate 25.00p, 5376x3584) */
    if (!strcmp(name, "54k29"))  return 0x20F0u; /* movs r0, #0xF0 (5.4K 3:2 Open Gate 29.97p, 5376x3584) */
    if (!strcmp(name, "59k24"))  return 0x20F1u; /* movs r0, #0xF1 (5.9K 16:9 23.98p, 5888x3312) */
    if (!strcmp(name, "59kc24")) return 0x20F2u; /* movs r0, #0xF2 (5.9K 16:9 24.00p, 5888x3312) */
    if (!strcmp(name, "59k25"))  return 0x20F3u; /* movs r0, #0xF3 (5.9K 16:9 25.00p, 5888x3312) */
    if (!strcmp(name, "59k29"))  return 0x20F4u; /* movs r0, #0xF4 (5.9K 16:9 29.97p, 5888x3312) */
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s verify | enable [6k24|6kc24|59k29|59k24|59kc24] --confirm-write | restore --confirm-write\n", argv[0]);
        return 1;
    }
    const char *mode = argv[1];
    const char *preset = "59k29";
    int confirmed = 0;
    for (int i = 2; i < argc; ++i) {
        if (!strcmp(argv[i], "--confirm-write")) confirmed = 1;
        else if (preset_insn(argv[i]) != 0) preset = argv[i];
        else { fprintf(stderr, "unknown arg/preset: %s\n", argv[i]); return 1; }
    }
    int is_write = (!strcmp(mode, "enable") || !strcmp(mode, "restore") ||
                    !strcmp(mode, "setslot") || !strcmp(mode, "restoreslot") ||
                    !strcmp(mode, "wl_enable") || !strcmp(mode, "wl_restore") ||
                    !strcmp(mode, "ui_enable") || !strcmp(mode, "ui_restore"));
    if (is_write && !confirmed) {
        fprintf(stderr, "refusing write without --confirm-write\n");
        return 1;
    } else if (!is_write && strcmp(mode, "verify") != 0) {
        fprintf(stderr, "unknown mode: %s\n", mode);
        return 1;
    }

    CFMutableDictionaryRef match = IOServiceMatching(kIOUSBDeviceClassName);
    int vid = PANASONIC_VID, pid = SERVICE_PID;
    CFNumberRef v = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &vid);
    CFNumberRef p = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &pid);
    CFDictionarySetValue(match, CFSTR(kUSBVendorID), v);
    CFDictionarySetValue(match, CFSTR(kUSBProductID), p);
    CFRelease(v); CFRelease(p);

    io_iterator_t iter = 0;
    IOServiceGetMatchingServices(kIOMainPortDefault, match, &iter);
    io_service_t device = IOIteratorNext(iter);
    IOObjectRelease(iter);
    if (!device) { fprintf(stderr, "no service device 04DA:2370\n"); return 2; }

    IOCFPlugInInterface **plug = NULL; SInt32 score = 0;
    IOCreatePlugInInterfaceForService(device, kIOUSBDeviceUserClientTypeID,
                                      kIOCFPlugInInterfaceID, &plug, &score);
    IOUSBDeviceInterface300 **dev = NULL;
    (*plug)->QueryInterface(plug, CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID300), (LPVOID *)&dev);

    IOUSBFindInterfaceRequest req = {
        kIOUSBFindInterfaceDontCare, kIOUSBFindInterfaceDontCare,
        kIOUSBFindInterfaceDontCare, kIOUSBFindInterfaceDontCare
    };
    io_iterator_t ifaces = 0;
    (*dev)->CreateInterfaceIterator(dev, &req, &ifaces);
    io_service_t ifaceService = IOIteratorNext(ifaces);
    IOObjectRelease(ifaces);

    IOCFPlugInInterface **ifacePlug = NULL;
    IOCreatePlugInInterfaceForService(ifaceService, kIOUSBInterfaceUserClientTypeID,
                                      kIOCFPlugInInterfaceID, &ifacePlug, &score);
    IOUSBInterfaceInterface300 **usb = NULL;
    (*ifacePlug)->QueryInterface(ifacePlug, CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID300),
                                 (LPVOID *)&usb);
    if ((*usb)->USBInterfaceOpenSeize(usb) != kIOReturnSuccess) {
        fprintf(stderr, "could not claim the service interface\n");
        return 1;
    }

    UInt8 count = 0, outPipe = 0, inPipe = 0;
    (*usb)->GetNumEndpoints(usb, &count);
    for (UInt8 pipe = 1; pipe <= count; ++pipe) {
        UInt8 dir = 0, num = 0, type = 0, interval = 0; UInt16 max = 0;
        if ((*usb)->GetPipeProperties(usb, pipe, &dir, &num, &type, &max, &interval) != kIOReturnSuccess)
            continue;
        if (type == kUSBBulk && dir == kUSBOut) outPipe = pipe;
        if (type == kUSBBulk && dir == kUSBIn) inPipe = pipe;
    }
    if (!outPipe || !inPipe) {
        fprintf(stderr, "bulk pipes not found\n");
        (*usb)->USBInterfaceClose(usb);
        return 1;
    }

    uint16_t prev = 0, cur_br = 0, next = 0, ldr_i = 0, cur_q = 0, pop_i = 0, raw_flag = 0, raw_qid = 0, act_qid = 0;
    int rc = 0;
    if (read_half(usb, outPipe, inPipe, SIG_PREV_ADDR, &prev) ||
        read_half(usb, outPipe, inPipe, BRANCH_ADDR, &cur_br) ||
        read_half(usb, outPipe, inPipe, SIG_NEXT_ADDR, &next) ||
        read_half(usb, outPipe, inPipe, LDR_ADDR, &ldr_i) ||
        read_half(usb, outPipe, inPipe, QID_INSN_ADDR, &cur_q) ||
        read_half(usb, outPipe, inPipe, POP_ADDR, &pop_i) ||
        read_half(usb, outPipe, inPipe, HDMI_RAW_FLAG, &raw_flag) ||
        read_half(usb, outPipe, inPipe, HDMI_RAW_QID, &raw_qid) ||
        read_half(usb, outPipe, inPipe, ACTIVE_QID, &act_qid)) {
        fprintf(stderr, "signature read failed\n");
        rc = 1;
    } else {
        printf("sig1: 0x%08X=0x%04X  0x%08X=0x%04X  0x%08X=0x%04X\n",
               SIG_PREV_ADDR, prev, BRANCH_ADDR, cur_br, SIG_NEXT_ADDR, next);
        printf("sig2: 0x%08X=0x%04X  0x%08X=0x%04X  0x%08X=0x%04X\n",
               LDR_ADDR, ldr_i, QID_INSN_ADDR, cur_q, POP_ADDR, pop_i);
        printf("raw:  0x%08X=0x%02X (hdmi_raw_flag)  0x%08X=0x%04X (qid)  0x%08X=0x%04X (active_qid)\n",
               HDMI_RAW_FLAG, raw_flag & 0xFF, HDMI_RAW_QID, raw_qid, ACTIVE_QID, act_qid);

        if (prev != SIG_PREV_VAL || next != SIG_NEXT_VAL || ldr_i != SIG_LDR_VAL || pop_i != SIG_POP_VAL) {
            fprintf(stderr, "SIGNATURE MISMATCH; aborting\n");
            rc = 1;
        } else if (!strcmp(mode, "setslot")) {
            uint16_t target_id = preset_insn(preset) & 0xFFu;
            printf("setting active_qid 0x%08X: 0x%04X -> 0x%04X (save original 0x%04X!)\n",
                   ACTIVE_QID, act_qid, target_id, act_qid);
            if (write_half(usb, outPipe, inPipe, ACTIVE_QID, target_id)) {
                fprintf(stderr, "setslot write failed\n");
                rc = 1;
            } else {
                uint16_t rb = 0;
                if (read_half(usb, outPipe, inPipe, ACTIVE_QID, &rb) || rb != target_id) {
                    fprintf(stderr, "setslot read-back mismatch: 0x%04X\n", rb);
                    rc = 1;
                } else {
                    printf("OK: active_qid 0x%08X=0x%04X (was 0x%04X)\n", ACTIVE_QID, rb, act_qid);
                }
            }
        } else if (!strcmp(mode, "restoreslot")) {
            uint16_t restore_id = 0x008Bu;
            printf("restoring active_qid 0x%08X: 0x%04X -> 0x%04X\n", ACTIVE_QID, act_qid, restore_id);
            if (write_half(usb, outPipe, inPipe, ACTIVE_QID, restore_id)) {
                fprintf(stderr, "restoreslot write failed\n");
                rc = 1;
            } else {
                uint16_t rb = 0;
                if (read_half(usb, outPipe, inPipe, ACTIVE_QID, &rb) || rb != restore_id) {
                    fprintf(stderr, "restoreslot read-back mismatch: 0x%04X\n", rb);
                    rc = 1;
                } else {
                    printf("OK: restored active_qid 0x%08X=0x%04X\n", ACTIVE_QID, rb);
                }
            }
        } else if (!strcmp(mode, "ui_enable") || !strcmp(mode, "ui_restore")) {
            uint16_t sp = 0, q0 = 0, f0 = 0, q1 = 0;
            uint16_t tsp = 0, tq0 = 0, tq1 = 0;
            if (read_half(usb, outPipe, inPipe, UI_SIG_PREV, &sp) ||
                read_half(usb, outPipe, inPipe, UI_SLOT_Q0, &q0) ||
                read_half(usb, outPipe, inPipe, UI_SLOT_F0, &f0) ||
                read_half(usb, outPipe, inPipe, UI_SLOT_Q1, &q1) ||
                read_half(usb, outPipe, inPipe, TPL_SIG_PREV, &tsp) ||
                read_half(usb, outPipe, inPipe, TPL_SLOT_Q0, &tq0) ||
                read_half(usb, outPipe, inPipe, TPL_SLOT_Q1, &tq1)) {
                fprintf(stderr, "ui/tpl table read failed\n");
                rc = 1;
            } else {
                printf("ui:  prev=%04X q0=%04X f0=%04X q1=%04X\n", sp, q0, f0, q1);
                printf("tpl: prev=%04X q0=%04X q1=%04X\n", tsp, tq0, tq1);
                if (sp != 0x00D1u || tsp != 0x00D1u) {
                    fprintf(stderr, "UI/TPL TABLE SIGNATURE MISMATCH; aborting\n");
                    rc = 1;
                } else {
                    int en = !strcmp(mode, "ui_enable");
                    uint16_t nq0 = en ? 0x00EDu : 0x00D2u;
                    uint16_t nf0 = 0x0104u;
                    uint16_t nq1 = en ? 0x80EDu : 0x80D2u;
                    if (write_half(usb, outPipe, inPipe, TPL_SLOT_Q0, nq0) ||
                        write_half(usb, outPipe, inPipe, TPL_SLOT_Q1, nq1) ||
                        write_half(usb, outPipe, inPipe, UI_SLOT_Q0, nq0) ||
                        write_half(usb, outPipe, inPipe, UI_SLOT_F0, nf0) ||
                        write_half(usb, outPipe, inPipe, UI_SLOT_Q1, nq1)) {
                        fprintf(stderr, "ui/tpl write failed\n");
                        rc = 1;
                    } else {
                        uint16_t r0 = 0, r1 = 0, r2 = 0, tr0 = 0, tr1 = 0;
                        if (read_half(usb, outPipe, inPipe, UI_SLOT_Q0, &r0) ||
                            read_half(usb, outPipe, inPipe, UI_SLOT_F0, &r1) ||
                            read_half(usb, outPipe, inPipe, UI_SLOT_Q1, &r2) ||
                            read_half(usb, outPipe, inPipe, TPL_SLOT_Q0, &tr0) ||
                            read_half(usb, outPipe, inPipe, TPL_SLOT_Q1, &tr1) ||
                            r0 != nq0 || r1 != nf0 || r2 != nq1 || tr0 != nq0 || tr1 != nq1) {
                            fprintf(stderr, "ui/tpl read-back mismatch: %04X/%04X/%04X tpl=%04X/%04X\n",
                                    r0, r1, r2, tr0, tr1);
                            rc = 1;
                        } else {
                            printf("OK: TPL 0x%08X=%04X/0x%08X=%04X + UI 0x%08X=%04X(f=%04X)/0x%08X=%04X\n",
                                   TPL_SLOT_Q0, tr0, TPL_SLOT_Q1, tr1, UI_SLOT_Q0, r0, r1, UI_SLOT_Q1, r2);
                        }
                    }
                }
            }
        } else if (!strcmp(mode, "wl_enable") || !strcmp(mode, "wl_restore")) {
            uint16_t s0 = 0, s1 = 0, v0 = 0, v1 = 0, sent = 0;
            if (read_half(usb, outPipe, inPipe, WL_SIG_LO, &s0) ||
                read_half(usb, outPipe, inPipe, WL_SIG_HI, &s1) ||
                read_half(usb, outPipe, inPipe, WL_SLOT_LO, &v0) ||
                read_half(usb, outPipe, inPipe, WL_SLOT_HI, &v1) ||
                read_half(usb, outPipe, inPipe, WL_SENTINEL, &sent)) {
                fprintf(stderr, "whitelist read failed\n");
                rc = 1;
            } else {
                printf("wl: sig=%04X/%04X slot=%04X/%04X sent=%04X\n", s0, s1, v0, v1, sent);
                if (s0 != 0x00D1u || s1 != 0x80D1u || sent != 0xFFFFu) {
                    fprintf(stderr, "WHITELIST SIGNATURE MISMATCH; aborting\n");
                    rc = 1;
                } else {
                    uint16_t w0 = !strcmp(mode, "wl_enable") ? 0x00EDu : 0x00D2u;
                    uint16_t w1 = !strcmp(mode, "wl_enable") ? 0x80EDu : 0x80D2u;
                    printf("writing whitelist 0x%08X=%04X, 0x%08X=%04X\n", WL_SLOT_LO, w0, WL_SLOT_HI, w1);
                    if (write_half(usb, outPipe, inPipe, WL_SLOT_LO, w0) ||
                        write_half(usb, outPipe, inPipe, WL_SLOT_HI, w1)) {
                        fprintf(stderr, "whitelist write failed\n");
                        rc = 1;
                    } else {
                        uint16_t rb0 = 0, rb1 = 0;
                        if (read_half(usb, outPipe, inPipe, WL_SLOT_LO, &rb0) ||
                            read_half(usb, outPipe, inPipe, WL_SLOT_HI, &rb1) ||
                            rb0 != w0 || rb1 != w1) {
                            fprintf(stderr, "whitelist read-back mismatch: %04X/%04X\n", rb0, rb1);
                            rc = 1;
                        } else {
                            printf("OK: whitelist 0x%08X=%04X, 0x%08X=%04X\n", WL_SLOT_LO, rb0, WL_SLOT_HI, rb1);
                        }
                    }
                }
            }
        } else if (!strcmp(mode, "enable")) {
            uint16_t want_q = preset_insn(preset);
            if ((raw_flag & 0xFF) != 0) {
                fprintf(stderr, "HDMI RAW flag is non-zero (%u); refusing\n", raw_flag & 0xFF);
                rc = 1;
            } else {
                printf("enabling preset '%s': 0x%08X=0x%04X, 0x%08X=0x%04X\n",
                       preset, QID_INSN_ADDR, want_q, BRANCH_ADDR, PATCH_BRANCH);
                if (write_half(usb, outPipe, inPipe, QID_INSN_ADDR, want_q) ||
                    write_half(usb, outPipe, inPipe, BRANCH_ADDR, PATCH_BRANCH)) {
                    fprintf(stderr, "write failed\n");
                    rc = 1;
                } else {
                    uint16_t rb1 = 0, rb2 = 0;
                    if (read_half(usb, outPipe, inPipe, QID_INSN_ADDR, &rb1) ||
                        read_half(usb, outPipe, inPipe, BRANCH_ADDR, &rb2) ||
                        rb1 != want_q || rb2 != PATCH_BRANCH) {
                        fprintf(stderr, "read-back mismatch: 0x%04X / 0x%04X\n", rb1, rb2);
                        rc = 1;
                    } else {
                        printf("OK: preset '%s' active (0x%08X=0x%04X, 0x%08X=0x%04X)\n",
                               preset, QID_INSN_ADDR, rb1, BRANCH_ADDR, rb2);
                    }
                }
            }
        } else if (!strcmp(mode, "restore")) {
            printf("restoring 0x%08X->0x%04X, 0x%08X->0x%04X\n",
                   BRANCH_ADDR, ORIG_BRANCH, QID_INSN_ADDR, ORIG_QID_INSN);
            if (write_half(usb, outPipe, inPipe, BRANCH_ADDR, ORIG_BRANCH) ||
                write_half(usb, outPipe, inPipe, QID_INSN_ADDR, ORIG_QID_INSN)) {
                fprintf(stderr, "restore write failed\n");
                rc = 1;
            } else {
                uint16_t rb1 = 0, rb2 = 0;
                if (read_half(usb, outPipe, inPipe, BRANCH_ADDR, &rb1) ||
                    read_half(usb, outPipe, inPipe, QID_INSN_ADDR, &rb2) ||
                    rb1 != ORIG_BRANCH || rb2 != ORIG_QID_INSN) {
                    fprintf(stderr, "restore read-back mismatch: 0x%04X / 0x%04X\n", rb1, rb2);
                    rc = 1;
                } else {
                    printf("OK: restored stock (0x%08X=0x%04X, 0x%08X=0x%04X)\n",
                           BRANCH_ADDR, rb1, QID_INSN_ADDR, rb2);
                }
            }
        }
    }

    (*usb)->USBInterfaceClose(usb);
    (*usb)->Release(usb); (*ifacePlug)->Release(ifacePlug);
    (*dev)->Release(dev); (*plug)->Release(plug);
    IOObjectRelease(ifaceService); IOObjectRelease(device);
    return rc;
}
