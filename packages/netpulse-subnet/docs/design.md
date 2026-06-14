# Design Philosophy & Algorithms

## Separation of Concerns
The business logic within `netpulse-subnet` is intentionally decoupled from `netpulse-core`. Subnet calculations do not require persistent database states, rust-level packet injection, or network discovery sweeps. By isolating it, we allow network engineers to use this library purely as an offline Subnet Calculator and VLSM Planner script without requiring root privileges.

## Fixed-Length Subnet Masking (FLSM)

The `split_fixed_length` algorithm allows operators to partition a large parent network into smaller, equal-sized chunks. It operates in two modes:
1. **By Subnet Count**: Given a target number of subnets, it finds the smallest power of 2 that accommodates that count, increments the prefix length, and generates the blocks.
2. **By Host Count**: Given a target number of hosts per subnet, it calculates the required host bits `h` where `2^h - 2 >= hosts`, calculates the new prefix length `32 - h`, and generates the blocks.

## Variable-Length Subnet Masking (VLSM)

The `allocate_vlsm` algorithm provides highly efficient address space utilization by avoiding wastage. 
The algorithm performs the following deterministic steps:
1. **Sorting**: It ingests a list of network requirements (e.g., HR needs 120 hosts, IT needs 50 hosts) and strictly sorts them in **descending order** of host count. This is a mathematically required step in VLSM to prevent fragmentation.
2. **Allocation**: For each requirement, it calculates the minimum necessary subnet mask. It then sequentially allocates the block from the lowest available boundary of the parent network.
3. **Tracking Available Space**: As blocks are allocated, the remaining free blocks of the parent CIDR are tracked. If a requirement exceeds the available free contiguous blocks, the algorithm throws a standard `ValueError`.
4. **Wastage Calculation**: For each allocated block, it compares the requested number of hosts against the total usable hosts in the new subnet and returns a `Wastage %` metric, allowing engineers to audit their network efficiency.
