import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../app_config.dart';
import '../services/auth_service.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  // ── Token status ─────────────────────────────────────────────────────────────
  bool _statusLoading = true;
  Map<String, dynamic>? _tokenStatus;
  String? _statusError;
  Timer? _pollTimer;

  // ── Rotation form ─────────────────────────────────────────────────────────────
  final _newTokenCtl = TextEditingController();
  final _clientIdCtl = TextEditingController();
  bool _rotating = false;

  @override
  void initState() {
    super.initState();
    _loadTokenStatus();
    // Auto-poll every 60 s so the admin screen always shows fresh data
    _pollTimer = Timer.periodic(const Duration(seconds: 60), (_) {
      if (mounted) _loadTokenStatus();
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _newTokenCtl.dispose();
    _clientIdCtl.dispose();
    super.dispose();
  }

  // ── Network ───────────────────────────────────────────────────────────────────

  Future<void> _loadTokenStatus() async {
    setState(() {
      _statusLoading = true;
      _statusError = null;
    });
    try {
      final headers = await AuthService.authHeaders();
      final res = await http
          .get(Uri.parse('$kHttpBase/api/admin/token-status'), headers: headers)
          .timeout(const Duration(seconds: 8));
      if (res.statusCode == 200) {
        setState(() => _tokenStatus = jsonDecode(res.body));
      } else if (res.statusCode == 401) {
        setState(() => _statusError = 'Not authenticated. Please log in again.');
      } else {
        setState(() => _statusError = 'Server error ${res.statusCode}');
      }
    } catch (e) {
      setState(() => _statusError = 'Could not reach backend: $e');
    } finally {
      if (mounted) setState(() => _statusLoading = false);
    }
  }

  Future<void> _rotateToken() async {
    final newToken = _newTokenCtl.text.trim();
    if (newToken.isEmpty) {
      _showSnack('Paste the new Dhan access token first.', isError: true);
      return;
    }
    setState(() => _rotating = true);
    try {
      final headers = await AuthService.authHeaders();
      final body = <String, dynamic>{'access_token': newToken};
      final clientId = _clientIdCtl.text.trim();
      if (clientId.isNotEmpty) body['client_id'] = clientId;

      final res = await http
          .post(
            Uri.parse('$kHttpBase/api/admin/update-dhan-token'),
            headers: headers,
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 10));

      if (res.statusCode == 200) {
        _newTokenCtl.clear();
        _clientIdCtl.clear();
        _showSnack('✅ Dhan token updated successfully!');
        await _loadTokenStatus();
      } else if (res.statusCode == 401) {
        _showSnack('Not authorised — please log in again.', isError: true);
      } else {
        _showSnack('Error ${res.statusCode}: ${res.body}', isError: true);
      }
    } catch (e) {
      _showSnack('Request failed: $e', isError: true);
    } finally {
      if (mounted) setState(() => _rotating = false);
    }
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
      behavior: SnackBarBehavior.floating,
    ));
  }

  // ── Build ──────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: _loadTokenStatus,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Token expiry card ────────────────────────────────────────────────
          _sectionHeader(context, 'Dhan Token Status'),
          const SizedBox(height: 8),
          _buildTokenStatusCard(theme),

          const SizedBox(height: 20),

          // ── Auto-renewal card ────────────────────────────────────────────────
          _sectionHeader(context, 'Auto-Renewal Schedule'),
          const SizedBox(height: 8),
          _buildAutoRenewalCard(theme),

          const SizedBox(height: 24),

          // ── Manual rotation form ─────────────────────────────────────────────
          _sectionHeader(context, 'Rotate Dhan Token Manually'),
          const SizedBox(height: 8),
          Card(
            elevation: 2,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Paste a new Dhan token here to hot-swap it immediately.\n'
                    'The server updates in-memory AND writes to .env (no restart needed).',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: Colors.grey.shade600),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    controller: _newTokenCtl,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      labelText: 'New Access Token *',
                      hintText: 'eyJ0eXAiOiJKV1QiLCJhbGci...',
                      border: OutlineInputBorder(),
                      alignLabelWithHint: true,
                    ),
                    style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _clientIdCtl,
                    decoration: const InputDecoration(
                      labelText: 'Client ID (optional — only if changed)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: _rotating ? null : _rotateToken,
                    icon: _rotating
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.rotate_right),
                    label: Text(_rotating ? 'Updating…' : 'Rotate Token'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ── Widget helpers ────────────────────────────────────────────────────────────

  Widget _sectionHeader(BuildContext context, String title) => Text(
        title,
        style: Theme.of(context)
            .textTheme
            .titleMedium
            ?.copyWith(fontWeight: FontWeight.bold),
      );

  Widget _buildTokenStatusCard(ThemeData theme) {
    if (_statusLoading) {
      return const Card(
        elevation: 2,
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }

    if (_statusError != null) {
      return Card(
        elevation: 2,
        color: Colors.red.shade50,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            const Icon(Icons.error_outline, color: Colors.red),
            const SizedBox(width: 10),
            Expanded(
                child: Text(_statusError!,
                    style: const TextStyle(color: Colors.red))),
          ]),
        ),
      );
    }

    final s = _tokenStatus!;
    final isValid       = s['valid'] as bool? ?? false;
    final hoursLeft     = (s['expires_in_hours'] as num?)?.toDouble() ?? 0.0;
    final minutesLeft   = (s['expires_in_minutes'] as num?)?.toDouble() ?? 0.0;
    final expiresAt     = s['expires_at'] as String? ?? '';
    final clientId      = s['client_id'] as String? ?? '—';

    Color statusColor;
    IconData statusIcon;
    String statusLabel;
    if (!isValid) {
      statusColor  = Colors.red;
      statusIcon   = Icons.cancel;
      statusLabel  = '⚠️ EXPIRED — rotate immediately!';
    } else if (hoursLeft < 2) {
      statusColor  = Colors.orange;
      statusIcon   = Icons.warning_amber_rounded;
      statusLabel  = 'Expiring in ${minutesLeft.toStringAsFixed(0)} min';
    } else {
      statusColor  = Colors.green;
      statusIcon   = Icons.check_circle_outline;
      statusLabel  = 'Expires in ${hoursLeft.toStringAsFixed(1)} h';
    }

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(children: [
              Icon(statusIcon, color: statusColor, size: 28),
              const SizedBox(width: 10),
              Expanded(
                child: Text(statusLabel,
                    style: theme.textTheme.titleSmall?.copyWith(
                        color: statusColor, fontWeight: FontWeight.bold)),
              ),
            ]),
            const Divider(height: 20),
            _infoRow('Client ID', clientId),
            _infoRow('Expires at',
                expiresAt.replaceFirst('T', '  ').replaceFirst('+00:00', ' UTC')),
          ],
        ),
      ),
    );
  }

  Widget _buildAutoRenewalCard(ThemeData theme) {
    if (_statusLoading || _tokenStatus == null) {
      return const Card(
          elevation: 2,
          child: Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator())));
    }

    final ar = _tokenStatus!['auto_renewal'] as Map<String, dynamic>?;
    if (ar == null) return const SizedBox.shrink();

    final lastOk      = ar['last_renewal_ok'] as bool? ?? false;
    final lastAt      = ar['last_renewal_at'] as String?;
    final lastErr     = ar['last_renewal_error'] as String?;
    final nextAt      = ar['next_renewal_at'] as String? ?? '';
    final nextInHours = (ar['next_renewal_in_hours'] as num?)?.toDouble() ?? 0.0;
    final reason      = ar['renewal_reason'] as String? ?? '';

    String _fmtDate(String iso) =>
        iso.replaceFirst('T', '  ').replaceFirst('+00:00', ' UTC').replaceFirst('.000000+00:00', ' UTC');

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
          Row(children: [
            const Icon(Icons.schedule, color: Colors.blue, size: 24),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Smart Auto-Renewal',
                style: theme.textTheme.bodyMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          ]),
          const Divider(height: 20),
          _infoRow('Strategy', reason.isEmpty ? '—' : reason),
          const SizedBox(height: 4),
          _infoRow(
            'Last renewal',
            lastAt != null
                ? '${lastOk ? "✅" : "❌"} ${_fmtDate(lastAt)}'
                    '${lastErr != null && !lastOk ? "\n$lastErr" : ""}'
                : 'Not yet (server just started)',
          ),
          const SizedBox(height: 4),
          _infoRow('Next renewal',
              '${_fmtDate(nextAt)}\n(in ${nextInHours.toStringAsFixed(1)} h)'),
          if (!lastOk && lastAt != null && lastErr != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(children: [
                const Icon(Icons.warning_amber, color: Colors.red, size: 18),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Last auto-renewal failed. Rotate manually if needed.',
                    style: TextStyle(color: Colors.red.shade700, fontSize: 12),
                  ),
                ),
              ]),
            ),
          ],
        ],
        ),
      ),
    );
  }


  Widget _infoRow(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 90,
              child: Text(label,
                  style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                      color: Colors.grey)),
            ),
            Expanded(
              child: Text(value,
                  style:
                      const TextStyle(fontSize: 12, fontFamily: 'monospace')),
            ),
          ],
        ),
      );
}
