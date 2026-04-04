import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/glass_panel.dart';
import '../../core/widgets/neon_button.dart';
import 'auth_controller.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isRegisterMode = false;
  String _selectedStyle = 'hiphop';
  String _selectedLevel = 'intermediate';

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final auth = context.read<AuthController>();
    final username = _usernameController.text.trim();
    final password = _passwordController.text.trim();

    if (username.isEmpty || password.isEmpty) {
      return;
    }

    if (_isRegisterMode) {
      await auth.register(
        username: username,
        password: password,
        danceStyle: _selectedStyle,
        level: _selectedLevel,
        favoriteStyle: _selectedStyle,
      );
    } else {
      await auth.login(username: username, password: password);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 1.3,
            colors: [
              Color(0x332B95FF),
              AppColors.surface,
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Text.rich(
                    TextSpan(
                      text: 'Har',
                      style: textTheme.displayLarge,
                      children: const [
                        TextSpan(
                          text: 'Beat',
                          style: TextStyle(color: AppColors.primary),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text('ENTER THE DIGITAL CYPHER', style: textTheme.labelSmall),
                  const SizedBox(height: 28),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: GlassPanel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: _ModeButton(
                                  label: 'Login',
                                  selected: !_isRegisterMode,
                                  onTap: () => setState(() => _isRegisterMode = false),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: _ModeButton(
                                  label: 'Register',
                                  selected: _isRegisterMode,
                                  onTap: () => setState(() => _isRegisterMode = true),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 24),
                          TextField(
                            controller: _usernameController,
                            decoration: const InputDecoration(
                              labelText: 'Username',
                              hintText: 'THE_KING_BBOY',
                            ),
                          ),
                          const SizedBox(height: 16),
                          TextField(
                            controller: _passwordController,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Password',
                              hintText: '••••••••',
                            ),
                          ),
                          if (_isRegisterMode) ...[
                            const SizedBox(height: 20),
                            Text('YOUR STYLE', style: textTheme.labelSmall),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 10,
                              runSpacing: 10,
                              children: [
                                'hiphop',
                                'breaking',
                                'popping',
                                'locking',
                                'house',
                                'krump',
                              ].map((style) {
                                final selected = style == _selectedStyle;
                                return ChoiceChip(
                                  label: Text(style.toUpperCase()),
                                  selected: selected,
                                  onSelected: (_) => setState(() => _selectedStyle = style),
                                  selectedColor: AppColors.primary,
                                  backgroundColor: AppColors.surfaceContainerHighest,
                                  labelStyle: TextStyle(
                                    color: selected ? Colors.black : AppColors.onSurface,
                                    fontWeight: FontWeight.w700,
                                  ),
                                );
                              }).toList(),
                            ),
                            const SizedBox(height: 20),
                            Text('EXPERIENCE LEVEL', style: textTheme.labelSmall),
                            const SizedBox(height: 12),
                            SegmentedButton<String>(
                              segments: const [
                                ButtonSegment(value: 'beginner', label: Text('BEGINNER')),
                                ButtonSegment(value: 'intermediate', label: Text('INTERMEDIATE')),
                                ButtonSegment(value: 'advanced', label: Text('ADVANCED')),
                              ],
                              selected: {_selectedLevel},
                              onSelectionChanged: (selection) {
                                setState(() => _selectedLevel = selection.first);
                              },
                            ),
                          ],
                          if (auth.errorMessage != null) ...[
                            const SizedBox(height: 16),
                            Text(
                              auth.errorMessage!,
                              style: const TextStyle(color: AppColors.error),
                            ),
                          ],
                          const SizedBox(height: 24),
                          NeonButton(
                            label: _isRegisterMode ? 'Start Dancing' : 'Login',
                            icon: Icons.arrow_forward,
                            onPressed: auth.isSubmitting ? null : _submit,
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ModeButton extends StatelessWidget {
  const _ModeButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: selected
              ? Colors.white.withValues(alpha: 0.08)
              : Colors.white.withValues(alpha: 0.03),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: selected ? AppColors.primary : Colors.white.withValues(alpha: 0.05),
          ),
        ),
        child: Center(
          child: Text(
            label.toUpperCase(),
            style: TextStyle(
              color: selected ? AppColors.primary : AppColors.onSurfaceVariant,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.2,
            ),
          ),
        ),
      ),
    );
  }
}
