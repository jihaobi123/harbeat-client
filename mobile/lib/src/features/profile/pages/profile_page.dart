import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/section_title.dart';
import '../../auth/auth_controller.dart';
import '../models.dart';
import '../profile_service.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  final _service = ProfileService();

  bool _loading = true;
  bool _generating = false;
  String? _error;
  UserProfile? _profile;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadProfile());
  }

  Future<void> _loadProfile() async {
    final userId = context.read<AuthController>().currentUser?.id;
    if (userId == null || userId <= 0) {
      setState(() {
        _loading = false;
        _error = 'Please login again to load your profile.';
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final profile = await _service.getProfile(userId);
      if (!mounted) return;
      setState(() => _profile = profile);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generateProfile() async {
    final userId = context.read<AuthController>().currentUser?.id;
    if (userId == null || userId <= 0) return;

    setState(() => _generating = true);
    try {
      final profile = await _service.generateProfile(userId);
      if (!mounted) return;
      setState(() {
        _profile = profile;
        _error = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profile regenerated from current music data.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Generate failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final user = auth.currentUser;

    return Scaffold(
      appBar: AppBar(
        title: const Text('HarBeat'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _loadProfile,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 180),
          children: [
            Row(
              children: [
                Container(
                  width: 72,
                  height: 72,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(
                      colors: [AppColors.primary, AppColors.secondary],
                    ),
                  ),
                  child: const Icon(Icons.person, color: Colors.black, size: 34),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        user == null ? '@guest' : '@${user.username}',
                        style: Theme.of(context).textTheme.headlineLarge,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        user == null
                            ? 'No profile loaded'
                            : '${user.danceStyle.toUpperCase()} - ${user.level.toUpperCase()}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 28),
            Row(
              children: [
                const Expanded(child: SectionTitle(title: 'Training Snapshot')),
                TextButton(
                  onPressed: _generating ? null : _generateProfile,
                  child: Text(_generating ? 'Generating...' : 'Regenerate'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              _InfoCard(
                child: Text(_error!, style: Theme.of(context).textTheme.bodyMedium),
              )
            else if (_profile == null)
              const _InfoCard(
                child: Text('No profile snapshot yet. Generate one from your music history.'),
              )
            else ...[
              Row(
                children: [
                  Expanded(
                    child: _StatCard(
                      label: 'Favorite Style',
                      value: _display(_profile!.favoriteStyle),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _StatCard(
                      label: 'Avg BPM',
                      value: _profile!.avgBpmPreference?.toString() ?? '--',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: _StatCard(
                      label: 'Energy',
                      value: _display(_profile!.energyPreference),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _StatCard(
                      label: 'Groove',
                      value: _display(_profile!.groovePreference),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: _StatCard(
                      label: 'Vocal',
                      value: _display(_profile!.vocalPreference),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _StatCard(
                      label: 'Base Style',
                      value: user == null ? '--' : _display(user.favoriteStyle),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 28),
            const SectionTitle(title: 'Activity'),
            const SizedBox(height: 16),
            _ActivityTile(
              title: user == null
                  ? 'Waiting for account data'
                  : 'Current style: ${_display(user.danceStyle)}',
            ),
            const SizedBox(height: 12),
            _ActivityTile(
              title: _profile == null
                  ? 'Generate a profile to unlock music insights'
                  : 'Profile built around ${_display(_profile!.favoriteStyle)} preferences',
            ),
            const SizedBox(height: 12),
            _ActivityTile(
              title: _profile?.avgBpmPreference == null
                  ? 'Average BPM preference not learned yet'
                  : 'Average BPM preference: ${_profile!.avgBpmPreference}',
            ),
          ],
        ),
      ),
    );
  }

  String _display(String? value) {
    if (value == null || value.trim().isEmpty) return '--';
    return value.toUpperCase();
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return _InfoCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label.toUpperCase(), style: Theme.of(context).textTheme.labelSmall),
          const SizedBox(height: 12),
          Text(value, style: Theme.of(context).textTheme.headlineLarge),
        ],
      ),
    );
  }
}

class _ActivityTile extends StatelessWidget {
  const _ActivityTile({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return _InfoCard(
      child: Row(
        children: [
          const Icon(Icons.bolt, color: AppColors.primary),
          const SizedBox(width: 12),
          Expanded(child: Text(title, style: Theme.of(context).textTheme.titleLarge)),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        color: AppColors.surfaceContainerHigh,
      ),
      child: child,
    );
  }
}
