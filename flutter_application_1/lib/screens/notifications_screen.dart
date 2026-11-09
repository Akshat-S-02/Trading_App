import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/notification_provider.dart';
import '../ui/components.dart';
import '../ui/theme.dart';
import '../utils/format.dart';

/// Every alert the server raised: fills, exits, halts, feed problems.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  @override
  void initState() {
    super.initState();
    // Opening the list counts as reading it (clears the bell badge).
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<NotificationProvider>().markAllRead());
  }

  @override
  Widget build(BuildContext context) {
    final notes = context.watch<NotificationProvider>();
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications', style: AppText.headline)),
      body: RefreshIndicator(
        onRefresh: notes.fetch,
        child: notes.items.isEmpty
            ? ListView(children: const [
                EmptyState(
                  icon: Icons.notifications_none_rounded,
                  title: 'No notifications yet',
                  message: 'Fills, exits, halts and feed problems show up here.',
                ),
              ])
            : ListView.separated(
                padding: const EdgeInsets.symmetric(vertical: 8),
                itemCount: notes.items.length,
                separatorBuilder: (_, __) => const Divider(height: 1, indent: 56),
                itemBuilder: (_, i) {
                  final n = notes.items[i];
                  return ListTile(
                    leading: Icon(levelIcon(n['level']), color: levelColor(n['level'])),
                    title: Text(n['title'] ?? '', style: AppText.headline),
                    subtitle: Text('${n['message'] ?? ''}\n${timeOf(n['created_at'])}', style: AppText.footnote),
                    isThreeLine: true,
                  );
                },
              ),
      ),
    );
  }
}
