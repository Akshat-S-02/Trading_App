import 'package:shared_preferences/shared_preferences.dart';

class AppConfig {
  static String backendHost = "192.168.0.113"; // Default fallback
  static const int backendPort = 8003;

  static Future<void> loadHost() async {
    final prefs = await SharedPreferences.getInstance();
    backendHost = prefs.getString('backend_host') ?? "192.168.0.113";
  }

  static Future<void> saveHost(String host) async {
    final prefs = await SharedPreferences.getInstance();
    backendHost = host;
    await prefs.setString('backend_host', host);
  }
}

String get kHttpBase => "http://${AppConfig.backendHost}:${AppConfig.backendPort}";
String get kWsBase   => "ws://${AppConfig.backendHost}:${AppConfig.backendPort}";
