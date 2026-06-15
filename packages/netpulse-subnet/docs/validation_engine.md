# Subnet Validation & Overlap Engine

The **Overlap Validation Engine** is a high-performance system within `netpulse-subnet` designed to identify routing conflicts across massive network architectures. 

When network engineers merge infrastructure or plan new VLAN architectures, ensuring that dozens or hundreds of subnets do not mathematically intersect is critical to prevent routing loops and IP fragmentation.

## The Problem with Brute Force
A naive approach to overlap detection compares every subnet against every other subnet in a list. This creates a nested loop with an exponential time complexity of $O(N^2)$. While acceptable for 10 subnets, attempting to validate 100,000 subnets would result in **10 billion comparisons**, causing severe performance degradation.

## Our Approach: The Line-Sweep Algorithm

`netpulse-subnet` utilizes an incredibly efficient `O(N log N)` "Line-Sweep" interval algorithm to detect clashes mathematically.

### 1. Integer Base Normalization
IP Addresses are fundamentally 32-bit (IPv4) or 128-bit (IPv6) integers. 
The engine first converts every provided CIDR string into an integer interval bounds:
`[Network_Address, Broadcast_Address]`

For example, `192.168.1.0/24` translates to the integer range `[3232235776, 3232236031]`.

### 2. Lexicographical Sorting
The subnets are then strictly sorted in ascending order by their base integer `Network_Address`.
Because the arrays are sorted, we guarantee that any subnet further down the list *cannot* start before the current subnet.

### 3. Linear Sweep
The engine iterates through the sorted array exactly once (`O(N)`). 
It maintains a pointer to the "current maximum broadcast extent". If the next subnet's start address falls mathematically before or directly on the current maximum broadcast address, **an overlap is definitively caught**.

This algorithm scales effortlessly, allowing validation of enterprise-scale address tables in fractions of a millisecond.

## Free Space Calculation

Often, engineers don't just want to know if their subnets overlap—they want to know exactly what unallocated blocks are remaining inside their parent network.

If a `--parent` CIDR block is provided, `netpulse-subnet` calculates this using Address Exclusion:
1. **Subnet Verification**: It first filters the array to ensure the user's subnets mathematically belong inside the `parent_network`.
2. **Block Collapse**: It utilizes `ipaddress.collapse_addresses()` to aggressively merge contiguous allocated blocks into their smallest possible supernets.
3. **Subtraction Pool**: Starting with the parent network as the only "free pool", it recursively iterates through the collapsed blocks, calling `.address_exclude()` to subtract the used blocks from the free pool.
4. **Result**: A highly fragmented free pool is sorted and returned, allowing engineers to instantly see exactly which `/24` or `/26` blocks are safe to use for their next deployment.
