# Purpose of Each Detection Script

## Overview

You have **3 scripts** for detecting and analyzing memory leaks. Each serves a different purpose:

## 1. `detect_leaking_objects.py` ⭐ **Primary Detection Tool**

**Purpose**: Track which Python objects are leaking over multiple iterations.

**What it does**:
- Takes snapshots before/after each iteration
- Tracks all gRPC objects created
- Identifies which objects persist after `close()`
- Shows object growth patterns over time
- **Best for**: Finding IF objects are leaking and WHICH types

**Output**:
- Lists all new gRPC objects created each iteration
- Shows which channels leaked
- Final summary of all leaked objects

**When to use**:
- **First step** - Run this to see if there's a leak
- When you want to see the big picture over many iterations
- To identify which object types are accumulating

**Example output**:
```
⚠️  LEAKED CHANNELS:
  Channel 94300444498576: refcount=3, created at snapshot 10
```

---

## 2. `analyze_channel_leak.py` 🔍 **Deep Reference Analysis**

**Purpose**: Find **exactly what's holding** a leaked channel object.

**What it does**:
- Finds all objects that reference a leaked channel
- Shows detailed information about each reference:
  - If it's in a list: which index, what else is in the list
  - If it's in a dict: which key, what other keys exist
  - If it's an attribute: which attribute name
- Traces reference chains (what holds the holder)
- Checks for ChannelCache

**Output**:
- Detailed breakdown of each reference
- Reference chains showing the full path
- Information about lists/dicts containing the channel

**When to use**:
- **After** `detect_leaking_objects.py` finds a leak
- When you need to know **WHY** a channel isn't being freed
- To find the root cause of the leak

**Example output**:
```
Channel 94300444498576 is referenced by 2 objects:

  Reference 94300412345678:
    Type: list
    Module: builtins
    List length: 5
    Contains channel at index: [2]
    First few items: ['Channel', 'Channel', 'Channel', ...]
    
  Reference 94300487654321:
    Type: ChannelCache
    Module: grpc._simple_stubs
    Has __dict__: ['_mapping', '_lock', ...]
    Channel stored in attribute: _mapping
```

---

## 3. `find_channel_references.py` 🔗 **Recursive Reference Tracker**

**Purpose**: Recursively trace reference chains to find the ultimate holder.

**What it does**:
- Similar to `analyze_channel_leak.py` but with **recursive depth tracking**
- Follows references of references (up to max_depth)
- Shows the full chain: Channel → List → Dict → Module → ...
- Helps find indirect references

**Output**:
- Reference chains with depth indicators
- Shows how deep the reference goes
- Multiple paths to the same object

**When to use**:
- When `analyze_channel_leak.py` shows references but you need to go deeper
- To find indirect references (A holds B, B holds C, C holds Channel)
- When debugging complex reference cycles

**Example output**:
```
Channel 94300444498576 is referenced by 1 objects:

  Reference 94300412345678:
    Type: list
    This reference is held by 1 objects:
      - dict: {'cache_key': <ChannelCache>}
        This reference is held by 1 objects:
          - ChannelCache: <grpc._simple_stubs.ChannelCache>
```

---

## Workflow: How to Use Them

### Step 1: Detect the Leak
```bash
python3 detect_leaking_objects.py > leak_report.txt
```
**Question**: Are objects leaking? Which ones?

### Step 2: Analyze the Leak
```bash
python3 analyze_channel_leak.py > reference_analysis.txt
```
**Question**: What's holding the leaked objects?

### Step 3: Deep Dive (if needed)
```bash
python3 find_channel_references.py > reference_chains.txt
```
**Question**: What's the full reference chain?

---

## Key Differences

| Feature | detect_leaking_objects.py | analyze_channel_leak.py | find_channel_references.py |
|---------|-------------------------|------------------------|---------------------------|
| **Purpose** | Find IF objects leak | Find WHAT holds them | Find REFERENCE CHAINS |
| **Iterations** | 50 (configurable) | 3-5 (quick test) | 3-5 (quick test) |
| **Output Detail** | Summary + leaks | Detailed references | Recursive chains |
| **Best For** | Initial detection | Root cause analysis | Complex debugging |
| **Reference Depth** | 1 level | 1-2 levels | 3+ levels (recursive) |

---

## Based on Your Results

From your `detect_leaking_objects.py` output, you found:
- ✅ Most channels ARE freed (4/5)
- ⚠️ One channel persists (iteration 5)
- ⚠️ Some gRPC objects persist (Channel, _ChannelState, etc.)
- They're referenced by a "list"

**Next step**: Run `analyze_channel_leak.py` to find:
- **Which list** is holding them
- **What else** is in that list
- **Why** that list isn't being cleared

This will tell you if it's:
- A gRPC internal cache (like ChannelCache)
- A Python GC issue (delayed cleanup)
- A reference cycle
- Something else

