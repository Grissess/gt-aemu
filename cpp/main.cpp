#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <sstream>
#include <charconv>
#include <exception>
#include <algorithm>
#include <iomanip>
#include <limits>

#include "mos6502/mos6502.h"

using namespace std;

/* the emulator we're using doesn't have context, so we're leaving this as global state */
class end_emulation : public exception {
	const char *what() const noexcept {
		return "end_emulation";
	}
};

uint32_t samples = 0;
void sample_callback(uint8_t);

constexpr size_t au_ram_size = 0x1000;
uint8_t au_ram[au_ram_size];
uint8_t au_ram_read(uint16_t addr) {
	return au_ram[addr % au_ram_size];
}
void au_ram_write(uint16_t addr, uint8_t data) {
	au_ram[addr % au_ram_size] = data;
	if(addr == 0x8000) {
		sample_callback(data);
	}
}
void au_stopped(void) {
	cerr << "CPU Halt." << endl;
}

struct ScriptEntry {
	uint32_t sample_count;
	uint16_t address;
	vector<uint8_t> data;
};
ostream &operator<<(ostream &os, const ScriptEntry &se) {
	os << hex << "0x" << se.sample_count << ":" <<
		"0x" << se.address << "=" << setw(2) << setfill('0');
	for(const uint8_t &byte: se.data)
		os << (unsigned int)byte;
	os << setw(0) << dec;
	return os;
}
vector<ScriptEntry> script;
size_t script_ptr = 0;

void run_current_script() {
	while(script_ptr < script.size()) {
		ScriptEntry &ent = script[script_ptr];
		if(ent.sample_count > samples) return;
		// cerr << "Running SE " << script_ptr << ": " << ent << endl;
		script_ptr++;
		if(ent.data.size() == 0) {
			if(ent.address == 0)
				throw end_emulation();
		} else {
			uint16_t addr = ent.address;
			for(const uint8_t &datum : ent.data)
				au_ram_write(addr++, datum);
		}
	}
}

void sample_callback(uint8_t sample) {
	cout.put(sample);
	samples++;
	run_current_script();
}

ostream &operator<<(ostream &os, const mos6502 &cpu) {
	os << setw(2) << setfill('0') << hex <<
		"A=" << cpu.A << " X=" << cpu.X << " Y=" << cpu.Y <<
		" sp=" << cpu.sp << setw(4) << " pc=" << cpu.pc <<
		setw(2) << " st=" << cpu.status <<
		" freeze=" << cpu.freeze << " waiting=" << cpu.waiting <<
		" illegal=" << cpu.illegalOpcode << setw(4) << " ilsrc=" << cpu.illegalOpcodeSrc <<
		dec << setw(0);
	return os;
}


int main(int argc, char **argv) {
	if(argc < 3) {
		const char *progname = argc >= 1 ? argv[0] : "emu";
		cerr << "usage: " << progname << " romfile scriptfile" << endl;
		return 1;
	}

	{
		ifstream romfile(argv[1]);
		romfile.read(reinterpret_cast<char *>(au_ram), au_ram_size);
		if(romfile.gcount() < au_ram_size) {
			cerr << "romfile: not enough bytes read; got " << romfile.gcount() << ", needed " << au_ram_size << endl;
			return 2;
		}
	}

	{
		ifstream scriptfile(argv[2]);
		string line, part;
		while(getline(scriptfile, line)) {
			ScriptEntry sent;
			istringstream ss(line);

			// FIXME: from_chars doesn't handle 0x prefices with base=0 very well
			getline(ss, part, ':');
			sent.sample_count = strtoul(part.c_str(), NULL, 0);
			getline(ss, part, '=');
			sent.address = strtoul(part.c_str(), NULL, 0);

			part = string(istreambuf_iterator<char>(ss), istreambuf_iterator<char>());
			sent.data.reserve(part.size() / 2);
			for(size_t i = 0; i < part.size(); i += 2) {
				uint8_t byte;
				from_chars(part.data() + i, part.data() + i + 2, byte, 16);
				sent.data.push_back(byte);
			}
			// cerr << "SE: line " << line << " -> " << sent << endl;
			script.push_back(sent);
		}
		sort(script.begin(), script.end(), [](const ScriptEntry &a, const ScriptEntry &b) {
			return a.sample_count < b.sample_count;
		});
		cerr << "Read " << script.size() << " script entries" << endl;
	}
	run_current_script();  // synchronize sample_count == 0 entries

	mos6502 cpu(au_ram_read, au_ram_write, au_stopped);
	uint64_t cycle_count = 0;
	try {
		while(true) {
			cpu.Run(numeric_limits<int32_t>::max(), cycle_count);
			if(cpu.waiting) {
				cpu.IRQ();
				cpu.ClearIRQ();
			}
		}
	} catch(exception *e) {
		cerr << "Terminating due to exception: " << e->what() << endl;
	}
	cerr << "Ran " << cycle_count << " cycles: " << cpu << endl;

	return 0;
}
