import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../services/auth_service.dart';
import '../app_config.dart';

/// Result of a user action (order, close, etc.) for UI feedback.
class ActionResult {
  final bool ok;
  final String message;
  const ActionResult(this.ok, this.message);
}

/// Owns trading data only: positions, trade history, spending limits, balance,
/// automation state and manual order actions.
/// Does NOT touch WebSocket, prices, or watchlist — those live in MarketDataProvider.
class TradingProvider with ChangeNotifier {
  // ── Portfolio metrics ────────────────────────────────────────────────────────
  Map<String, dynamic> _portfolioMetrics = {};
  Map<String, dynamic> get portfolioMetrics => _portfolioMetrics;

  // ── Open positions & pending orders ─────────────────────────────────────────
  List<Map<String, dynamic>> _positions = [];
  List<Map<String, dynamic>> get positions => _positions;

  List<Map<String, dynamic>> _pendingOrders = [];
  List<Map<String, dynamic>> get pendingOrders => _pendingOrders;

  String _executionMode = 'paper';
  String get executionMode => _executionMode;

  bool _emergencyStop = false;
  bool get emergencyStop => _emergencyStop;

  /// Ids with a close request in flight (to disable the button)
  final Set<int> _closing = {};
  bool isClosing(int id) => _closing.contains(id);

  // ── Trade history ────────────────────────────────────────────────────────────
  List<dynamic> _trades = [];
  List<dynamic> get trades => _trades;

  // ── Spending limits & balance ────────────────────────────────────────────────
  double _dailyLimit = 0;
  double _monthlyLimit = 0;
  double _dailySpent = 0;
  double _monthlySpent = 0;
  double _balance = 0;

  Map<String, dynamic> _paperStatus = {};
  Map<String, dynamic> get paperStatus => _paperStatus;

  bool get autoRunning =>
      _paperStatus['runner_enabled'] == true && _paperStatus['runner_paused'] != true;

  double get dailyLimit   => _dailyLimit;
  double get monthlyLimit => _monthlyLimit;
  double get dailySpent   => _dailySpent;
  double get monthlySpent => _monthlySpent;
  double get balance      => _balance;

  final String _baseUrl = kHttpBase;
  bool _initialized = false;
  Timer? _pollTimer;

  /// Fetch all protected trading data and start live polling.
  /// Idempotent — safe to call from both LoginScreen and DashboardScreen.
  void initialize() {
    if (_initialized) return;
    _initialized = true;
    fetchUserLimits();
    refreshAll();
    // Positions, fills and automation state change server-side; keep them fresh.
    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      fetchPositions();
      fetchPaperStatus();
    });
  }

  Future<void> refreshAll() async {
    await Future.wait([
      fetchPortfolio(),
      fetchPositions(),
      fetchTrades(),
      fetchPaperStatus(),
    ]);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  static String _errorOf(http.Response r) {
    try {
      final body = jsonDecode(r.body);
      final detail = body is Map ? body['detail'] : null;
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] != null) return first['msg'].toString();
      }
    } catch (_) {}
    return 'Request failed (${r.statusCode})';
  }

  Future<http.Response> _post(String path, [Object? body]) async {
    final headers = await AuthService.authHeaders();
    return http
        .post(Uri.parse('$_baseUrl$path'),
            headers: headers, body: body == null ? null : jsonEncode(body))
        .timeout(const Duration(seconds: 10));
  }

  // ── Reads ────────────────────────────────────────────────────────────────────

  Future<void> fetchPortfolio() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/portfolio'),
        headers: headers,
      );
      AuthService.checkAuth(response);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data is Map<String, dynamic>) {
          _portfolioMetrics = data;
        }
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching portfolio: $e');
    }
  }

  Future<void> fetchPositions() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/trade/positions'),
        headers: headers,
      );
      AuthService.checkAuth(response);
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final prevOpen = _positions.length;
        _positions = List<Map<String, dynamic>>.from(data['positions'] ?? []);
        _pendingOrders = List<Map<String, dynamic>>.from(data['pending'] ?? []);
        _executionMode = (data['execution_mode'] ?? 'paper').toString();
        _emergencyStop = data['emergency_stop'] == true;
        // A position closed server-side (SL / target / EOD): refresh P&L + history
        if (_positions.length < prevOpen) {
          fetchPortfolio();
          fetchTrades();
        }
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching positions: $e');
    }
  }

  Future<void> fetchTrades() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/trades'),
        headers: headers,
      );
      AuthService.checkAuth(response);
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
      AuthService.checkAuth(response);
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
      final response = await _post('/api/admin/limits', {
        'max_daily_dd':   daily,
        'max_monthly_dd': monthly,
      });
      AuthService.checkAuth(response);
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

  Future<void> fetchPaperStatus() async {
    try {
      final headers = await AuthService.authHeaders();
      final response = await http.get(
        Uri.parse('$_baseUrl/api/paper/status'),
        headers: headers,
      );
      AuthService.checkAuth(response);
      if (response.statusCode == 200) {
        _paperStatus = jsonDecode(response.body);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching paper status: $e');
    }
  }

  // ── Manual trading ───────────────────────────────────────────────────────────

  Future<ActionResult> placeOrder({
    required String symbol,
    required int qty,
    required String side,
    double? stopLoss,
    double? target,
  }) async {
    try {
      final r = await _post('/api/trade/order', {
        'symbol': symbol,
        'qty': qty,
        'side': side,
        if (stopLoss != null) 'stop_loss': stopLoss,
        if (target != null) 'target': target,
      });
      AuthService.checkAuth(r);
      if (r.statusCode == 200) {
        await Future.wait([fetchPositions(), fetchTrades()]);
        return ActionResult(true, '$side $qty × ${symbol.split('.').first} placed');
      }
      return ActionResult(false, _errorOf(r));
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }

  Future<ActionResult> closePosition(int orderId) async {
    _closing.add(orderId);
    notifyListeners();
    try {
      final r = await _post('/api/trade/positions/$orderId/close');
      AuthService.checkAuth(r);
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body);
        final pnl = (data['pnl'] as num?)?.toDouble() ?? 0;
        await refreshAll();
        return ActionResult(true,
            'Position closed. P&L ${pnl >= 0 ? '+' : '-'}₹${pnl.abs().toStringAsFixed(2)}');
      }
      return ActionResult(false, _errorOf(r));
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    } finally {
      _closing.remove(orderId);
      notifyListeners();
    }
  }

  Future<ActionResult> updateBracket(int orderId, {double? stopLoss, double? target}) async {
    try {
      final headers = await AuthService.authHeaders();
      final r = await http
          .patch(Uri.parse('$_baseUrl/api/trade/positions/$orderId'),
              headers: headers,
              body: jsonEncode({'stop_loss': stopLoss, 'target': target}))
          .timeout(const Duration(seconds: 10));
      AuthService.checkAuth(r);
      if (r.statusCode == 200) {
        await fetchPositions();
        return const ActionResult(true, 'Stop-loss / target updated');
      }
      return ActionResult(false, _errorOf(r));
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }

  // ── Automation & safety ──────────────────────────────────────────────────────

  Future<ActionResult> setAutomation(bool run) async {
    try {
      final r = await _post(run ? '/api/paper/start' : '/api/paper/pause');
      await fetchPaperStatus();
      AuthService.checkAuth(r);
      if (r.statusCode == 200) {
        return ActionResult(true, run ? 'Auto-trading started' : 'Auto-trading paused');
      }
      return ActionResult(false, _errorOf(r));
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }

  /// Trip the global kill switch. Optionally square off every open position
  /// first (while prices are still flowing).
  Future<ActionResult> tripEmergencyStop({required bool closeAll}) async {
    int closed = 0;
    final failures = <String>[];
    if (closeAll) {
      for (final p in List<Map<String, dynamic>>.from(_positions)) {
        final res = await closePosition(p['id'] as int);
        if (res.ok) {
          closed++;
        } else {
          failures.add('${p['symbol']}: ${res.message}');
        }
      }
    }
    try {
      final r = await _post('/api/admin/emergency-stop');
      await refreshAll();
      AuthService.checkAuth(r);
      if (r.statusCode != 200) return ActionResult(false, _errorOf(r));
      var msg = 'Emergency stop active. New orders blocked.';
      if (closeAll) msg += ' Closed $closed position(s).';
      if (failures.isNotEmpty) msg += ' Failed: ${failures.join('; ')}';
      return ActionResult(failures.isEmpty, msg);
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }

  Future<ActionResult> clearEmergencyStop() async {
    try {
      final r = await _post('/api/admin/emergency-stop/clear');
      await fetchPositions();
      AuthService.checkAuth(r);
      if (r.statusCode == 200) {
        return const ActionResult(true,
            'Emergency stop cleared. New orders allowed again.');
      }
      return ActionResult(false, _errorOf(r));
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }
}
