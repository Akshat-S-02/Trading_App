import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart' show DateFormat;
import 'package:provider/provider.dart';
import '../app_config.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../screens/chart_screen.dart';
import '../services/auth_service.dart';
import '../utils/format.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

/// Pushes a full-screen news feed limited to one stock (used from the chart).
void openStockNews(BuildContext context, String symbol) {
  final bare = bareSymbol(symbol);
  Navigator.of(context).push(MaterialPageRoute(
    builder: (_) => Scaffold(
      appBar: AppBar(title: Text('$bare news', style: AppText.headline)),
      body: NewsWidget(fixedSymbols: [bare]),
    ),
  ));
}

class _ServerError implements Exception {
  final String message;
  _ServerError(this.message);
}

class NewsItem {
  final String title, text, sentiment;
  final String? category, subCategory, symbol, name, topic;
  final DateTime? date;

  NewsItem.fromJson(Map<String, dynamic> j)
      : title = (j['title'] ?? '').toString(),
        text = (j['text'] ?? '').toString(),
        sentiment = (j['sentiment'] ?? 'neutral').toString(),
        category = j['category']?.toString(),
        subCategory = j['sub_category']?.toString(),
        symbol = j['symbol']?.toString(),
        name = j['name']?.toString(),
        topic = j['topic']?.toString(),
        date = DateTime.tryParse((j['date'] ?? '').toString());

  /// Dhan gives no article id; title + stock is unique enough.
  String get key => '$symbol|$title';
}

/// Live market news from Dhan's news-headline API: category / watchlist /
/// positions filters, sentiment filter, search, auto-refresh every 60 s.
class NewsWidget extends StatefulWidget {
  /// When set, the feed is locked to these stocks and the scope chips are hidden.
  final List<String>? fixedSymbols;
  const NewsWidget({super.key, this.fixedSymbols});

  @override
  State<NewsWidget> createState() => _NewsWidgetState();
}

enum _Scope { all, watchlist, positions }

class _NewsWidgetState extends State<NewsWidget> {
  static const _categories = <String, String>{
    'ALL': 'All news',
    'COMPANIES': 'Companies',
    'EQUITY_MARKETS': 'Markets',
    'INDIAN_ECONOMY': 'Economy',
    'GLOBAL': 'Global',
    'GLOBAL_ECONOMY': 'Global economy',
    'IPO': 'IPO',
    'COMMODITIES': 'Commodities',
    'CURRENCY': 'Currency',
    'GOVERNMENT_POLICY_AND_REGULATION': 'Policy',
    'TECHNOLOGY': 'Tech',
    'MUTUAL_FUNDS': 'Mutual funds',
    'INVESTMENT_IDEAS': 'Ideas',
  };

  _Scope _scope = _Scope.all;
  String _category = 'ALL';
  String? _sentiment; // null = all
  String _query = '';

  List<NewsItem> _items = [];
  final Set<String> _seen = {};
  final Set<String> _fresh = {};
  final Set<String> _expanded = {};
  bool _loading = false;
  String? _error;
  DateTime? _updatedAt;
  Timer? _timer;
  int _requestId = 0;

  final _searchCtl = TextEditingController();

  bool get _locked => widget.fixedSymbols != null;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    _searchCtl.dispose();
    super.dispose();
  }

  List<String> _scopeSymbols() {
    if (_locked) return widget.fixedSymbols!;
    switch (_scope) {
      case _Scope.all:
        return const [];
      case _Scope.watchlist:
        return context.read<MarketDataProvider>().watchlist.map(bareSymbol).toList();
      case _Scope.positions:
        return context
            .read<TradingProvider>()
            .positions
            .map((p) => bareSymbol((p['symbol'] ?? '').toString()))
            .where((s) => s.isNotEmpty)
            .toSet()
            .toList();
    }
  }

  Future<void> _load({bool silent = false}) async {
    final id = ++_requestId;
    final symbols = _scopeSymbols();
    if (!_locked && _scope != _Scope.all && symbols.isEmpty) {
      setState(() {
        _items = [];
        _error = null;
        _loading = false;
      });
      return;
    }
    if (!silent) setState(() => _loading = true);
    try {
      final uri = Uri.parse('$kHttpBase/api/market/news').replace(queryParameters: {
        'category': _category,
        'limit': '50',
        if (symbols.isNotEmpty) 'symbols': symbols.join(','),
      });
      final res =
          await http.get(uri, headers: await AuthService.authHeaders()).timeout(const Duration(seconds: 20));
      if (!mounted || id != _requestId) return;
      AuthService.checkAuth(res);
      if (res.statusCode != 200) {
        String msg = 'HTTP ${res.statusCode}';
        try {
          msg = (jsonDecode(res.body)['detail'] ?? msg).toString();
        } catch (_) {}
        throw _ServerError(msg);
      }
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final items =
          (data['news'] as List? ?? []).map((e) => NewsItem.fromJson(Map<String, dynamic>.from(e))).toList();
      setState(() {
        // Mark headlines that arrived since the previous load (not on first load).
        _fresh.clear();
        if (_seen.isNotEmpty) {
          _fresh.addAll(items.map((n) => n.key).where((k) => !_seen.contains(k)));
        }
        _seen.addAll(items.map((n) => n.key));
        _items = items;
        _error = null;
        _updatedAt = DateTime.now();
      });
    } on _ServerError catch (e) {
      if (!mounted || id != _requestId) return;
      // Keep showing the last good list on a failed background refresh.
      setState(() => _error = e.message);
    } catch (e) {
      if (!mounted || id != _requestId) return;
      setState(() => _error = "Can't reach the backend at $kHttpBase");
    } finally {
      if (mounted && id == _requestId) setState(() => _loading = false);
    }
  }

  void _changeFilter(VoidCallback change) {
    setState(() {
      change();
      _seen.clear();
      _fresh.clear();
      _items = [];
    });
    _load();
  }

  List<NewsItem> get _visible {
    final q = _query.trim().toLowerCase();
    return _items.where((n) {
      if (_sentiment != null && n.sentiment != _sentiment) return false;
      if (q.isEmpty) return true;
      return n.title.toLowerCase().contains(q) ||
          n.text.toLowerCase().contains(q) ||
          (n.symbol ?? '').toLowerCase().contains(q) ||
          (n.name ?? '').toLowerCase().contains(q) ||
          (n.topic ?? '').toLowerCase().contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visible;
    return Column(
      children: [
        _searchBar(),
        if (!_locked) _scopeRow(),
        _categoryRow(),
        _sentimentRow(),
        // Fixed-height slot so the list doesn't jump when loading starts/stops.
        SizedBox(height: 2, child: _loading ? const LinearProgressIndicator(minHeight: 2) : null),
        if (_error != null && _items.isNotEmpty) _errorStrip(),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _load,
            child: _body(visible),
          ),
        ),
      ],
    );
  }

  // ── Filters ────────────────────────────────────────────────────────────

  Widget _searchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: TextField(
        controller: _searchCtl,
        decoration: InputDecoration(
          hintText: 'Search headlines or stocks',
          prefixIcon: const Icon(Icons.search_rounded),
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(vertical: 11),
          suffixIcon: _query.isEmpty
              ? null
              : IconButton(
                  icon: const Icon(Icons.cancel_rounded, size: 20),
                  onPressed: () {
                    _searchCtl.clear();
                    setState(() => _query = '');
                  },
                ),
        ),
        onChanged: (v) => setState(() => _query = v),
      ),
    );
  }

  Widget _scopeRow() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
      child: SizedBox(
        width: double.infinity,
        child: SegmentedButton<_Scope>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: _Scope.all, label: Text('All')),
            ButtonSegment(value: _Scope.watchlist, label: Text('Watchlist')),
            ButtonSegment(value: _Scope.positions, label: Text('Positions')),
          ],
          selected: {_scope},
          onSelectionChanged: (s) {
            HapticFeedback.selectionClick();
            _changeFilter(() => _scope = s.first);
          },
        ),
      ),
    );
  }

  Widget _categoryRow() {
    return SizedBox(
      height: 46,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
        children: _categories.entries
            .map((e) => Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    label: Text(e.value),
                    selected: _category == e.key,
                    visualDensity: VisualDensity.compact,
                    onSelected: (_) {
                      if (_category != e.key) _changeFilter(() => _category = e.key);
                    },
                  ),
                ))
            .toList(),
      ),
    );
  }

  Widget _sentimentRow() {
    int count(String s) => _items.where((n) => n.sentiment == s).length;
    Widget chip(String? value, IconData icon, Color color, int n) {
      final selected = _sentiment == value;
      return Padding(
        padding: const EdgeInsets.only(right: 6),
        child: FilterChip(
          visualDensity: VisualDensity.compact,
          showCheckmark: false,
          selected: selected,
          selectedColor: color.withValues(alpha: 0.24),
          avatar: Icon(icon, size: 16, color: color),
          label: Text('$n',
              style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600,
                  fontFeatures: AppText.tabular)),
          tooltip: '${value![0].toUpperCase()}${value.substring(1)} headlines',
          onSelected: (_) => setState(() => _sentiment = selected ? null : value),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      child: Row(
        children: [
          chip('positive', Icons.trending_up, kBuyColor, count('positive')),
          chip('negative', Icons.trending_down, kSellColor, count('negative')),
          chip('neutral', Icons.trending_flat, AppColors.secondary, count('neutral')),
          const Spacer(),
          if (_updatedAt != null)
            Text('Updated ${DateFormat('HH:mm').format(_updatedAt!)}', style: AppText.caption),
        ],
      ),
    );
  }

  Widget _errorStrip() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      child: Surface(
        color: AppColors.orange.withValues(alpha: 0.14),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Text('Couldn’t refresh. Showing earlier headlines. $_error',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: AppText.footnote.copyWith(color: AppColors.orange)),
      ),
    );
  }

  // ── List ───────────────────────────────────────────────────────────────

  Widget _message(IconData icon, String text, {Widget? action}) {
    // ListView so pull-to-refresh still works on empty states.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 40),
        EmptyState(icon: icon, title: text, action: action),
      ],
    );
  }

  Widget _body(List<NewsItem> visible) {
    if (_items.isEmpty) {
      if (_loading) return const SizedBox.shrink();
      if (_error != null) {
        return _message(Icons.cloud_off, "Couldn't load news.\n$_error",
            action: OutlinedButton(onPressed: _load, child: const Text('Try again')));
      }
      if (!_locked && _scope == _Scope.watchlist && _scopeSymbols().isEmpty) {
        return _message(Icons.star_outline, 'Your watchlist is empty. Add stocks in the Market tab.');
      }
      if (!_locked && _scope == _Scope.positions && _scopeSymbols().isEmpty) {
        return _message(Icons.account_balance_wallet_outlined, 'No open positions.');
      }
      return _message(Icons.article_outlined, 'No recent headlines for this filter.');
    }
    if (visible.isEmpty) {
      return _message(Icons.filter_alt_off, 'No headlines match your search or sentiment filter.');
    }

    // Group by publish date, newest first (API order is already newest first).
    final rows = <Widget>[];
    String? lastDay;
    for (final n in visible) {
      final day = _dayLabel(n.date);
      if (day != lastDay) {
        rows.add(SectionHeader(day, padding: const EdgeInsets.fromLTRB(20, 16, 20, 8)));
        lastDay = day;
      }
      rows.add(_card(n));
    }
    rows.add(SizedBox(height: bottomInset(context)));
    return ListView(physics: const AlwaysScrollableScrollPhysics(), children: rows);
  }

  String _dayLabel(DateTime? d) {
    if (d == null) return 'Earlier';
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(d.year, d.month, d.day);
    final diff = today.difference(day).inDays;
    if (diff == 0) return 'Today';
    if (diff == 1) return 'Yesterday';
    return DateFormat('EEE, d MMM').format(d);
  }

  Color _sentimentColor(String s) =>
      s == 'positive' ? kBuyColor : (s == 'negative' ? kSellColor : AppColors.tertiary);

  String _pretty(String? s) {
    if (s == null || s.isEmpty) return '';
    final words = s.replaceAll(RegExp(r'[-_]'), ' ').toLowerCase().split(' ');
    return words.map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}').join(' ');
  }

  Widget _card(NewsItem n) {
    final expanded = _expanded.contains(n.key);
    final color = _sentimentColor(n.sentiment);
    final isFresh = _fresh.contains(n.key);
    final hasStock = (n.symbol ?? '').isNotEmpty;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
      child: Pressable(
        pressedScale: 0.985,
        onTap: () => setState(() => expanded ? _expanded.remove(n.key) : _expanded.add(n.key)),
        child: ClipPath(
          clipper: ShapeBorderClipper(shape: rounded(16)),
          child: Container(
            color: AppColors.card,
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(width: 3, color: color),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(13, 12, 14, 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              if (hasStock) ...[
                                Pill(n.symbol!, color: AppColors.accent),
                                const SizedBox(width: 6),
                              ] else if ((n.topic ?? '').isNotEmpty) ...[
                                ConstrainedBox(
                                    constraints: const BoxConstraints(maxWidth: 160),
                                    child: Pill(
                                        n.topic == n.topic!.toLowerCase() ? _pretty(n.topic) : n.topic!,
                                        color: AppColors.secondary)),
                                const SizedBox(width: 6),
                              ],
                              Expanded(
                                child: Text(
                                  [_pretty(n.category), _pretty(n.subCategory)]
                                      .where((s) => s.isNotEmpty)
                                      .join(' · '),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: AppText.caption,
                                ),
                              ),
                              if (isFresh) ...[
                                const Pill('New', color: AppColors.teal),
                                const SizedBox(width: 6),
                              ],
                              Icon(
                                n.sentiment == 'positive'
                                    ? Icons.trending_up_rounded
                                    : n.sentiment == 'negative'
                                        ? Icons.trending_down_rounded
                                        : Icons.trending_flat_rounded,
                                size: 16,
                                color: color,
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(n.title, style: AppText.headline),
                          if (n.text.isNotEmpty) ...[
                            const SizedBox(height: 6),
                            AnimatedSize(
                              duration: motionDuration(context),
                              curve: motionCurve,
                              alignment: Alignment.topCenter,
                              child: Text(
                                n.text,
                                maxLines: expanded ? null : 2,
                                overflow: expanded ? TextOverflow.visible : TextOverflow.ellipsis,
                                style: AppText.callout.copyWith(color: AppColors.secondary),
                              ),
                            ),
                          ],
                          if (expanded && hasStock) _stockActions(n),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _stockActions(NewsItem n) {
    final sym = '${n.symbol}.NS';
    final inList = context.watch<MarketDataProvider>().watchlist.contains(sym);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if ((n.name ?? '').isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(n.name!, style: AppText.footnote),
            ),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(visualDensity: VisualDensity.compact),
              onPressed: () => openChart(context, sym),
              icon: const Icon(Icons.show_chart_rounded, size: 16),
              label: const Text('Chart'),
            ),
            if (!inList)
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(visualDensity: VisualDensity.compact),
                onPressed: () {
                  context.read<MarketDataProvider>().addToWatchlist(sym);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text('${n.symbol} added to watchlist'), duration: const Duration(seconds: 2)));
                },
                icon: const Icon(Icons.star_outline, size: 16),
                label: const Text('Watch'),
              ),
          ]),
        ],
      ),
    );
  }
}
