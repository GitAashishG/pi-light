CXX ?= c++
ROOT := $(abspath ../..)
OUT := $(ROOT)/firmware/build/native/test-core
CXXFLAGS := -std=c++14 -Wall -Wextra -Werror -pedantic -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer

.PHONY: test

test: $(OUT)
	$(OUT)
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -p 'test_header.py'

$(OUT): test_core.cpp $(ROOT)/firmware/src/light_core.cpp $(ROOT)/firmware/src/light_core.h
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -I$(ROOT)/firmware/src test_core.cpp $(ROOT)/firmware/src/light_core.cpp -o $@
