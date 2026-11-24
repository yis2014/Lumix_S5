"""RAM safety tests, independent of Windows/WinUSB and camera hardware."""
import contextlib
import io
import json
import os
import runpy
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import s5focus as focus


class FakeService:
    def __init__(self):
        self.memory = {}
        self.reads = []
        self.writes = []
        self.closed = False

    def put(self, address, data):
        self.memory.update((address + i, value) for i, value in enumerate(data))

    def get(self, address, size):
        return bytes(self.memory.get(address + i, 0x55) for i in range(size))

    def exchange(self, address):
        assert address % 1024 == 0
        self.reads.append(address)
        return b'\x01\x00\xff\x05' + self.get(address, 1024) + b'\x00\x00'

    def exchange_write(self, item):
        address, value = item
        self.writes.append(item)
        self.put(address, struct.pack('<H', value))

    def close(self):
        self.closed = True


def stock_entry(index, addr=0x06A97580, samples=14464):
    raw = bytearray(32)
    struct.pack_into('<II', raw, 0, index, addr)
    struct.pack_into('<I', raw, 0x14, samples)
    struct.pack_into('<I', raw, 0x1C, 1)
    return bytes(raw)


def seed_verified_camera(svc, version=0x0290):
    """Firmware 2.90 body version and a plausible stock sound table."""
    svc.put(focus.VERSION_ADDR, struct.pack('<H', version))
    for i in range(focus.SLOT_COUNT):
        svc.put(focus.TBL + i * 32, stock_entry(i, 0x06A97580 + i * 0x1000))


class SlotTests(unittest.TestCase):
    def setUp(self):
        self.svc = FakeService()
        seed_verified_camera(self.svc)
        self.transport = types.SimpleNamespace(
            build_0x5c=lambda addr: addr,
            build_0x9c=lambda addr, value: (addr, value),
            Service=lambda **kwargs: self.svc,
        )
        self.patcher = patch.object(focus, 'S', self.transport)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.pcm = os.path.join(self.directory.name, 'test.pcm')
        with open(self.pcm, 'wb') as target:
            target.write(b'\x01\x00\xff\x7f')

    def test_header_is_exactly_16_bytes_and_rejects_invalid_headers(self):
        raw = focus.encode_header(7, 132300)
        self.assertEqual(raw, b'LMXTSLOT' + struct.pack('<II', 7, 132300))
        self.assertEqual(focus.decode_header(raw), (7, 132300))
        for invalid in [raw[:15], b'X' + raw[1:],
                        b'LMXTSLOT' + struct.pack('<II', 28, 2),
                        b'LMXTSLOT' + struct.pack('<II', 1, 0),
                        b'LMXTSLOT' + struct.pack('<II', 1, 132301)]:
            self.assertIsNone(focus.decode_header(invalid))
        for samples in [0, -1, 132301, 1.5, True]:
            with self.assertRaises(ValueError):
                focus.encode_header(7, samples)

    def test_alignment_range_and_span_validate_before_opening_device(self):
        for addr in [0x8EFFFC00, 0x8F800000, 0x8F084100, 0x8F000001, True, 1.5]:
            with self.subTest(addr=addr), patch.object(self.transport, 'Service') as service:
                with self.assertRaises(ValueError):
                    focus.cmd_apply(self.pcm, 2, 1, addr)
                service.assert_not_called()
        with self.assertRaises(ValueError):
            focus.validate_region(0x8F7FFC00, 512)
        self.assertEqual(focus.validate_region(0x8F7FFC00, 504), 0x8F7FFC00)
        self.assertEqual(self.svc.reads, [])
        self.assertEqual(self.svc.writes, [])

    def test_exact_span_all_55_is_accepted_and_data_just_beyond_ignored(self):
        addr = 0x8F000000
        self.svc.put(addr + 20, b'\x00')
        with contextlib.redirect_stdout(io.StringIO()):
            focus.cmd_apply(self.pcm, 2, 1, addr)
        self.assertEqual(self.svc.get(addr, 16), focus.encode_header(1, 2))
        self.assertEqual(self.svc.get(addr + 16, 4), b'\x01\x00\xff\x7f')
        self.assertEqual(self.svc.get(addr + 20, 1), b'\x00')

    def test_stale_bytes_are_overwritten(self):
        addr = 0x8F000000
        self.svc.put(addr, b'stale data from an earlier boot')
        with contextlib.redirect_stdout(io.StringIO()):
            focus.cmd_apply(self.pcm, 2, 20, addr)
        self.assertEqual(self.svc.get(addr, 16), focus.encode_header(20, 2))
        self.assertEqual(self.svc.get(addr + 16, 4), b'\x01\x00\xff\x7f')

    def test_other_entry_header_refuses_before_any_write(self):
        addr = 0x8F000000
        self.svc.put(addr, focus.encode_header(5, 2))
        with self.assertRaises(focus.RegionNotFree) as raised:
            focus.cmd_apply(self.pcm, 2, 20, addr)
        self.assertEqual(str(raised.exception), 'region not free')
        self.assertEqual(raised.exception.address, '0x8F000000')
        self.assertEqual(self.svc.writes, [])
        self.assertTrue(self.svc.closed)
        # Firmware/table checks read first; the guard read of the span comes last.
        self.assertEqual(self.svc.reads[-1], addr)

    def test_same_owner_may_shrink_rewrite_or_grow(self):
        addr = 0x8F001000
        for old_samples in [1, 2, 10]:
            self.svc.put(addr, focus.encode_header(3, old_samples))
            self.svc.put(addr + 16, b'\xAA' * 40)
            with contextlib.redirect_stdout(io.StringIO()):
                focus.write_pcm(self.svc, self.pcm, 2, 3, addr)
            self.assertEqual(self.svc.get(addr, 16), focus.encode_header(3, 2))

    def test_other_index_header_refused_and_invalid_header_is_stale_data(self):
        addr = 0x8F001000
        self.svc.put(addr, focus.encode_header(2, 2))
        with self.assertRaises(focus.RegionNotFree):
            focus.write_pcm(self.svc, self.pcm, 2, 3, addr)
        self.assertEqual(self.svc.writes, [])
        for raw in [b'LMXTSLOT' + struct.pack('<II', 3, 0), b'LMXTSLOT' + struct.pack('<II', 3, 132301)]:
            self.svc.put(addr, raw)
            with contextlib.redirect_stdout(io.StringIO()):
                focus.write_pcm(self.svc, self.pcm, 2, 3, addr)
            self.assertEqual(self.svc.get(addr, 16), focus.encode_header(3, 2))

    def test_two_uploads_only_retarget_two_fields(self):
        for index, addr in [(1, 0x8F000000), (4, 0x8F000400)]:
            original = struct.pack('<8I', index, 0x06AA3180, 3, 4, 5, 14464, 7, 8)
            self.svc.put(focus.entry_addr(index), original)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                focus.cmd_apply(self.pcm, 2, index, addr)
            lines = output.getvalue().splitlines()
            self.assertEqual(lines[0], 'PROGRESS 2 2')
            self.assertTrue(json.loads(lines[-1])['ok'])
            expected = bytearray(original)
            struct.pack_into('<I', expected, 4, addr + 16 - 0x80000000)
            struct.pack_into('<I', expected, 0x14, 4)  # +0x14 is PCM bytes: 2 samples
            self.assertEqual(self.svc.get(focus.entry_addr(index), 32), expected)

    def test_read_failure_and_invalid_pcm_never_write(self):
        with self.assertRaises(RuntimeError):
            focus.write_pcm(self.svc, self.pcm, 3, 2, 0x8F000000)
        self.svc.exchange = lambda addr: b'bad frame'
        with self.assertRaises(RuntimeError):
            focus.write_pcm(self.svc, self.pcm, 2, 2, 0x8F000000)
        self.assertEqual(self.svc.writes, [])

    def test_restore_id_round_trips_saved_entry(self):
        raw = stock_entry(27, 0x06BB8500, 22400)
        self.svc.put(focus.entry_addr(27), stock_entry(27, 0x0F000010, 2))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            focus.cmd_restore_id(27, raw.hex())
        self.assertTrue(json.loads(output.getvalue())['ok'])
        self.assertEqual(self.svc.get(focus.entry_addr(27), 32), raw)
        self.assertEqual(len(self.svc.writes), 16)

    def cli(self, arguments):
        with patch.dict(sys.modules, {'s5svc': self.transport}), \
                patch.object(sys, 'argv', ['s5focus.py'] + arguments), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            runpy.run_path(focus.__file__, run_name='__main__')
        return output.getvalue().splitlines()

    def test_cli_region_error_is_one_json_line_and_no_writes(self):
        self.svc.put(0x8F000000, focus.encode_header(5, 2))  # owned by another entry
        lines = self.cli(['apply-slot', '20', self.pcm, '2', '0x8F000000'])
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {
            'ok': False, 'error': 'region not free', 'address': '0x8F000000',
        })
        self.assertEqual(self.svc.writes, [])

    def test_all_cli_apply_commands_require_explicit_region(self):
        for command in ['apply', 'apply-id', 'apply-slot']:
            arguments = [command] + ([] if command == 'apply' else ['1']) + [self.pcm, '2']
            lines = self.cli(arguments)
            self.assertEqual(len(lines), 1)
            self.assertFalse(json.loads(lines[0])['ok'])
            self.assertEqual(self.svc.writes, [])
        for command, index, addr in [('apply', 1, '0x8F000000'), ('apply-id', 4, '0x8F000400')]:
            arguments = [command] + ([] if command == 'apply' else [str(index)]) + [self.pcm, '2', addr]
            self.assertTrue(json.loads(self.cli(arguments)[-1])['ok'])
            self.assertEqual(self.svc.get(int(addr, 0), 16), focus.encode_header(index, 2))

    def test_scan_is_read_only_and_merges_runs(self):
        self.svc.put(0x8F000400, bytes(1024))
        self.svc.put(0x8F000800, focus.encode_header(1, 2))
        self.svc.put(0x8F000C00, b'X')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            focus.cmd_scan(0x8F000000, 5 * 1024)
        result = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual([r['kind'] for r in result['runs']],
                         ['free-0x55', 'zero', 'lumixtool', 'data', 'free-0x55'])
        self.assertEqual(self.svc.writes, [])
        self.assertTrue(self.svc.closed)
        self.assertEqual(output.getvalue().splitlines()[0], 'PROGRESS 5 5')


class FirmwareGateTest(unittest.TestCase):
    setUp = SlotTests.setUp
    cli = SlotTests.cli

    def assert_refused(self, args, message):
        before = list(self.svc.writes)
        lines = self.cli(args)
        result = json.loads(lines[-1])
        self.assertFalse(result['ok'])
        self.assertIn(message, result['error'])
        self.assertEqual(self.svc.writes, before)

    def test_unverified_body_version_blocks_every_write(self):
        self.svc.put(focus.VERSION_ADDR, struct.pack('<H', 0x0280))
        self.assert_refused(['apply-slot', '1', self.pcm, '2', '0x8F000000'], 'body version 0x0280')
        self.assert_refused(['restore'], 'body version 0x0280')
        self.assert_refused(['restore-id', '1', stock_entry(1).hex()], 'body version 0x0280')

    def test_unexpected_sound_table_blocks_writes(self):
        self.svc.put(focus.TBL + 5 * 32, stock_entry(9))
        self.assert_refused(['apply-slot', '1', self.pcm, '2', '0x8F000000'], 'entry 5 has id 9')
        self.svc.put(focus.TBL + 5 * 32, stock_entry(5, addr=0x12345678))
        self.assert_refused(['apply-slot', '1', self.pcm, '2', '0x8F000000'], 'unexpected address 0x12345678')

    def test_table_patched_by_older_builds_is_still_accepted(self):
        self.svc.put(focus.TBL + 32, stock_entry(1, addr=0x0B5B0110, samples=4))
        self.assertIsNone(focus.table_problem(self.svc.get(focus.TBL, 28 * 32)))

    def test_restore_id_only_accepts_stock_entries_for_that_index(self):
        with self.assertRaises(ValueError):
            focus.cmd_restore_id(1, stock_entry(2).hex())
        with self.assertRaises(ValueError):
            focus.cmd_restore_id(1, stock_entry(1, addr=0x0F000010).hex())
        self.assertEqual(self.svc.writes, [])

    def test_status_reports_whether_writing_is_allowed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            focus.cmd_status()
        self.assertTrue(json.loads(out.getvalue().splitlines()[-1])['verified'])
        self.svc.put(focus.VERSION_ADDR, struct.pack('<H', 0x0280))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            focus.cmd_status()
        result = json.loads(out.getvalue().splitlines()[-1])
        self.assertFalse(result['verified'])
        self.assertEqual(result['body_version'], '0x0280')


class StatusErrorTest(unittest.TestCase):
    def test_status_reports_why_the_device_could_not_be_opened(self):
        def refuse(**_kwargs):
            raise SystemExit("CreateFile failed for every 04DA:2370 instance")
        out = io.StringIO()
        with patch.object(focus, "protocol", return_value=types.SimpleNamespace(Service=refuse)), \
                contextlib.redirect_stdout(out):
            focus.cmd_status()
        result = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertFalse(result["connected"])
        self.assertIn("CreateFile failed", result["error"])


if __name__ == '__main__':
    unittest.main()
