all: emu
.PHONY: all
emu: main.o mos6502/mos6502.o
	$(CXX) $(LDFLAGS) -o $@ $^
