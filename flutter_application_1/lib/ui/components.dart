import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter/services.dart';

import 'theme.dart';

// ── Motion ─────────────────────────────────────────────────────────────────

/// A spring described the way designers think about it: [response] is how
/// quickly it gets there (seconds, not a duration) and [damping] is the
/// overshoot (1.0 = none, lower = bouncier).
SpringDescription appSpring({double response = 0.35, double damping = 1.0}) {
  final stiffness = math.pow(2 * math.pi / response, 2).toDouble();
  final c = 4 * math.pi * damping / response;
  return SpringDescription(mass: 1, stiffness: stiffness, damping: c);
}

/// True when the user asked the OS to reduce motion.
bool reduceMotion(BuildContext context) => MediaQuery.disableAnimationsOf(context);

/// Expand/collapse timing: a curve close to a critically damped spring, or
/// nothing at all with reduce motion on.
Duration motionDuration(BuildContext context, [int ms = 320]) =>
    reduceMotion(context) ? Duration.zero : Duration(milliseconds: ms);

const motionCurve = Curves.easeOutCubic;

/// Space to leave at the bottom of a scrolling list so its last item clears
/// the translucent tab bar the content scrolls under.
double bottomInset(BuildContext context, [double extra = 16]) =>
    MediaQuery.paddingOf(context).bottom + extra;

// ── Press feedback ────────────────────────────────────────────────────────

/// Wraps a tappable surface with instant press feedback: it sinks the moment
/// the finger lands (not when it lifts) and springs back from wherever it is,
/// so quick repeated taps never jump. With reduce motion on it dims instead
/// of scaling.
class Pressable extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double pressedScale;

  /// Fire a light selection tick when the tap commits.
  final bool haptic;

  const Pressable({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.pressedScale = 0.97,
    this.haptic = false,
  });

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> with SingleTickerProviderStateMixin {
  // 0 = at rest, 1 = fully pressed. Unbounded so the spring can carry its
  // velocity through a reversal.
  late final AnimationController _c = AnimationController.unbounded(vsync: this);

  bool get _enabled => widget.onTap != null || widget.onLongPress != null;

  void _to(double target, double response) {
    _c.animateWith(SpringSimulation(appSpring(response: response), _c.value, target, _c.velocity));
  }

  void _down(PointerDownEvent _) {
    if (_enabled) _to(1, 0.15);
  }

  void _release() => _to(0, 0.35);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduced = reduceMotion(context);
    return Listener(
      onPointerDown: _down,
      onPointerUp: (_) => _release(),
      onPointerCancel: (_) => _release(),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        // A scroll winning the gesture cancels the tap: release right away.
        onTapCancel: _release,
        onTap: widget.onTap == null
            ? null
            : () {
                if (widget.haptic) HapticFeedback.selectionClick();
                widget.onTap!();
              },
        onLongPress: widget.onLongPress,
        child: AnimatedBuilder(
          animation: _c,
          child: widget.child,
          builder: (_, child) {
            final p = _c.value;
            if (reduced) return Opacity(opacity: (1 - 0.35 * p).clamp(0.0, 1.0), child: child);
            return Transform.scale(
              scale: 1 - (1 - widget.pressedScale) * p,
              child: Opacity(opacity: (1 - 0.12 * p).clamp(0.0, 1.0), child: child),
            );
          },
        ),
      ),
    );
  }
}

// ── Materials ─────────────────────────────────────────────────────────────

/// Translucent chrome that content scrolls underneath: blurred, slightly
/// saturated, with a hairline where it meets the content. Goes solid when
/// the user has turned on increased contrast.
class GlassBar extends StatelessWidget {
  final Widget child;
  final bool topEdge;
  const GlassBar({super.key, required this.child, this.topEdge = true});

  @override
  Widget build(BuildContext context) {
    final solid = MediaQuery.highContrastOf(context);
    final edge = topEdge
        ? const Border(top: BorderSide(color: AppColors.separator, width: 0.5))
        : const Border(bottom: BorderSide(color: AppColors.separator, width: 0.5));
    final body = DecoratedBox(
      decoration: BoxDecoration(
        color: solid ? AppColors.card : AppColors.card.withValues(alpha: 0.72),
        border: edge,
      ),
      child: child,
    );
    if (solid) return body;
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: body,
      ),
    );
  }
}

// ── Building blocks ───────────────────────────────────────────────────────

/// Section heading for a group of cards: sentence case, bold, with an
/// optional trailing widget (count, action).
class SectionHeader extends StatelessWidget {
  final String title;
  final Widget? trailing;
  final EdgeInsetsGeometry padding;
  const SectionHeader(this.title,
      {super.key, this.trailing, this.padding = const EdgeInsets.fromLTRB(4, 8, 4, 10)});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding,
      child: Row(
        children: [
          Expanded(child: Text(title, style: AppText.title3)),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// Small capsule label (LONG, MANUAL, NEW…).
class Pill extends StatelessWidget {
  final String text;
  final Color color;
  final IconData? icon;
  const Pill(this.text, {super.key, required this.color, this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2.5),
      decoration: ShapeDecoration(color: color.withValues(alpha: 0.16), shape: const StadiumBorder()),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 11, color: color),
            const SizedBox(width: 3),
          ],
          Flexible(
            child: Text(text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    color: color, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 0.15, height: 1.2)),
          ),
        ],
      ),
    );
  }
}

/// Plain surface for grouped content.
class Surface extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  final BorderSide side;
  const Surface({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.color = AppColors.card,
    this.side = BorderSide.none,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: ShapeDecoration(color: color, shape: rounded(16, side: side)),
      child: child,
    );
  }
}

/// Inset grouped list: rows on one surface separated by hairlines that start
/// at the text, not the edge.
class InsetGroup extends StatelessWidget {
  final List<Widget> children;
  final double dividerIndent;
  const InsetGroup({super.key, required this.children, this.dividerIndent = 16});

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Divider(indent: dividerIndent));
      rows.add(children[i]);
    }
    return Surface(padding: EdgeInsets.zero, child: Column(children: rows));
  }
}

/// Empty or error state: what happened, and what to do next.
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;
  const EmptyState({super.key, required this.icon, required this.title, this.message, this.action});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 44, color: AppColors.tertiary),
          const SizedBox(height: 12),
          Text(title, textAlign: TextAlign.center, style: AppText.headline),
          if (message != null) ...[
            const SizedBox(height: 4),
            Text(message!, textAlign: TextAlign.center, style: AppText.footnote),
          ],
          if (action != null) ...[const SizedBox(height: 16), action!],
        ],
      ),
    );
  }
}

/// Small coloured status dot with a soft glow.
class StatusDot extends StatelessWidget {
  final Color color;
  final double size;
  const StatusDot(this.color, {super.key, this.size = 8});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
        boxShadow: [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: size * 0.75)],
      ),
    );
  }
}

// ── Feedback ──────────────────────────────────────────────────────────────

/// Completion / error toast. The haptic fires on the same frame the toast
/// appears, and only for outcomes that matter.
void notify(ScaffoldMessengerState messenger, String message, {bool ok = true, Duration? duration}) {
  if (ok) {
    HapticFeedback.lightImpact();
  } else {
    HapticFeedback.heavyImpact();
  }
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      duration: duration ?? const Duration(seconds: 3),
      content: Row(
        children: [
          Icon(ok ? Icons.check_circle : Icons.error,
              color: ok ? AppColors.green : AppColors.red, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    ));
}

/// Bottom sheet that rises from the bottom edge and leaves the same way:
/// drag it down and it follows the finger, a flick dismisses it at the
/// flick's speed. Reduce motion swaps the slide for an instant change.
Future<T?> showAppSheet<T>(BuildContext context, WidgetBuilder builder) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    sheetAnimationStyle: reduceMotion(context)
        ? AnimationStyle.noAnimation
        : AnimationStyle(
            duration: const Duration(milliseconds: 380),
            reverseDuration: const Duration(milliseconds: 260),
          ),
    builder: builder,
  );
}

/// Confirmation for irreversible actions only (placing or closing a trade,
/// the kill switch). The destructive choice is red and on the right.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  required String confirmLabel,
  String cancelLabel = 'Cancel',
  Color confirmColor = AppColors.red,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(message, style: const TextStyle(height: 1.45)),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(cancelLabel)),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: confirmColor, foregroundColor: Colors.white),
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return ok == true;
}
