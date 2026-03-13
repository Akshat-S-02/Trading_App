import 'package:flutter/foundation.dart';
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
        _error = 'Connection failed. Is the backend running on 0.0.0.0?';
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
