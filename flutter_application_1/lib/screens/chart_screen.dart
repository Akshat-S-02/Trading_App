import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import '../app_config.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../services/auth_service.dart';
import '../utils/format.dart';
import '../widgets/candle_chart.dart';
import '../widgets/order_ticket_sheet.dart';
import '../widgets/news_widget.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

void openChart(BuildContext context, String symbol) {
  Navigator.of(context).push(MaterialPageRoute(builder: (_) => ChartScreen(symbol: symbol)));
}

/// Full-screen candlestick chart for manual trading: timeframes, live last
/// candle, your position / SL / target levels, and one-tap BUY / SELL.
class ChartScreen extends StatefulWidget {
  final String symbol;
  const ChartScreen({super.key, required this.symbol});

  @override
  State<ChartScreen> createState() => _ChartScreenState();
}

class _ChartScreenState extends State<ChartScreen> {
  static const _ist = Duration(hours: 5, minutes: 30);
  static const _intervals = {'1': '1m', '5': '5m', '15': '15m', '60': '1H', 'D': '1D'};

  String _interval = '5';
  List<Candle> _candles = [];
  bool _loading = true;
  String? _error;
  String? _source;
  Candle? _hover;
  Timer? _refresh;
  late final MarketDataProvider _market;

  String get _bare => bareSymbol(widget.symbol);

  @override
  void initState() {
    super.initState();
    _market = context.read<MarketDataProvider>();
    _market.ensurePrice(widget.symbol);
    _market.addListener(_onMarket);
    _load();
    // Re-sync with the server's candles so the live candle's volume/OHLC correct themselves
    _refresh = Timer.periodic(const Duration(seconds: 60), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _refresh?.cancel();
    _market.removeListener(_onMarket);
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    final interval = _interval;
    if (!silent) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final headers = await AuthService.authHeaders();
      final r = await http
          .get(Uri.parse('$kHttpBase/api/market/candles/$_bare?interval=$interval'), headers: headers)
          .timeout(const Duration(seconds: 30));
      if (!mounted || interval != _interval) return;
      AuthService.checkAuth(r);
      if (r.statusCode != 200) {
        String msg = 'Could not load candles (${r.statusCode})';
        try {
          msg = jsonDecode(r.body)['detail']?.toString() ?? msg;
        } catch (_) {}
        if (!silent) setState(() => _error = msg);
        return;
      }
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      final candles = (data['candles'] as List).map((e) => Candle.fromJson(Map<String, dynamic>.from(e))).toList();
      setState(() {
        _candles = candles;
        _source = data['source']?.toString();
        _error = null;
      });
      final p = _market.getPrice(widget.symbol);
      if (p != null) _applyLive(p);
    } catch (e) {
      if (mounted && !silent) setState(() => _error = 'Could not reach the backend: $e');
    } finally {
      if (mounted && !silent) setState(() => _loading = false);
    }
  }

  void _onMarket() {
    final p = _market.getPrice(widget.symbol);
    if (p != null && mounted && _applyLive(p)) setState(() {});
  }

  /// Fold a live price into the last candle, or open a new one when the
  /// current bucket has rolled over. Only during the NSE session.
  bool _applyLive(double price) {
    if (_candles.isEmpty) return false;
    final nowIst = DateTime.now().toUtc().add(_ist); // fields read as IST
    final mins = nowIst.hour * 60 + nowIst.minute;
    if (mins < 9 * 60 + 15 || mins >= 15 * 60 + 30) return false;

    final int bucketMs;
    if (_interval == 'D') {
      bucketMs = DateTime.utc(nowIst.year, nowIst.month, nowIst.day).subtract(_ist).millisecondsSinceEpoch;
    } else {
      final m = int.parse(_interval);
      final open = DateTime.utc(nowIst.year, nowIst.month, nowIst.day, 9, 15);
      final k = nowIst.difference(open).inMinutes ~/ m;
      bucketMs = open.add(Duration(minutes: k * m)).subtract(_ist).millisecondsSinceEpoch;
    }

    final last = _candles.last;
    if (bucketMs == last.t) {
      if (last.c == price) return false;
      last.c = price;
      last.h = math.max(last.h, price);
      last.l = math.min(last.l, price);
    } else if (bucketMs > last.t) {
      _candles.add(Candle(bucketMs, price, price, price, price, 0));
    } else {
      return false;
    }
    return true;
  }

  /// Previous session's close, for the day-change figure.
  double? _prevClose() {
    if (_candles.length < 2) return null;
    if (_interval == 'D') return _candles[_candles.length - 2].c;
    final d = _candles.last.ist;
    for (var i = _candles.length - 1; i >= 0; i--) {
      final c = _candles[i].ist;
      if (c.year != d.year || c.month != d.month || c.day != d.day) return _candles[i].c;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final livePrice = context.select<MarketDataProvider, double?>((p) => p.getPrice(widget.symbol));
    final trading = context.watch<TradingProvider>();
    final positions = trading.positions.where((p) => p['symbol'] == _bare).toList();

    final ltp = livePrice ?? (_candles.isNotEmpty ? _candles.last.c : null);
    final prev = _prevClose();
    final change = (ltp != null && prev != null) ? ltp - prev : null;
    final changePct = (change != null && prev != null && prev != 0) ? change / prev * 100 : null;

    final lines = <ChartLine>[];
    for (final p in positions) {
      final isLong = p['side'] == 'BUY';
      final qty = p['filled_qty'] ?? p['qty'];
      final avg = ((p['avg_price'] ?? p['entry_price']) as num?)?.toDouble();
      if (avg != null) {
        lines.add(ChartLine(avg, AppColors.accent, '${isLong ? 'LONG' : 'SHORT'} $qty @ ${avg.toStringAsFixed(2)}'));
      }
      final sl = (p['stop_loss'] as num?)?.toDouble();
      if (sl != null) lines.add(ChartLine(sl, kSellColor, 'SL'));
      final tgt = (p['target'] as num?)?.toDouble();
      if (tgt != null) lines.add(ChartLine(tgt, kBuyColor, 'TARGET'));
    }

    final shown = _hover ?? (_candles.isNotEmpty ? _candles.last : null);

    return Scaffold(
      extendBody: true,
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_bare, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.headline),
                  const Text('NSE', style: AppText.caption),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(ltp == null ? '—' : inr(ltp), style: AppText.headline.copyWith(fontFeatures: AppText.tabular)),
                if (change != null)
                  Text(
                    '${change >= 0 ? '+' : ''}${change.toStringAsFixed(2)} '
                    '(${changePct!.toStringAsFixed(2)}%)',
                    style: AppText.caption.copyWith(color: pnlColor(change), fontFeatures: AppText.tabular),
                  ),
              ],
            ),
            const SizedBox(width: 4),
          ],
        ),
        actions: [
          IconButton(
              tooltip: 'News',
              onPressed: () => openStockNews(context, widget.symbol),
              icon: const Icon(Icons.article_outlined)),
          IconButton(tooltip: 'Reload', onPressed: _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: Column(
        children: [
          // ── Timeframes ───────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 6),
            child: SizedBox(
              width: double.infinity,
              child: SegmentedButton<String>(
                showSelectedIcon: false,
                segments: _intervals.entries.map((e) => ButtonSegment(value: e.key, label: Text(e.value))).toList(),
                selected: {_interval},
                onSelectionChanged: (sel) {
                  final k = sel.first;
                  if (_interval == k) return;
                  HapticFeedback.selectionClick();
                  setState(() {
                    _interval = k;
                    _candles = [];
                    _hover = null;
                  });
                  _load();
                },
              ),
            ),
          ),

          // ── OHLC readout ─────────────────────────────────────────────────
          SizedBox(
            height: 20,
            child: shown == null
                ? null
                : Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: DefaultTextStyle(
                      style: AppText.caption
                          .copyWith(color: shown.up ? kBuyColor : kSellColor, fontFeatures: AppText.tabular),
                      // Scales down rather than overflowing on narrow phones.
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        alignment: Alignment.centerLeft,
                        child: Row(
                          children: [
                            Text('O ${shown.o.toStringAsFixed(2)}'),
                            const SizedBox(width: 10),
                            Text('H ${shown.h.toStringAsFixed(2)}'),
                            const SizedBox(width: 10),
                            Text('L ${shown.l.toStringAsFixed(2)}'),
                            const SizedBox(width: 10),
                            Text('C ${shown.c.toStringAsFixed(2)}'),
                            const SizedBox(width: 14),
                            Text('Vol ${_compact(shown.v)}', style: const TextStyle(color: AppColors.tertiary)),
                          ],
                        ),
                      ),
                    ),
                  ),
          ),

          // ── Chart ────────────────────────────────────────────────────────
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(left: 4),
              child: _buildChartArea(lines),
            ),
          ),

          if (_source != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 4, top: 2),
              child: Text(
                '${_source == 'yfinance' ? 'Yahoo Finance' : 'Dhan'} · '
                'drag to pan · pinch to zoom · hold for crosshair · double-tap to reset',
                style: AppText.caption.copyWith(color: AppColors.quaternary, fontSize: 10),
              ),
            ),

          // ── Your position here ───────────────────────────────────────────
          ...positions.map((p) => _positionStrip(context, p, ltp)),
          // Clear the translucent trade bar.
          // (Builder: the inset must be read inside the Scaffold, which adds the bar's height.)
          Builder(builder: (context) => SizedBox(height: bottomInset(context, 8))),
        ],
      ),

      // ── Trade buttons, on a translucent bar the chart sits behind ─────────
      bottomNavigationBar: GlassBar(
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
            child: Row(
              children: [
                Expanded(child: _tradeButton('Sell', 'SELL', kSellColor, ltp)),
                const SizedBox(width: 12),
                Expanded(child: _tradeButton('Buy', 'BUY', kBuyColor, ltp)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _tradeButton(String label, String side, Color color, double? ltp) {
    return Pressable(
      haptic: true,
      onTap: () => showOrderTicket(context, widget.symbol, side: side),
      child: Container(
        height: 54,
        alignment: Alignment.center,
        decoration: ShapeDecoration(color: color, shape: rounded(14)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label, style: AppText.headline.copyWith(color: Colors.white)),
            if (ltp != null)
              Text(ltp.toStringAsFixed(2),
                  style: AppText.caption
                      .copyWith(color: Colors.white.withValues(alpha: 0.8), fontFeatures: AppText.tabular)),
          ],
        ),
      ),
    );
  }

  Widget _buildChartArea(List<ChartLine> lines) {
    if (_loading && _candles.isEmpty) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2.5));
    }
    if (_error != null && _candles.isEmpty) {
      return Center(
        child: EmptyState(
          icon: Icons.show_chart_rounded,
          title: 'Chart unavailable',
          message: _error,
          action: OutlinedButton(onPressed: _load, child: const Text('Try again')),
        ),
      );
    }
    return CandleChart(
      key: ValueKey(_interval),
      candles: _candles,
      daily: _interval == 'D',
      lines: lines,
      onHover: (c) => setState(() => _hover = c),
    );
  }

  Widget _positionStrip(BuildContext context, Map<String, dynamic> p, double? ltp) {
    final isLong = p['side'] == 'BUY';
    final qty = (p['filled_qty'] ?? p['qty']) as int;
    final avg = ((p['avg_price'] ?? p['entry_price']) as num?)?.toDouble() ?? 0;
    final pnl = ltp == null ? null : (isLong ? ltp - avg : avg - ltp) * qty;
    final trading = context.watch<TradingProvider>();
    final id = p['id'] as int;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
      child: Surface(
        padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
        child: Row(
          children: [
            Pill(isLong ? 'Long' : 'Short', color: isLong ? kBuyColor : kSellColor),
            const SizedBox(width: 8),
            Text('$qty @ ${avg.toStringAsFixed(2)}', style: AppText.subhead.copyWith(fontFeatures: AppText.tabular)),
            const Spacer(),
            Text(signedInr(pnl), style: AppText.headline.copyWith(color: pnlColor(pnl), fontFeatures: AppText.tabular)),
            const SizedBox(width: 4),
            TextButton(
              style: TextButton.styleFrom(foregroundColor: AppColors.red),
              onPressed: trading.isClosing(id)
                  ? null
                  : () async {
                      final messenger = ScaffoldMessenger.of(context);
                      final ok = await confirmAction(
                        context,
                        title: 'Close $_bare?',
                        message: 'Squares off $qty shares at market.\n'
                            'Estimated P&L ${signedInr(pnl)}, before charges.',
                        confirmLabel: 'Close position',
                        cancelLabel: 'Keep open',
                      );
                      if (!ok) return;
                      final res = await trading.closePosition(id);
                      notify(messenger, res.message, ok: res.ok);
                    },
              child: const Text('Close'),
            ),
          ],
        ),
      ),
    );
  }

  static String _compact(int v) {
    if (v >= 10000000) return '${(v / 10000000).toStringAsFixed(2)}Cr';
    if (v >= 100000) return '${(v / 100000).toStringAsFixed(2)}L';
    if (v >= 1000) return '${(v / 1000).toStringAsFixed(1)}K';
    return '$v';
  }
}
