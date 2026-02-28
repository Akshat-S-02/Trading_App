/// Central configuration — change ONE line to switch between device and emulator.
///
/// Android Emulator : 10.0.2.2
/// Physical Device  : 172.20.10.2  (your hotspot/LAN IP)
library app_config;

// ─── Change only this line ───────────────────────────────────────────────────
// const String kBackendHost ="192.168.0.110";
    // "192.168.0.107";
const String kBackendHost = "10.0.2.2";  // ← uncomment for emulator
// ─────────────────────────────────────────────────────────────────────────────

const int    kBackendPort = 8000;

const String kHttpBase = "http://$kBackendHost:$kBackendPort";
const String kWsBase   = "ws://$kBackendHost:$kBackendPort";
