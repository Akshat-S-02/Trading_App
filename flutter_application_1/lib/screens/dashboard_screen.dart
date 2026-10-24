import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../widgets/market_widget.dart';
import '../widgets/portfolio_widget.dart';
import '../widgets/orders_widget.dart';
import '../widgets/settings_dialog.dart';
import '../theme/brutal_theme.dart';
import '../widgets/brutal/brutal.dart';
import 'terminal_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    // Handles the auto-login path: user had a stored token so they skip
    // LoginScreen. Both initialize() calls are idempotent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MarketDataProvider>().initialize();
      context.read<TradingProvider>().initialize();
    });
  }

  final List<Widget> _pages = [
    const MarketWidget(),
    const PortfolioWidget(),
    const OrdersWidget(),
  ];

  void _onItemTapped(int index) {
    setState(() => _selectedIndex = index);
    final trading = context.read<TradingProvider>();
    if (index == 1) trading.fetchPortfolio();
    if (index == 2) trading.fetchTrades();
  }

  void _openTerminal() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const TerminalScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 12,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              color: Brutal.ink,
              child: Text('AI/TRADER',
                  style: Brutal.display(
                      size: 16, weight: FontWeight.w900, color: Brutal.accent)),
            ),
            const SizedBox(width: 8),
            const BrutalTag('Sandbox', color: Brutal.accent),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: BrutalButton(
              label: 'Terminal',
              icon: Icons.terminal,
              height: 40,
              fontSize: 12,
              color: Brutal.ink,
              foreground: Brutal.accent,
              onPressed: _openTerminal,
            ),
          ),
          const SizedBox(width: 10),
          BrutalIconButton(
            icon: Icons.tune,
            tooltip: 'Risk settings',
            onPressed: () {
              showDialog(
                context: context,
                builder: (_) => const SettingsDialog(),
              );
            },
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: Column(
        children: [
          // Balance & Limits header
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 20, 8),
            child: BrutalBox(
              color: Brutal.accent,
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('SANDBOX BALANCE', style: Brutal.label(color: Brutal.ink)),
                  const SizedBox(height: 4),
                  FittedBox(
                    alignment: Alignment.centerLeft,
                    fit: BoxFit.scaleDown,
                    child: Text(
                      Brutal.money(trading.balance),
                      style: Brutal.mono(size: 36, weight: FontWeight.w800),
                    ),
                  ),
                  const SizedBox(height: 14),
                  BrutalMeter(
                      label: 'Daily limit',
                      spent: trading.dailySpent,
                      limit: trading.dailyLimit),
                  const SizedBox(height: 10),
                  BrutalMeter(
                      label: 'Monthly limit',
                      spent: trading.monthlySpent,
                      limit: trading.monthlyLimit),
                ],
              ),
            ),
          ),

          Expanded(child: _pages[_selectedIndex]),
        ],
      ),
      bottomNavigationBar: _BrutalNav(
        currentIndex: _selectedIndex,
        onTap: _onItemTapped,
        items: const [
          (Icons.candlestick_chart, 'Market'),
          (Icons.pie_chart_outline, 'Portfolio'),
          (Icons.receipt_long, 'Orders'),
        ],
      ),
    );
  }
}

class _BrutalNav extends StatelessWidget {
  final int currentIndex;
  final ValueChanged<int> onTap;
  final List<(IconData, String)> items;

  const _BrutalNav({
    required this.currentIndex,
    required this.onTap,
    required this.items,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Brutal.paper,
        border: Border(top: Brutal.side),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 64,
          child: Row(
            children: [
              for (var i = 0; i < items.length; i++)
                Expanded(
                  child: Semantics(
                    button: true,
                    selected: i == currentIndex,
                    label: items[i].$2,
                    child: InkWell(
                      onTap: () => onTap(i),
                      child: Container(
                        decoration: BoxDecoration(
                          color: i == currentIndex ? Brutal.ink : Brutal.paper,
                          border: i == 0
                              ? null
                              : const Border(left: Brutal.side),
                        ),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(items[i].$1,
                                size: 22,
                                color: i == currentIndex
                                    ? Brutal.accent
                                    : Brutal.ink),
                            const SizedBox(height: 4),
                            Text(
                              '0${i + 1} ${items[i].$2.toUpperCase()}',
                              style: Brutal.mono(
                                size: 11,
                                weight: FontWeight.w800,
                                color: i == currentIndex
                                    ? Brutal.accent
                                    : Brutal.ink,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
