/// Fixed backend location: the Lightsail server's Tailscale IP. Port 8000 is
/// not open on the public IP (13.200.209.203); the phone reaches the server
/// over Tailscale, which also encrypts the traffic. Change it here if the
/// server ever moves; users never type it.
class AppConfig {
  static const String backendHost = '100.102.217.43';
  static const int backendPort = 8000;

  /// The backend has a single account (APP_USERNAME in backend/.env).
  static const String username = 'admin';
}

// http/ws inside the Tailscale tunnel (WireGuard-encrypted). Public HTTPS is on
// hold; only needed if the server is ever exposed outside Tailscale.
const String kHttpBase = 'http://${AppConfig.backendHost}:${AppConfig.backendPort}';
const String kWsBase = 'ws://${AppConfig.backendHost}:${AppConfig.backendPort}';
