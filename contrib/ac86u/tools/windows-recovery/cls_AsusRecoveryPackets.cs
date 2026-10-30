// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoveryPackets.cs</FILE> - <DESC>Pure wire codec for ASUS discovery and binary TFTP recovery packets.</DESC>
// <VERS>VERSION: 0.1.1</VERS>
// <WCTX>Encode the vendor packet layouts established from the installed Rescue.exe.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
using System;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace AsusRecovery
{
    public static class RecoveryPackets
    {
        public static byte[] BuildDiscovery(IPAddress routerIP)
        {
            if (routerIP == null || routerIP.AddressFamily != AddressFamily.InterNetwork)
                throw new ArgumentException("An IPv4 router address is required.");
            byte[] packet = new byte[26];
            packet[1] = 1;
            Encoding.ASCII.GetBytes("ASUSSPACELINK").CopyTo(packet, 2);
            byte[] ip = routerIP.GetAddressBytes();
            for (int i = 0; i < 4; i++) packet[15 + i] = ip[3 - i];
            Encoding.ASCII.GetBytes("octet").CopyTo(packet, 20);
            return packet;
        }

        public static byte[] BuildWriteRequest()
        {
            byte[] packet = new byte[22];
            packet[1] = 2;
            Encoding.ASCII.GetBytes("ASUSSPACELINK").CopyTo(packet, 2);
            Encoding.ASCII.GetBytes("octet").CopyTo(packet, 16);
            return packet;
        }

        public static byte[] BuildData(ushort block, byte[] data, int count)
        {
            if (data == null || count < 0 || count > 512 || count > data.Length)
                throw new ArgumentException("DATA payload must contain zero through 512 bytes.");
            byte[] packet = new byte[count + 4];
            packet[1] = 3;
            packet[2] = (byte)(block >> 8);
            packet[3] = (byte)block;
            Buffer.BlockCopy(data, 0, packet, 4, count);
            return packet;
        }

        public static ushort ReadU16(byte[] packet, int offset)
        {
            if (packet == null || offset < 0 || offset > packet.Length - 2)
                throw new ArgumentException("Truncated packet field.");
            return (ushort)((packet[offset] << 8) | packet[offset + 1]);
        }

        public static ushort Opcode(byte[] packet) { return ReadU16(packet, 0); }
        public static ushort Code(byte[] packet) { return ReadU16(packet, 2); }
    }
}
// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoveryPackets.cs</FILE> - <DESC>Pure wire codec for ASUS discovery and binary TFTP recovery packets.</DESC>
// <VERS>END OF VERSION: 0.1.1</VERS>
