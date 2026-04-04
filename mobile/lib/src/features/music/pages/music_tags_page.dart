import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/theme/app_colors.dart';
import '../../auth/auth_controller.dart';
import '../models.dart';
import '../music_service.dart';

class MusicTagsPage extends StatefulWidget {
  const MusicTagsPage({super.key});

  @override
  State<MusicTagsPage> createState() => _MusicTagsPageState();
}

class _MusicTagsPageState extends State<MusicTagsPage> {
  final _service = MusicService();
  final _searchController = TextEditingController();
  bool _loading = true;
  List<CatalogSong> _songs = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load({String? query}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final songs = (query == null || query.trim().isEmpty)
          ? await _service.getCatalogSongs()
          : await _service.searchCatalogSongs(query.trim());
      if (!mounted) return;
      setState(() => _songs = songs);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Catalog Tags & Cues')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
          children: [
            TextField(
              controller: _searchController,
              onSubmitted: (value) => _load(query: value),
              decoration: InputDecoration(
                hintText: 'Search catalog songs',
                suffixIcon: IconButton(
                  onPressed: () => _load(query: _searchController.text),
                  icon: const Icon(Icons.search),
                ),
              ),
            ),
            const SizedBox(height: 20),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              Text(_error!, style: const TextStyle(color: Colors.redAccent))
            else
              ..._songs.map(
                (song) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(22),
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => SongTagEditorPage(songId: song.id)),
                      );
                      await _load(query: _searchController.text);
                    },
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(22),
                        color: AppColors.surfaceContainerHigh,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(song.title, style: Theme.of(context).textTheme.titleLarge),
                          const SizedBox(height: 4),
                          Text('${song.artist}${song.style == null ? '' : ' - ${song.style}'}'),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: song.tags.map((tag) => Chip(label: Text(tag))).toList(),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class SongTagEditorPage extends StatefulWidget {
  const SongTagEditorPage({
    super.key,
    required this.songId,
  });

  final int songId;

  @override
  State<SongTagEditorPage> createState() => _SongTagEditorPageState();
}

class _SongTagEditorPageState extends State<SongTagEditorPage> {
  final _service = MusicService();
  final _bpmController = TextEditingController();
  final _energyController = TextEditingController();
  final _styleController = TextEditingController();
  final _vocalController = TextEditingController();
  final _eraController = TextEditingController();
  final _grooveController = TextEditingController();
  final _difficultyController = TextEditingController();
  final _tagsController = TextEditingController();

  CatalogSong? _song;
  List<SongCue> _cues = [];
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _bpmController.dispose();
    _energyController.dispose();
    _styleController.dispose();
    _vocalController.dispose();
    _eraController.dispose();
    _grooveController.dispose();
    _difficultyController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final userId = context.read<AuthController>().currentUser?.id ?? 0;
    setState(() => _loading = true);
    final song = await _service.getCatalogSong(widget.songId);
    final cues = userId <= 0 ? <SongCue>[] : await _service.getCues(widget.songId, userId);
    if (!mounted) return;
    _song = song;
    _bpmController.text = song.bpm?.toString() ?? '';
    _energyController.text = song.energy ?? '';
    _styleController.text = song.style ?? '';
    _vocalController.text = song.vocalType ?? '';
    _eraController.text = song.eraTag ?? '';
    _grooveController.text = song.grooveTag ?? '';
    _difficultyController.text = song.difficultyFit ?? '';
    _tagsController.text = song.tags.join(', ');
    setState(() {
      _cues = cues;
      _loading = false;
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await _service.updateSongTags(widget.songId, {
        'bpm': int.tryParse(_bpmController.text.trim()),
        'energy': _energyController.text.trim().isEmpty ? null : _energyController.text.trim(),
        'style': _styleController.text.trim().isEmpty ? null : _styleController.text.trim(),
        'vocal_type': _vocalController.text.trim().isEmpty ? null : _vocalController.text.trim(),
        'era_tag': _eraController.text.trim().isEmpty ? null : _eraController.text.trim(),
        'groove_tag': _grooveController.text.trim().isEmpty ? null : _grooveController.text.trim(),
        'difficulty_fit': _difficultyController.text.trim().isEmpty ? null : _difficultyController.text.trim(),
        'tags': _tagsController.text
            .split(',')
            .map((tag) => tag.trim())
            .where((tag) => tag.isNotEmpty)
            .toList(),
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Song tags updated')),
      );
      await _load();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Save failed: $error')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _addCue() async {
    final userId = context.read<AuthController>().currentUser?.id;
    if (userId == null) return;

    final cueTypeController = TextEditingController(text: 'marker');
    final startController = TextEditingController();
    final endController = TextEditingController();
    final labelController = TextEditingController();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add Cue'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: cueTypeController, decoration: const InputDecoration(labelText: 'Cue type')),
            TextField(controller: startController, decoration: const InputDecoration(labelText: 'Start time (sec)')),
            TextField(controller: endController, decoration: const InputDecoration(labelText: 'End time (optional)')),
            TextField(controller: labelController, decoration: const InputDecoration(labelText: 'Label')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Add')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await _service.createCue(widget.songId, {
        'user_id': userId,
        'song_id': widget.songId,
        'cue_type': cueTypeController.text.trim(),
        'start_time': double.tryParse(startController.text.trim()) ?? 0,
        'end_time': endController.text.trim().isEmpty ? null : double.tryParse(endController.text.trim()),
        'label': labelController.text.trim().isEmpty ? null : labelController.text.trim(),
      });
      if (!mounted) return;
      await _load();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Add cue failed: $error')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_song?.title ?? 'Song Editor'),
        actions: [
          IconButton(onPressed: _saving ? null : _save, icon: const Icon(Icons.save)),
        ],
      ),
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 40),
                children: [
                  _field(_bpmController, 'BPM', keyboardType: TextInputType.number),
                  _field(_styleController, 'Style'),
                  _field(_energyController, 'Energy'),
                  _field(_vocalController, 'Vocal Type'),
                  _field(_eraController, 'Era Tag'),
                  _field(_grooveController, 'Groove Tag'),
                  _field(_difficultyController, 'Difficulty Fit'),
                  _field(_tagsController, 'Tags (comma separated)', maxLines: 2),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Cue Points',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                        ),
                      ),
                      TextButton(onPressed: _addCue, child: const Text('Add Cue')),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ..._cues.map(
                    (cue) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(18),
                          color: AppColors.surfaceContainerHigh,
                        ),
                        child: Text(
                          '${cue.cueType} - ${cue.startTime}${cue.label == null ? '' : ' - ${cue.label}'}',
                        ),
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    TextInputType? keyboardType,
    int maxLines = 1,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextField(
        controller: controller,
        keyboardType: keyboardType,
        maxLines: maxLines,
        decoration: InputDecoration(labelText: label),
      ),
    );
  }
}
