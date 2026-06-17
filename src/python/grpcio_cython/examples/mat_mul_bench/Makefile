UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    TARGET = matmul_handler.dylib
    SHARED_FLAGS = -dynamiclib -undefined dynamic_lookup
else
    TARGET = matmul_handler.so
    SHARED_FLAGS = -shared -fPIC
endif

all: $(TARGET)

$(TARGET): matmul_handler.c
	gcc $(SHARED_FLAGS) -O3 -o $(TARGET) matmul_handler.c

clean:
	rm -f $(TARGET)
