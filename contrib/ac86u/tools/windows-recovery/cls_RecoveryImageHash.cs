// <FILE>contrib/ac86u/tools/windows-recovery/cls_RecoveryImageHash.cs</FILE> - <DESC>Cancellable background SHA256 preview with detached image identity snapshots.</DESC>
// <VERS>VERSION: 0.1.1</VERS>
// <WCTX>Show the selected firmware digest without blocking Windows Forms or sharing recovery socket ownership.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
using System;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace AsusRecovery
{
    public sealed class RecoveryImageHashSnapshot
    {
        public string Hash { get; internal set; }
        public string Path { get; internal set; }
        public long Length { get; internal set; }
        public DateTime LastWriteUtc { get; internal set; }
        public long BytesRead { get; internal set; }
        public string Error { get; internal set; }
        public bool Terminal { get; internal set; }
        internal RecoveryImageHashSnapshot Copy() { return (RecoveryImageHashSnapshot)MemberwiseClone(); }
    }

    public sealed class RecoveryImageHash : IDisposable
    {
        private readonly object gate = new object();
        private readonly RecoveryImageHashSnapshot status;
        private readonly Task worker;
        private volatile bool cancelled;

        public RecoveryImageHash(string path)
        {
            if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("Choose a firmware file.");
            status = new RecoveryImageHashSnapshot { Path = System.IO.Path.GetFullPath(path), Hash = "", Error = "" };
            worker = Task.Factory.StartNew(Run, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        }

        public bool IsStopped { get { return worker.IsCompleted; } }
        public RecoveryImageHashSnapshot GetSnapshot() { lock (gate) return status.Copy(); }
        public void Cancel() { cancelled = true; }
        public void Dispose()
        {
            Cancel();
            if (!worker.Wait(5000)) throw new TimeoutException("The previous file read is still stopping. No new hash job may start yet.");
        }

        private void CheckCancellation()
        {
            if (cancelled) throw new OperationCanceledException("Image hash cancelled.");
        }

        private void Run()
        {
            try
            {
                CheckCancellation();
                using (FileStream file = new FileStream(status.Path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, FileOptions.SequentialScan))
                using (SHA256 sha = SHA256.Create())
                {
                    long length = file.Length;
                    DateTime lastWrite = File.GetLastWriteTimeUtc(status.Path);
                    if (length == 0) throw new IOException("Choose a nonempty firmware file.");
                    lock (gate) { status.Length = length; status.LastWriteUtc = lastWrite; }
                    byte[] buffer = new byte[262144];
                    int count;
                    while (true)
                    {
                        CheckCancellation();
                        count = file.Read(buffer, 0, buffer.Length);
                        CheckCancellation();
                        if (count == 0) break;
                        sha.TransformBlock(buffer, 0, count, buffer, 0);
                        lock (gate) status.BytesRead += count;
                    }
                    sha.TransformFinalBlock(new byte[0], 0, 0);
                    CheckCancellation();
                    if (file.Length != length || File.GetLastWriteTimeUtc(status.Path) != lastWrite)
                        throw new IOException("The image changed while calculating its checksum. Select it again.");
                    string digest = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                    lock (gate) status.Hash = digest;
                }
            }
            catch (Exception error)
            {
                lock (gate) { status.Hash = ""; status.Error = error.Message; }
            }
            finally { lock (gate) status.Terminal = true; }
        }
    }
}
// <FILE>contrib/ac86u/tools/windows-recovery/cls_RecoveryImageHash.cs</FILE> - <DESC>Cancellable background SHA256 preview with detached image identity snapshots.</DESC>
// <VERS>END OF VERSION: 0.1.1</VERS>
