import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class WebSocketService {
  final String url;
  final void Function(dynamic data) onMessage;
  final void Function(Object error)? onError;
  final void Function()? onDone;

  WebSocketChannel? _channel;
  bool _isDisposed = false;

  WebSocketService({
    required this.url,
    required this.onMessage,
    this.onError,
    this.onDone,
  });

  void connect() {
    debugPrint("🌐 WS connecting → $url");

    try {
      _channel = WebSocketChannel.connect(Uri.parse(url));

      _channel!.stream.listen(
            (data) {
          if (!_isDisposed) {
            // debugPrint("📩 WS RAW → $data");
            onMessage(data);
          }
        },
        onError: (e) {
          debugPrint("❌ WS ERROR: $e");
          if (!_isDisposed && onError != null) onError!(e);
        },
        onDone: () {
          debugPrint("🔌 WS CLOSED");
          if (!_isDisposed && onDone != null) onDone!();
        },
        cancelOnError: true,
      );
    } catch (e) {
      debugPrint("❌ WS CONNECT FAILED: $e");
      if (onError != null) onError!(e);
    }
  }

  void dispose() {
    _isDisposed = true;
    try {
      _channel?.sink.close();
    } catch (_) {}
  }
}
