import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';

/// Design tokens, modelled on Apple's dark system palette.
///
/// One accent (system blue) for anything interactive, green/red only for
/// money moving up or down, and a grey ramp for everything else so the
/// numbers are the loudest thing on screen.
abstract final class AppColors {
  // Surfaces: black base, then lighter = higher.
  static const bg = Color(0xFF000000);
  static const card = Color(0xFF1C1C1E);
  static const elevated = Color(0xFF2C2C2E);
  static const fill = Color(0x3D767680); // controls, search fields, chips
  static const separator = Color(0xFF38383A);

  // Text ramp.
  static const label = Color(0xFFFFFFFF);
  static const secondary = Color(0x99EBEBF5);
  static const tertiary = Color(0x4DEBEBF5);
  static const quaternary = Color(0x2EEBEBF5);

  // Semantic.
  static const accent = Color(0xFF0A84FF);
  static const green = Color(0xFF30D158);
  static const red = Color(0xFFFF453A);
  static const orange = Color(0xFFFF9F0A);
  static const yellow = Color(0xFFFFD60A);
  static const indigo = Color(0xFF5E5CE6);
  static const purple = Color(0xFFBF5AF2);
  static const teal = Color(0xFF64D2FF);
}

/// Corner shape used everywhere: a continuous (squircle) corner like iOS,
/// rather than a circular arc.
ShapeBorder rounded(double r, {BorderSide side = BorderSide.none}) =>
    RoundedSuperellipseBorder(borderRadius: BorderRadius.circular(r), side: side);

/// Type ramp. Tracking is size-specific: large text is tightened, small text
/// loosened slightly. Leading gets tighter as size grows.
abstract final class AppText {
  static const largeTitle = TextStyle(
      fontSize: 34, fontWeight: FontWeight.w700, letterSpacing: -0.7, height: 1.1, color: AppColors.label);
  static const title1 = TextStyle(
      fontSize: 28, fontWeight: FontWeight.w700, letterSpacing: -0.55, height: 1.15, color: AppColors.label);
  static const title2 = TextStyle(
      fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.35, height: 1.2, color: AppColors.label);
  static const title3 = TextStyle(
      fontSize: 20, fontWeight: FontWeight.w600, letterSpacing: -0.3, height: 1.25, color: AppColors.label);
  static const headline = TextStyle(
      fontSize: 17, fontWeight: FontWeight.w600, letterSpacing: -0.25, height: 1.3, color: AppColors.label);
  static const body = TextStyle(
      fontSize: 17, fontWeight: FontWeight.w400, letterSpacing: -0.25, height: 1.35, color: AppColors.label);
  static const callout = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w400, letterSpacing: -0.15, height: 1.4, color: AppColors.label);
  static const subhead = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: -0.15, height: 1.35, color: AppColors.label);
  static const footnote = TextStyle(
      fontSize: 13, fontWeight: FontWeight.w400, letterSpacing: -0.05, height: 1.35, color: AppColors.secondary);
  static const caption = TextStyle(
      fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.1, height: 1.3, color: AppColors.tertiary);

  /// Prices and P&L: same-width digits so values don't jitter as they tick.
  static const tabular = [FontFeature.tabularFigures()];
}

ThemeData buildAppTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.accent,
      onPrimary: Colors.white,
      secondary: AppColors.accent,
      surface: AppColors.card,
      onSurface: AppColors.label,
      onSurfaceVariant: AppColors.secondary,
      surfaceContainerHighest: AppColors.elevated,
      outline: AppColors.separator,
      outlineVariant: AppColors.separator,
      error: AppColors.red,
    ),
  );

  final buttonShape = WidgetStatePropertyAll<OutlinedBorder>(
      RoundedSuperellipseBorder(borderRadius: BorderRadius.circular(12)));
  const buttonText = WidgetStatePropertyAll(
      TextStyle(fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: -0.15));
  const minTarget = WidgetStatePropertyAll(Size(44, 44));

  return base.copyWith(
    scaffoldBackgroundColor: AppColors.bg,
    canvasColor: AppColors.bg,
    // Press feedback is an instant highlight on touch-down, not a ripple
    // that blooms after the finger lifts.
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.white.withValues(alpha: 0.06),
    textTheme: base.textTheme.copyWith(
      displaySmall: AppText.largeTitle,
      headlineMedium: AppText.title1,
      headlineSmall: AppText.title2,
      titleLarge: AppText.title3,
      titleMedium: AppText.headline,
      titleSmall: AppText.subhead,
      bodyLarge: AppText.body,
      bodyMedium: AppText.callout,
      bodySmall: AppText.footnote,
      labelLarge: buttonText.value,
      labelMedium: AppText.footnote.copyWith(fontWeight: FontWeight.w600, color: AppColors.label),
      labelSmall: AppText.caption,
    ),
    // iOS-style push: slides in from the right, and the edge swipe back
    // tracks the finger 1:1 and can be reversed mid-gesture.
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
    }),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bg,
      foregroundColor: AppColors.label,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: AppText.title2,
      iconTheme: IconThemeData(color: AppColors.accent),
      actionsIconTheme: IconThemeData(color: AppColors.accent),
    ),
    cardTheme: CardThemeData(
      color: AppColors.card,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: rounded(16),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.separator, thickness: 0.5, space: 0.5),
    iconTheme: const IconThemeData(color: AppColors.secondary),
    filledButtonTheme: FilledButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        minimumSize: minTarget,
        padding: const WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 18, vertical: 14)),
        backgroundColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.disabled) ? AppColors.fill : AppColors.accent),
        foregroundColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.disabled) ? AppColors.tertiary : Colors.white),
        overlayColor: WidgetStatePropertyAll(Colors.black.withValues(alpha: 0.12)),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        minimumSize: minTarget,
        elevation: const WidgetStatePropertyAll(0),
        backgroundColor: const WidgetStatePropertyAll(AppColors.accent),
        foregroundColor: const WidgetStatePropertyAll(Colors.white),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: buttonText,
        minimumSize: minTarget,
        // "Gray" button: tinted fill instead of a hairline outline.
        side: const WidgetStatePropertyAll(BorderSide.none),
        backgroundColor: const WidgetStatePropertyAll(AppColors.fill),
        foregroundColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.disabled) ? AppColors.tertiary : AppColors.accent),
        iconColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.disabled) ? AppColors.tertiary : AppColors.accent),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(
        shape: buttonShape,
        textStyle: const WidgetStatePropertyAll(
            TextStyle(fontSize: 17, fontWeight: FontWeight.w400, letterSpacing: -0.25)),
        minimumSize: minTarget,
        foregroundColor: const WidgetStatePropertyAll(AppColors.accent),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: ButtonStyle(
        minimumSize: minTarget,
        foregroundColor: const WidgetStatePropertyAll(AppColors.accent),
        side: const WidgetStatePropertyAll(BorderSide.none),
        shape: buttonShape,
      ),
    ),
    // Segmented control: grey track, raised lighter segment for the selection.
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        visualDensity: VisualDensity.compact,
        shape: WidgetStatePropertyAll(RoundedSuperellipseBorder(borderRadius: BorderRadius.circular(9))),
        side: const WidgetStatePropertyAll(BorderSide(color: Colors.transparent, width: 0)),
        backgroundColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.selected) ? const Color(0xFF636366) : AppColors.fill),
        foregroundColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.selected) ? AppColors.label : AppColors.secondary),
        textStyle: const WidgetStatePropertyAll(
            TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: -0.05)),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppColors.fill,
      selectedColor: AppColors.accent.withValues(alpha: 0.22),
      disabledColor: AppColors.fill,
      side: BorderSide.none,
      shape: const StadiumBorder(),
      showCheckmark: false,
      labelStyle: const TextStyle(
          fontSize: 13, fontWeight: FontWeight.w500, letterSpacing: -0.05, color: AppColors.label),
      secondaryLabelStyle: const TextStyle(
          fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: -0.05, color: AppColors.accent),
      padding: const EdgeInsets.symmetric(horizontal: 6),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.fill,
      hintStyle: const TextStyle(color: AppColors.tertiary),
      labelStyle: const TextStyle(color: AppColors.secondary),
      prefixIconColor: AppColors.secondary,
      suffixIconColor: AppColors.secondary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.accent, width: 1.5)),
      errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.red)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.elevated,
      surfaceTintColor: Colors.transparent,
      shape: rounded(22),
      titleTextStyle: AppText.headline,
      contentTextStyle: AppText.callout.copyWith(color: AppColors.secondary),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.card,
      surfaceTintColor: Colors.transparent,
      modalBarrierColor: Color(0x99000000),
      showDragHandle: true,
      dragHandleColor: AppColors.tertiary,
      dragHandleSize: Size(36, 5),
      shape: RoundedSuperellipseBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.elevated,
      contentTextStyle: AppText.subhead,
      actionTextColor: AppColors.accent,
      elevation: 0,
      shape: rounded(14),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      height: 58,
      // Tab bars tint the selected item; there's no pill behind it.
      indicatorColor: Colors.transparent,
      overlayColor: const WidgetStatePropertyAll(Colors.transparent),
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
          fontSize: 10.5,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.1,
          color: s.contains(WidgetState.selected) ? AppColors.accent : AppColors.secondary)),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
          size: 25, color: s.contains(WidgetState.selected) ? AppColors.accent : AppColors.secondary)),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? AppColors.green : AppColors.fill),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
      thumbIcon: const WidgetStatePropertyAll(null),
    ),
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.selected) ? AppColors.accent : Colors.transparent),
      side: const BorderSide(color: AppColors.tertiary, width: 1.5),
      shape: const CircleBorder(),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.accent,
      linearTrackColor: AppColors.fill,
      circularTrackColor: Colors.transparent,
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: AppColors.secondary,
      titleTextStyle: AppText.body,
      subtitleTextStyle: AppText.footnote,
    ),
    badgeTheme: const BadgeThemeData(backgroundColor: AppColors.red, textColor: Colors.white),
    tooltipTheme: TooltipThemeData(
      decoration: ShapeDecoration(color: AppColors.elevated, shape: rounded(8)),
      textStyle: AppText.footnote.copyWith(color: AppColors.label),
    ),
  );
}
