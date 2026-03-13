import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../services/auth_service.dart';
import '../app_config.dart';

/// Owns trading data only: portfolio, trade history, spending limits, balance.
/// Does NOT touch WebSocket, prices, or watchlist — those live in MarketDataProvider.
class TradingProvider with ChangeNotifier {
  // ── Portfolio ────────────────────────────────────────────────────────────────
  List<dynamic> _portfolio = [];
  List<dynamic> get portfolio => _portfolio;

  // ── Trade history ────────────────────────────────────────────────────────────
  List<dynamic> _trades = [];
  List<dynamic> get trades => _trades;

  // ── Spending limits & balance ────────────────────────────────────────────────
  double _dailyLimit = 0;
  double _monthlyLimit = 0;
  double _dailySpent = 0;
  double _monthlySpent = 0;
  double _balance = 0;

  double get dailyLimit   => _dailyLimit;
  double get monthlyLimit => _monthlyLimit;
  double get dailySpent   => _dailySpent;
  double get monthlySpent => _monthlySpent;
  double get balance      => _balance;

  final String _baseUrl = kHttpBase;
  bool _initialized = false;

  /// Fetch all protected trading data.
  /// Idempotent — safe to call from both LoginScreen and DashboardScreen.
  void initialize() {
    if (_initialized) return;
    _initialized = true;
    fetchUserLimits();
    fetchPortfolio();
    fetchTrades();
  }

  // ── Network calls ────────────────────────────────────────────────────────────

  Future<void> fetchPortfolio() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/portfolio'),
        headers: headers,
      );
      if (response.statusCode == 200) {
        _portfolio = jsonDecode(response.body);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching portfolio: $e');
    }
  }

  Future<void> fetchTrades() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/trades'),
        headers: headers,
      );
      if (response.statusCode == 200) {
        _trades = jsonDecode(response.body);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching trades: $e');
    }
  }

  Future<void> fetchUserLimits() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/admin/limits'),
        headers: headers,
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _dailyLimit   = (data['daily_limit']   ?? 0).toDouble();
        _monthlyLimit = (data['monthly_limit'] ?? 0).toDouble();
        _dailySpent   = (data['daily_spent']   ?? 0).toDouble();
        _monthlySpent = (data['monthly_spent'] ?? 0).toDouble();
        _balance      = (data['tokens']        ?? 0).toDouble();
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching limits: $e');
    }
  }

  Future<bool> setLimits(double daily, double monthly) async {
    try {
      final token = await AuthService.getToken();
      final response = await http.post(
        Uri.parse('$_baseUrl/api/admin/limits'),
        headers: {
          'Content-Type': 'application/json',
          if (token != null) 'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'max_daily_dd':   daily,
          'max_monthly_dd': monthly,
        }),
      );
      if (response.statusCode == 200) {
        await fetchUserLimits();
        return true;
      }
      debugPrint('❌ setLimits failed [${response.statusCode}]: ${response.body}');
    } catch (e) {
      debugPrint('❌ setLimits exception: $e');
    }
    return false;
  }
}
