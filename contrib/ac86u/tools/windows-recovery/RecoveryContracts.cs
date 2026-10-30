// <FILE>contrib/ac86u/tools/windows-recovery/RecoveryContracts.cs</FILE> - <DESC>Options and detached status contract for the ASUS recovery session.</DESC>
// <VERS>VERSION: 0.1.2</VERS>
// <WCTX>Keep the PowerShell UI independent of UDP resources and background protocol execution.</WCTX>
// <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
namespace AsusRecovery
{
    public sealed class RecoveryOptions
    {
        public string FirmwarePath { get; set; }
        public string ExpectedSha256 { get; set; }
        public string SourceIP { get; set; }
        public string RouterIP { get; set; }
        public int Port { get; set; }
        public bool BroadcastDiscovery { get; set; }
        public int DiscoveryTimeoutMilliseconds { get; set; }
        public int RequestTimeoutMilliseconds { get; set; }
        public int DiscoveryRetryMilliseconds { get; set; }
        public int RequestRetryMilliseconds { get; set; }
        public int DataRetryMilliseconds { get; set; }
        public int DataAttempts { get; set; }
        public int TransferTimeoutMilliseconds { get; set; }
        public int DiscoverySettleMilliseconds { get; set; }
        public int FlashIdleTimeoutMilliseconds { get; set; }
        public int MaxFlashWaitMilliseconds { get; set; }

        public RecoveryOptions()
        {
            ExpectedSha256 = "";
            SourceIP = "192.168.1.10";
            RouterIP = "192.168.1.1";
            Port = 69;
            BroadcastDiscovery = true;
            DiscoveryTimeoutMilliseconds = 31000;
            RequestTimeoutMilliseconds = 11000;
            DiscoveryRetryMilliseconds = RequestRetryMilliseconds = 5000;
            DataRetryMilliseconds = 2000;
            DataAttempts = 6;
            TransferTimeoutMilliseconds = 600000;
            DiscoverySettleMilliseconds = 2000;
        }

        internal RecoveryOptions Copy() { return (RecoveryOptions)MemberwiseClone(); }
    }

    public sealed class RecoverySnapshot
    {
        public string Stage { get; internal set; }
        public string Message { get; internal set; }
        public string ErrorKind { get; internal set; }
        public long FileBytes { get; internal set; }
        public long AcknowledgedBytes { get; internal set; }
        public double Percent { get; internal set; }
        public string LocalEndpoint { get; internal set; }
        public string PeerEndpoint { get; internal set; }
        public int Retransmissions { get; internal set; }
        public int VendorStatus { get; internal set; }
        public bool Terminal { get; internal set; }

        internal RecoverySnapshot Copy() { return (RecoverySnapshot)MemberwiseClone(); }
    }
}
// <FILE>contrib/ac86u/tools/windows-recovery/RecoveryContracts.cs</FILE> - <DESC>Options and detached status contract for the ASUS recovery session.</DESC>
// <VERS>END OF VERSION: 0.1.2</VERS>
