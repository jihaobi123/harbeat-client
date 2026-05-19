import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../state/providers.dart';

class NineKeyGrid extends ConsumerWidget {
  const NineKeyGrid({super.key});

  static const Map<int, String> LABELS = {
    1: 'ha!',
    2: 'scratch',
    3: 'horn',
    4: 'drum*',
    5: 'bass*',
    6: 'hat*',
    7: 'mute V',
    8: 'solo D',
    9: 'LPF',
  };

  static const Map<int, String> STEM_FX_NAMES = {
    7: 'vocals_mute',
    8: 'drums_only',
    9: 'lpf',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final liveState = ref.watch(liveProvider);
    final playback = ref.watch(playbackProvider);

    return GridView.count(
      crossAxisCount: 3,
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: List.generate(9, (index) {
        final key = index + 1;
        final active = _isActive(key, playback?.activeLoops, playback?.activeStemFx);
        final recentlyPressed = liveState.isRecentlyPressed(key);

        return _KeyButton(
          keyNum: key,
          label: LABELS[key] ?? 'key$key',
          active: active,
          recentlyPressed: recentlyPressed,
          onTap: () async {
            HapticFeedback.mediumImpact();
            await ref.read(liveProvider.notifier).trigger(key);
          },
          enabled: liveState.isConnected,
        );
      }),
    );
  }

  bool _isActive(int key, List<int>? activeLoops, String? activeStemFx) {
    if (key >= 4 && key <= 6 && activeLoops != null) {
      return activeLoops.contains(key);
    }
    if (key >= 7 && key <= 9 && activeStemFx != null) {
      return activeStemFx == STEM_FX_NAMES[key];
    }
    return false;
  }
}

class _KeyButton extends StatefulWidget {
  final int keyNum;
  final String label;
  final bool active;
  final bool recentlyPressed;
  final VoidCallback onTap;
  final bool enabled;

  const _KeyButton({
    required this.keyNum,
    required this.label,
    required this.active,
    required this.recentlyPressed,
    required this.onTap,
    required this.enabled,
  });

  @override
  State<_KeyButton> createState() => _KeyButtonState();
}

class _KeyButtonState extends State<_KeyButton> with SingleTickerProviderStateMixin {
  late AnimationController _flashController;
  late Animation<double> _flashAnimation;

  @override
  void initState() {
    super.initState();
    _flashController = AnimationController(
      duration: const Duration(milliseconds: 150),
      vsync: this,
    );
    _flashAnimation = Tween<double>(begin: 1.0, end: 0.0).animate(
      CurvedAnimation(parent: _flashController, curve: Curves.easeOut),
    );
  }

  @override
  void didUpdateWidget(_KeyButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.recentlyPressed && !oldWidget.recentlyPressed) {
      _flashController.forward(from: 0.0);
    }
  }

  @override
  void dispose() {
    _flashController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AnimatedBuilder(
      animation: _flashAnimation,
      builder: (context, child) {
        return Material(
          color: _getBackgroundColor(theme),
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            onTap: widget.enabled ? widget.onTap : null,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: widget.active
                      ? theme.colorScheme.primary
                      : theme.colorScheme.outline.withOpacity(0.5),
                  width: 2,
                ),
              ),
              child: Stack(
                children: [
                  if (widget.recentlyPressed)
                    Positioned.fill(
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(_flashAnimation.value * 0.5),
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                    ),
                  Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '${widget.keyNum}',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: widget.active
                                ? theme.colorScheme.primary
                                : theme.colorScheme.onSurface.withOpacity(widget.enabled ? 1.0 : 0.3),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          widget.label,
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: widget.active
                                ? theme.colorScheme.primary
                                : theme.colorScheme.onSurface.withOpacity(widget.enabled ? 0.7 : 0.3),
                          ),
                          textAlign: TextAlign.center,
                        ),
                        if (widget.active)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: theme.colorScheme.primary,
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'ON',
                                style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Color _getBackgroundColor(ThemeData theme) {
    if (!widget.enabled) {
      return theme.colorScheme.surface.withOpacity(0.3);
    }
    if (widget.active) {
      return theme.colorScheme.primaryContainer;
    }
    return theme.colorScheme.surface;
  }
}
