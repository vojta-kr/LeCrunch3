"""Waveform decoding against a synthetic `C1:WF? ALL` reply built from the module's own descriptor template."""

import struct

import numpy as np

from LeCrunch3.LeCrunch3 import String, TimeStamp, UnitDefinition, wavedesc_template, wavedesclength

from test_transport import OK, Peer, vicp


def wavedesc(**values):
    """A little-endian WAVEDESC block with every field zero except `values` and the names."""
    block = bytearray(wavedesclength)
    for name, pos, datatype in wavedesc_template:
        if datatype is String:
            text = {'descriptor_name': b'WAVEDESC', 'template_name': b'LECROY_2_3'}.get(name, b'')
            block[pos:pos + 16] = text.ljust(16, b'\x00')
        elif datatype is UnitDefinition:
            pass
        elif datatype is TimeStamp:
            struct.pack_into('<' + datatype.packfmt, block, pos, 0.0, 0, 0, 0, 0, 0, 0)
        else:
            struct.pack_into('<' + datatype.packfmt, block, pos, values.get(name, 0))
    return bytes(block)


def test_sequence_mode_trigger_arrays_and_samples():
    times = [0.0, 1.5e-6, 3.25e-6]
    offsets = [-2e-9, 1e-9, 0.0]
    samples = np.arange(-6, 6, dtype='i1')  # 3 segments x 4 points
    desc = wavedesc(comm_type=0, wave_descriptor=wavedesclength, trigtime_array=16 * len(times),
                    wave_array_1=len(samples), wave_array_count=len(samples), subarray_count=len(times))
    trig = b''.join(struct.pack('<dd', t, o) for t, o in zip(times, offsets))
    body = desc + trig + samples.tobytes()
    reply = b'C1:WF ALL,#9%09d' % len(body) + body

    scope = Peer([OK, OK, vicp(reply)]).scope()
    wavedesc_out, trigger_times, trigger_offsets, waveform = scope.get_waveform_all(1)

    assert wavedesc_out['subarray_count'] == 3
    np.testing.assert_array_equal(trigger_times, times)
    np.testing.assert_array_equal(trigger_offsets, offsets)
    np.testing.assert_array_equal(waveform, samples)
