// <FILE>contrib/ac86u/tests/cls_AsusRecoverySimulator.cs</FILE> - <DESC>Local-only synthetic ASUS recovery peer for native protocol acceptance.</DESC>
// <VERS>VERSION: 0.3.1</VERS>
// <WCTX>Exercise discovery, transfer and post-flash statuses without contacting router hardware.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Net.NetworkInformation;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace AsusRecoveryTests
{
    public sealed class AsusRecoverySimulator : IDisposable
    {
        private readonly string mode;
        private readonly int expectedLength;
        private readonly IPAddress bindAddress;
        private readonly UdpClient listener;
        private readonly Task worker;
        private UdpClient transfer;
        private volatile bool stopping;
        private volatile string error = "";
        private volatile bool finalAckSent, successSent, matches = true, stable = true, rollover;
        private int clientPort, discoveryCount, requestCount, dataPackets, progressSent, finalLength = -1;
        private int receivedPackets;
        private long bytesReceived;
        public int Port { get; private set; }
        public string Error { get { return error; } }
        public bool FinalAckSent { get { return finalAckSent; } }
        public bool SuccessSent { get { return successSent; } }
        public bool PayloadMatches { get { return matches; } }
        public bool ClientPortStable { get { return stable; } }
        public bool SawRollover { get { return rollover; } }
        public int DataPackets { get { return Volatile.Read(ref dataPackets); } }
        public int TotalReceivedPackets { get { return Volatile.Read(ref receivedPackets); } }
        public int DiscoveryRequests { get { return Volatile.Read(ref discoveryCount); } }
        public int WriteRequests { get { return Volatile.Read(ref requestCount); } }
        public int ProgressSent { get { return Volatile.Read(ref progressSent); } }
        public int FinalDataLength { get { return Volatile.Read(ref finalLength); } }
        public long BytesReceived { get { return Interlocked.Read(ref bytesReceived); } }

        public AsusRecoverySimulator(string scenario, int length) : this(scenario, length, "127.0.0.1") { }

        public AsusRecoverySimulator(string scenario, int length, string localAddress)
        {
            if (length <= 0) throw new ArgumentOutOfRangeException("length");
            IPAddress address;
            if (!IPAddress.TryParse(localAddress, out address) || address.AddressFamily != AddressFamily.InterNetwork)
                throw new ArgumentException("Simulator needs an assigned local IPv4 address.");
            bool local = false;
            foreach (NetworkInterface adapter in NetworkInterface.GetAllNetworkInterfaces())
                foreach (UnicastIPAddressInformation item in adapter.GetIPProperties().UnicastAddresses)
                    if (item.Address.Equals(address)) local = true;
            if (!local) throw new ArgumentException("Simulator bind address is not assigned to this PC.");
            bindAddress = address;
            mode = scenario; expectedLength = length;
            listener = NewSocket(bindAddress);
            Port = ((IPEndPoint)listener.Client.LocalEndPoint).Port;
            transfer = listener;
            worker = Task.Factory.StartNew(Run, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        }

        public static void CreateFixture(string path, int length)
        {
            byte[] buffer = new byte[65536];
            using (FileStream stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
            {
                int offset = 0;
                while (offset < length)
                {
                    int count = Math.Min(buffer.Length, length - offset);
                    for (int i = 0; i < count; i++) buffer[i] = (byte)((offset + i) % 251);
                    stream.Write(buffer, 0, count); offset += count;
                }
            }
        }

        private static UdpClient NewSocket(IPAddress address)
        {
            UdpClient socket = new UdpClient(new IPEndPoint(address, 0));
            socket.Client.ReceiveTimeout = 100;
            return socket;
        }

        private byte[] Receive(UdpClient socket, out IPEndPoint peer)
        {
            peer = new IPEndPoint(IPAddress.Any, 0);
            try {
                byte[] packet = socket.Receive(ref peer);
                Interlocked.Increment(ref receivedPackets);
                return packet;
            }
            catch (SocketException exception)
            {
                if (exception.SocketErrorCode == SocketError.TimedOut || exception.SocketErrorCode == SocketError.WouldBlock) return null;
                if (stopping) return null;
                throw;
            }
            catch (ObjectDisposedException) { if (stopping) return null; throw; }
        }

        private void CheckPeer(IPEndPoint peer)
        {
            if (!peer.Address.Equals(bindAddress)) throw new InvalidOperationException("Client source differs from this PC's selected local address");
            if (clientPort == 0) clientPort = peer.Port;
            if (peer.Port != clientPort) { stable = false; throw new InvalidOperationException("Local UDP endpoint changed between phases"); }
        }

        private static ushort Word(byte[] packet, int offset) { return (ushort)((packet[offset] << 8) | packet[offset + 1]); }
        private static byte[] Ack(ushort block) { return new byte[] { 0, 4, (byte)(block >> 8), (byte)block }; }
        private static byte[] Status(ushort code) { return new byte[] { 0, 6, (byte)(code >> 8), (byte)code }; }
        private static void Send(UdpClient socket, byte[] packet, IPEndPoint peer) { socket.Send(packet, packet.Length, peer); }

        private void Delay(int milliseconds)
        {
            Stopwatch watch = Stopwatch.StartNew();
            while (!stopping && watch.ElapsedMilliseconds < milliseconds) Thread.Sleep(5);
        }

        private void ValidateRequest(byte[] packet, bool discovery)
        {
            byte[] name = Encoding.ASCII.GetBytes("ASUSSPACELINK");
            int length = discovery ? 26 : 22;
            if (packet.Length != length || packet[0] != 0 || packet[1] != (discovery ? 1 : 2)) throw new InvalidOperationException("Malformed request length/opcode");
            for (int i = 0; i < name.Length; i++) if (packet[i + 2] != name[i]) throw new InvalidOperationException("Wrong ASUS filename");
            int end = 15;
            if (discovery)
            {
                byte[] ip = bindAddress.GetAddressBytes();
                Array.Reverse(ip);
                for (int i = 0; i < 4; i++) if (packet[15 + i] != ip[i]) throw new InvalidOperationException("Discovery encoded wrong router IPv4");
                end = 19;
            }
            if (packet[end] != 0 || Encoding.ASCII.GetString(packet, end + 1, 5) != "octet" || packet[length - 1] != 0) throw new InvalidOperationException("Wrong request mode/terminator");
        }

        private void AfterTransfer(IPEndPoint peer)
        {
            if (mode == "flash_timeout" || mode == "cancel_flash") { while (!stopping) Delay(20); return; }
            if (mode == "late_success")
            {
                Delay(280);
                if (!stopping) { successSent = true; Send(transfer, Status(1), peer); }
                return;
            }
            if (mode == "wrong_packets")
            {
                Send(transfer, new byte[] { 0, 6 }, peer);
                Send(transfer, Ack(1), peer);
                using (UdpClient wrongPort = NewSocket(IPAddress.Loopback)) Send(wrongPort, Status(1), peer);
                using (UdpClient wrongAddress = NewSocket(IPAddress.Parse("127.0.0.2"))) Send(wrongAddress, Status(1), peer);
                Delay(180);
            }
            if (mode == "progress_forever")
            {
                while (!stopping) { Send(transfer, Status(3), peer); Interlocked.Increment(ref progressSent); Delay(100); }
                return;
            }
            int progressCount = mode == "progress_success" ? 5 : 1;
            for (int i = 0; i < progressCount && !stopping; i++)
            {
                Send(transfer, Status(3), peer); Interlocked.Increment(ref progressSent); Delay(mode == "progress_success" ? 150 : 180);
            }
            if (stopping) return;
            if (mode == "flash_failure") Send(transfer, Status(2), peer);
            else { successSent = true; Send(transfer, Status(1), peer); }
            IPEndPoint sender;
            byte[] unexpected = Receive(transfer, out sender);
            if (unexpected != null) throw new InvalidOperationException("Client sent a packet after ASUS flash status");
        }

        private void Run()
        {
            try
            {
                bool discovered = false, requested = false, lostDataAck = false;
                ushort expectedBlock = 1, previousBlock = 0;
                byte[] previousPacket = null;
                Stopwatch deadline = Stopwatch.StartNew();
                while (!stopping && deadline.ElapsedMilliseconds < 180000)
                {
                    IPEndPoint peer;
                    byte[] packet = Receive(requested ? transfer : listener, out peer);
                    if (packet == null) continue;
                    CheckPeer(peer);
                    if (packet.Length < 2) throw new InvalidOperationException("Truncated client packet");
                    ushort opcode = Word(packet, 0);
                    if (opcode == 1)
                    {
                        ValidateRequest(packet, true); discoveryCount++;
                        if (mode == "discovery_timeout" || (mode == "discovery_retry" && discoveryCount == 1)) continue;
                        Send(listener, new byte[] { 0, 3, 0, 1 }, peer); discovered = true; continue;
                    }
                    if (opcode == 2)
                    {
                        if (!discovered) throw new InvalidOperationException("WRQ arrived before discovery");
                        ValidateRequest(packet, false); requestCount++;
                        if (mode == "request_timeout" || (mode == "request_retry" && requestCount == 1)) continue;
                        if (mode == "server_error")
                        {
                            Send(listener, new byte[] { 0, 5, 0, 2, 100, 101, 110, 105, 101, 100, 0 }, peer); return;
                        }
                        if (mode == "changed_port" && !requested) transfer = NewSocket(bindAddress);
                        Send(transfer, Ack(0), peer); requested = true; continue;
                    }
                    if (opcode != 3 || !requested || packet.Length < 4 || packet.Length > 516) throw new InvalidOperationException("Expected DATA, not discovery ACK or another command");
                    Interlocked.Increment(ref dataPackets);
                    ushort block = Word(packet, 2);
                    if (previousPacket != null && block == previousBlock)
                    {
                        if (Convert.ToBase64String(packet) != Convert.ToBase64String(previousPacket)) throw new InvalidOperationException("Retransmission changed buffered DATA");
                        if (mode != "data_timeout" && mode != "cancel_upload") Send(transfer, Ack(block), peer);
                        continue;
                    }
                    if (block != expectedBlock) throw new InvalidOperationException("Unexpected DATA block number");
                    if (block == 0) rollover = true;
                    long offset = Interlocked.Read(ref bytesReceived);
                    for (int i = 4; i < packet.Length; i++)
                        if (packet[i] != (byte)((offset + i - 4) % 251)) { matches = false; throw new InvalidOperationException("Payload bytes differ"); }
                    Interlocked.Add(ref bytesReceived, packet.Length - 4);
                    previousPacket = packet; previousBlock = block; expectedBlock = unchecked((ushort)(block + 1));
                    if (mode == "cancel_upload" || mode == "data_timeout") continue;
                    if (mode == "data_retry" && !lostDataAck) { lostDataAck = true; continue; }
                    if (mode == "wrong_packets" && block == 1)
                    {
                        Send(transfer, Status(1), peer);
                        Send(transfer, Ack(65535), peer); Send(transfer, Ack(0), peer); Send(transfer, new byte[] { 0, 4 }, peer);
                    }
                    Send(transfer, Ack(block), peer);
                    if (packet.Length < 516)
                    {
                        finalLength = packet.Length - 4;
                        if (BytesReceived != expectedLength) throw new InvalidOperationException("Final DATA ended at wrong length");
                        finalAckSent = true;
                        AfterTransfer(peer); return;
                    }
                }
                if (!stopping) throw new TimeoutException("Simulator total deadline exceeded");
            }
            catch (Exception exception) { if (!stopping) error = exception.GetType().Name + ": " + exception.Message; }
        }

        public void Dispose()
        {
            stopping = true;
            listener.Close();
            if (!Object.ReferenceEquals(transfer, listener)) transfer.Close();
            if (!worker.Wait(3000)) throw new TimeoutException("Simulator worker failed to stop");
        }
    }
}
// <FILE>contrib/ac86u/tests/cls_AsusRecoverySimulator.cs</FILE> - <DESC>Local-only synthetic ASUS recovery peer for native protocol acceptance.</DESC>
// <VERS>END OF VERSION: 0.3.1</VERS>
