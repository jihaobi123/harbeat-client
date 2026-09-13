import pytest

from harbeat_audio_runtime.default_render_contract import DefaultRenderCommand, validate_default_render_command


def plan():
    return {'pair_id':'pair-a-b','from_song_id':'a','to_song_id':'b','from_at_sec':14.0,'to_at_sec':8.0,'duration_sec':6.0}


def test_validates_prepare_schedule_and_play_commands():
    for command in DefaultRenderCommand:
        validated=validate_default_render_command(command.value,plan(),requested_to_song_id='b')
        assert validated.pair_id=='pair-a-b'; assert validated.to_song_id=='b'
    assert validate_default_render_command('schedule_default_render',plan()).min_lead_sec==1.5


def test_rejects_missing_pair_invalid_times_and_lead():
    bad=plan(); bad.pop('pair_id')
    with pytest.raises(ValueError,match='pair_id'): validate_default_render_command('prepare_default_render',bad)
    bad=plan(); bad['from_at_sec']=float('nan')
    with pytest.raises(ValueError,match='from_at_sec'): validate_default_render_command('prepare_default_render',bad)
    with pytest.raises(ValueError,match='min_lead_sec'): validate_default_render_command('schedule_default_render',plan(),min_lead_sec=0)
