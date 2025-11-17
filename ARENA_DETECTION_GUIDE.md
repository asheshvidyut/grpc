# How to Detect Which Memory Arena is Leaking

## Overview

Memory leaks can occur in different arenas:
1. **pymalloc arenas** (Python's default allocator)
2. **glibc malloc arenas** (system malloc)
3. **Thread-local arenas** (per-thread malloc)

## Tools Created

### 1. `detect_arena_leak.py` - General Arena Detection

**Purpose**: Identify which allocator is being used and track arena growth.

**What it shows**:
- Which allocator (pymalloc vs system malloc)
- RSS growth vs Python object growth
- Heap map count (number of arenas)
- Total heap size growth

**Run**:
```bash
python3 detect_arena_leak.py
```

**Output**:
```
Allocator: pymalloc
RSS: +50.23 MB
Heap: +48.12 MB
Python objects: +5
Heap maps: +2
```

**Interpretation**:
- If RSS grows but objects don't → Memory in arenas
- If heap maps increase → New arenas created
- If allocator is pymalloc → Can't release memory

### 2. `detect_thread_arenas.py` - Thread-Local Arena Detection

**Purpose**: Detect thread-local malloc arenas using glibc's `mallinfo2()`.

**What it shows**:
- Arena size per thread
- Used vs free memory in arenas
- Releasable memory (that `malloc_trim()` could free)
- Per-thread allocation patterns

**Run**:
```bash
PYTHONMALLOC=malloc python3 detect_thread_arenas.py
```

**Output**:
```
Arena: +25.45 MB
Used: +10.23 MB
Free: +15.22 MB
Releasable: 12.34 MB
```

**Interpretation**:
- If "Releasable" is high → `malloc_trim()` could free it
- If "Free" grows → Memory freed but not released to OS
- If arena grows per thread → Thread-local arenas being created

## Detection Methods

### Method 1: Check Allocator

```python
import os
python_malloc = os.environ.get('PYTHONMALLOC', '')
if python_malloc == '':
    print("Using pymalloc - can't release memory")
elif python_malloc == 'malloc':
    print("Using system malloc - can use malloc_trim()")
```

### Method 2: Compare RSS vs Python Objects

```python
import psutil
import gc

rss_mb = psutil.Process().memory_info().rss / 1024 ** 2
python_objects = len(gc.get_objects())

# If RSS is high but objects are low → Memory in arenas
```

### Method 3: Check Memory Maps

```bash
cat /proc/self/maps | grep heap
```

**What to look for**:
- Multiple `[heap]` entries → Multiple arenas
- Growing heap size → Arenas growing
- Anonymous mappings → Likely arenas

### Method 4: Use glibc's mallinfo2()

```python
import ctypes

libc = ctypes.CDLL('libc.so.6')
info = libc.mallinfo2()

print(f"Arena: {info.arena / 1024**2} MB")
print(f"Free: {info.fordblks / 1024**2} MB")
print(f"Releasable: {info.keepcost / 1024**2} MB")
```

**Interpretation**:
- High "Releasable" → `malloc_trim()` can free it
- High "Free" → Memory freed but not released

### Method 5: Track Per-Thread Allocations

```python
import threading

def worker():
    # Allocate memory in this thread
    data = b'x' * (10 * 1024 * 1024)
    # Memory goes into this thread's arena
    del data

# Each thread gets its own arena
for i in range(10):
    t = threading.Thread(target=worker)
    t.start()
    t.join()
```

**What happens**:
- Each thread may create its own arena
- Memory allocated in thread stays in that thread's arena
- `malloc_trim()` from main thread can't trim thread arenas

## Diagnosis Flowchart

```
Is PYTHONMALLOC=malloc set?
├─ No → Using pymalloc
│   └─ pymalloc keeps arenas (can't release)
│   └─ Solution: Set PYTHONMALLOC=malloc
│
└─ Yes → Using system malloc
    ├─ Is RSS growing?
    │   ├─ No → No leak! ✅
    │   └─ Yes → Check mallinfo2()
    │       ├─ High "Releasable" → malloc_trim() can fix it
    │       └─ High "Free" → Memory in arenas not released
    │           └─ Are threads being used?
    │               ├─ Yes → Thread-local arenas
    │               │   └─ Solution: Call malloc_trim() from threads
    │               └─ No → Main arena
    │                   └─ Solution: Call malloc_trim() from main thread
```

## Quick Detection Script

```bash
# Check allocator
python3 -c "import os; print('Allocator:', os.environ.get('PYTHONMALLOC', 'pymalloc'))"

# Check RSS growth
python3 verify_arena_leak.py

# Check thread arenas (requires PYTHONMALLOC=malloc)
PYTHONMALLOC=malloc python3 detect_thread_arenas.py
```

## Common Scenarios

### Scenario 1: pymalloc Leak

**Symptoms**:
- `PYTHONMALLOC` not set (using pymalloc)
- RSS grows continuously
- Python objects are freed
- Heap maps increase

**Solution**: Set `PYTHONMALLOC=malloc`

### Scenario 2: Thread-Local Arena Leak

**Symptoms**:
- `PYTHONMALLOC=malloc` set
- RSS grows when using threads
- `mallinfo2()` shows high "Releasable"
- `malloc_trim()` from main thread doesn't help

**Solution**: Call `malloc_trim()` from each thread

### Scenario 3: Main Arena Leak

**Symptoms**:
- `PYTHONMALLOC=malloc` set
- RSS grows even without threads
- `mallinfo2()` shows high "Releasable"
- `malloc_trim()` from main thread helps

**Solution**: Call `malloc_trim()` periodically

## Next Steps

1. **Run `detect_arena_leak.py`** to identify allocator
2. **Run `detect_thread_arenas.py`** (if using system malloc) to check thread arenas
3. **Check memory maps** to see arena count
4. **Compare RSS vs Python objects** to confirm arena leak

