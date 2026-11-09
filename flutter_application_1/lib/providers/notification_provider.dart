import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../app_config.dart';
import '../services/auth_service.dart';
import '../ui/theme.dart';

/// Attached to MaterialApp so a pop-up banner can show on whatever screen is open.
final appMessengerKey = GlobalKey<ScaffoldMessengerState>();

/// Server alerts (fills, exits, halts, feed problems) for the bell + list.
/// While the app is open, new ones also show as a pop-up banner. With the app
/// closed, the server pushes the same alerts through Telegram.
class NotificationProvider with ChangeNotifier {
  List<Map<String, dynamic>> _items = [];
  List<Map<String, dynamic>> get items => _items;
  int _unread = 0;
  int get unread => _unread;

  int? _lastSeenId; // newest id already shown; null until the first fetch
  Timer? _timer;

  void initialize() {
    if (_timer != null) return;
    fetch();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => fetch());
  }

  Future<void> fetch() async {
    try {
      final r = await http
          .get(Uri.parse('$kHttpBase/api/notifications?limit=100'), headers: await AuthService.authHeaders())
          .timeout(const Duration(seconds: 10));
      AuthService.checkAuth(r);
      if (r.statusCode != 200) return;
      final data = jsonDecode(r.body) as Map<String, dynamic>;
      _items = List<Map<String, dynamic>>.from(data['items'] ?? []);
      _unread = (data['unread'] as num?)?.toInt() ?? 0;

      final newest = _items.isEmpty ? 0 : _items.first['id'] as int;
      // Startup loads history silently; only alerts that arrive afterwards pop up.
      if (_lastSeenId != null && newest > _lastSeenId!) {
        _popUp(_items.where((n) => (n['id'] as int) > _lastSeenId!).toList());
      }
      _lastSeenId = newest;
      notifyListeners();
    } catch (e) {
      debugPrint('Error fetching notifications: $e');
    }
  }

  Future<void> markAllRead() async {
    if (_unread == 0) return;
    _unread = 0;
    notifyListeners();
    try {
      final r = await http
          .post(Uri.parse('$kHttpBase/api/notifications/read-all'), headers: await AuthService.authHeaders())
          .timeout(const Duration(seconds: 10));
      AuthService.checkAuth(r);
    } catch (e) {
      debugPrint('Error marking notifications read: $e');
    }
  }

  void _popUp(List<Map<String, dynamic>> fresh) {
    final m = appMessengerKey.currentState;
    if (m == null || fresh.isEmpty) return;
    final n = fresh.first;
    final more = fresh.length > 1 ? '  (+${fresh.length - 1} more)' : '';
    m
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        duration: const Duration(seconds: 5),
        content: Row(children: [
          Icon(levelIcon(n['level']), color: levelColor(n['level']), size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text('${n['title']}$more\n${n['message']}', maxLines: 3, overflow: TextOverflow.ellipsis)),
        ]),
      ));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

IconData levelIcon(dynamic level) => switch (level) {
      'WARNING' => Icons.warning_amber_rounded,
      'CRITICAL' || 'FATAL' => Icons.error_rounded,
      _ => Icons.notifications_rounded,
    };

Color levelColor(dynamic level) => switch (level) {
      'WARNING' => AppColors.orange,
      'CRITICAL' || 'FATAL' => AppColors.red,
      _ => AppColors.accent,
    };
