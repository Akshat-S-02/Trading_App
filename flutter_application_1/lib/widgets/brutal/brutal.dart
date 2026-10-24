import 'package:flutter/material.dart';
import '../../theme/brutal_theme.dart';

/// Hard-edged box: thick ink border plus an un-blurred offset shadow.
class BrutalBox extends StatelessWidget {
  final Widget child;
  final Color color;
  final EdgeInsetsGeometry? padding;
  final double shadow;
  final Color borderColor;

  const BrutalBox({
    super.key,
    required this.child,
    this.color = Brutal.white,
    this.padding,
    this.shadow = Brutal.shadow,
    this.borderColor = Brutal.ink,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: borderColor, width: Brutal.border),
        boxShadow: shadow > 0 ? Brutal.hardShadow(shadow) : null,
      ),
      child: child,
    );
  }
}

/// Button that physically "presses" into its shadow on tap.
class BrutalButton extends StatefulWidget {
  final String label;
  final VoidCallback? onPressed;
  final Color color;
  final Color foreground;
  final IconData? icon;
  final bool loading;
  final bool expand;
  final double height;
  final double fontSize;

  const BrutalButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.color = Brutal.accent,
    this.foreground = Brutal.ink,
    this.icon,
    this.loading = false,
    this.expand = false,
    this.height = 48,
    this.fontSize = 14,
  });

  @override
  State<BrutalButton> createState() => _BrutalButtonState();
}

class _BrutalButtonState extends State<BrutalButton> {
  bool _down = false;

  bool get _enabled => widget.onPressed != null && !widget.loading;

  @override
  Widget build(BuildContext context) {
    final offset = _down ? Brutal.shadow : 0.0;
    final content = widget.loading
        ? SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
                strokeWidth: 2.5, color: widget.foreground),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.icon != null) ...[
                Icon(widget.icon, size: widget.fontSize + 4, color: widget.foreground),
                const SizedBox(width: 8),
              ],
              Flexible(
                child: Text(
                  widget.label.toUpperCase(),
                  overflow: TextOverflow.ellipsis,
                  style: Brutal.display(
                    size: widget.fontSize,
                    weight: FontWeight.w800,
                    color: widget.foreground,
                    spacing: 1,
                  ),
                ),
              ),
            ],
          );

    return MouseRegion(
      cursor: _enabled ? SystemMouseCursors.click : SystemMouseCursors.forbidden,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: _enabled ? (_) => setState(() => _down = true) : null,
        onTapCancel: _enabled ? () => setState(() => _down = false) : null,
        onTapUp: _enabled
            ? (_) {
                setState(() => _down = false);
                widget.onPressed!();
              }
            : null,
        child: Semantics(
          button: true,
          enabled: _enabled,
          label: widget.label,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 60),
            transform: Matrix4.translationValues(offset, offset, 0),
            height: widget.height,
            width: widget.expand ? double.infinity : null,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: _enabled ? widget.color : Brutal.rule,
              border: Border.all(color: Brutal.ink, width: Brutal.border),
              boxShadow: _down || !_enabled ? null : Brutal.hardShadow(),
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}

/// Small square icon button with a border.
class BrutalIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final String tooltip;
  final Color color;
  final Color foreground;

  const BrutalIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    required this.tooltip,
    this.color = Brutal.white,
    this.foreground = Brutal.ink,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        child: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: color,
            border: Border.all(color: Brutal.ink, width: Brutal.border),
          ),
          child: Icon(icon, size: 20, color: foreground),
        ),
      ),
    );
  }
}

/// Black header strip with an index number, used to title panels.
class BrutalStrip extends StatelessWidget {
  final String index;
  final String title;
  final List<Widget> actions;
  final Color color;
  final Color foreground;

  const BrutalStrip({
    super.key,
    required this.index,
    required this.title,
    this.actions = const [],
    this.color = Brutal.ink,
    this.foreground = Brutal.accent,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: color,
      height: 34,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: Row(
        children: [
          Text('$index /', style: Brutal.mono(size: 11, color: foreground.withValues(alpha: 0.6), weight: FontWeight.w700)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title.toUpperCase(),
              overflow: TextOverflow.ellipsis,
              style: Brutal.display(size: 13, weight: FontWeight.w800, color: foreground, spacing: 1.5),
            ),
          ),
          ...actions,
        ],
      ),
    );
  }
}

/// Bordered panel = strip + body.
class BrutalPanel extends StatelessWidget {
  final String index;
  final String title;
  final Widget child;
  final List<Widget> actions;
  final double shadow;

  const BrutalPanel({
    super.key,
    required this.index,
    required this.title,
    required this.child,
    this.actions = const [],
    this.shadow = Brutal.shadow,
  });

  @override
  Widget build(BuildContext context) {
    return BrutalBox(
      shadow: shadow,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          BrutalStrip(index: index, title: title, actions: actions),
          Expanded(child: child),
        ],
      ),
    );
  }
}

/// Segmented usage meter (e.g. daily spend vs limit).
class BrutalMeter extends StatelessWidget {
  final String label;
  final double spent;
  final double limit;
  final int segments;

  const BrutalMeter({
    super.key,
    required this.label,
    required this.spent,
    required this.limit,
    this.segments = 20,
  });

  @override
  Widget build(BuildContext context) {
    final ratio = limit > 0 ? (spent / limit).clamp(0.0, 1.0) : 0.0;
    final filled = (ratio * segments).round();
    final hot = ratio >= 0.85;
    final fill = hot ? Brutal.down : Brutal.ink;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(child: Text(label.toUpperCase(), style: Brutal.label())),
            Text(
              '${Brutal.money(spent, decimals: 0)} / ${Brutal.money(limit, decimals: 0)}',
              style: Brutal.mono(size: 11, weight: FontWeight.w700),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Container(
          height: 16,
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            color: Brutal.white,
            border: Border.all(color: Brutal.ink, width: 2),
          ),
          child: Row(
            children: List.generate(segments, (i) {
              return Expanded(
                child: Container(
                  margin: EdgeInsets.only(right: i == segments - 1 ? 0 : 2),
                  color: i < filled ? fill : Brutal.rule.withValues(alpha: 0.5),
                ),
              );
            }),
          ),
        ),
      ],
    );
  }
}

/// Inline uppercase tag (e.g. NSE, BUY, SELL).
class BrutalTag extends StatelessWidget {
  final String text;
  final Color color;
  final Color foreground;

  const BrutalTag(
    this.text, {
    super.key,
    this.color = Brutal.white,
    this.foreground = Brutal.ink,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: Brutal.ink, width: 1.5),
      ),
      child: Text(text.toUpperCase(),
          style: Brutal.mono(size: 10, weight: FontWeight.w800, color: foreground)),
    );
  }
}

/// Big, loud empty state.
class BrutalEmpty extends StatelessWidget {
  final String title;
  final String? subtitle;
  final IconData icon;

  const BrutalEmpty({
    super.key,
    required this.title,
    this.subtitle,
    this.icon = Icons.crop_square,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: Brutal.accent,
                border: Border.all(color: Brutal.ink, width: Brutal.border),
                boxShadow: Brutal.hardShadow(),
              ),
              child: Icon(icon, color: Brutal.ink, size: 28),
            ),
            const SizedBox(height: 16),
            Text(title.toUpperCase(),
                textAlign: TextAlign.center,
                style: Brutal.display(size: 18, weight: FontWeight.w800, spacing: 1)),
            if (subtitle != null) ...[
              const SizedBox(height: 6),
              Text(subtitle!, textAlign: TextAlign.center, style: Brutal.mono(size: 12, color: Brutal.muted)),
            ],
          ],
        ),
      ),
    );
  }
}

/// Consistent snack bar for success / error messages.
void showBrutalSnack(BuildContext context, String message, {bool isError = false}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) return;
  messenger.showSnackBar(
    SnackBar(
      backgroundColor: isError ? Brutal.down : Brutal.ink,
      content: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            color: isError ? Brutal.white : Brutal.accent,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message,
                style: Brutal.mono(color: Brutal.white, weight: FontWeight.w700)),
          ),
        ],
      ),
    ),
  );
}
