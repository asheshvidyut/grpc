#!/bin/bash
# Script to use glibc's mtrace for memory leak detection

set -e

echo "=========================================="
echo "Memory Leak Debugging with mtrace (glibc)"
echo "=========================================="
echo ""

# Set mtrace output file
export MALLOC_TRACE=/tmp/mtrace.log

# Clean up any existing trace file
rm -f $MALLOC_TRACE

echo "MALLOC_TRACE set to: $MALLOC_TRACE"
echo ""

# Create a wrapper script that enables mtrace
cat > /tmp/run_with_mtrace.py << 'EOF'
import mtrace
import sys

# Start tracing
mtrace.trace()

# Import and run the actual script
import debug_memory_leak
debug_memory_leak.main()
EOF

# Run the script
python3 /tmp/run_with_mtrace.py

echo ""
echo "=========================================="
echo "mtrace output saved to: $MALLOC_TRACE"
echo "=========================================="
echo ""
echo "To analyze the trace:"
echo "  mtrace python3 $MALLOC_TRACE"
echo ""
echo "Or use the mtrace tool:"
echo "  mtrace python3 $MALLOC_TRACE | less"

