UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    TARGET = echo_handler.dylib
    SHARED_FLAGS = -dynamiclib -undefined dynamic_lookup
else
    TARGET = echo_handler.so
    SHARED_FLAGS = -shared -fPIC
endif

all: $(TARGET)

$(TARGET): echo_handler.c
	gcc $(SHARED_FLAGS) -O3 -o $(TARGET) echo_handler.c

clean:
	rm -f $(TARGET)
