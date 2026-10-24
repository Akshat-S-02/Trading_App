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

  /// Place a manual sandbox order via POST /api/trade/place.
  /// The backend fills at its own latest price and enforces balance,
  /// holdings and spend limits; on success all trading data is refreshed.
  Future<OrderResult> placeOrder({
    required String symbol,
    required String side,
    required double qty,
    double? stopLoss,
  }) async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.post(
        Uri.parse('$_baseUrl/api/trade/place'),
        headers: headers,
        body: jsonEncode({
          'symbol': symbol,
          'qty': qty,
          'side': side,
          if (stopLoss != null) 'stop_loss': stopLoss,
        }),
      );
      final body = response.body.isNotEmpty ? jsonDecode(response.body) : null;
      if (response.statusCode == 200 && body is Map) {
        await Future.wait([fetchUserLimits(), fetchPortfolio(), fetchTrades()]);
        return OrderResult(
          ok: true,
          message: '${body['message'] ?? 'Order executed'}',
          price: (body['price'] as num?)?.toDouble(),
          value: (body['value'] as num?)?.toDouble(),
        );
      }
      final detail = body is Map ? body['detail'] : null;
      return OrderResult(
        ok: false,
        message: detail != null ? '$detail' : 'Order rejected [${response.statusCode}]',
      );
    } catch (e) {
      debugPrint('❌ placeOrder exception: $e');
      return OrderResult(ok: false, message: 'Could not reach backend');
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
          'daily_limit':   daily,
          'monthly_limit': monthly,
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

class OrderResult {
  final bool ok;
  final String message;
  final double? price;
  final double? value;

  OrderResult({required this.ok, required this.message, this.price, this.value});
}
