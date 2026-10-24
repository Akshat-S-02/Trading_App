import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../services/websocket_service.dart';
import '../app_config.dart';

/// Owns everything related to live market data:
///   - WebSocket connection + price map
///   - Watchlist (with SharedPreferences persistence)
///   - Snapshot HTTP fetch to seed prices immediately
class MarketDataProvider with ChangeNotifier {
  // ── Price map ────────────────────────────────────────────────────────────────
  final Map<String, dynamic> _prices = {};
  Map<String, dynamic> get prices => _prices;

  double? getPrice(String symbol) {
    final v = _prices[symbol];
    return v is num ? v.toDouble() : null;
  }

  // ── Session tick history (client-side only, used by the terminal view) ─────
  static const int _maxHistory = 240;
  final Map<String, List<double>> _history = {};
  final Map<String, double> _sessionFirst = {};

  /// Distinct prices seen this session for [symbol] (oldest first).
  List<double> historyFor(String symbol) =>
      _history[_normalize(symbol)] ?? const [];

  /// Change since the first price this app session saw for [symbol].
  /// Not the exchange day change — the feed only carries LTP.
  double? sessionChange(String symbol) {
    final first = _sessionFirst[_normalize(symbol)];
    final now = getPrice(symbol);
    if (first == null || now == null) return null;
    return now - first;
  }

  DateTime? _lastMessageAt;
  /// Time the last WebSocket frame arrived (null until the first one).
  DateTime? get lastMessageAt => _lastMessageAt;

  String _normalize(String s) => s.endsWith('.NS') ? s : '$s.NS';

  // ── Watchlist ────────────────────────────────────────────────────────────────
  List<String> _watchlist = [];
  List<String> get watchlist => _watchlist;

  // ── WebSocket ────────────────────────────────────────────────────────────────
  WebSocketService? _wsService;
  bool _initialized = false;

  final String _baseUrl = kHttpBase;

  MarketDataProvider() {
    _loadWatchlist();
  }

  /// Start WebSocket and subscribe all current watchlist symbols.
  /// Idempotent — safe to call multiple times (e.g. from both LoginScreen and DashboardScreen).
  void initialize() {
    if (_initialized) return;
    _initialized = true;

    _wsService = WebSocketService(
      url: '$kWsBase/ws/market',
      onMessage: _ingest,
      onDone: () => debugPrint('MarketData WS closed'),
      onError: (e) => debugPrint('❌ MarketData WS error: $e'),
    );
    _wsService!.connect();
  }

  @override
  void dispose() {
    _wsService?.dispose();
    super.dispose();
  }

  // ── Watchlist persistence ────────────────────────────────────────────────────

  Future<void> _loadWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getStringList('watchlist');
      if (saved != null && saved.isNotEmpty) {
        _watchlist = saved;
      } else {
        _watchlist = [
          'RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS',
          'SBIN.NS', 'ICICIBANK.NS', 'AXISBANK.NS', 'KOTAKBANK.NS',
          'ITC.NS', 'LT.NS', 'BHARTIARTL.NS', 'ASIANPAINT.NS',
          'MARUTI.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'TITAN.NS',
          'BAJFINANCE.NS', 'ULTRACEMCO.NS', 'M&M.NS', 'TATASTEEL.NS',
        ];
        await _saveWatchlist();
      }
      notifyListeners();

      // Seed prices for all watchlist symbols in one fast batch request
      _seedWatchlistPricesBatch();
    } catch (e) {
      debugPrint('Error loading watchlist: $e');
    }
  }

  Future<void> _seedWatchlistPricesBatch() async {
    if (_watchlist.isEmpty) return;

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/market/ltp/batch'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'symbols': _watchlist}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final results = data['results'] as Map<String, dynamic>?;
        if (results != null) {
          bool updated = false;
          results.forEach((bareSymbol, info) {
            final ltp = info['ltp'];
            if (ltp != null && ltp != 0) {
              final price = (ltp is num) ? ltp.toDouble() : double.tryParse(ltp.toString());
              if (price != null && price > 0) {
                _prices['$bareSymbol.NS'] = price;
                _prices[bareSymbol] = price;
                _record(bareSymbol, price);
                updated = true;
              }
            }
          });
          if (updated) notifyListeners();
        }
      }
    } catch (e) {
      debugPrint('Batch subscription failed: $e');
    }
  }

  Future<void> _saveWatchlist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('watchlist', _watchlist);
    } catch (e) {
      debugPrint('Error saving watchlist: $e');
    }
  }

  void addToWatchlist(String symbol) {
    if (!_watchlist.contains(symbol)) {
      _watchlist.insert(0, symbol);
      _saveWatchlist();
      notifyListeners();
      
      // For a single symbol added by the user, we can still use the batch API
      // just with an array of 1, to keep it simple.
      _seedSinglePrice(symbol);
    }
  }

  void removeFromWatchlist(String symbol) {
    if (_watchlist.remove(symbol)) {
      _saveWatchlist();
      notifyListeners();
    }
  }

  // ── HTTP snapshot to seed price + tell backend to subscribe ─────────────────

  Future<void> _seedSinglePrice(String symbol) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/market/ltp/batch'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'symbols': [symbol]}),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final results = data['results'] as Map<String, dynamic>?;
        if (results != null) {
          results.forEach((bareSymbol, info) {
            final ltp = info['ltp'];
            if (ltp != null && ltp != 0) {
              final price = (ltp is num) ? ltp.toDouble() : double.tryParse(ltp.toString());
              if (price != null && price > 0) {
                _prices['$bareSymbol.NS'] = price;
                _prices[bareSymbol] = price;
                _record(bareSymbol, price);
                notifyListeners();
              }
            }
          });
        }
      }
    } catch (e) {
      debugPrint('Single subscription failed for $symbol: $e');
    }
  }

  // ── WebSocket message ingestion ──────────────────────────────────────────────

  void _ingest(dynamic msg) {
    try {
      final data = msg is String ? jsonDecode(msg) : msg;
      _lastMessageAt = DateTime.now();

      if (data is List) {
        for (final item in data) {
          if (item is Map && item.containsKey('symbol') && item.containsKey('LTP')) {
            _updatePrice(item['symbol'] as String, item['LTP']);
          }
        }
        notifyListeners();
      } else if (data is Map && data.containsKey('symbol') && data.containsKey('LTP')) {
        _updatePrice(data['symbol'] as String, data['LTP']);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('⚠️ MarketData WS ingest error: $e');
    }
  }

  void _updatePrice(String symbol, dynamic ltp) {
    // Backend sends bare symbol (e.g. "RELIANCE"). Store both variants so
    // widgets can look up by either "RELIANCE" or "RELIANCE.NS".
    final normalized = _normalize(symbol);
    final price = ltp is num ? ltp.toDouble() : double.tryParse('$ltp');
    if (price == null) return;
    _prices[symbol] = price;
    _prices[normalized] = price;
    _record(symbol, price);
  }

  void _record(String symbol, double price) {
    if (price <= 0) return;
    final key = _normalize(symbol);
    _sessionFirst.putIfAbsent(key, () => price);
    final list = _history.putIfAbsent(key, () => <double>[]);
    if (list.isNotEmpty && list.last == price) return;
    list.add(price);
    if (list.length > _maxHistory) list.removeAt(0);
  }
}
