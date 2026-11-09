import 'dart:math' as math;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import '../ui/theme.dart';
import 'package:intl/intl.dart' show DateFormat;

const _istOffset = Duration(hours: 5, minutes: 30);

class Candle {
  final int t; // bucket start, epoch ms (UTC)
  double o, h, l, c;
  int v;
  Candle(this.t, this.o, this.h, this.l, this.c, this.v);

  factory Candle.fromJson(Map<String, dynamic> j) => Candle(
        (j['t'] as num).toInt(),
        (j['o'] as num).toDouble(),
        (j['h'] as num).toDouble(),
        (j['l'] as num).toDouble(),
        (j['c'] as num).toDouble(),
        (j['v'] as num? ?? 0).toInt(),
      );

  /// UTC DateTime whose fields read as IST wall-clock time (for formatting).
  DateTime get ist => DateTime.fromMillisecondsSinceEpoch(t, isUtc: true).add(_istOffset);

  bool get up => c >= o;
}

/// A horizontal price level drawn across the chart (entry, SL, target…).
class ChartLine {
  final double price;
  final Color color;
  final String label;
  const ChartLine(this.price, this.color, this.label);
}

/// Candlestick + volume chart. Drag to pan, pinch / scroll-wheel to zoom,
/// long-press (or hover with a mouse) for a crosshair, double-tap to reset.
class CandleChart extends StatefulWidget {
  final List<Candle> candles;
  final bool daily;
  final List<ChartLine> lines;
  final ValueChanged<Candle?>? onHover;

  const CandleChart({
    super.key,
    required this.candles,
    this.daily = false,
    this.lines = const [],
    this.onHover,
  });

  @override
  State<CandleChart> createState() => _CandleChartState();
}

class _CandleChartState extends State<CandleChart> {
  static const _defaultVisible = 70.0;
  double _visible = _defaultVisible;
  double _offset = 0; // bars hidden to the right of the view
  double _baseVisible = _defaultVisible;
  Offset? _cross;

  int get _n => widget.candles.length;

  double _maxVisible() => math.max(20, math.min(_n.toDouble(), 400));

  void _setCross(Offset? p, Size size) {
    setState(() => _cross = p);
    if (widget.onHover == null) return;
    if (p == null) {
      widget.onHover!(null);
      return;
    }
    final g = _Geom(size, _n, _visible, _offset);
    final i = g.indexAt(p.dx);
    widget.onHover!(i == null ? null : widget.candles[i]);
  }

  void _zoom(double factor) {
    setState(() {
      _visible = (_visible * factor).clamp(15.0, _maxVisible());
      _offset = _offset.clamp(0.0, math.max(0, _n - 10).toDouble());
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final size = Size(box.maxWidth, box.maxHeight);
      return Listener(
        onPointerSignal: (e) {
          if (e is PointerScrollEvent) _zoom(e.scrollDelta.dy > 0 ? 1.1 : 0.9);
        },
        child: MouseRegion(
          onHover: (e) => _setCross(e.localPosition, size),
          onExit: (_) => _setCross(null, size),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onDoubleTap: () => setState(() {
              _visible = _defaultVisible;
              _offset = 0;
            }),
            onScaleStart: (_) => _baseVisible = _visible,
            onScaleUpdate: (d) {
              setState(() {
                if (d.pointerCount > 1 && d.horizontalScale != 1.0) {
                  _visible = (_baseVisible / d.horizontalScale).clamp(15.0, _maxVisible());
                }
                final barW = (size.width - _Geom.axisW) / _visible;
                _offset = (_offset + d.focalPointDelta.dx / barW)
                    .clamp(0.0, math.max(0, _n - 10).toDouble());
              });
            },
            onLongPressStart: (d) => _setCross(d.localPosition, size),
            onLongPressMoveUpdate: (d) => _setCross(d.localPosition, size),
            onLongPressEnd: (_) => _setCross(null, size),
            child: CustomPaint(
              size: size,
              painter: _ChartPainter(
                candles: widget.candles,
                daily: widget.daily,
                lines: widget.lines,
                visible: _visible,
                offset: _offset,
                cross: _cross,
              ),
            ),
          ),
        ),
      );
    });
  }
}

/// Shared x-axis geometry for painting and hit-testing.
class _Geom {
  static const axisW = 68.0;
  static const timeH = 22.0;

  final Size size;
  final int n;
  final double visible;
  final double offset;

  _Geom(this.size, this.n, this.visible, this.offset);

  double get plotW => size.width - axisW;
  double get plotH => size.height - timeH;
  double get barW => plotW / visible;
  int get end => (n - offset.floor()).clamp(0, n); // exclusive
  int get start => math.max(0, end - visible.ceil() - 1);

  /// Centre x of candle [i]; the newest visible candle sits at the right edge.
  double xOf(int i) => plotW - (end - i - 0.5) * barW;

  int? indexAt(double x) {
    if (x < 0 || x > plotW) return null;
    final i = end - 1 - ((plotW - x) / barW).floor();
    return (i >= start && i < end) ? i : null;
  }
}

class _ChartPainter extends CustomPainter {
  final List<Candle> candles;
  final bool daily;
  final List<ChartLine> lines;
  final double visible;
  final double offset;
  final Offset? cross;

  _ChartPainter({
    required this.candles,
    required this.daily,
    required this.lines,
    required this.visible,
    required this.offset,
    required this.cross,
  });

  static const _up = AppColors.green;
  static const _down = AppColors.red;
  static const _grid = Color(0x14FFFFFF);
  static const _axisText = Color(0x99FFFFFF);

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= _Geom.axisW) return;
    final g = _Geom(size, candles.length, visible, offset);
    if (g.end <= g.start) return;

    // ── Price range over visible candles (+ position levels) ─────────────
    double hi = -double.infinity, lo = double.infinity;
    int maxVol = 1;
    for (var i = g.start; i < g.end; i++) {
      final c = candles[i];
      hi = math.max(hi, c.h);
      lo = math.min(lo, c.l);
      maxVol = math.max(maxVol, c.v);
    }
    for (final l in lines) {
      hi = math.max(hi, l.price);
      lo = math.min(lo, l.price);
    }
    if (hi - lo < 1e-9) {
      hi += 1;
      lo -= 1;
    }
    final pad = (hi - lo) * 0.06;
    hi += pad;
    lo -= pad;

    const top = 8.0;
    final priceH = g.plotH * 0.80 - top;
    final volTop = g.plotH * 0.82;
    final volH = g.plotH - volTop;
    double y(double p) => top + (hi - p) / (hi - lo) * priceH;
    double priceAt(double py) => hi - (py - top) / priceH * (hi - lo);

    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width, size.height));

    // ── Grid + price axis ────────────────────────────────────────────────
    final gridPaint = Paint()..color = _grid..strokeWidth = 1;
    final step = _niceStep((hi - lo) / 6);
    for (var p = (lo / step).ceil() * step; p <= hi; p += step) {
      final py = y(p);
      canvas.drawLine(Offset(0, py), Offset(g.plotW, py), gridPaint);
      _text(canvas, p.toStringAsFixed(2), Offset(g.plotW + 6, py - 7), _axisText, 11);
    }
    canvas.drawLine(Offset(g.plotW, 0), Offset(g.plotW, g.plotH), Paint()..color = const Color(0x22FFFFFF));

    // ── Time axis ────────────────────────────────────────────────────────
    final every = math.max(1, (visible / 5).round());
    for (var i = g.start; i < g.end; i++) {
      if (i % every != 0) continue;
      final x = g.xOf(i);
      if (x < 20 || x > g.plotW - 20) continue;
      canvas.drawLine(Offset(x, 0), Offset(x, g.plotH), gridPaint);
      _text(canvas, _timeLabel(i), Offset(x, g.plotH + 5), _axisText, 10, center: true);
    }

    // ── Candles + volume ─────────────────────────────────────────────────
    final bodyW = math.max(1.0, g.barW * 0.7);
    for (var i = g.start; i < g.end; i++) {
      final c = candles[i];
      final x = g.xOf(i);
      final color = c.up ? _up : _down;
      final paint = Paint()..color = color;

      // volume
      final vh = c.v / maxVol * volH;
      canvas.drawRect(Rect.fromLTWH(x - bodyW / 2, g.plotH - vh, bodyW, vh),
          Paint()..color = color.withValues(alpha: 0.35));

      // wick
      canvas.drawLine(Offset(x, y(c.h)), Offset(x, y(c.l)), paint..strokeWidth = 1);
      // body
      final top_ = y(math.max(c.o, c.c));
      final bot = y(math.min(c.o, c.c));
      canvas.drawRect(Rect.fromLTRB(x - bodyW / 2, top_, x + bodyW / 2, math.max(bot, top_ + 1)), paint);
    }

    // ── Position levels ──────────────────────────────────────────────────
    for (final l in lines) {
      final py = y(l.price);
      _dashed(canvas, Offset(0, py), g.plotW, l.color);
      _text(canvas, l.label, Offset(6, py - 16), l.color, 10, bold: true);
      _axisTag(canvas, g, py, l.price.toStringAsFixed(2), l.color);
    }

    // ── Last price ───────────────────────────────────────────────────────
    final last = candles.last;
    final lastColor = last.up ? _up : _down;
    final ly = y(last.c);
    _dashed(canvas, Offset(0, ly), g.plotW, lastColor.withValues(alpha: 0.7));
    _axisTag(canvas, g, ly, last.c.toStringAsFixed(2), lastColor);

    // ── Crosshair ────────────────────────────────────────────────────────
    final cp = cross;
    if (cp != null) {
      final i = g.indexAt(cp.dx);
      final crossPaint = Paint()..color = Colors.white38..strokeWidth = 1;
      if (i != null) {
        final x = g.xOf(i);
        canvas.drawLine(Offset(x, 0), Offset(x, g.plotH), crossPaint);
        final label = _fullTime(i);
        final tp = _layout(label, Colors.black, 10, bold: true);
        final rx = (x - tp.width / 2 - 4).clamp(0.0, g.plotW - tp.width - 8);
        canvas.drawRRect(
            RRect.fromRectAndRadius(Rect.fromLTWH(rx, g.plotH + 2, tp.width + 8, 18), const Radius.circular(3)),
            Paint()..color = Colors.white70);
        tp.paint(canvas, Offset(rx + 4, g.plotH + 5));
      }
      if (cp.dy >= top && cp.dy <= top + priceH) {
        canvas.drawLine(Offset(0, cp.dy), Offset(g.plotW, cp.dy), crossPaint);
        _axisTag(canvas, g, cp.dy, priceAt(cp.dy).toStringAsFixed(2), Colors.white70, dark: true);
      }
    }

    canvas.restore();
  }

  String _timeLabel(int i) {
    final d = candles[i].ist;
    if (daily) return DateFormat('dd MMM yy').format(d);
    final prev = i > 0 ? candles[i - 1].ist : null;
    final newDay = prev == null || prev.day != d.day || prev.month != d.month;
    return newDay ? DateFormat('dd MMM').format(d) : DateFormat('HH:mm').format(d);
  }

  String _fullTime(int i) {
    final d = candles[i].ist;
    return daily ? DateFormat('EEE dd MMM yyyy').format(d) : DateFormat('EEE dd MMM HH:mm').format(d);
  }

  static double _niceStep(double raw) {
    if (raw <= 0) return 1;
    final mag = math.pow(10, (math.log(raw) / math.ln10).floor()).toDouble();
    final norm = raw / mag;
    final nice = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
    return nice * mag;
  }

  static TextPainter _layout(String s, Color color, double size, {bool bold = false}) {
    return TextPainter(
      text: TextSpan(
        text: s,
        style: TextStyle(
            color: color,
            fontSize: size,
            fontWeight: bold ? FontWeight.bold : FontWeight.normal,
            fontFeatures: const [FontFeature.tabularFigures()]),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
  }

  static void _text(Canvas canvas, String s, Offset at, Color color, double size,
      {bool center = false, bool bold = false}) {
    final tp = _layout(s, color, size, bold: bold);
    tp.paint(canvas, center ? at.translate(-tp.width / 2, 0) : at);
  }

  static void _axisTag(Canvas canvas, _Geom g, double y, String s, Color color, {bool dark = false}) {
    final tp = _layout(s, dark ? Colors.black : Colors.white, 11, bold: true);
    final r = Rect.fromLTWH(g.plotW + 2, y - 9, _Geom.axisW - 4, 18);
    canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), Paint()..color = color);
    tp.paint(canvas, Offset(r.left + 4, y - tp.height / 2));
  }

  static void _dashed(Canvas canvas, Offset from, double width, Color color) {
    final p = Paint()..color = color..strokeWidth = 1;
    for (var x = from.dx; x < width; x += 8) {
      canvas.drawLine(Offset(x, from.dy), Offset(math.min(x + 4, width), from.dy), p);
    }
  }

  @override
  bool shouldRepaint(covariant _ChartPainter old) => true;
}
