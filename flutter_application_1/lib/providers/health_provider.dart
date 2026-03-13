import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../services/auth_service.dart';
import '../app_config.dart';

class HealthProvider with ChangeNotifier {
  final String _baseUrl = kHttpBase;
  Timer? _pollingTimer;

  bool _isBackendReachable = false;
  Map<String, dynamic> _tokenData = {};
  Map<String, dynamic> _feedData = {};

  bool get isBackendReachable => _isBackendReachable;
  Map<String, dynamic> get tokenData => _tokenData;
  Map<String, dynamic> get feedData => _feedData;

  bool get isTokenValid => _tokenData['valid'] ?? false;
  bool get isFeedConnected => _feedData['connected'] ?? false;
  int get feedReconnectCount => _feedData['reconnect_count'] ?? 0;
  
  double get lastTickAgeSec {
    final lastStr = _feedData['last_tick_time'];
    if (lastStr == null) return double.infinity;
    try {
      final lastTime = DateTime.parse(lastStr);
      final age = DateTime.now().toUtc().difference(lastTime);
      return age.inMilliseconds / 1000.0;
    } catch (_) {
      return double.infinity;
    }
  }

  bool get isFeedHealthy => isFeedConnected && lastTickAgeSec < 5.0;

  void startPolling() {
    if (_pollingTimer != null) return;
    _fetchHealth(); // initial fetch
    _pollingTimer = Timer.periodic(const Duration(seconds: 5), (_) => _fetchHealth());
  }

  void stopPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = null;
  }

  Future<void> _fetchHealth() async {
    try {
      final token = await AuthService.getToken();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/admin/health'),
        headers: {
          if (token != null) 'Authorization': 'Bearer $token',
        },
      ).timeout(const Duration(seconds: 3));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _isBackendReachable = true;
        _tokenData = data['token'] ?? {};
        _feedData = data['feed'] ?? {};
      } else {
        _isBackendReachable = false;
        _feedData = {};
      }
    } catch (e) {
      _isBackendReachable = false;
      _feedData = {};
    }
    notifyListeners();
  }

  @override
  void dispose() {
    stopPolling();
    super.dispose();
  }
}
