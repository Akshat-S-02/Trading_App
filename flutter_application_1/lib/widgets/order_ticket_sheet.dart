import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/market_data_provider.dart';
import '../providers/trading_provider.dart';
import '../utils/format.dart';
import '../ui/components.dart';
import '../ui/theme.dart';

/// Opens the manual order ticket for [symbol] as a bottom sheet.
Future<void> showOrderTicket(BuildContext context, String symbol, {String side = 'BUY'}) {
  return showAppSheet(context, (_) => OrderTicketSheet(symbol: symbol, initialSide: side));
}

class OrderTicketSheet extends StatefulWidget {
  final String symbol;
  final String initialSide;
  const OrderTicketSheet({super.key, required this.symbol, this.initialSide = 'BUY'});

  @override
  State<OrderTicketSheet> createState() => _OrderTicketSheetState();
}

class _OrderTicketSheetState extends State<OrderTicketSheet> {
  late String _side = widget.initialSide;
  final _qtyCtrl = TextEditingController(text: '1');
  final _slCtrl = TextEditingController();
  final _tgtCtrl = TextEditingController();
  bool _useBracket = false;
  bool _submitting = false;

  bool get _isBuy => _side == 'BUY';
  Color get _sideColor => _isBuy ? kBuyColor : kSellColor;
  int get _qty => int.tryParse(_qtyCtrl.text) ?? 0;
  double? get _sl => _useBracket ? double.tryParse(_slCtrl.text) : null;
  double? get _tgt => _useBracket ? double.tryParse(_tgtCtrl.text) : null;

  @override
  void initState() {
    super.initState();
    context.read<MarketDataProvider>().ensurePrice(widget.symbol);
  }

  @override
  void dispose() {
    _qtyCtrl.dispose();
    _slCtrl.dispose();
    _tgtCtrl.dispose();
    super.dispose();
  }

  void _setQty(int q) {
    if (q < 1) q = 1;
    if (q != _qty) HapticFeedback.selectionClick();
    _qtyCtrl.text = '$q';
    setState(() {});
  }

  /// Fill SL / target at a % distance from [ltp] on the correct side.
  void _presetBracket(double ltp, double slPct, double tgtPct) {
    final sl = _isBuy ? ltp * (1 - slPct / 100) : ltp * (1 + slPct / 100);
    final tgt = _isBuy ? ltp * (1 + tgtPct / 100) : ltp * (1 - tgtPct / 100);
    _slCtrl.text = sl.toStringAsFixed(2);
    _tgtCtrl.text = tgt.toStringAsFixed(2);
    setState(() => _useBracket = true);
  }

  /// Client-side check mirroring the backend, so mistakes show before submitting.
  String? _validate(double? ltp) {
    if (ltp == null) return 'Waiting for a live price…';
    if (_qty < 1) return 'Enter a quantity of at least 1';
    if (_useBracket) {
      final sl = _sl, tgt = _tgt;
      if (_slCtrl.text.isNotEmpty && sl == null) return 'Stop-loss is not a valid number';
      if (_tgtCtrl.text.isNotEmpty && tgt == null) return 'Target is not a valid number';
      if (_isBuy) {
        if (sl != null && sl >= ltp) return 'Stop-loss must be below the price for a BUY';
        if (tgt != null && tgt <= ltp) return 'Target must be above the price for a BUY';
      } else {
        if (sl != null && sl <= ltp) return 'Stop-loss must be above the price for a SELL';
        if (tgt != null && tgt >= ltp) return 'Target must be below the price for a SELL';
      }
    }
    return null;
  }

  Future<void> _submit(double ltp) async {
    final verb = _isBuy ? 'Buy' : 'Sell';
    final confirmed = await confirmAction(
      context,
      title: '$verb $_qty × ${bareSymbol(widget.symbol)}?',
      message: 'At market, about ${inr(ltp)} each.\n'
          'Estimated value ${inr(ltp * _qty)}'
          '${_sl != null ? '\nStop-loss ${inr(_sl)}' : ''}'
          '${_tgt != null ? '\nTarget ${inr(_tgt)}' : ''}',
      confirmLabel: verb,
      confirmColor: _sideColor,
    );
    if (!confirmed || !mounted) return;

    setState(() => _submitting = true);
    final res = await context.read<TradingProvider>().placeOrder(
          symbol: widget.symbol,
          qty: _qty,
          side: _side,
          stopLoss: _sl,
          target: _tgt,
        );
    if (!mounted) return;
    setState(() => _submitting = false);
    notify(ScaffoldMessenger.of(context), res.message, ok: res.ok);
    if (res.ok) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final ltp = context.select<MarketDataProvider, double?>((p) => p.getPrice(widget.symbol));
    final trading = context.watch<TradingProvider>();
    final error = _validate(ltp);
    final value = ltp == null ? null : ltp * _qty;

    double? riskReward;
    if (ltp != null && _sl != null && _tgt != null) {
      final risk = (ltp - _sl!).abs();
      if (risk > 0) riskReward = (_tgt! - ltp).abs() / risk;
    }

    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header: symbol + live price
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(bareSymbol(widget.symbol), style: AppText.title1),
                      const Text('NSE · Intraday · Market order', style: AppText.footnote),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(ltp == null ? '—' : inr(ltp),
                        style: AppText.title2.copyWith(fontFeatures: AppText.tabular)),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        StatusDot(ltp == null ? AppColors.orange : AppColors.green, size: 6),
                        const SizedBox(width: 5),
                        Text(ltp == null ? 'Waiting for price' : 'Live', style: AppText.caption),
                      ],
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 18),

            if (trading.emergencyStop)
              _banner(Icons.block_rounded, 'Emergency stop is on. Orders are blocked.', AppColors.red),
            if (trading.executionMode != 'paper')
              _banner(Icons.info_outline_rounded,
                  'Manual trading only works in paper mode.', AppColors.orange),

            // Buy / Sell
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'BUY', label: Text('Buy')),
                ButtonSegment(value: 'SELL', label: Text('Sell')),
              ],
              showSelectedIcon: false,
              selected: {_side},
              onSelectionChanged: (s) {
                HapticFeedback.selectionClick();
                setState(() {
                  _side = s.first;
                  _slCtrl.clear();
                  _tgtCtrl.clear();
                });
              },
              style: ButtonStyle(
                visualDensity: VisualDensity.standard,
                backgroundColor: WidgetStateProperty.resolveWith((states) =>
                    states.contains(WidgetState.selected) ? _sideColor : AppColors.fill),
                foregroundColor: WidgetStateProperty.resolveWith((states) =>
                    states.contains(WidgetState.selected) ? Colors.white : AppColors.secondary),
                textStyle: const WidgetStatePropertyAll(AppText.subhead),
              ),
            ),
            if (!_isBuy)
              const Padding(
                padding: EdgeInsets.only(top: 8, left: 4),
                child: Text('Sell opens an intraday short. To exit a buy, use Close on the Positions tab.',
                    style: AppText.caption),
              ),
            const SizedBox(height: 22),

            // Quantity stepper
            const Text('Quantity', style: AppText.subhead),
            const SizedBox(height: 8),
            Row(
              children: [
                _stepButton(Icons.remove_rounded, () => _setQty(_qty - 1)),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _qtyCtrl,
                    textAlign: TextAlign.center,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    style: AppText.title2.copyWith(fontFeatures: AppText.tabular),
                    decoration: const InputDecoration(isDense: true, contentPadding: EdgeInsets.symmetric(vertical: 10)),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
                const SizedBox(width: 8),
                _stepButton(Icons.add_rounded, () => _setQty(_qty + 1)),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              children: [1, 5, 10, 25, 50]
                  .map((q) => ChoiceChip(
                        label: Text('$q'),
                        selected: _qty == q,
                        onSelected: (_) => _setQty(q),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 14),

            // Stop-loss / target
            Surface(
              color: AppColors.elevated,
              padding: const EdgeInsets.fromLTRB(14, 4, 6, 4),
              child: Row(
                children: [
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Stop-loss & target', style: AppText.callout),
                        Text('Closes the trade automatically', style: AppText.caption),
                      ],
                    ),
                  ),
                  Switch(
                    value: _useBracket,
                    onChanged: (v) {
                      HapticFeedback.selectionClick();
                      setState(() => _useBracket = v);
                    },
                  ),
                ],
              ),
            ),
            AnimatedSize(
              duration: motionDuration(context),
              curve: motionCurve,
              alignment: Alignment.topCenter,
              child: !_useBracket
                  ? const SizedBox(width: double.infinity)
                  : Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (ltp != null)
                            Wrap(
                              spacing: 8,
                              children: [
                                ActionChip(label: const Text('0.5% / 1%'),
                                    onPressed: () => _presetBracket(ltp, 0.5, 1)),
                                ActionChip(label: const Text('1% / 2%'),
                                    onPressed: () => _presetBracket(ltp, 1, 2)),
                                ActionChip(label: const Text('2% / 4%'),
                                    onPressed: () => _presetBracket(ltp, 2, 4)),
                              ],
                            ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Expanded(child: _priceField(_slCtrl, 'Stop-loss', kSellColor)),
                              const SizedBox(width: 12),
                              Expanded(child: _priceField(_tgtCtrl, 'Target', kBuyColor)),
                            ],
                          ),
                        ],
                      ),
                    ),
            ),
            const SizedBox(height: 16),

            // Summary
            Surface(
              color: AppColors.elevated,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Column(
                children: [
                  _summaryRow('Estimated value', inr(value)),
                  if (_sl != null && ltp != null)
                    _summaryRow('Loss at stop-loss', inr((ltp - _sl!).abs() * _qty), color: kSellColor),
                  if (_tgt != null && ltp != null)
                    _summaryRow('Profit at target', inr((_tgt! - ltp).abs() * _qty), color: kBuyColor),
                  if (riskReward != null)
                    _summaryRow('Risk : reward', '1 : ${riskReward.toStringAsFixed(2)}'),
                ],
              ),
            ),
            // Inline validation, right above the button it affects.
            AnimatedSize(
              duration: motionDuration(context, 200),
              curve: motionCurve,
              alignment: Alignment.topCenter,
              child: error == null
                  ? const SizedBox(width: double.infinity, height: 8)
                  : Padding(
                      padding: const EdgeInsets.only(top: 10, left: 4),
                      child: Text(error, style: AppText.footnote.copyWith(color: AppColors.orange)),
                    ),
            ),
            const SizedBox(height: 12),

            FilledButton(
              onPressed: (error != null || _submitting || trading.emergencyStop)
                  ? null
                  : () => _submit(ltp!),
              style: FilledButton.styleFrom(
                backgroundColor: _sideColor,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 16),
                textStyle: AppText.headline,
              ),
              child: _submitting
                  ? const SizedBox(
                      height: 20, width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text('${_isBuy ? 'Buy' : 'Sell'} ${_qty > 0 ? _qty : ''} ${bareSymbol(widget.symbol)}'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stepButton(IconData icon, VoidCallback onTap) => Pressable(
        pressedScale: 0.9,
        onTap: onTap,
        child: Container(
          width: 48,
          height: 48,
          alignment: Alignment.center,
          decoration: ShapeDecoration(color: AppColors.fill, shape: rounded(12)),
          child: Icon(icon, color: AppColors.accent),
        ),
      );

  Widget _banner(IconData icon, String text, Color color) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Surface(
          color: color.withValues(alpha: 0.14),
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(width: 10),
            Expanded(child: Text(text, style: AppText.footnote.copyWith(color: AppColors.label))),
          ]),
        ),
      );

  Widget _priceField(TextEditingController c, String label, Color color) => TextField(
        controller: c,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
        style: AppText.body.copyWith(fontFeatures: AppText.tabular),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: TextStyle(color: color),
          floatingLabelStyle: TextStyle(color: color),
          prefixText: '₹ ',
          isDense: true,
        ),
        onChanged: (_) => setState(() {}),
      );

  Widget _summaryRow(String label, String value, {Color? color}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: AppText.footnote),
            Text(value,
                style: AppText.subhead.copyWith(color: color ?? AppColors.label, fontFeatures: AppText.tabular)),
          ],
        ),
      );
}
