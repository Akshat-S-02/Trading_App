import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/health_provider.dart';

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
    // We stop polling when they leave the Health tab
    // (though in a real app you might leave it running)
    Future.microtask(() => context.read<HealthProvider>().stopPolling());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final health = context.watch<HealthProvider>();
    
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'SYSTEM HEALTH',
          style: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.2,
          ),
        ),
        const SizedBox(height: 24),
        
        _buildSectionTitle('Backend'),
        _buildStatusRow(
          'API Reachable',
          health.isBackendReachable,
          valueText: health.isBackendReachable ? 'Online' : 'Offline',
        ),
        
        const SizedBox(height: 24),
        _buildSectionTitle('Broker'),
        _buildStatusRow(
          'Token Valid',
          health.isTokenValid,
        ),
        _buildInfoRow(
          'Next Renewal At',
          health.tokenData['auto_renewal']?['next_renewal_at'] != null 
              ? DateTime.parse(health.tokenData['auto_renewal']!['next_renewal_at']).toLocal().toString().split('.')[0]
              : 'Unknown',
        ),
        
        const SizedBox(height: 24),
        _buildSectionTitle('Market Feed'),
         _buildStatusRow(
          'WebSocket Connected',
          health.isFeedConnected,
          isWarning: health.feedData['stale'] == true,
        ),
        _buildInfoRow(
          'Last Tick',
          health.lastTickAgeSec < 90000 
            ? '${health.lastTickAgeSec.toStringAsFixed(1)}s ago' 
            : 'Unknown',
          textColor: health.lastTickAgeSec < 2.0 
              ? Colors.green 
              : (health.lastTickAgeSec < 10.0 ? Colors.orange : Colors.red),
        ),
        _buildInfoRow(
          'Reconnects Today',
          '${health.feedReconnectCount}',
          textColor: health.feedReconnectCount > 5 ? Colors.orange : Colors.white70,
        ),
        
        const SizedBox(height: 24),
        _buildSectionTitle('Workers'),
        _buildStatusRow(
          'Outbox Worker',
          health.isBackendReachable, // Placeholder until added to backend
          valueText: health.isBackendReachable ? 'Running' : 'Unknown',
        ),
        _buildInfoRow(
          'Orders Pending',
          '0', // Placeholder
        ),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          color: Colors.indigoAccent[100],
          fontSize: 14,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.1,
        ),
      ),
    );
  }

  Widget _buildStatusRow(String label, bool isOk, {String? valueText, bool isWarning = false}) {
    Color dotColor = isOk ? Colors.green : Colors.red;
    if (isWarning) dotColor = Colors.orange;
    
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(Icons.circle, color: dotColor, size: 12),
          const SizedBox(width: 12),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          if (valueText != null)
            Text(valueText, style: TextStyle(color: dotColor, fontSize: 14, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value, {Color textColor = Colors.white70}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          const Icon(Icons.circle, color: Colors.transparent, size: 12), // indent alignment
          const SizedBox(width: 12),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          Text(value, style: TextStyle(color: textColor, fontSize: 14)),
        ],
      ),
    );
  }
}
