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

  /// A risk guard (loss limit, losing streak, broker rejections) switched
  /// auto-trading off. Only [resumeAutomation] turns it back on.
  bool get autoHalted => _paperStatus['automation_enabled'] == false;

  bool get autoRunning =>
      _paperStatus['runner_enabled'] == true && _paperStatus['runner_paused'] != true && !autoHalted;

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

  /// GET [path] -> decoded JSON; null on a network error or non-200.
  Future<dynamic> _getJson(String path) async {
    try {
      final r = await http
          .get(Uri.parse('$_baseUrl$path'), headers: await AuthService.authHeaders())
          .timeout(const Duration(seconds: 10));
      AuthService.checkAuth(r);
      if (r.statusCode == 200) return jsonDecode(r.body);
    } catch (e) {
      debugPrint('GET $path failed: $e');
    }
    return null;
  }

  /// 200 -> ok with [okMessage]; otherwise the server's error message.
  ActionResult _result(http.Response r, String okMessage) {
    AuthService.checkAuth(r);
    return r.statusCode == 200 ? ActionResult(true, okMessage) : ActionResult(false, _errorOf(r));
  }

  /// Runs a user action; a network error becomes a failed result instead of a throw.
  Future<ActionResult> _guard(Future<ActionResult> Function() action) async {
    try {
      return await action();
    } catch (e) {
      return ActionResult(false, 'Could not reach the backend: $e');
    }
  }

  // ── Reads ────────────────────────────────────────────────────────────────────

  Future<void> fetchPortfolio() async {
    final data = await _getJson('/api/portfolio');
    if (data is! Map<String, dynamic>) return;
    _portfolioMetrics = data;
    notifyListeners();
  }

  Future<void> fetchPositions() async {
    final data = await _getJson('/api/trade/positions');
    if (data is! Map<String, dynamic>) return;
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

  Future<void> fetchTrades() async {
    final data = await _getJson('/api/trades');
    if (data is! List) return;
    _trades = data;
    notifyListeners();
  }

  Future<void> fetchUserLimits() async {
    final data = await _getJson('/api/admin/limits');
    if (data is! Map) return;
    double val(String k) => (data[k] ?? 0).toDouble();
    _dailyLimit = val('daily_limit');
    _monthlyLimit = val('monthly_limit');
    _dailySpent = val('daily_spent');
    _monthlySpent = val('monthly_spent');
    _balance = val('tokens');
    notifyListeners();
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
    final data = await _getJson('/api/paper/status');
    if (data is! Map<String, dynamic>) return;
    _paperStatus = data;
    notifyListeners();
  }

  // ── Manual trading ───────────────────────────────────────────────────────────

  Future<ActionResult> placeOrder({
    required String symbol,
    required int qty,
    required String side,
    double? stopLoss,
    double? target,
  }) => _guard(() async {
    final r = await _post('/api/trade/order', {
      'symbol': symbol,
      'qty': qty,
      'side': side,
      if (stopLoss != null) 'stop_loss': stopLoss,
      if (target != null) 'target': target,
    });
    if (r.statusCode == 200) await Future.wait([fetchPositions(), fetchTrades()]);
    return _result(r, '$side $qty × ${symbol.split('.').first} placed');
  });

  Future<ActionResult> closePosition(int orderId) async {
    _closing.add(orderId);
    notifyListeners();
    try {
      return await _guard(() async {
        final r = await _post('/api/trade/positions/$orderId/close');
        if (r.statusCode != 200) return _result(r, '');
        final pnl = (jsonDecode(r.body)['pnl'] as num?)?.toDouble() ?? 0;
        await refreshAll();
        return ActionResult(true, 'Position closed. P&L ${pnl >= 0 ? '+' : '-'}₹${pnl.abs().toStringAsFixed(2)}');
      });
    } finally {
      _closing.remove(orderId);
      notifyListeners();
    }
  }

  Future<ActionResult> updateBracket(int orderId, {double? stopLoss, double? target}) => _guard(() async {
    final r = await http
        .patch(Uri.parse('$_baseUrl/api/trade/positions/$orderId'),
            headers: await AuthService.authHeaders(),
            body: jsonEncode({'stop_loss': stopLoss, 'target': target}))
        .timeout(const Duration(seconds: 10));
    if (r.statusCode == 200) await fetchPositions();
    return _result(r, 'Stop-loss / target updated');
  });

  // ── Automation & safety ──────────────────────────────────────────────────────

  Future<ActionResult> setAutomation(bool run) => _guard(() async {
    final r = await _post(run ? '/api/paper/start' : '/api/paper/pause');
    await fetchPaperStatus();
    return _result(r, run ? 'Auto-trading started' : 'Auto-trading paused');
  });

  Future<ActionResult> resumeAutomation() => _guard(() async {
    final r = await _post('/api/admin/automation/enable');
    await fetchPaperStatus();
    return _result(r, 'Auto-trading resumed');
  });

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
    return _guard(() async {
      final r = await _post('/api/admin/emergency-stop');
      await refreshAll();
      if (r.statusCode != 200) return _result(r, '');
      var msg = 'Emergency stop active. New orders blocked.';
      if (closeAll) msg += ' Closed $closed position(s).';
      if (failures.isNotEmpty) msg += ' Failed: ${failures.join('; ')}';
      return ActionResult(failures.isEmpty, msg);
    });
  }

  Future<ActionResult> clearEmergencyStop() => _guard(() async {
    final r = await _post('/api/admin/emergency-stop/clear');
    await fetchPositions();
    return _result(r, 'Emergency stop cleared. New orders allowed again.');
  });
}
