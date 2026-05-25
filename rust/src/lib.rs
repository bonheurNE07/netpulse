use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::exceptions::{PyValueError, PyPermissionError, PyOSError};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use std::collections::HashMap;
use std::time::{Instant, Duration};
use std::thread;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::mem::MaybeUninit;

use ipnet::IpNet;
use socket2::{Socket, Domain, Type, Protocol};

use pnet::datalink::{self, Channel::Ethernet};
use pnet::packet::ethernet::{MutableEthernetPacket, EtherTypes, EthernetPacket};
use pnet::packet::arp::{MutableArpPacket, ArpOperations, ArpPacket};
use pnet::packet::{Packet, MutablePacket};
use pnet::util::MacAddr;

/// Helper function to calculate Internet Checksum (RFC 1071)
fn calculate_checksum(data: &[u8]) -> u16 {
    let mut sum = 0u32;
    for chunk in data.chunks_exact(2) {
        sum += u16::from_be_bytes([chunk[0], chunk[1]]) as u32;
    }
    if data.len() % 2 != 0 {
        sum += (data[data.len() - 1] as u32) << 8;
    }
    while sum >> 16 != 0 {
        sum = (sum & 0xffff) + (sum >> 16);
    }
    !(sum as u16)
}

/// Perform a high-speed, native ARP scan on a local network.
#[pyfunction]
#[pyo3(signature = (target, timeout_ms=1000, interface=None))]
fn scan_arp(
    py: Python<'_>,
    target: String,
    timeout_ms: u64,
    interface: Option<String>,
) -> PyResult<Bound<'_, PyList>> {
    // 1. Parse the target CIDR
    let net: IpNet = target.parse().map_err(|e| {
        PyValueError::new_err(format!("Invalid network CIDR '{}': {}", target, e))
    })?;

    // ARP is IPv4 only
    let ipv4_net = match net {
        IpNet::V4(v4) => v4,
        IpNet::V6(_) => {
            return Err(PyValueError::new_err("ARP scans are only supported for IPv4 networks."));
        }
    };

    // 2. Locate network interface
    let interfaces = datalink::interfaces();
    let selected_interface = if let Some(ref name) = interface {
        interfaces.into_iter().find(|i| i.name == *name).ok_or_else(|| {
            PyOSError::new_err(format!("Specified network interface '{}' not found.", name))
        })?
    } else {
        // Auto-detect: 
        // 1. Try strict check: find interface containing IP in target network, that is up and not loopback
        // 2. Fallback check: find interface containing IP in target network, regardless of is_up/loopback flags (required on Windows where flags can be unreliable)
        let mut selected = None;
        
        // Try strict check first
        for i in &interfaces {
            if i.is_up() && !i.is_loopback() && i.ips.iter().any(|ip| {
                match ip.ip() {
                    IpAddr::V4(ipv4) => ipv4_net.contains(&ipv4),
                    _ => false,
                }
            }) {
                selected = Some(i.clone());
                break;
            }
        }
        
        // Fallback check if nothing matched strict
        if selected.is_none() {
            for i in &interfaces {
                if i.ips.iter().any(|ip| {
                    match ip.ip() {
                        IpAddr::V4(ipv4) => ipv4_net.contains(&ipv4),
                        _ => false,
                    }
                }) {
                    selected = Some(i.clone());
                    break;
                }
            }
        }
        
        selected.ok_or_else(|| {
            PyOSError::new_err("Could not automatically determine network interface for target. Please specify one explicitly.")
        })?
    };

    let source_mac = selected_interface.mac.ok_or_else(|| {
        PyOSError::new_err("Selected network interface has no hardware (MAC) address.")
    })?;

    let source_ip = selected_interface
        .ips
        .iter()
        .find(|ip| ip.ip().is_ipv4())
        .map(|ip| match ip.ip() {
            IpAddr::V4(ipv4) => ipv4,
            _ => unreachable!(),
        })
        .ok_or_else(|| {
            PyOSError::new_err("Selected network interface has no IPv4 address.")
        })?;

    // 3. Open low-level raw Ethernet datalink channel
    let (mut tx, mut rx) = match datalink::channel(&selected_interface, Default::default()) {
        Ok(Ethernet(tx, rx)) => (tx, rx),
        Ok(_) => return Err(PyOSError::new_err("Unsupported channel type (expected Ethernet)")),
        Err(e) => {
            return Err(PyPermissionError::new_err(format!(
                "Permission Denied: Failed to open raw datalink interface.\n\
                 Low-level L2 ARP scanning requires CAP_NET_RAW / CAP_NET_ADMIN capabilities or root privileges.\n\
                 System error: {}", e
            )));
        }
    };

    // 4. Thread-safe map to hold responses
    let discovered = Arc::new(Mutex::new(HashMap::<Ipv4Addr, (MacAddr, Duration)>::new()));
    let stop_rx = Arc::new(AtomicBool::new(false));

    // 5. Spawn background receiver thread
    let rx_discovered = Arc::clone(&discovered);
    let rx_stop = Arc::clone(&stop_rx);
    let start_time = Instant::now();

    let rx_handle = thread::spawn(move || {
        while !rx_stop.load(Ordering::Relaxed) {
            match rx.next() {
                Ok(frame) => {
                    if let Some(eth) = EthernetPacket::new(frame) {
                        if eth.get_ethertype() == EtherTypes::Arp {
                            if let Some(arp) = ArpPacket::new(eth.payload()) {
                                if arp.get_operation() == ArpOperations::Reply {
                                    let sender_ip = arp.get_sender_proto_addr();
                                    let sender_mac = arp.get_sender_hw_addr();
                                    let rtt = start_time.elapsed();
                                    
                                    let mut locked = rx_discovered.lock().unwrap();
                                    locked.insert(sender_ip, (sender_mac, rtt));
                                }
                            }
                        }
                    }
                }
                Err(_) => {
                    // Timeout or read failure
                    thread::sleep(Duration::from_micros(50));
                }
            }
        }
    });

    // 6. Send ARP Request broad-casts
    // Iterate hosts (ignoring network and broadcast address if standard subnet)
    for host in ipv4_net.hosts() {
        let mut ethernet_buffer = [0u8; 42];
        let mut eth_packet = MutableEthernetPacket::new(&mut ethernet_buffer).unwrap();
        eth_packet.set_destination(MacAddr::broadcast());
        eth_packet.set_source(source_mac);
        eth_packet.set_ethertype(EtherTypes::Arp);

        {
            let mut arp_packet = MutableArpPacket::new(eth_packet.payload_mut()).unwrap();
            arp_packet.set_hardware_type(pnet::packet::arp::ArpHardwareTypes::Ethernet);
            arp_packet.set_protocol_type(EtherTypes::Ipv4);
            arp_packet.set_hw_addr_len(6);
            arp_packet.set_proto_addr_len(4);
            arp_packet.set_operation(ArpOperations::Request);
            arp_packet.set_sender_hw_addr(source_mac);
            arp_packet.set_sender_proto_addr(source_ip);
            arp_packet.set_target_hw_addr(MacAddr::zero());
            arp_packet.set_target_proto_addr(host);
        }
        
        // Send packet
        let packet_data = eth_packet.packet();
        if let Some(Err(e)) = tx.send_to(packet_data, None) {
            eprintln!("Failed to send ARP frame for IP {}: {}", host, e);
        }
        
        // Brief pacing sleep to avoid overwhelming network
        thread::sleep(Duration::from_micros(100));
    }

    // 7. Wait for outstanding replies
    thread::sleep(Duration::from_millis(timeout_ms));

    // 8. Clean up receiver thread
    stop_rx.store(true, Ordering::Relaxed);
    // Ignore join errors
    let _ = rx_handle.join();

    // 9. Process final results to PyList
    let results = PyList::empty(py);
    let final_discovered = discovered.lock().unwrap();
    for (ip, (mac, rtt)) in final_discovered.iter() {
        let device = PyDict::new(py);
        device.set_item("ip", ip.to_string())?;
        device.set_item("mac", mac.to_string())?;
        device.set_item("rtt_ms", rtt.as_secs_f64() * 1000.0)?;
        device.set_item("status", "up")?;
        results.append(device)?;
    }

    Ok(results)
}

/// Perform a high-speed ICMP reachability sweep across a network.
#[pyfunction]
#[pyo3(signature = (target, timeout_ms=1000, concurrency=100))]
fn scan_icmp(
    py: Python<'_>,
    target: String,
    timeout_ms: u64,
    concurrency: u32,
) -> PyResult<Bound<'_, PyList>> {
    let _ = concurrency; // Silence unused variable warning while matching signature
    
    // 1. Parse target network
    let net: IpNet = target.parse().map_err(|e| {
        PyValueError::new_err(format!("Invalid network CIDR '{}': {}", target, e))
    })?;

    // 2. Open ICMP Socket
    // Try RAW socket (requires CAP_NET_RAW or root) first. If it fails, fallback to unprivileged DGRAM socket.
    let socket = match Socket::new(Domain::IPV4, Type::RAW, Some(Protocol::ICMPV4)) {
        Ok(s) => s,
        Err(e) => {
            match Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::ICMPV4)) {
                Ok(s) => s,
                Err(_) => {
                    return Err(PyPermissionError::new_err(format!(
                        "Permission Denied: Failed to create raw or ping ICMP socket.\n\
                         Low-level ICMP sweep requires CAP_NET_RAW capability or root privileges.\n\
                         Raw socket system error: {}", e
                    )));
                }
            }
        }
    };

    // Configure read timeout so the receiver thread loop can terminate
    socket.set_read_timeout(Some(Duration::from_millis(50))).unwrap_or(());

    let socket = Arc::new(socket);
    let replies = Arc::new(Mutex::new(HashMap::<IpAddr, Instant>::new()));
    let stop_rx = Arc::new(AtomicBool::new(false));

    // 3. Spawn background receiver thread
    let rx_socket = Arc::clone(&socket);
    let rx_replies = Arc::clone(&replies);
    let rx_stop = Arc::clone(&stop_rx);

    let rx_handle = thread::spawn(move || {
        let mut buf = [MaybeUninit::<u8>::uninit(); 512];
        while !rx_stop.load(Ordering::Relaxed) {
            match rx_socket.recv_from(&mut buf) {
                Ok((size, addr)) => {
                    let ip = addr.as_socket_ipv4().map(|s| IpAddr::V4(*s.ip()))
                        .or_else(|| addr.as_socket_ipv6().map(|s| IpAddr::V6(*s.ip())));

                    if let Some(ip) = ip {
                        // Safe conversion because socket filled `size` bytes
                        let initialized_slice = unsafe {
                            std::slice::from_raw_parts(buf.as_ptr() as *const u8, size)
                        };

                        // If it's a RAW socket, we get the whole IPv4 packet.
                        // If it's a DGRAM ping socket, we get only the ICMP payload.
                        let icmp_payload = if size >= 20 && (initialized_slice[0] >> 4) == 4 {
                            let ihl = (initialized_slice[0] & 0x0f) as usize * 4;
                            if size >= ihl + 8 {
                                &initialized_slice[ihl..size]
                            } else {
                                continue;
                            }
                        } else if size >= 8 {
                            &initialized_slice[0..size]
                        } else {
                            continue;
                        };

                        let icmp_type = icmp_payload[0];
                        if icmp_type == 0 { // Echo Reply
                            // Check the Identifier to make sure it matches our sent requests (0x1234)
                            let identifier = u16::from_be_bytes([icmp_payload[4], icmp_payload[5]]);
                            if identifier == 0x1234 {
                                let mut locked = rx_replies.lock().unwrap();
                                locked.insert(ip, Instant::now());
                            }
                        }
                    }
                }
                Err(_) => {
                    // Read timeout or socket closed
                }
            }
        }
    });

    // 4. Construct the ICMP Echo Request packet
    let mut packet = [0u8; 16];
    packet[0] = 8;     // Type: Echo Request
    packet[1] = 0;     // Code: 0
    packet[2] = 0;     // Checksum High (calculated below)
    packet[3] = 0;     // Checksum Low
    packet[4] = 0x12;  // Identifier High (0x12)
    packet[5] = 0x34;  // Identifier Low (0x34)
    packet[6] = 0;     // Sequence High
    packet[7] = 1;     // Sequence Low
    packet[8..16].copy_from_slice(b"NETPULSE");

    let cs = calculate_checksum(&packet);
    packet[2] = (cs >> 8) as u8;
    packet[3] = (cs & 0xff) as u8;

    // 5. Send packets to all host targets
    let mut send_times = HashMap::<IpAddr, Instant>::new();
    for ip in net.hosts() {
        let socket_addr = SocketAddr::new(ip, 0);
        let target_addr = socket2::SockAddr::from(socket_addr);

        let now = Instant::now();
        match socket.send_to(&packet, &target_addr) {
            Ok(_) => {
                send_times.insert(ip, now);
            }
            Err(e) => {
                eprintln!("Failed to send ICMP Echo Request to {}: {}", ip, e);
            }
        }
        
        // Pacing delay to avoid congestion and packet drops
        thread::sleep(Duration::from_micros(100));
    }

    // 6. Wait for final replies
    thread::sleep(Duration::from_millis(timeout_ms));

    // 7. Clean up receiver thread
    stop_rx.store(true, Ordering::Relaxed);
    // Ignore join errors
    let _ = rx_handle.join();

    // 8. Correlate send/receive times and format PyList results
    let results = PyList::empty(py);
    let final_replies = replies.lock().unwrap();

    for (ip, send_time) in send_times.iter() {
        if let Some(recv_time) = final_replies.get(ip) {
            if *recv_time >= *send_time {
                let rtt_ms = (*recv_time - *send_time).as_secs_f64() * 1000.0;
                let device = PyDict::new(py);
                device.set_item("ip", ip.to_string())?;
                device.set_item("mac", py.None())?;
                device.set_item("rtt_ms", rtt_ms)?;
                device.set_item("status", "up")?;
                results.append(device)?;
            }
        }
    }

    Ok(results)
}

/// A Python module implemented in Rust.
#[pymodule]
fn netpulse_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_arp, m)?)?;
    m.add_function(wrap_pyfunction!(scan_icmp, m)?)?;
    Ok(())
}
