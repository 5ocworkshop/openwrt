// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoveryChannel.cs</FILE> - <DESC>Owned source/interface-bound UDP channel for one recovery session.</DESC>
// <VERS>VERSION: 0.1.2</VERS>
// <WCTX>Retain the same local endpoint through transfer and vendor flash-status monitoring.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
using System;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace AsusRecovery
{
    internal sealed class RecoveryChannel : IDisposable
    {
        private readonly object gate = new object();
        private readonly byte[] receiveBuffer = new byte[65535];
        private Socket socket;
        internal string LocalEndpoint { get; private set; }

        internal RecoveryChannel(IPAddress local)
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
                throw new PlatformNotSupportedException("The recovery channel requires native Windows.");
            int index = -1;
            foreach (NetworkInterface adapter in NetworkInterface.GetAllNetworkInterfaces())
                foreach (UnicastIPAddressInformation address in adapter.GetIPProperties().UnicastAddresses)
                    if (address.Address.Equals(local))
                    {
                        if (index != -1) throw new ArgumentException("Source IP belongs to multiple interfaces.");
                        index = adapter.GetIPProperties().GetIPv4Properties().Index;
                    }
            if (index == -1) throw new ArgumentException("Source IP does not belong to a local interface.");
            Socket created = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
            try
            {
                created.EnableBroadcast = true;
                created.Bind(new IPEndPoint(local, 0));
                // IP_UNICAST_IF requires a DWORD interface index in network byte order.
                created.SetSocketOption(SocketOptionLevel.IP, (SocketOptionName)31, IPAddress.HostToNetworkOrder(index));
                LocalEndpoint = created.LocalEndPoint.ToString();
                socket = created;
            }
            catch { created.Close(); throw; }
        }

        internal void Send(byte[] data, IPEndPoint destination)
        {
            lock (gate)
            {
                if (socket == null) throw new ObjectDisposedException("RecoveryChannel");
                socket.SendTo(data, destination);
            }
        }

        internal byte[] Receive(int waitMilliseconds, IPEndPoint expected, bool allowNewPort, out IPEndPoint sender)
        {
            sender = null;
            Socket current;
            lock (gate) current = socket;
            if (current == null) throw new ObjectDisposedException("RecoveryChannel");
            if (!current.Poll(Math.Max(1, Math.Min(waitMilliseconds, 100)) * 1000, SelectMode.SelectRead)) return null;
            EndPoint from = new IPEndPoint(IPAddress.Any, 0);
            int length = current.ReceiveFrom(receiveBuffer, ref from);
            IPEndPoint remote = (IPEndPoint)from;
            if (!remote.Address.Equals(expected.Address) || (!allowNewPort && remote.Port != expected.Port)) return null;
            sender = remote;
            byte[] packet = new byte[length];
            Buffer.BlockCopy(receiveBuffer, 0, packet, 0, length);
            return packet;
        }

        public void Dispose()
        {
            lock (gate)
            {
                if (socket == null) return;
                socket.Close();
                socket = null;
            }
        }
    }
}
// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoveryChannel.cs</FILE> - <DESC>Owned source/interface-bound UDP channel for one recovery session.</DESC>
// <VERS>END OF VERSION: 0.1.2</VERS>
