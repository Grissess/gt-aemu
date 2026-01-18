import argparse
import time

import pyaudio
from py65.devices import mpu65c02
from py65 import disassembler
from py65.utils.devices import make_instruction_decorator

parser = argparse.ArgumentParser(description='Emulate the GameTank ACP')
parser.add_argument('rom', help='Path to ROM file to load')
parser.add_argument('-o', '--output', help='Instead of playing, write samples to named file (as 1-channel raw U8)')
parser.add_argument('-O', '--ram-output', help='When emulation ends, write the contents of RAM to this file')
parser.add_argument('-p', '--poke', action='append', default=[], help='Poke values (of form `addr=hexstring`) into memory after loading; can be specified more than once')
parser.add_argument('-@', '--at', action='append', default=[], help='Time pokes (of form `samples:addr=hexstring`); can be specified more than once')
parser.add_argument('--script', help='A poke-script--a file whose lines are structured as with -@ above')
parser.add_argument('-t', '--trace', action='store_true', help='Turn on tracing (VERY slow)')
parser.add_argument('-I', '--instructions', type=int, help='Run only up to this number of instructions')
parser.add_argument('-C', '--cycles', type=int, help='Run only up to this number of cycles')
parser.add_argument('-S', '--samples', type=int, help='Run only up to this number of samples')
parser.add_argument('-s', '--seconds', type=float, help='Run only up to this number of seconds')

class Memory:
    def __init__(self, backing, samp_cb):
        self.backing, self.samp_cb = backing, samp_cb
        
    def __getitem__(self, i):
        return self.backing[i % len(self.backing)]

    def __setitem__(self, i, v):
        if i & 0x8000:
            self.samp_cb(v)
        else:
            self.backing[i % len(self.backing)] = v

# XXX upstream forgot BBS/BBR
class MPU(mpu65c02.MPU):
    instruct = mpu65c02.MPU.instruct[:]
    cycletime = mpu65c02.MPU.cycletime[:]
    extracycles = mpu65c02.MPU.extracycles[:]
    disassemble = mpu65c02.MPU.disassemble[:]

    instruction = make_instruction_decorator(instruct, disassemble, cycletime, extracycles)

    def opBBx(self, msk, polarity):
        addr = self.ZeroPageAddr()
        self.pc += 1
        if bool(self.ByteAt(addr) & msk) == polarity:
            self.BranchRelAddr()
        else:
            self.pc += 1

    # TODO: find a way to metaprogram this
    @instruction(name='BBR0', mode='zpb', cycles=5, extracycles=1)
    def inst_0x0F(self):
        self.opBBx(0x01, False)
    @instruction(name='BBR1', mode='zpb', cycles=5, extracycles=1)
    def inst_0x1F(self):
        self.opBBx(0x02, False)
    @instruction(name='BBR2', mode='zpb', cycles=5, extracycles=1)
    def inst_0x2F(self):
        self.opBBx(0x04, False)
    @instruction(name='BBR3', mode='zpb', cycles=5, extracycles=1)
    def inst_0x3F(self):
        self.opBBx(0x08, False)
    @instruction(name='BBR4', mode='zpb', cycles=5, extracycles=1)
    def inst_0x4F(self):
        self.opBBx(0x10, False)
    @instruction(name='BBR5', mode='zpb', cycles=5, extracycles=1)
    def inst_0x5F(self):
        self.opBBx(0x20, False)
    @instruction(name='BBR6', mode='zpb', cycles=5, extracycles=1)
    def inst_0x6F(self):
        self.opBBx(0x40, False)
    @instruction(name='BBR7', mode='zpb', cycles=5, extracycles=1)
    def inst_0x7F(self):
        self.opBBx(0x80, False)
    @instruction(name='BBS0', mode='zpb', cycles=5, extracycles=1)
    def inst_0x8F(self):
        self.opBBx(0x01, True)
    @instruction(name='BBS1', mode='zpb', cycles=5, extracycles=1)
    def inst_0x9F(self):
        self.opBBx(0x02, True)
    @instruction(name='BBS2', mode='zpb', cycles=5, extracycles=1)
    def inst_0xAF(self):
        self.opBBx(0x04, True)
    @instruction(name='BBS3', mode='zpb', cycles=5, extracycles=1)
    def inst_0xBF(self):
        self.opBBx(0x08, True)
    @instruction(name='BBS4', mode='zpb', cycles=5, extracycles=1)
    def inst_0xCF(self):
        self.opBBx(0x10, True)
    @instruction(name='BBS5', mode='zpb', cycles=5, extracycles=1)
    def inst_0xDF(self):
        self.opBBx(0x20, True)
    @instruction(name='BBS6', mode='zpb', cycles=5, extracycles=1)
    def inst_0xEF(self):
        self.opBBx(0x40, True)
    @instruction(name='BBS7', mode='zpb', cycles=5, extracycles=1)
    def inst_0xFF(self):
        self.opBBx(0x80, True)

# XXX new addressing mode
class Disassembler(disassembler.Disassembler):
    def instruction_at(self, pc):
        insn = self._mpu.ByteAt(pc)
        mnemonic, mode = self._mpu.disassemble[insn]

        # handle our new mode
        if mode == 'zpb':
            zpa = self._mpu.ByteAt(pc+1)
            off = self._mpu.ByteAt(pc+2)
            rela = pc + 3
            if off & (1 << (self.byteWidth - 1)):
                rela -= (off ^ self.byteMask) + 1
            else:
                rela += off
            lbl = self._address_parser.label_for(rela, f'${self.addrFmt % rela}')
            return 3, f'{mnemonic} {self.byteFmt % zpa}, {lbl}'
        else:
            # defer
            return super().instruction_at(pc)

def main(args):
    with open(args.rom, 'rb') as f:
        buf = f.read(0x1000)
        if len(buf) < 0x1000:
            raise ValueError(f'ROM size {len(buf)} invalid; expected {0x1000} bytes')

    mem = Memory(bytearray(buf), None)
    for poke in args.poke:
        addr, _, val = poke.partition('=')
        addr, val = int(addr, 0), bytes.fromhex(val)
        for offset, byte in enumerate(val):
            mem[addr + offset] = byte
    dev = MPU(mem, None)
    dis = Disassembler(dev)

    samp = None
    def mcb(v):
        nonlocal samp
        samp = v
    mem.samp_cb = mcb

    if args.output:
        of = open(args.output, 'wb')
    else:
        pa = pyaudio.PyAudio()
        queue = []
        last_buffer = bytes(256).replace(b'\0', b'\x80')
        def scb(data, frames, tinfo, status):
            nonlocal last_buffer
            if not queue:
                print('UFLOW')
            else:
                last_buffer = queue.pop(0)
            return last_buffer, pyaudio.paContinue
        s = pa.open(format=pyaudio.paUInt8, channels=1, rate=44192, output=True, frames_per_buffer=256, stream_callback=scb)

    script = {}
    lines = []
    if args.script:
        with open(args.script) as f:
            lines = list(f)
    for arg in args.at + lines:
        scnt, _, poke = arg.partition(':')
        addr, _, val = poke.partition('=')
        scnt, addr, val = int(scnt, 0), int(addr, 0), bytes.fromhex(val)
        script.setdefault(scnt, []).append((addr, val))
    script = sorted(script.items(), key=lambda pair: pair[0])

    # do any 0-time pokes, often from the scriptfile
    while script and 0 >= script[0][0]:
        scnt, pokes = script.pop(0)
        for addr, val in pokes:
            for offset, byte in enumerate(val):
                mem[addr + offset] = byte

    buf = bytearray(256)
    bix = 0

    samp_insns = 0
    last_cyc = dev.processorCycles
    total_insns = 0
    total_samps = 0
    dl = 324
    insn_rate = []
    cycle_rate = []
    samp_rate = []
    last_samp = time.perf_counter()
    last_status = time.perf_counter()
    while True:
        samp_insns += 1
        total_insns += 1
        if (
                (args.instructions is not None and total_insns > args.instructions)
                or
                (args.cycles is not None and dev.processorCycles > args.cycles)
        ):
            print('Break.')
            break
        if args.trace:
            ln, ex = dis.instruction_at(dev.pc)
            print(f'A={dev.a:02x} X={dev.x:02x} Y={dev.y:02x} S={dev.sp:02x} PC={dev.pc:04x}: {bytes(dev.memory[i] for i in range(dev.pc, dev.pc + ln)).hex().upper():8} {ex}')
        dev.step()
        if dev.waiting:
            if args.trace:
                print('IRQ')
            dev.irq()
            dev.waiting = False  # XXX upstream bug
        if samp is not None:
            if args.trace:
                print('SAMP', hex(samp))
            insn_rate.append(samp_insns)
            samp_insns = 0

            cycle_rate.append(dev.processorCycles - last_cyc)
            last_cyc = dev.processorCycles

            now = time.perf_counter()
            samp_rate.append(now - last_samp)
            last_samp = now

            buf[bix] = samp
            samp = None
            bix += 1
            if bix >= len(buf):
                if args.output:
                    of.write(buf)
                else:
                    if len(queue) > 128:
                        print('OFLOW')
                        while True:
                            if len(queue) < 64:
                                break
                            time.sleep(0.05)
                    queue.append(bytes(buf))
                bix = 0
                total_samps += len(buf)
                if (
                        (args.samples is not None and total_samps > args.samples)
                        or
                        (args.seconds is not None and total_samps / 44192 > args.seconds)
                ):
                    print('Break.')
                    break

                term = False
                while script and total_samps >= script[0][0]:
                    scnt, pokes = script.pop(0)
                    for addr, val in pokes:
                        if addr == 0 and not val:
                            term = True
                            break
                        for offset, byte in enumerate(val):
                            mem[addr + offset] = byte
                if term:
                    print('Break (script).')
                    break

            if now > last_status + 1:
                srav = len(samp_rate)/sum(samp_rate)
                crav = sum(cycle_rate)/len(cycle_rate)
                load = crav / dl
                print(f'IPS avg {sum(insn_rate)/len(insn_rate)} min {min(insn_rate)} max {max(insn_rate)}\nCPS avg {crav} min {min(cycle_rate)} max {max(cycle_rate)} load {load}{"(!)" if load > 1 else ""}\nS/s {srav} RT {srav/44192} Dur: {total_samps / 44192}s')
                del samp_rate[:]
                del cycle_rate[:]
                del insn_rate[:]
                last_status = now
    print(f'Exiting after {dev.processorCycles} cycles, {total_insns} instructions, {total_samps} samples ({total_samps / 44192}s).')
    if args.ram_output:
        open(args.ram_output, 'wb').write(bytes(mem.backing))
        print('RAM written.')

if __name__ == '__main__':
    main(parser.parse_args())
