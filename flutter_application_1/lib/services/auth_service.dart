import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../app_config.dart';

class AuthService {
  static const _tokenKey = 'auth_token';

  /// Set in main(): shows the login screen when the session has expired.
  static void Function()? onSessionExpired;
  static bool _expiring = false;

  /// Pass every response from a protected endpoint through this. A 401 means
  /// the 24 h login token expired (or the server restarted with a new secret):
  /// clear it and send the user to the login screen, once.
  static void checkAuth(http.Response r) {
    if (r.statusCode != 401 || _expiring) return;
    _expiring = true;
    logout();
    onSessionExpired?.call();
  }

  /// Login — returns the token or throws on failure.
  static Future<String> login(String username, String password) async {
    final response = await http.post(
      Uri.parse('$kHttpBase/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final token = data['access_token'] as String;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
      _expiring = false;
      return token;
    } else if (response.statusCode == 429) {
      throw Exception('Too many attempts');
    } else {
      throw Exception('Invalid credentials');
    }
  }

  /// Retrieve stored token (null if not logged in).
  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  /// Clear stored token.
  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  /// Auth headers to attach to every protected API call.
  static Future<Map<String, String>> authHeaders() async {
    final token = await getToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }
}
