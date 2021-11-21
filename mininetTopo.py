'''
Please add your name: She Jiayu
Please add your matric number: A0188314B
'''

import os
import atexit
from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo
from mininet.link import Link
from mininet.node import RemoteController

net = None

class TreeTopo(Topo):
    def __init__(self):
        # Initialize topology
        Topo.__init__(self)
        self.bandwidths = {}
        self.parseTopo("topology.in")
    
    def parseTopo(self, filename):
        file = open(filename, "r")
        n_host, n_switch, n_link = file.readline().strip().split(" ")
        # Add hosts
        for i in range(int(n_host)):
            self.addHost("h%d" % (i + 1))
        # Add switches
        for i in range(int(n_switch)):
            sconfig = {"dpid": "%016x" % (i + 1)}
            self.addSwitch("s%d" % (i + 1), **sconfig)
        # Add links
        for i in range(int(n_link)):
            src, dst, bw = file.readline().strip().split(",")
            self.addLink(src, dst)
            if src not in self.bandwidths:
                self.bandwidths[src] = {}
            self.bandwidths[src][dst] = int(bw)
            if dst not in self.bandwidths:
                self.bandwidths[dst] = {}
            self.bandwidths[dst][src] = int(bw)

def startNetwork():
    info('** Creating the tree network\n')
    topo = TreeTopo()

    global net
    net = Mininet(topo=topo, link=Link,
                  controller=lambda name: RemoteController(name, ip="192.168.56.101"),
                  listenPort=6633, autoSetMacs=True)

    info('** Starting the network\n')
    net.start()

    for switch in net.switches:
        for interface in switch.intfList():
            if interface.link:
                node1 = interface.link.intf1.node
                node2 = interface.link.intf2.node
                if node1 == switch:
                    dst = node2
                    interface = interface.link.intf1
                else:
                    dst = node1
                    interface = interface.link.intf2
                bw = topo.bandwidths[switch.name][dst.name] * 1000000
                # Create QoS and Queues
                # normal <= 0.5bw
                # premium >= 0.8bw
                os.system("sudo ovs-vsctl -- set Port %s qos=@newqos \
                        -- --id=@newqos create QoS type=linux-htb other-config:max-rate=%i queues=0=@q0,1=@q1 \
                        -- --id=@q0 create queue other-config:min-rate=%i \
                        -- --id=@q1 create queue other-config:max-rate=%i" % (interface.name, bw, int(0.8 * bw), int(0.5 * bw)))

    info('** Running CLI\n')
    CLI(net)

def stopNetwork():
    if net is not None:
        net.stop()
        # Remove QoS and Queues
        os.system('sudo ovs-vsctl --all destroy Qos')
        os.system('sudo ovs-vsctl --all destroy Queue')

if __name__ == '__main__':
    # Force cleanup on exit by registering a cleanup function
    atexit.register(stopNetwork)

    # Tell mininet to print useful information
    setLogLevel('info')
    startNetwork()
