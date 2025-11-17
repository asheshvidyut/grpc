#!/bin/bash
# Script to run memory leak debugging with valgrind

set -e

echo "=========================================="
echo "Memory Leak Debugging with Valgrind"
echo "=========================================="
echo ""

# Check if valgrind is installed
if ! command -v valgrind &> /dev/null; then
    echo "ERROR: valgrind is not installed."
    echo "Install with: sudo apt-get install valgrind"
    exit 1
fi

# Check if Python debug symbols are available
echo "Note: For best results, use a Python build with debug symbols."
echo ""

# Run with valgrind
valgrind \
    --leak-check=full \
    --show-leak-kinds=all \
    --track-origins=yes \
    --verbose \
    --log-file=valgrind_output.log \
    --suppressions=/usr/share/valgrind/python.supp \
    python3 debug_memory_leak.py

echo ""
echo "=========================================="
echo "Valgrind output saved to: valgrind_output.log"
echo "=========================================="
echo ""
echo "To view the output:"
echo "  cat valgrind_output.log | less"
echo ""
echo "Key sections to look for:"
echo "  - 'definitely lost' - memory leaks"
echo "  - 'indirectly lost' - leaks through pointers"
echo "  - 'possibly lost' - potential leaks"
echo "  - 'still reachable' - memory not freed but still accessible"

