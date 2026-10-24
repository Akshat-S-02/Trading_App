import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Brutalist design tokens: raw paper, black ink, hard edges, one loud accent.
class Brutal {
  Brutal._();

  // ── Palette ──────────────────────────────────────────────────────────────────
  static const Color paper  = Color(0xFFF4F1EA);
  static const Color white  = Color(0xFFFFFFFF);
  static const Color ink    = Color(0xFF0A0A0A);
  static const Color muted  = Color(0xFF5E5E5E);
  static const Color rule   = Color(0xFFD8D3C7);
  static const Color accent = Color(0xFFFFD400); // signal yellow
  static const Color up     = Color(0xFF00A651);
  static const Color down   = Color(0xFFE5261E);
  static const Color info   = Color(0xFF2347FF);

  // ── Geometry ─────────────────────────────────────────────────────────────────
  static const double border = 2.5;
  static const double shadow = 4;

  static const BorderSide side = BorderSide(color: ink, width: border);

  static List<BoxShadow> hardShadow([double offset = shadow, Color color = ink]) =>
      [BoxShadow(color: color, offset: Offset(offset, offset))];

  // ── Type ─────────────────────────────────────────────────────────────────────
  /// Display / labels — heavy grotesk.
  static TextStyle display({
    double size = 14,
    FontWeight weight = FontWeight.w700,
    Color color = ink,
    double spacing = 0,
  }) =>
      GoogleFonts.spaceGrotesk(
        fontSize: size,
        fontWeight: weight,
        color: color,
        letterSpacing: spacing,
        height: 1.1,
      );

  /// Numbers, symbols, timestamps — monospace so columns line up.
  static TextStyle mono({
    double size = 13,
    FontWeight weight = FontWeight.w500,
    Color color = ink,
  }) =>
      GoogleFonts.jetBrainsMono(
        fontSize: size,
        fontWeight: weight,
        color: color,
        height: 1.2,
        fontFeatures: const [FontFeature.tabularFigures()],
      );

  /// Small uppercase caption, e.g. "SANDBOX BALANCE".
  static TextStyle label({Color color = muted, double size = 11}) =>
      mono(size: size, weight: FontWeight.w700, color: color)
          .copyWith(letterSpacing: 1.2);

  static Color signColor(num v) => v > 0 ? up : (v < 0 ? down : ink);

  static String money(double v, {int decimals = 2}) =>
      '₹${v.toStringAsFixed(decimals)}';

  static ThemeData theme() {
    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: const ColorScheme.light(
        primary: ink,
        onPrimary: white,
        secondary: accent,
        onSecondary: ink,
        surface: paper,
        onSurface: ink,
        error: down,
        onError: white,
      ),
    );

    const sharp = RoundedRectangleBorder(borderRadius: BorderRadius.zero);
    const sharpBorder = OutlineInputBorder(
      borderRadius: BorderRadius.zero,
      borderSide: side,
    );

    return base.copyWith(
      scaffoldBackgroundColor: paper,
      textTheme: GoogleFonts.spaceGroteskTextTheme(base.textTheme).apply(
        bodyColor: ink,
        displayColor: ink,
      ),
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
      appBarTheme: AppBarTheme(
        backgroundColor: paper,
        foregroundColor: ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: display(size: 18, weight: FontWeight.w800),
        shape: const Border(bottom: side),
      ),
      cardTheme: const CardThemeData(
        color: white,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.zero,
          side: side,
        ),
      ),
      dividerTheme: const DividerThemeData(color: ink, thickness: 1.5, space: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: white,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        labelStyle: label(),
        floatingLabelStyle: label(color: ink),
        hintStyle: mono(color: muted),
        border: sharpBorder,
        enabledBorder: sharpBorder,
        disabledBorder: sharpBorder.copyWith(
          borderSide: const BorderSide(color: rule, width: border),
        ),
        focusedBorder: sharpBorder.copyWith(
          borderSide: const BorderSide(color: info, width: 3),
        ),
        errorBorder: sharpBorder.copyWith(
          borderSide: const BorderSide(color: down, width: border),
        ),
      ),
      textSelectionTheme: const TextSelectionThemeData(
        cursorColor: ink,
        selectionColor: accent,
        selectionHandleColor: ink,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: ink,
          foregroundColor: accent,
          shape: sharp,
          textStyle: display(size: 14, weight: FontWeight.w800, spacing: 1),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: ink,
          elevation: 0,
          shape: const RoundedRectangleBorder(
            borderRadius: BorderRadius.zero,
            side: side,
          ),
          textStyle: display(size: 14, weight: FontWeight.w800, spacing: 1),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: ink,
          shape: sharp,
          textStyle: display(size: 14, weight: FontWeight.w800, spacing: 1),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: paper,
        elevation: 0,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.zero,
          side: BorderSide(color: ink, width: 3),
        ),
        titleTextStyle: display(size: 18, weight: FontWeight.w800),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: ink,
        contentTextStyle: mono(color: white, weight: FontWeight.w700),
        shape: sharp,
        behavior: SnackBarBehavior.floating,
        elevation: 0,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: ink,
        linearTrackColor: white,
        circularTrackColor: Colors.transparent,
      ),
      tooltipTheme: TooltipThemeData(
        decoration: const BoxDecoration(color: ink),
        textStyle: mono(size: 11, color: white),
      ),
    );
  }
}
