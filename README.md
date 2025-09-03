# gt-aemu

A little emulator for the GameTank ACP, with a focus on debugging.

Here are the arguments as of this writing:

```
usage: emu.py [-h] [-o OUTPUT] [-O RAM_OUTPUT] [-p POKE] [-@ AT] [--script SCRIPT] [-t] [-I INSTRUCTIONS] [-C CYCLES] [-S SAMPLES] [-s SECONDS] rom

Emulate the GameTank ACP

positional arguments:
  rom                   Path to ROM file to load

options:
  -h, --help            show this help message and exit
  -o, --output OUTPUT   Instead of playing, write samples to named file (as 1-channel raw U8)
  -O, --ram-output RAM_OUTPUT
                        When emulation ends, write the contents of RAM to this file
  -p, --poke POKE       Poke values (of form `addr=hexstring`) into memory after loading; can be specified more than once
  -@, --at AT           Time pokes (of form `samples:addr=hexstring`); can be specified more than once
  --script SCRIPT       A poke-script--a file whose lines are structured as with -@ above
  -t, --trace           Turn on tracing (VERY slow)
  -I, --instructions INSTRUCTIONS
                        Run only up to this number of instructions
  -C, --cycles CYCLES   Run only up to this number of cycles
  -S, --samples SAMPLES
                        Run only up to this number of samples
  -s, --seconds SECONDS
                        Run only up to this number of seconds
```

## Getting Started

I'll assume some familiarity with the terminal and the shell. Many parts (e.g.
paths) can be changed without issue, but the instructions below should suffice
for beginners. You'll need `git` and `python3`, often widely available in
package managers; getting them is outside the scope. Windows users are welcome
to try from WSL, although this environment is not tested.

1. Get this repository and enter it.

```
git clone https://github.com/Grissess/gt-aemu.git
cd gt-aemu
```

2. Make a virtual environment (`venv`) and install dependencies. This may need
   separate packages to be installed as well, such as `python3-venv` and
   `python3-pip`; check your package manager for more details.

```
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

## Usage

You'll need an audio firmware; for example, the [gametank_sdk][gtsdk] puts such
a ROM by default into `build/assets/audio_fw.bin`. You'll also need to know
enough about the firmware to know how to "drive" it; presumably you'll want to
poke values into the memory space of the running ACP. There are two ways of
specifying these loads:

- `-p`, `--poke`: given `0x12=ABCDEF`, initially (after ROM load) sets
  `0x12=0xAB`, `0x13=0xCD`, `0x14=0xEF`, etc.
- `-@`, `--at`: given `0x3000:0x12=ABCDEF`, does exactly the same as above, but
  only after (approximately) `0x3000` audio samples have passed. Thus you can
  "animate" the values in memory.

At present, pokes are treated as instantaneous.

> [!NOTE]
> Some firmwares wire the NMI to a fast RAM copy loop, since the ACP runs
> faster than the main processor and this allows for more precise triggering.
> You can ignore those considerations here--just poke straight into the
> underlying RAM values.

If you have _many_ loads you want to do, it's usually better to pass them as a
`--script`. The format for a "scriptfile" or "pokescript" is exactly the same
as for the `-@`, `--at` parameter, with one such entry on each line. Loads
specified with `-@`, `--at` and `--script` together are combined.

It's _much better_ at the moment to write offline to a file, since Python isn't
fast. When you do, you need to define any of these stop conditions:

- `-I`, `--instructions`: Stop after this many instructions.
- `-C`, `--cycles`: Stop after this many cycles.
- `-S`, `--samples`: Stop after this many samples have been emitted.
- `-s`, `--seconds`: Stop after this many seconds worth of audio have been emitted.

The emulator can also be told to stop by being instructed to `-@`, `--at`-poke
an empty bytestring to address `0`. This is useful for scriptfile generators,
which may have better knowledge of when output should cease.

The file to be written is specified with `-o` or `--output`. It will contain
"raw" unsigned 8-bit, one-channel samples, exactly as would be fed into the
DAC. At present, the sample-rate is hard-coded to 44192Hz. (On Linux with ALSA,
an example to play the output would be `aplay -f U8 -c 1 -r 44192 output`. You
can also load it into Audacity with the "raw import" tool.)

Finally, tracing can be enabled with `-t`, `--trace`, but this will make the
emulator _much_ slower. It's very useful for debugging audio ROMs, however.

During generation, lines of this sort will occasionally be output:

```
IPS avg 44.30337383748557 min 43 max 58
CPS avg 155.73633833412532 min 152 max 195 load 0.4806677109077942
S/s 14730.72705246874 RT 0.3333346997752702
```

The fields are as follows:
- `IPS` (Instructions Per Sample): statistics about the number of instructions
  retired between samples.
- `CPS` (Cycles Per Sample): statistics about the number of processor cycles
  clocked between samples.
  - `load`: the ratio between the average CPS and the "deadline"--the number of
    cycles between IRQs in the current mode. If this is >1, real hardware will
    probably experience glitches/stutters.
- `S/s` (Samples per second): how fast the _emulator_ is generating samples.
 - `RT` (Real-Time ratio): ratio between S/s and the sample rate. If this is
   <1, the emulator will probably underflow trying to play samples in
   real-time--writing to a file instead is recommended in such cases.

Statistics are sampled at each sample, with the sampling window being since the
last info line was generated (or the beginning of the emulation). This window
is important to keep in mind when debugging "rare" glitches.

[gtsdk]: https://github.com/clydeshaffer/gametank_sdk

## Caveats

At present, the emulator sends an IRQ whenever `WAI` is issued, on the
assumption that a firmware that is `WAI`ting is ready for an interrupt. This
leads to a couple of non-authentic behaviors:

1. Programs can spend as much time as they'd like making another sample,
   including overrunning a number of hard deadlines. This is perfectly fine for
   profiling and optimizing, but don't expect the hardware to be as lenient.

2. Firmware that doesn't `WAI` (instead, e.g., busy looping) will never be
   interrupted. Since such firmwares can't be scheduled, they won't work with
   this emulator.

Right now, the sample rate is 44192. This is apparently on the upper end of
feasibility for this platform; most firmwares expect to run somewhere near the
lowest sample rate, around 13983Hz. I want to make this an option, but that
would require finding out how [this table][audio] is generated, so the
parameters can be adjusted.

## Contributing

PRs and issues are welcome! I'll get around to them when I can. Besides that,
feel free to incorporate this project into your own. (A proper license is
forthcoming.)
