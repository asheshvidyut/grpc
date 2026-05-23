# Build the echo_c native handler shared library.
#
#   $ make
#   $ python3 echo_server.py &
#   $ python3 echo_client.py

UNAME_S := $(shell uname -s)

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -fPIC -std=c11
INCLUDE  = -I../../include

ifeq ($(UNAME_S),Darwin)
  LDFLAGS = -dynamiclib
  TARGET  = echo_handler.dylib
else
  LDFLAGS = -shared
  TARGET  = echo_handler.so
endif

all: $(TARGET)

$(TARGET): echo.c ../../include/grpcio_native/handler.h
	$(CC) $(CFLAGS) $(INCLUDE) $(LDFLAGS) -o $@ echo.c

clean:
	rm -f $(TARGET) echo_handler.so echo_handler.dylib

.PHONY: all clean
