import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/health_provider.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

class HealthWidget extends StatefulWidget {
  const HealthWidget({super.key});

  @override
  State<HealthWidget> createState() => _HealthWidgetState();
}

class _HealthWidgetState extends State<HealthWidget> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<HealthProvider>().startPolling();
    });
  }

  @override
  void dispose() {
    // Polling is owned by the dashboard (the feed dot needs it on every tab),
    // so leaving this screen must not stop it.
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final health = context.watch<HealthProvider>();
    final renewal = health.tokenData['auto_renewal']?['next_renewal_at'];
    final age = health.lastTickAgeSec;

    return ListView(
      padding: EdgeInsets.fromLTRB(16, 8, 16, bottomInset(context)),
      children: [
        const SectionHeader('Backend'),
        InsetGroup(children: [
          _status('API', health.isBackendReachable ? _ok : _bad,
              health.isBackendReachable ? 'Online' : 'Offline'),
        ]),
        const SizedBox(height: 24),
        const SectionHeader('Broker'),
        InsetGroup(children: [
          _status('Access token', health.isTokenValid ? _ok : _bad,
              health.isTokenValid ? 'Valid' : 'Expired'),
          _info('Next renewal',
              renewal != null ? DateTime.parse(renewal).toLocal().toString().split('.')[0] : 'Unknown'),
        ]),
        const SizedBox(height: 24),
        const SectionHeader('Market feed'),
        InsetGroup(children: [
          _status(
            'WebSocket',
            health.feedData['stale'] == true ? _warn : (health.isFeedConnected ? _ok : _bad),
            health.feedData['stale'] == true ? 'Stale' : (health.isFeedConnected ? 'Connected' : 'Disconnected'),
          ),
          _info('Last tick', age < 90000 ? '${age.toStringAsFixed(1)}s ago' : 'Unknown',
              color: age < 2.0 ? _ok : (age < 10.0 ? _warn : _bad)),
          _info('Reconnects today', '${health.feedReconnectCount}',
              color: health.feedReconnectCount > 5 ? _warn : null),
        ]),
        const SizedBox(height: 24),
        const SectionHeader('Workers'),
        InsetGroup(children: [
          // The backend doesn't report worker status yet, so say so rather
          // than showing a status we can't back up.
          _info('Outbox worker', 'Not reported'),
          _info('Orders pending', 'Not reported'),
        ]),
      ],
    );
  }

  static const _ok = AppColors.green;
  static const _warn = AppColors.orange;
  static const _bad = AppColors.red;

  Widget _status(String label, Color color, String value) => _row(
        label,
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            StatusDot(color),
            const SizedBox(width: 8),
            Text(value, style: AppText.callout.copyWith(color: AppColors.secondary)),
          ],
        ),
      );

  Widget _info(String label, String value, {Color? color}) => _row(
        label,
        Text(value,
            style: AppText.callout.copyWith(color: color ?? AppColors.secondary, fontFeatures: AppText.tabular)),
      );

  Widget _row(String label, Widget trailing) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        child: Row(
          children: [
            Expanded(child: Text(label, style: AppText.body)),
            trailing,
          ],
        ),
      );
}
