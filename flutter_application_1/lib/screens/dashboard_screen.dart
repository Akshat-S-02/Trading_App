import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/health_provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/notification_provider.dart';
import 'notifications_screen.dart';
import '../providers/trading_provider.dart';
import '../ui/components.dart';
import '../ui/theme.dart';
import '../widgets/market_widget.dart';
import '../widgets/portfolio_widget.dart';
import '../widgets/orders_widget.dart';
import '../widgets/control_widget.dart';
import '../widgets/health_widget.dart';
import '../widgets/news_widget.dart';
import '../widgets/settings_dialog.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _selectedIndex = 0;

  static const _titles = ['Market', 'News', 'Positions', 'Orders', 'Auto-trading'];


  @override
  void initState() {
    super.initState();
    // Handles the auto-login path: user had a stored token so they skip
    // LoginScreen. Both initialize() calls are idempotent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MarketDataProvider>().initialize();
      context.read<TradingProvider>().initialize();
      context.read<NotificationProvider>().initialize();
      // Feed dot and stale-price banner need health data on every tab.
      context.read<HealthProvider>().startPolling();
    });
  }

  void _onItemTapped(int index) {
    setState(() => _selectedIndex = index);
    final trading = context.read<TradingProvider>();
    if (index == 2) {
      trading.fetchPortfolio();
      trading.fetchPositions();
    }
    if (index == 3) trading.fetchTrades();
    if (index == 4) trading.fetchPaperStatus();
  }

  @override
  Widget build(BuildContext context) {
    final trading = context.watch<TradingProvider>();
    final openCount = trading.positions.length + trading.pendingOrders.length;

    Widget badged(IconData icon) => Badge(
          isLabelVisible: openCount > 0,
          label: Text('$openCount'),
          child: Icon(icon),
        );

    return Scaffold(
      // Content scrolls under the translucent tab bar.
      extendBody: true,
      appBar: AppBar(
        titleSpacing: 20,
        toolbarHeight: 60,
        title: Text(_titles[_selectedIndex], style: AppText.title1),
        actions: [
          _modeChip(trading),
          const SizedBox(width: 4),
          _feedDot(),
          Consumer<NotificationProvider>(
            builder: (_, notes, __) => IconButton(
              tooltip: 'Notifications',
              onPressed: () => Navigator.of(context)
                  .push(MaterialPageRoute(builder: (_) => const NotificationsScreen())),
              icon: Badge(
                isLabelVisible: notes.unread > 0,
                label: Text('${notes.unread}'),
                child: const Icon(Icons.notifications_outlined),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Risk limits',
            icon: const Icon(Icons.tune_rounded),
            onPressed: () => showRiskLimits(context),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: const [
          MarketWidget(),
          NewsWidget(),
          PortfolioWidget(),
          OrdersWidget(),
          ControlWidget(),
        ],
      ),
      bottomNavigationBar: GlassBar(
        child: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: (i) {
            if (i != _selectedIndex) HapticFeedback.selectionClick();
            _onItemTapped(i);
          },
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          animationDuration: Duration.zero,
          destinations: [
            const NavigationDestination(
              icon: Icon(Icons.show_chart_rounded),
              label: 'Market',
            ),
            const NavigationDestination(
              icon: Icon(Icons.article_outlined),
              selectedIcon: Icon(Icons.article),
              label: 'News',
            ),
            NavigationDestination(
              icon: badged(Icons.account_balance_wallet_outlined),
              selectedIcon: badged(Icons.account_balance_wallet),
              label: 'Positions',
            ),
            const NavigationDestination(
              icon: Icon(Icons.receipt_long_outlined),
              selectedIcon: Icon(Icons.receipt_long),
              label: 'Orders',
            ),
            NavigationDestination(
              icon: Stack(
                clipBehavior: Clip.none,
                children: [
                  const Icon(Icons.auto_awesome_outlined),
                  if (trading.autoRunning)
                    const Positioned(right: -2, top: -1, child: StatusDot(AppColors.green, size: 7)),
                ],
              ),
              selectedIcon: const Icon(Icons.auto_awesome),
              label: 'Auto',
            ),
          ],
        ),
      ),
    );
  }

  Widget _modeChip(TradingProvider trading) {
    final stopped = trading.emergencyStop;
    final live = trading.executionMode == 'live';
    final color = stopped ? AppColors.red : (live ? AppColors.orange : AppColors.teal);
    final label = stopped ? 'Stopped' : (live ? 'Live' : 'Paper');
    return Pill(label, color: color, icon: stopped ? Icons.block : null);
  }

  void _openHealth() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => Scaffold(
        appBar: AppBar(title: const Text('System health', style: AppText.headline)),
        body: const HealthWidget(),
      ),
    ));
  }

  Widget _feedDot() {
    return Consumer<HealthProvider>(
      builder: (_, health, __) {
        final healthy = health.isFeedHealthy;
        return IconButton(
          tooltip: healthy ? 'Market feed live · system health' : 'Market feed down or stale · system health',
          onPressed: _openHealth,
          icon: StatusDot(healthy ? AppColors.green : AppColors.red, size: 10),
        );
      },
    );
  }
}
