#!/usr/bin/env python

from __future__ import print_function
from bcc import BPF
from time import strftime
from socket import inet_ntop, AF_INET, AF_INET6
from struct import pack
import ctypes as ct
from bcc import tcp
from os import kill, getpid
from signal import SIGKILL
import argparse

# arguments
examples = """examples:
    ./in_probe             # trace all TCP packets
    ./in_porbe -p  5205    # only trace port 5205
    ./in_porbe -dp 5205    # only trace remote port 5205
    ./in_porbe -sp 5205    # only trace local port 5205
    ./in_porbe -s  5       # only trace one packet in every 2^5 packets
"""

parser = argparse.ArgumentParser(
    description="Trace the duration in TCP, IP and MAC layers",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=examples)
parser.add_argument("-p", "--port", 
    help="TCP port")
parser.add_argument("-sp", "--sport", 
    help="TCP source port")
parser.add_argument("-dp", "--dport",
    help="TCP destination port")
parser.add_argument("-s", "--sample",
    help="Trace sampling")

args = parser.parse_args()

# define BPF program
bpf_text = """
#include <uapi/linux/ptrace.h>
#define KBUILD_MODNAME "foo"
#include <linux/tcp.h>
#include <linux/ip.h>
#include <uapi/linux/tcp.h>
#include <uapi/linux/ip.h>
#include <uapi/linux/if_ether.h>
#include <net/sock.h>
#include <bcc/proto.h>
#include <linux/skbuff.h>
#include <linux/netdevice.h>
#include <net/tcp.h>
#include <net/ip.h>


struct packet_tuple {
    u32 saddr;
    u32 daddr;
    u16 sport;
    u16 dport;
    u32 seq;
    u32 ack;
};


struct ktime_info {
    u64 mac_time;
    u64 ip_time;
    u64 tcp_time;
    u64 app_time;
};

struct data_t {
    u64 total_time;
    u64 mac_time;
    u64 ip_time;
    u64 tcp_time;
    u32 saddr;
    u32 daddr;
    u16 sport;
    u16 dport;
    u32 seq;
    u32 ack;
};

BPF_HASH(in_timestamps, struct packet_tuple, struct ktime_info);
BPF_PERF_OUTPUT(timestamp_events);

static struct tcphdr *skb_to_tcphdr(const struct sk_buff *skb)
{
    // unstable API. verify logic in tcp_hdr() -> skb_transport_header().
    return (struct tcphdr *)(skb->head + skb->transport_header);
}

static inline struct iphdr *skb_to_iphdr(const struct sk_buff *skb)
{
    // unstable API. verify logic in ip_hdr() -> skb_network_header().
    return (struct iphdr *)(skb->head + skb->network_header);
}


int trace_eth_type_trans(struct pt_regs *ctx, struct sk_buff *skb)
{
    const struct ethhdr* eth = (struct ethhdr*) skb->data;
    u16 protocol = eth->h_proto;
    // Protocol is IP
    if (protocol == 8) 
    {
        u64 time = bpf_ktime_get_ns();
        SAMPLING

        struct iphdr *ip = (struct iphdr *)(skb->data + 14);
        struct tcphdr *tcp = (struct tcphdr *)(skb->data + 34);
        struct packet_tuple pkt_tuple = {};
        pkt_tuple.saddr = ip->saddr;
        pkt_tuple.daddr = ip->daddr;
        u16 sport = 0, dport = 0;
        u32 seq = 0, ack = 0; 
        sport = tcp->source;
        dport = tcp->dest;
        sport = ntohs(sport);
        dport = ntohs(dport);

        pkt_tuple.sport = sport;
        pkt_tuple.dport = dport;

        FILTER_PORT
        FILTER_DPORT
        FILTER_SPORT

        seq = tcp->seq;
        ack = tcp->ack_seq;
        pkt_tuple.seq = ntohl(seq);
        pkt_tuple.ack = ntohl(ack);
        
        struct ktime_info *tinfo, zero={}; 
        if ((tinfo = in_timestamps.lookup_or_init(&pkt_tuple, &zero)) == NULL)
            return 0;
        tinfo->mac_time = time;
    }

    return 0;
}


int trace_ip_rcv(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);

    struct packet_tuple pkt_tuple = {};
    pkt_tuple.saddr = ip->saddr;
    pkt_tuple.daddr = ip->daddr;
    u16 sport = 0, dport = 0;
    u32 seq = 0, ack = 0; 
    sport = tcp->source;
    dport = tcp->dest;
    sport = ntohs(sport);
    dport = ntohs(dport);
    pkt_tuple.sport = sport;
    pkt_tuple.dport = dport;

    FILTER_PORT
    FILTER_DPORT
    FILTER_SPORT

    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);
    
    struct ktime_info *tinfo;
    if ((tinfo = in_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->ip_time = bpf_ktime_get_ns();
    
    return 0;
}

int trace_tcp_v4_rcv(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);
    struct packet_tuple pkt_tuple = {};
    pkt_tuple.saddr = ip->saddr;
    pkt_tuple.daddr = ip->daddr;
    u16 sport = 0, dport = 0;
    u32 seq = 0, ack = 0; 
    sport = tcp->source;
    dport = tcp->dest;
    sport = ntohs(sport);
    dport = ntohs(dport);
    pkt_tuple.sport = sport;
    pkt_tuple.dport = dport;

    FILTER_PORT
    FILTER_DPORT
    FILTER_SPORT

    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);
    
    struct ktime_info *tinfo;
    if ((tinfo = in_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->tcp_time = bpf_ktime_get_ns();
    
    return 0;
}

int trace_skb_copy_datagram_iter(struct pt_regs *ctx, struct sk_buff *skb)
{
    if (skb == NULL)
        return 0;

    struct iphdr *ip = skb_to_iphdr(skb);
    struct tcphdr *tcp = skb_to_tcphdr(skb);
    struct packet_tuple pkt_tuple = {};
    pkt_tuple.saddr = ip->saddr;
    pkt_tuple.daddr = ip->daddr;
    u16 sport = 0, dport = 0;
    u32 seq = 0, ack = 0; 
    sport = tcp->source;
    dport = tcp->dest;
    sport = ntohs(sport);
    dport = ntohs(dport);
    pkt_tuple.sport = sport;
    pkt_tuple.dport = dport;

    FILTER_PORT
    FILTER_DPORT
    FILTER_SPORT

    seq = tcp->seq;
    ack = tcp->ack_seq;
    pkt_tuple.seq = ntohl(seq);
    pkt_tuple.ack = ntohl(ack);
    
    struct ktime_info *tinfo;
    if ((tinfo = in_timestamps.lookup(&pkt_tuple)) == NULL)
        return 0;
    tinfo->app_time = bpf_ktime_get_ns();
    struct data_t data = {};
    data.total_time = tinfo->app_time - tinfo->mac_time;
    data.mac_time = tinfo->ip_time - tinfo->mac_time;
    data.ip_time = tinfo->tcp_time - tinfo->ip_time;
    data.tcp_time = tinfo->app_time - tinfo->tcp_time;
    data.saddr = pkt_tuple.saddr;
    data.daddr = pkt_tuple.daddr;
    data.sport = pkt_tuple.sport;
    data.dport = pkt_tuple.dport;
    data.seq = pkt_tuple.seq;
    data.ack = ack;
  
    in_timestamps.delete(&pkt_tuple);
    timestamp_events.perf_submit(ctx, &data, sizeof(data));

    return 0;
}

"""

# code substitutions
if args.port:
    bpf_text = bpf_text.replace('FILTER_PORT',
        'if (pkt_tuple.sport != %s && pkt_tuple.dport != %s) { return 0; }' % (args.port, args.port))
else:
    bpf_text = bpf_text.replace('FILTER_SPORT', '')
if args.sport:
    bpf_text = bpf_text.replace('FILTER_SPORT',
        'if (pkt_tuple.sport != %s) { return 0; }' % args.sport)
else:
    bpf_text = bpf_text.replace('FILTER_SPORT', '')
    
if args.dport:
    bpf_text = bpf_text.replace('FILTER_DPORT',
        'if (pkt_tuple.dport != %s) { return 0; }' % args.dport)
else:
    bpf_text = bpf_text.replace('FILTER_DPORT', '')
if args.sample:
    bpf_text = bpf_text.replace('SAMPLING',
        'if ((time << (64-%s) >> (64-%s)) != ((0x01 << %s) - 1)) { return 0;}' % (args.sample, args.sample, args.sample))
else:
    bpf_text = bpf_text.replace('SAMPLING', '')

class Data_t(ct.Structure):
    _fields_ = [
        ("total_time", ct.c_ulonglong),
        ("mac_time", ct.c_ulonglong),
        ("ip_time", ct.c_ulonglong),
        ("tcp_time", ct.c_ulonglong),
        ("saddr", ct.c_uint),
        ("daddr", ct.c_uint),
        ("sport", ct.c_ushort),
        ("dport", ct.c_ushort),
        ("seq", ct.c_uint),
        ("ack", ct.c_uint),
    ]

# process event
def print_event(cpu, data, size):
    event = ct.cast(data, ct.POINTER(Data_t)).contents
    print("%-20s > %-20s %-12s %-12s %-10s %-10s %-10s %-10s" % (
        "%s:%d" % (inet_ntop(AF_INET, pack('I', event.saddr)), event.sport),
        "%s:%d" % (inet_ntop(AF_INET, pack('I', event.daddr)), event.dport),
        "%d" % (event.seq),
        "%d" % (event.ack),
        "%d" % (event.total_time/1000),
        "%d" % (event.mac_time/1000),
        "%d" % (event.ip_time/1000),
        "%d" % (event.tcp_time/1000)))


# initialize BPF
b = BPF(text=bpf_text)
trace_prefix = "trace_"
kprobe_functions_list = ["eth_type_trans", "ip_rcv", "tcp_v4_rcv", "skb_copy_datagram_iter"]
kretprobe_functions_list = []
for i in range(len(kprobe_functions_list)):
    function = kprobe_functions_list[i]
    trace_function = trace_prefix + function
    if b.get_kprobe_functions(function):
        b.attach_kprobe(event=function, fn_name=trace_function)
    else:
        print("ERROR: %s() kernel function not found or traceable." % (function))
        exit()

for i in range(len(kretprobe_functions_list)):
    function = kretprobe_functions_list[i]
    trace_function = trace_prefix + function
    if b.get_kprobe_functions(function):
        b.attach_kretprobe(event=function, fn_name=trace_function)
    else:
        print("ERROR: %s() kernel function not found or traceable." % (function))
        exit()

# header
print("%-20s > %-20s %-12s %-12s %-10s %-10s %-10s %-10s" % ("SADDR:SPORT", "DADDR:DPORT", "SEQ", "ACK", "TOTAL", "MAC", "IP", "TCP"))

# read events
b["timestamp_events"].open_perf_buffer(print_event)
while 1:
    try:
        b.perf_buffer_poll()
    except KeyboardInterrupt:
        kill(getpid(), SIGKILL)
