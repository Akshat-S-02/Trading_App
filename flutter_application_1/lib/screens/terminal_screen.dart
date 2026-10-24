import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../theme/brutal_theme.dart';
import '../widgets/brutal/brutal.dart';
import '../widgets/orders_widget.dart';
import '../widgets/portfolio_widget.dart';

/// Optional multi-panel view for placing manual sandbox orders.
///
/// Reads prices from [MarketDataProvider] and places orders through
/// [TradingProvider.placeOrder] (POST /api/trade/place). It owns no data
/// of its own besides the order-ticket form state.
class TerminalScreen extends StatefulWidget {
  const TerminalScreen({super.key});

  @override
  State<TerminalScreen> createState() => _TerminalScreenState();
}

enum _Side { buy, sell }

class _TerminalScreenState extends State<TerminalScreen> {
  String? _selected;
  _Side _side = _Side.buy;
  int _bottomTab = 0;
  bool _placing = false;

  final _qtyCtrl = TextEditingController(text: '1');
  final _slCtrl = TextEditingController();
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    // Repaint once a second for the IST clock and feed-link indicator.
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final trading = context.read<TradingProvider>();
      trading.fetchUserLimits();
      trading.fetchPortfolio();
      trading.fetchTrades();
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    _qtyCtrl.dispose();
    _slCtrl.dispose();
    super.dispose();
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  static String _bare(String s) => s.contains('.') ? s.split('.').first : s;

  int get _qty => int.tryParse(_qtyCtrl.text.trim()) ?? 0;

  double? get _stopLoss {
    final t = _slCtrl.text.trim();
    if (t.isEmpty) return null;
    return double.tryParse(t);
  }

  void _select(String symbol) {
    setState(() {
      _selected = symbol;
      _slCtrl.clear();
    });
  }

  double _holdingQty(List<dynamic> portfolio, String symbol) {
    for (final h in portfolio) {
      if (h['symbol'] == symbol) return (h['qty'] as num).toDouble();
    }
    return 0;
  }

  Map<String, dynamic>? _holding(List<dynamic> portfolio, String symbol) {
    for (final h in portfolio) {
      if (h['symbol'] == symbol) return Map<String, dynamic>.from(h as Map);
    }
    return null;
  }

  /// Largest whole quantity the backend should accept for the current side.
  int _maxQty(TradingProvider t, double? ltp, double held) {
    if (_side == _Side.sell) return held.floor();
    if (ltp == null || ltp <= 0) return 0;
    final budget = [
      t.balance,
      t.dailyLimit - t.dailySpent,
      t.monthlyLimit - t.monthlySpent,
    ].reduce(math.min);
    if (budget <= 0) return 0;
    return (budget / ltp).floor();
  }

  /// First blocking problem with the ticket, or null when it can be sent.
  String? _validate(double? ltp, double held) {
    if (_selected == null) return 'Select an instrument';
    if (_qty <= 0) return 'Quantity must be a whole number above 0';
    if (_side == _Side.sell && _qty > held) {
      return 'You hold ${held.toStringAsFixed(0)} — cannot sell $_qty';
    }
    if (_side == _Side.buy && _slCtrl.text.trim().isNotEmpty) {
      final sl = _stopLoss;
      if (sl == null || sl <= 0) return 'Stop loss must be a positive price';
      if (ltp != null && sl >= ltp) return 'Stop loss must be below LTP';
    }
    return null;
  }

  Future<void> _submit() async {
    final market = context.read<MarketDataProvider>();
    final trading = context.read<TradingProvider>();
    final symbol = _selected;
    if (symbol == null) return;

    final ltp = market.getPrice(symbol);
    final held = _holdingQty(trading.portfolio, symbol);
    final problem = _validate(ltp, held);
    if (problem != null) {
      showBrutalSnack(context, problem, isError: true);
      return;
    }

    final side = _side == _Side.buy ? 'BUY' : 'SELL';
    final qty = _qty;
    final sl = _side == _Side.buy ? _stopLoss : null;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmOrderDialog(
        side: side,
        symbol: _bare(symbol),
        qty: qty,
        ltp: ltp,
        stopLoss: sl,
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _placing = true);
    final result = await trading.placeOrder(
      symbol: symbol,
      side: side,
      qty: qty.toDouble(),
      stopLoss: sl,
    );
    if (!mounted) return;
    setState(() => _placing = false);

    if (result.ok) {
      final fill = result.price != null ? ' @ ${Brutal.money(result.price!)}' : '';
      showBrutalSnack(context, '$side ${_bare(symbol)} ×$qty$fill — ${result.message}');
      setState(() => _bottomTab = 1);
    } else {
      showBrutalSnack(context, 'REJECTED: ${result.message}', isError: true);
    }
  }

  // ── Build ───────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final market = context.watch<MarketDataProvider>();
    final watchlist = market.watchlist;
    if (_selected == null && watchlist.isNotEmpty) _selected = watchlist.first;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _TerminalHeader(lastMessageAt: market.lastMessageAt),
            _TickerTape(symbols: watchlist),
            Expanded(
              child: LayoutBuilder(
                builder: (context, c) => c.maxWidth >= 1100
                    ? _wideLayout(watchlist)
                    : c.maxWidth >= 720
                        ? _mediumLayout(watchlist)
                        : _narrowLayout(watchlist),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _wideLayout(List<String> watchlist) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 16, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(width: 270, child: _watchlistPanel(watchlist)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(flex: 3, child: _instrumentPanel()),
                const SizedBox(height: 14),
                Expanded(flex: 2, child: _bookPanel()),
              ],
            ),
          ),
          const SizedBox(width: 14),
          SizedBox(width: 340, child: _ticketPanel(scroll: true)),
        ],
      ),
    );
  }

  Widget _mediumLayout(List<String> watchlist) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 16, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _symbolChips(watchlist),
                const SizedBox(height: 12),
                Expanded(flex: 3, child: _instrumentPanel()),
                const SizedBox(height: 14),
                Expanded(flex: 2, child: _bookPanel()),
              ],
            ),
          ),
          const SizedBox(width: 14),
          SizedBox(width: 310, child: _ticketPanel(scroll: true)),
        ],
      ),
    );
  }

  Widget _narrowLayout(List<String> watchlist) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 12, 16, 24),
      children: [
        _symbolChips(watchlist),
        const SizedBox(height: 12),
        SizedBox(height: 420, child: _instrumentPanel()),
        const SizedBox(height: 16),
        _ticketPanel(scroll: false),
        const SizedBox(height: 16),
        SizedBox(height: 380, child: _bookPanel()),
      ],
    );
  }

  // ── Panels ──────────────────────────────────────────────────────────────────

  Widget _watchlistPanel(List<String> watchlist) {
    final market = context.read<MarketDataProvider>();
    return BrutalPanel(
      index: '01',
      title: 'Watchlist',
      actions: [
        Text('${watchlist.length}',
            style: Brutal.mono(size: 11, color: Brutal.accent, weight: FontWeight.w800)),
      ],
      child: watchlist.isEmpty
          ? const BrutalEmpty(
              title: 'Empty',
              subtitle: 'Add symbols from the Market tab',
              icon: Icons.playlist_add)
          : ListView.separated(
              itemCount: watchlist.length,
              separatorBuilder: (_, __) =>
                  Container(height: 1.5, color: Brutal.ink),
              itemBuilder: (context, i) {
                final s = watchlist[i];
                final price = market.getPrice(s);
                final chg = market.sessionChange(s);
                final sel = s == _selected;
                return InkWell(
                  onTap: () => _select(s),
                  child: Container(
                    color: sel ? Brutal.ink : Brutal.white,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                    child: Row(
                      children: [
                        Container(
                          width: 6,
                          height: 26,
                          color: sel ? Brutal.accent : Brutal.signColor(chg ?? 0),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(_bare(s),
                              overflow: TextOverflow.ellipsis,
                              style: Brutal.display(
                                  size: 13,
                                  weight: FontWeight.w800,
                                  color: sel ? Brutal.accent : Brutal.ink)),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(price != null ? price.toStringAsFixed(2) : '—',
                                style: Brutal.mono(
                                    size: 13,
                                    weight: FontWeight.w800,
                                    color: sel ? Brutal.white : Brutal.ink)),
                            if (chg != null)
                              Text(
                                '${chg >= 0 ? '+' : ''}${chg.toStringAsFixed(2)}',
                                style: Brutal.mono(
                                    size: 10,
                                    weight: FontWeight.w700,
                                    color: sel
                                        ? Brutal.accent
                                        : Brutal.signColor(chg)),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }

  Widget _symbolChips(List<String> watchlist) {
    if (watchlist.isEmpty) {
      return BrutalBox(
        shadow: 0,
        padding: const EdgeInsets.all(12),
        child: Text('WATCHLIST EMPTY — ADD SYMBOLS FROM THE MARKET TAB',
            style: Brutal.label(color: Brutal.ink)),
      );
    }
    return SizedBox(
      height: 42,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: watchlist.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final s = watchlist[i];
          final sel = s == _selected;
          return InkWell(
            onTap: () => _select(s),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: sel ? Brutal.ink : Brutal.white,
                border: Border.all(color: Brutal.ink, width: Brutal.border),
              ),
              child: Text(_bare(s),
                  style: Brutal.display(
                      size: 13,
                      weight: FontWeight.w800,
                      color: sel ? Brutal.accent : Brutal.ink)),
            ),
          );
        },
      ),
    );
  }

  Widget _instrumentPanel() {
    final market = context.watch<MarketDataProvider>();
    final trading = context.watch<TradingProvider>();
    final symbol = _selected;

    if (symbol == null) {
      return const BrutalPanel(
        index: '02',
        title: 'Instrument',
        child: BrutalEmpty(title: 'No instrument selected', icon: Icons.ads_click),
      );
    }

    final ltp = market.getPrice(symbol);
    final chg = market.sessionChange(symbol);
    final hist = market.historyFor(symbol);
    final holding = _holding(trading.portfolio, symbol);
    final hi = hist.isEmpty ? null : hist.reduce(math.max);
    final lo = hist.isEmpty ? null : hist.reduce(math.min);

    return BrutalPanel(
      index: '02',
      title: 'Instrument — ${_bare(symbol)}',
      actions: const [BrutalTag('NSE · EQ', color: Brutal.accent)],
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.end,
              spacing: 16,
              runSpacing: 8,
              children: [
                Text(ltp != null ? ltp.toStringAsFixed(2) : '— —',
                    style: Brutal.mono(size: 40, weight: FontWeight.w800)),
                if (chg != null)
                  Container(
                    margin: const EdgeInsets.only(bottom: 6),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    color: chg >= 0 ? Brutal.up : Brutal.down,
                    child: Text(
                      '${chg >= 0 ? '▲ +' : '▼ '}${chg.toStringAsFixed(2)}'
                      '${ltp != null && ltp - chg != 0 ? '  (${(chg / (ltp - chg) * 100).toStringAsFixed(2)}%)' : ''}',
                      style: Brutal.mono(
                          size: 13, weight: FontWeight.w800, color: Brutal.white),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text('CHANGE IS SINCE THIS SESSION OPENED — NOT EXCHANGE DAY CHANGE',
                style: Brutal.label(size: 9)),
            const SizedBox(height: 10),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: Brutal.paper,
                  border: Border.all(color: Brutal.ink, width: 2),
                ),
                child: hist.length < 2
                    ? Center(
                        child: Text('WAITING FOR TICKS…',
                            style: Brutal.label(color: Brutal.ink)))
                    : CustomPaint(
                        painter: _TickChartPainter(hist),
                        size: Size.infinite,
                      ),
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _stat('Sess. High', hi?.toStringAsFixed(2) ?? '—'),
                _stat('Sess. Low', lo?.toStringAsFixed(2) ?? '—'),
                _stat('Ticks', '${hist.length}'),
                _stat('Held',
                    holding != null ? '${holding['qty']}' : '0'),
                if (holding != null)
                  _stat('Avg',
                      (holding['avg_price'] as num).toDouble().toStringAsFixed(2)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _stat(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Brutal.white,
        border: Border.all(color: Brutal.ink, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('${label.toUpperCase()} ', style: Brutal.label(size: 10)),
          Text(value, style: Brutal.mono(size: 12, weight: FontWeight.w800)),
        ],
      ),
    );
  }

  Widget _ticketPanel({required bool scroll}) {
    final market = context.watch<MarketDataProvider>();
    final trading = context.watch<TradingProvider>();
    final symbol = _selected;
    final ltp = symbol != null ? market.getPrice(symbol) : null;
    final held = symbol != null ? _holdingQty(trading.portfolio, symbol) : 0.0;
    final maxQty = _maxQty(trading, ltp, held);
    final est = ltp != null ? ltp * _qty : null;
    final problem = _validate(ltp, held);
    final isBuy = _side == _Side.buy;
    final sideColor = isBuy ? Brutal.up : Brutal.down;
    final dailyLeft = trading.dailyLimit - trading.dailySpent;
    final overBudget = isBuy && est != null &&
        (est > trading.balance || est > dailyLeft);

    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Side toggle
        Row(
          children: [
            Expanded(child: _sideButton(_Side.buy)),
            const SizedBox(width: 10),
            Expanded(child: _sideButton(_Side.sell)),
          ],
        ),
        const SizedBox(height: 16),
        Text('INSTRUMENT', style: Brutal.label()),
        const SizedBox(height: 4),
        Text(symbol != null ? _bare(symbol) : '—',
            style: Brutal.display(size: 22, weight: FontWeight.w900)),
        const SizedBox(height: 14),

        // Quantity
        Row(
          children: [
            Expanded(child: Text('QUANTITY', style: Brutal.label())),
            Text('MAX $maxQty', style: Brutal.label(color: Brutal.ink)),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            _stepButton(Icons.remove, 'Decrease quantity',
                () => _setQty(math.max(1, _qty - 1))),
            Expanded(
              child: TextField(
                controller: _qtyCtrl,
                textAlign: TextAlign.center,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                style: Brutal.mono(size: 20, weight: FontWeight.w800),
                decoration: const InputDecoration(
                  contentPadding: EdgeInsets.symmetric(vertical: 12),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            _stepButton(Icons.add, 'Increase quantity', () => _setQty(_qty + 1)),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final q in const [1, 5, 10, 25, 100]) _quickQty('$q', q),
            if (maxQty > 0) _quickQty('MAX', maxQty),
          ],
        ),

        // Stop loss (BUY only — the backend's SL monitor watches open buys)
        if (isBuy) ...[
          const SizedBox(height: 14),
          Text('STOP LOSS (OPTIONAL)', style: Brutal.label()),
          const SizedBox(height: 6),
          TextField(
            controller: _slCtrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'^\d*\.?\d{0,2}')),
            ],
            style: Brutal.mono(size: 16, weight: FontWeight.w700),
            decoration: InputDecoration(
              hintText: ltp != null
                  ? 'e.g. ${(ltp * 0.95).toStringAsFixed(2)} (−5%)'
                  : 'Trigger price',
              prefixText: '₹ ',
            ),
            onChanged: (_) => setState(() {}),
          ),
        ],

        const SizedBox(height: 16),
        Container(height: Brutal.border, color: Brutal.ink),
        const SizedBox(height: 10),
        _kv('LTP', ltp != null ? Brutal.money(ltp) : '—'),
        _kv('Est. value', est != null ? Brutal.money(est) : '—',
            color: overBudget ? Brutal.down : Brutal.ink),
        if (isBuy) ...[
          _kv('Available', Brutal.money(trading.balance)),
          _kv('Daily limit left', Brutal.money(dailyLeft),
              color: dailyLeft <= 0 ? Brutal.down : Brutal.ink),
        ] else
          _kv('Holding', held.toStringAsFixed(0)),
        const SizedBox(height: 6),
        Text('FILLS AT THE BACKEND\'S LATEST PRICE — MAY DIFFER FROM LTP',
            style: Brutal.label(size: 9)),
        if (problem != null && _selected != null) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Brutal.white,
              border: Border.all(color: Brutal.down, width: 2),
            ),
            child: Text(problem.toUpperCase(),
                style: Brutal.mono(
                    size: 11, weight: FontWeight.w800, color: Brutal.down)),
          ),
        ],
        const SizedBox(height: 16),
        BrutalButton(
          label: '${isBuy ? 'Buy' : 'Sell'} ${symbol != null ? _bare(symbol) : ''}',
          icon: isBuy ? Icons.north_east : Icons.south_east,
          expand: true,
          height: 58,
          fontSize: 17,
          color: sideColor,
          foreground: Brutal.white,
          loading: _placing,
          onPressed: problem == null && !_placing ? _submit : null,
        ),
      ],
    );

    return BrutalBox(
      shadow: 6,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: scroll ? MainAxisSize.max : MainAxisSize.min,
        children: [
          BrutalStrip(
            index: '03',
            title: 'Order Ticket',
            color: sideColor,
            foreground: Brutal.white,
            actions: [
              Text('MARKET · SANDBOX',
                  style: Brutal.mono(
                      size: 10, color: Brutal.white, weight: FontWeight.w800)),
            ],
          ),
          if (scroll)
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(14),
                child: body,
              ),
            )
          else
            Padding(padding: const EdgeInsets.all(14), child: body),
        ],
      ),
    );
  }

  void _setQty(int q) {
    _qtyCtrl.text = '$q';
    setState(() {});
  }

  Widget _sideButton(_Side side) {
    final active = _side == side;
    final isBuy = side == _Side.buy;
    final color = isBuy ? Brutal.up : Brutal.down;
    return Semantics(
      button: true,
      selected: active,
      label: isBuy ? 'Buy side' : 'Sell side',
      child: InkWell(
        onTap: () => setState(() => _side = side),
        child: Container(
          height: 48,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: active ? color : Brutal.white,
            border: Border.all(color: Brutal.ink, width: Brutal.border),
            boxShadow: active ? null : Brutal.hardShadow(3),
          ),
          child: Text(isBuy ? 'BUY' : 'SELL',
              style: Brutal.display(
                  size: 18,
                  weight: FontWeight.w900,
                  spacing: 2,
                  color: active ? Brutal.white : Brutal.ink)),
        ),
      ),
    );
  }

  Widget _stepButton(IconData icon, String tooltip, VoidCallback onTap) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        child: Container(
          width: 46,
          height: 50,
          decoration: BoxDecoration(
            color: Brutal.accent,
            border: Border.all(color: Brutal.ink, width: Brutal.border),
          ),
          child: Icon(icon, color: Brutal.ink),
        ),
      ),
    );
  }

  Widget _quickQty(String label, int q) {
    final active = _qty == q;
    return InkWell(
      onTap: () => _setQty(q),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: active ? Brutal.ink : Brutal.white,
          border: Border.all(color: Brutal.ink, width: 1.5),
        ),
        child: Text(label,
            style: Brutal.mono(
                size: 12,
                weight: FontWeight.w800,
                color: active ? Brutal.accent : Brutal.ink)),
      ),
    );
  }

  Widget _kv(String k, String v, {Color color = Brutal.ink}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Expanded(child: Text(k.toUpperCase(), style: Brutal.label())),
          Text(v, style: Brutal.mono(size: 13, weight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }

  Widget _bookPanel() {
    final trading = context.watch<TradingProvider>();
    final portfolio = trading.portfolio;
    final trades = trading.trades;

    Widget tab(int i, String label, int count) {
      final active = _bottomTab == i;
      return InkWell(
        onTap: () {
          setState(() => _bottomTab = i);
          if (i == 0) trading.fetchPortfolio();
          if (i == 1) trading.fetchTrades();
        },
        child: Container(
          height: 34,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          alignment: Alignment.center,
          color: active ? Brutal.accent : Brutal.ink,
          child: Text('$label ($count)',
              style: Brutal.display(
                  size: 12,
                  weight: FontWeight.w800,
                  spacing: 1,
                  color: active ? Brutal.ink : Brutal.white)),
        ),
      );
    }

    return BrutalBox(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: Brutal.ink,
            child: Row(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  child: Text('04 /',
                      style: Brutal.mono(
                          size: 11,
                          weight: FontWeight.w700,
                          color: Brutal.accent.withValues(alpha: 0.6))),
                ),
                tab(0, 'POSITIONS', portfolio.length),
                tab(1, 'ORDER LOG', trades.length),
                const Spacer(),
                IconButton(
                  tooltip: 'Refresh',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.refresh, color: Brutal.accent, size: 18),
                  onPressed: () {
                    trading.fetchPortfolio();
                    trading.fetchTrades();
                    trading.fetchUserLimits();
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: _bottomTab == 0
                ? (portfolio.isEmpty
                    ? const BrutalEmpty(
                        title: 'No open positions', icon: Icons.inventory_2_outlined)
                    : ListView.builder(
                        padding: const EdgeInsets.all(10),
                        itemCount: portfolio.length,
                        itemBuilder: (_, i) => PortfolioItem(
                          item: portfolio[i],
                          compact: true,
                          onTap: () {
                            _select(portfolio[i]['symbol'] as String);
                            setState(() => _side = _Side.sell);
                          },
                        ),
                      ))
                : (trades.isEmpty
                    ? const BrutalEmpty(
                        title: 'No orders yet', icon: Icons.receipt_long)
                    : ListView.separated(
                        padding: const EdgeInsets.all(10),
                        itemCount: trades.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (_, i) =>
                            TradeRow(trade: trades[i], compact: true),
                      )),
          ),
        ],
      ),
    );
  }
}

// ── Header ────────────────────────────────────────────────────────────────────

class _TerminalHeader extends StatelessWidget {
  final DateTime? lastMessageAt;

  const _TerminalHeader({required this.lastMessageAt});

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();
    final ist = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
    String two(int v) => v.toString().padLeft(2, '0');
    final clock = '${two(ist.hour)}:${two(ist.minute)}:${two(ist.second)} IST';

    final age = lastMessageAt == null
        ? null
        : DateTime.now().difference(lastMessageAt!).inSeconds;
    final (linkText, linkColor) = switch (age) {
      null => ('NO FEED', Brutal.down),
      <= 3 => ('LIVE', Brutal.up),
      _ => ('STALE ${age}s', Brutal.accent),
    };

    return Container(
      color: Brutal.ink,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            color: Brutal.accent,
            child: Text('▮ TERMINAL',
                style: Brutal.display(size: 15, weight: FontWeight.w900)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _chip('FEED', linkText, linkColor),
                  _chip('CLOCK', clock, Brutal.white),
                  _chip('FUNDS', Brutal.money(trading.balance), Brutal.accent),
                  _chip(
                    'DAY LEFT',
                    Brutal.money(trading.dailyLimit - trading.dailySpent, decimals: 0),
                    Brutal.white,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          Tooltip(
            message: 'Exit terminal',
            child: InkWell(
              onTap: () => Navigator.of(context).maybePop(),
              child: Container(
                height: 34,
                padding: const EdgeInsets.symmetric(horizontal: 10),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  border: Border.all(color: Brutal.white, width: 2),
                ),
                child: Text('EXIT ✕',
                    style: Brutal.mono(
                        size: 12, weight: FontWeight.w800, color: Brutal.white)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String k, String v, Color color) {
    return Padding(
      padding: const EdgeInsets.only(right: 16),
      child: Row(
        children: [
          Text('$k ', style: Brutal.label(size: 10, color: Brutal.white.withValues(alpha: 0.55))),
          Text(v, style: Brutal.mono(size: 12, weight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }
}

// ── Ticker tape ───────────────────────────────────────────────────────────────

class _TickerTape extends StatefulWidget {
  final List<String> symbols;
  const _TickerTape({required this.symbols});

  @override
  State<_TickerTape> createState() => _TickerTapeState();
}

class _TickerTapeState extends State<_TickerTape> {
  final _scroll = ScrollController();
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 40), (_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.offset + 1);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final symbols = widget.symbols;
    final market = context.watch<MarketDataProvider>();
    return Container(
      height: 30,
      decoration: const BoxDecoration(
        color: Brutal.accent,
        border: Border(bottom: Brutal.side),
      ),
      child: symbols.isEmpty
          ? const SizedBox.shrink()
          : ExcludeSemantics(
              child: ListView.builder(
                controller: _scroll,
                scrollDirection: Axis.horizontal,
                physics: const NeverScrollableScrollPhysics(),
                // Unbounded list: indexes wrap around the watchlist forever.
                itemBuilder: (context, i) {
                  final s = symbols[i % symbols.length];
                  final p = market.getPrice(s);
                  final c = market.sessionChange(s);
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    child: Center(
                      child: Text.rich(
                        TextSpan(children: [
                          TextSpan(
                              text: '${s.split('.').first} ',
                              style: Brutal.display(size: 12, weight: FontWeight.w900)),
                          TextSpan(
                              text: p?.toStringAsFixed(2) ?? '—',
                              style: Brutal.mono(size: 12, weight: FontWeight.w700)),
                          if (c != null && c != 0)
                            TextSpan(
                              text: ' ${c > 0 ? '▲' : '▼'}${c.abs().toStringAsFixed(2)}',
                              style: Brutal.mono(
                                  size: 12,
                                  weight: FontWeight.w800,
                                  color: c > 0 ? const Color(0xFF006B34) : Brutal.down),
                            ),
                          TextSpan(text: '   ◆', style: Brutal.mono(size: 10)),
                        ]),
                      ),
                    ),
                  );
                },
              ),
            ),
    );
  }
}

// ── Tick chart ────────────────────────────────────────────────────────────────

/// Step chart of distinct prices received this session. No candles: the
/// backend feed only carries LTP, so this is an honest tick tape.
class _TickChartPainter extends CustomPainter {
  final List<double> points;
  _TickChartPainter(List<double> points) : points = List.of(points);

  @override
  void paint(Canvas canvas, Size size) {
    const padR = 64.0, padV = 14.0;
    final w = size.width - padR;
    final h = size.height - padV * 2;
    if (w <= 0 || h <= 0) return;

    var lo = points.reduce(math.min);
    var hi = points.reduce(math.max);
    if (hi == lo) {
      hi += 0.5;
      lo -= 0.5;
    }
    double y(double v) => padV + (hi - v) / (hi - lo) * h;
    final dx = w / (points.length - 1);

    final last = points.last;
    final ly = y(last);

    // Grid (axis labels that would sit under the last-price tag are skipped)
    final grid = Paint()
      ..color = Brutal.rule
      ..strokeWidth = 1;
    for (var i = 0; i <= 4; i++) {
      final gy = padV + h * i / 4;
      canvas.drawLine(Offset(0, gy), Offset(w, gy), grid);
      if ((gy - ly).abs() < 18) continue;
      _label(canvas, (hi - (hi - lo) * i / 4).toStringAsFixed(2),
          Offset(w + 6, gy - 7), Brutal.muted);
    }

    // Step path
    final line = Path()..moveTo(0, y(points.first));
    for (var i = 1; i < points.length; i++) {
      line.lineTo(dx * i, y(points[i - 1]));
      line.lineTo(dx * i, y(points[i]));
    }
    final area = Path.from(line)
      ..lineTo(w, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(area, Paint()..color = Brutal.accent.withValues(alpha: 0.55));
    canvas.drawPath(
      line,
      Paint()
        ..color = Brutal.ink
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeJoin = StrokeJoin.miter,
    );

    // Last-price marker
    final up = last >= points.first;
    canvas.drawLine(
        Offset(0, ly),
        Offset(w, ly),
        Paint()
          ..color = Brutal.ink
          ..strokeWidth = 1);
    final tag = Rect.fromLTWH(w, ly - 10, padR, 20);
    canvas.drawRect(tag, Paint()..color = up ? Brutal.up : Brutal.down);
    _label(canvas, last.toStringAsFixed(2), Offset(w + 5, ly - 7), Brutal.white,
        bold: true);
  }

  void _label(Canvas c, String text, Offset at, Color color, {bool bold = false}) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: Brutal.mono(
            size: 10, color: color, weight: bold ? FontWeight.w800 : FontWeight.w500),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(c, at);
  }

  @override
  bool shouldRepaint(_TickChartPainter old) =>
      old.points.length != points.length ||
      (points.isNotEmpty && old.points.last != points.last);
}

// ── Confirmation ──────────────────────────────────────────────────────────────

class _ConfirmOrderDialog extends StatelessWidget {
  final String side;
  final String symbol;
  final int qty;
  final double? ltp;
  final double? stopLoss;

  const _ConfirmOrderDialog({
    required this.side,
    required this.symbol,
    required this.qty,
    required this.ltp,
    required this.stopLoss,
  });

  @override
  Widget build(BuildContext context) {
    final isBuy = side == 'BUY';
    final color = isBuy ? Brutal.up : Brutal.down;

    Widget row(String k, String v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            children: [
              Expanded(child: Text(k, style: Brutal.label())),
              Text(v, style: Brutal.mono(size: 15, weight: FontWeight.w800)),
            ],
          ),
        );

    return Dialog(
      insetPadding: const EdgeInsets.all(20),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 380),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BrutalStrip(
              index: '!!',
              title: 'Confirm $side',
              color: color,
              foreground: Brutal.white,
            ),
            Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('$side $qty × $symbol',
                      style: Brutal.display(size: 22, weight: FontWeight.w900)),
                  const SizedBox(height: 12),
                  Container(height: Brutal.border, color: Brutal.ink),
                  const SizedBox(height: 8),
                  row('ORDER TYPE', 'MARKET'),
                  row('LAST PRICE', ltp != null ? Brutal.money(ltp!) : '—'),
                  row('EST. VALUE', ltp != null ? Brutal.money(ltp! * qty) : '—'),
                  if (stopLoss != null) row('STOP LOSS', Brutal.money(stopLoss!)),
                  const SizedBox(height: 8),
                  Text('Sandbox order — paper money only.',
                      style: Brutal.mono(size: 11, color: Brutal.muted)),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Expanded(
                        child: BrutalButton(
                          label: 'Cancel',
                          color: Brutal.white,
                          onPressed: () => Navigator.pop(context, false),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: BrutalButton(
                          label: 'Confirm',
                          color: color,
                          foreground: Brutal.white,
                          onPressed: () => Navigator.pop(context, true),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
