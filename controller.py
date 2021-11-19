'''
Please add your name: She Jiayu
Please add your matric number: A0188314B
'''

from pox.core import core
import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
import pox.openflow.spanning_forest
from pox.lib.revent import *
from pox.lib.util import dpid_to_str
from pox.lib.addresses import IPAddr, EthAddr
import time

log = core.getLogger()

P_FIREWALL = 20
P_PREMIUM = 10
Q_NORMAL = 1
Q_PREMIUM = 0
TTL = 30

class Controller(EventMixin):
    def __init__(self):
        self.listenTo(core.openflow)
        core.openflow_discovery.addListeners(self)
        self.mac_table = {}
        self.policies = []
        self.premiums = set()
        self.parsePolicy("policy.in")
    
    def parsePolicy(self, filename):
        file = open(filename, "r")
        line = file.readline().strip()
        n_fw, n_premium = line.split(" ")
        # Add firewalls
        for i in range(int(n_fw)):
            line = file.readline().strip()
            fields = line.split(",")
            if len(fields) == 2:
                self.policies.append((None, fields[0], fields[1]))
            elif len(fields) == 3:
                self.policies.append((fields[0], fields[1], fields[2]))
            else:
                log.info("Error parsing line [%s]\n", line)
        # Add premiums
        for i in range(int(n_premium)):
            line = file.readline().strip()
            self.premiums.add(line)

    def _handle_PacketIn(self, event):
        dpid = event.dpid
        inport = event.port
        packet = event.parsed
        src, dst = packet.src, packet.dst
        ip_src, ip_dst = None, None
        if packet.type == packet.ARP_TYPE:
            ip_src, ip_dst = str(packet.payload.protosrc), str(packet.payload.protodst)
        elif packet.type == packet.IP_TYPE:
            ip_src, ip_dst = str(packet.payload.srcip), str(packet.payload.dstip)

        # Install entries to the route table
        def install_enqueue(outport, q_id):
            msg = of.ofp_flow_mod()
            msg.priority = P_PREMIUM
            msg.match = of.ofp_match.from_packet(packet, inport)
            msg.data = event.ofp
            msg.idle_timeout = TTL
            msg.hard_timeout = TTL
            msg.actions.append(of.ofp_action_enqueue(port=outport, queue_id=q_id))
            event.connection.send(msg)
            # log.info("# S%i: Message sent: Outport %i\n", dpid, outport)

        # When it knows nothing about the destination, flood but don't install the rule
        def flood():
            msg = of.ofp_packet_out()
            msg.data = event.ofp
            msg.in_port = inport
            # OFPP_FLOOD: output all openflow ports expect the input port and those with flooding disabled via the OFPPC_NO_FLOOD port config bit
            msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
            event.connection.send(msg)
            # log.info("# S%i: Message sent: Outport %i\n", dpid, of.OFPP_FLOOD)

        # Check the packet and decide how to route the packet
        def forward():
            if dpid not in self.mac_table:
                self.mac_table[dpid] = {}
            if dst in self.mac_table[dpid] and time.time() - self.mac_table[dpid][dst][1] > 30.0:
                self.mac_table[dpid].pop(dst)
            if dst in self.mac_table[dpid]:
                outport = self.mac_table[dpid][dst][0]
                q_id = Q_PREMIUM if ip_src in self.premiums and ip_dst in self.premiums else Q_NORMAL
                install_enqueue(outport, q_id)
            else:
                # update mac table only when dst is not seen
                self.mac_table[dpid][src] = (inport, time.time())
                flood()
        
        forward()

    def _handle_ConnectionUp(self, event):
        dpid = dpid_to_str(event.dpid)
        log.info("Switch %s has come up.", dpid)
        
        # Send the firewall policies to the switch
        def sendFirewallPolicy(policy):
            src, dst, port = policy
            msg = of.ofp_flow_mod()
            msg.priority = P_FIREWALL
            msg.match.dl_type = 0x800
            msg.match.nw_proto = 6
            if src is not None:
                msg.match.nw_src = IPAddr(src)
            msg.match.nw_dst = IPAddr(dst)
            msg.match.tp_dst = int(port)
            # This line causes errors due to bugs in pox
            # Ref: https://github.com/noxrepo/pox/issues/171
            # OFPP_NONE: outputting to nowhere
            # msg.actions.append(of.ofp_action_output(port=of.OFPP_NONE))
            event.connection.send(msg)

        for policy in self.policies:
            sendFirewallPolicy(policy)

def launch():
    # Run discovery and spanning tree modules
    pox.openflow.discovery.launch()
    pox.openflow.spanning_forest.launch()

    # Starting the controller module
    core.registerNew(Controller)
