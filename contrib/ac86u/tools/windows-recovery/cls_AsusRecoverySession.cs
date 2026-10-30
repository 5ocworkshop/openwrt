// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoverySession.cs</FILE> - <DESC>Asynchronous ASUS discovery, upload and router-status lifecycle.</DESC>
// <VERS>VERSION: 0.1.3</VERS>
// <WCTX>Keep one UDP endpoint alive until the router reports its flash outcome.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace AsusRecovery
{
    public sealed class RecoverySession : IDisposable
    {
        private readonly object gate = new object();
        private readonly RecoveryOptions options;
        private readonly Stopwatch clock = new Stopwatch();
        private readonly RecoverySnapshot status = new RecoverySnapshot { Stage = "ready", Message = "Ready.", ErrorKind = "", VendorStatus = -1 };
        private readonly IPAddress source, router;
        private volatile bool cancelled;
        private RecoveryChannel channel;
        private Task worker;

        public RecoverySession(RecoveryOptions requested)
        {
            if (requested == null) throw new ArgumentNullException("requested");
            options = requested.Copy();
            if (!String.IsNullOrEmpty(options.ExpectedSha256))
            {
                if (options.ExpectedSha256.Length != 64) throw new ArgumentException("Expected SHA256 must contain exactly 64 hexadecimal characters.");
                foreach (char c in options.ExpectedSha256)
                    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
                        throw new ArgumentException("Expected SHA256 must contain exactly 64 hexadecimal characters.");
            }
            source = IPAddress.Parse(options.SourceIP); router = IPAddress.Parse(options.RouterIP);
            if (source.AddressFamily != AddressFamily.InterNetwork || router.AddressFamily != AddressFamily.InterNetwork)
                throw new ArgumentException("Local and router addresses must be IPv4.");
            if (String.IsNullOrWhiteSpace(options.FirmwarePath) || options.Port < 1 || options.Port > 65535)
                throw new ArgumentException("A firmware path and valid UDP port are required.");
            int[] positive = { options.DiscoveryTimeoutMilliseconds, options.RequestTimeoutMilliseconds,
                options.DiscoveryRetryMilliseconds, options.RequestRetryMilliseconds, options.DataRetryMilliseconds,
                options.DataAttempts, options.TransferTimeoutMilliseconds };
            foreach (int value in positive) if (value <= 0) throw new ArgumentException("Timeouts and attempts must be positive.");
            if (options.DataAttempts > 100 || options.DiscoverySettleMilliseconds < 0 || options.DiscoverySettleMilliseconds > 60000 ||
                options.FlashIdleTimeoutMilliseconds < 0 || options.MaxFlashWaitMilliseconds < 0)
                throw new ArgumentException("Invalid recovery timing options.");
        }

        public bool IsStopped { get { lock (gate) return worker == null || worker.IsCompleted; } }
        public RecoverySnapshot GetSnapshot() { lock (gate) return status.Copy(); }

        public void Start()
        {
            lock (gate)
            {
                if (worker != null || status.Terminal) throw new InvalidOperationException("A session can only be started once.");
                status.Stage = "discovering"; status.Message = "Discovering the configured router.";
                clock.Start();
                worker = Task.Factory.StartNew(Run, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
            }
        }

        public void Cancel()
        {
            RecoveryChannel owned;
            lock (gate)
            {
                if (status.Terminal) return;
                cancelled = true; owned = channel;
                if (worker == null) Finish("cancelled", "Recovery cancelled before starting.", "cancelled");
            }
            if (owned != null) owned.Dispose();
        }

        public void Dispose()
        {
            Cancel();
            Task current;
            lock (gate) current = worker;
            if (current != null && !current.Wait(5000))
                throw new TimeoutException("Recovery worker is still stopping; no new session may be started.");
        }

        private void CheckCancellation()
        {
            if (cancelled) throw new OperationCanceledException();
        }

        private void CheckTransferTime()
        {
            CheckCancellation();
            if (clock.ElapsedMilliseconds >= options.TransferTimeoutMilliseconds)
                throw new ProtocolFailure("transfer_timeout", "The overall discovery/upload time limit expired.");
        }

        private void Stage(string value, string message)
        {
            lock (gate)
            {
                if (status.Terminal) return;
                status.Stage = value; status.Message = message;
            }
        }

        private void Finish(string value, string message, string error)
        {
            lock (gate)
            {
                if (status.Terminal) return;
                if (cancelled && value != "cancelled")
                {
                    value = "cancelled";
                    message = status.Stage == "waiting_for_flash" ? "Monitoring stopped. The router may still be writing flash." : "Recovery upload cancelled.";
                    error = "cancelled";
                }
                status.Stage = value; status.Message = message; status.ErrorKind = error; status.Terminal = true;
            }
        }

        private IPEndPoint Exchange(byte[] request, IPEndPoint destination, IPEndPoint expected,
            bool allowNewPort, ushort opcode, ushort code, int retry, long timeout, string errorKind)
        {
            long deadline = clock.ElapsedMilliseconds + timeout;
            long nextSend = 0;
            bool sent = false;
            while (clock.ElapsedMilliseconds < deadline)
            {
                CheckTransferTime();
                if (clock.ElapsedMilliseconds >= nextSend)
                {
                    channel.Send(request, destination);
                    if (sent) { lock (gate) status.Retransmissions++; }
                    sent = true; nextSend = clock.ElapsedMilliseconds + retry;
                }
                IPEndPoint sender;
                int wait = (int)Math.Max(1L, Math.Min(100L, deadline - clock.ElapsedMilliseconds));
                byte[] packet = channel.Receive(wait, expected, allowNewPort, out sender);
                CheckTransferTime();
                if (clock.ElapsedMilliseconds >= deadline) break;
                if (packet == null || packet.Length < 4) continue;
                if (RecoveryPackets.Opcode(packet) == 5)
                    throw new ProtocolFailure("server_error", "Router TFTP error " + RecoveryPackets.Code(packet) + ": " +
                        Encoding.ASCII.GetString(packet, 4, Math.Min(256, packet.Length - 4)).TrimEnd('\0'));
                if (RecoveryPackets.Opcode(packet) == opcode && RecoveryPackets.Code(packet) == code) return sender;
            }
            throw new ProtocolFailure(errorKind, "Timed out during " + GetSnapshot().Stage + ".");
        }

        private void Run()
        {
            try
            {
                CheckCancellation();
                using (FileStream file = new FileStream(options.FirmwarePath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (file.Length == 0) throw new ProtocolFailure("local_file", "Firmware file is empty.");
                    lock (gate) status.FileBytes = file.Length;
                    VerifySelectedImage(file);
                    RecoveryChannel created = new RecoveryChannel(source);
                    lock (gate) { channel = created; status.LocalEndpoint = created.LocalEndpoint; }
                    CheckCancellation();
                    IPEndPoint configured = new IPEndPoint(router, options.Port);
                    IPEndPoint discovery = new IPEndPoint(options.BroadcastDiscovery ? IPAddress.Broadcast : router, options.Port);
                    Exchange(RecoveryPackets.BuildDiscovery(router), discovery, configured, false, 3, 1,
                        options.DiscoveryRetryMilliseconds, options.DiscoveryTimeoutMilliseconds, "discovery_timeout");
                    long settle = clock.ElapsedMilliseconds + options.DiscoverySettleMilliseconds;
                    while (clock.ElapsedMilliseconds < settle) { CheckTransferTime(); Thread.Sleep(20); }
                    Stage("requesting_upload", "Router discovered; requesting ASUSSPACELINK upload.");
                    IPEndPoint peer = Exchange(RecoveryPackets.BuildWriteRequest(), configured, configured, true, 4, 0,
                        options.RequestRetryMilliseconds, options.RequestTimeoutMilliseconds, "request_timeout");
                    lock (gate) status.PeerEndpoint = peer.ToString();
                    Stage("uploading", "Uploading firmware bytes.");
                    Transfer(file, peer);
                    Stage("waiting_for_flash", "Upload complete; waiting for the router's flash result. Keep power connected.");
                    WaitForFlash(peer, file.Length);
                }
            }
            catch (Exception error)
            {
                if (cancelled)
                {
                    bool delivered;
                    lock (gate) delivered = status.Stage == "waiting_for_flash";
                    Finish("cancelled", delivered ? "Monitoring stopped. The router may still be writing flash." : "Recovery upload cancelled.", "cancelled");
                }
                else
                {
                    ProtocolFailure protocol = error as ProtocolFailure;
                    string kind = protocol != null ? protocol.Kind : error is SocketException ? "network" :
                        error is IOException || error is UnauthorizedAccessException ? "local_file" :
                        error is ArgumentException ? "invalid_input" : "internal";
                    Finish("failed", error.Message, kind);
                }
            }
            finally
            {
                RecoveryChannel owned;
                lock (gate) owned = channel;
                if (owned != null) owned.Dispose();
            }
        }

        private void VerifySelectedImage(FileStream file)
        {
            if (String.IsNullOrEmpty(options.ExpectedSha256)) return;
            Stage("discovering", "Verifying the selected firmware SHA256 before network activity.");
            using (SHA256 hash = SHA256.Create())
            {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = file.Read(buffer, 0, buffer.Length)) != 0)
                {
                    CheckCancellation();
                    hash.TransformBlock(buffer, 0, count, buffer, 0);
                }
                hash.TransformFinalBlock(new byte[0], 0, 0);
                CheckCancellation();
                string actual = BitConverter.ToString(hash.Hash).Replace("-", "");
                if (!String.Equals(actual, options.ExpectedSha256, StringComparison.OrdinalIgnoreCase))
                    throw new ProtocolFailure("image_changed", "The firmware image changed since selection. Select it again before uploading. No packets were sent.");
            }
            file.Position = 0;
            Stage("discovering", "Firmware SHA256 verified. Discovering the configured router.");
        }

        private void Transfer(FileStream file, IPEndPoint peer)
        {
            byte[] payload = new byte[512];
            ushort block = 1;
            while (true)
            {
                CheckTransferTime();
                int count = 0;
                while (count < payload.Length)
                {
                    int read = file.Read(payload, count, payload.Length - count);
                    if (read == 0) break;
                    count += read;
                }
                Exchange(RecoveryPackets.BuildData(block, payload, count), peer, peer, false, 4, block,
                    options.DataRetryMilliseconds, (long)options.DataRetryMilliseconds * options.DataAttempts, "transfer_timeout");
                lock (gate)
                {
                    status.AcknowledgedBytes += count;
                    status.Percent = Math.Min(100, status.AcknowledgedBytes * 100.0 / status.FileBytes);
                }
                if (count < 512) return;
                block = unchecked((ushort)(block + 1));
            }
        }

        private void WaitForFlash(IPEndPoint peer, long bytes)
        {
            long idle = options.FlashIdleTimeoutMilliseconds > 0 ? options.FlashIdleTimeoutMilliseconds :
                (450L + 24L * (bytes / 1048576L)) * 1000L;
            long maximum = options.MaxFlashWaitMilliseconds > 0 ? options.MaxFlashWaitMilliseconds : Math.Max(1800000L, idle * 3L);
            long absolute = clock.ElapsedMilliseconds + maximum;
            long deadline = clock.ElapsedMilliseconds + idle;
            while (clock.ElapsedMilliseconds < deadline && clock.ElapsedMilliseconds < absolute)
            {
                CheckCancellation();
                IPEndPoint sender;
                int wait = (int)Math.Max(1L, Math.Min(100L, Math.Min(deadline, absolute) - clock.ElapsedMilliseconds));
                byte[] packet = channel.Receive(wait, peer, false, out sender);
                CheckCancellation();
                if (clock.ElapsedMilliseconds >= deadline || clock.ElapsedMilliseconds >= absolute) break;
                if (packet == null || packet.Length < 4) continue;
                ushort opcode = RecoveryPackets.Opcode(packet), code = RecoveryPackets.Code(packet);
                if (opcode == 5) throw new ProtocolFailure("server_error", "Router reported a TFTP error after upload: " + code);
                if (opcode != 6) continue;
                // ASCII option-negotiation OACKs are not binary ASUS flash status.
                if (packet.Length > 4 && packet[2] != 0) continue;
                lock (gate) status.VendorStatus = code;
                if (code == 1)
                {
                    Finish("recovery_success", "Router reports recovery succeeded. Waiting for reboot; operating-system readiness is not confirmed.", "");
                    return;
                }
                if (code != 3) throw new ProtocolFailure("flash_rejected", "Router reports recovery failed (ASUS status " + code + ").");
                deadline = clock.ElapsedMilliseconds + idle;
                Stage("waiting_for_flash", "Router reports firmware programming in progress. Keep power connected.");
            }
            throw new ProtocolFailure("flash_timeout", "Upload completed, but no successful router flash result arrived before the wait limit.");
        }

        private sealed class ProtocolFailure : Exception
        {
            internal string Kind { get; private set; }
            internal ProtocolFailure(string kind, string message) : base(message) { Kind = kind; }
        }
    }
}
// <FILE>contrib/ac86u/tools/windows-recovery/cls_AsusRecoverySession.cs</FILE> - <DESC>Asynchronous ASUS discovery, upload and router-status lifecycle.</DESC>
// <VERS>END OF VERSION: 0.1.3</VERS>
