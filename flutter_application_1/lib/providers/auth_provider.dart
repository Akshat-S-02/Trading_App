import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../app_config.dart';
import '../services/auth_service.dart';

/// Thin ChangeNotifier wrapper around [AuthService].
/// Exposes [isLoggedIn] so widgets can reactively respond to auth state changes.
class AuthProvider with ChangeNotifier {
  bool _isLoggedIn = false;
  bool get isLoggedIn => _isLoggedIn;

  String? _error;
  String? get error => _error;

  bool _loading = false;
  bool get loading => _loading;

  /// Initialise from a pre-checked token (called in main()).
  AuthProvider({required bool isLoggedIn}) : _isLoggedIn = isLoggedIn;

  /// Login with username + password. Returns true on success.
  Future<bool> login(String username, String password) async {
    _loading = true;
    _error = null;
    notifyListeners();
    
    // 1. Pre-flight health check
    try {
      final res = await http.get(Uri.parse(kHttpBase)).timeout(const Duration(seconds: 3));
      if (res.statusCode != 200) {
        throw Exception("Backend returned ${res.statusCode}");
      }
    } catch (e) {
      _error = '❌ Cannot reach backend at ${AppConfig.backendHost}\nCheck that:\n• Backend is running\n• Phone and PC are on same Wi-Fi\n• Port ${AppConfig.backendPort} is correct';
      _isLoggedIn = false;
      _loading = false;
      notifyListeners();
      return false;
    }

    // 2. Actual authentication
    try {
      await AuthService.login(username, password);
      _isLoggedIn = true;
      _loading = false;
      notifyListeners();
      return true;
    } catch (e) {
      if (e.toString().contains('Invalid credentials')) {
        _error = 'Wrong password. Try again.';
      } else {
        _error = 'Connection dropped during login.';
      }
      _isLoggedIn = false;
      _loading = false;
      notifyListeners();
      return false;
    }
  }

  /// Logout — clears the stored token and updates state.
  Future<void> logout() async {
    await AuthService.logout();
    _isLoggedIn = false;
    notifyListeners();
  }
}
